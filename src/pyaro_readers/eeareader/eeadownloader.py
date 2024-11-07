import requests
import polars as pl
import typer
from typing_extensions import Annotated

from pathlib import Path


try:
    import tomllib
except ImportError:  # python <3.11
    import tomli as tomllib


from tqdm import tqdm
import shutil


app = typer.Typer()


DATABASES = dict(
    NRT=1,
    VERIFIED=2,
    HISTORICAL=3,
)


class EEADownloader:
    BASE_URL = "https://eeadmz1-downloads-api-appservice.azurewebsites.net/"
    ENDPOINT = "ParquetFile/"
    URL_ENDPOINT = "urls"
    URL_POLLUTANT = "http://dd.eionet.europa.eu/vocabulary/aq/pollutant/"

    METADATFILE = Path(__file__).parent / "metadata.csv"
    DATAFILE = Path(__file__).parent / "data.toml"

    request_body = dict(contries=[], cities=[], properties=[], datasets=[], source="")

    def __init__(
        self,
    ) -> None:
        pass

    def _get_urls(self, request: dict):
        results = requests.post(
            self.BASE_URL + self.ENDPOINT + self.URL_ENDPOINT, json=request
        )

        if results.status_code == 200:
            return results.text
        else:
            raise results.raise_for_status()

    def download_and_save(self, request: dict, save_loc: Path) -> None:
        urls = self._get_urls(request)

        if not save_loc.is_dir():
            save_loc.mkdir(parents=True, exist_ok=True)
        urls = urls.split("\r\n")[1:]
        if not isinstance(urls, list):
            urls = [urls]
        for url in urls:
            url = url.strip()
            if len(url) < 2:
                continue

            filename = url.split("/")[-1]
            # print(f"Downloading {filename}")
            try:
                result = requests.get(url)
            except Exception as e:
                raise ValueError(f"{url} failed to download due to {e}")
            with open(save_loc / filename, "wb") as f:
                f.write(result.content)

    def _make_request(self, request: dict):
        results = requests.post(self.BASE_URL + self.ENDPOINT, json=request)

        if results.status_code == 200:
            return results.content
        else:
            raise results.raise_for_status()

    def _copy_metadata_to_folder(self, to_folder: Path) -> None:
        shutil.copyfile(self.METADATFILE, to_folder / "metadata.csv")

    def get_countries(self):
        country_file = requests.get(self.BASE_URL + "Country").json()
        return [country["countryCode"] for country in country_file]

    def get_station_metadata(self) -> dict:
        metadata = {}
        with open(self.METADATFILE, "r") as f:
            f.readline()
            for line in f:
                words = line.split(",")
                try:
                    lon = float(words[3])
                    lat = float(words[4])
                    alt = float(words[5])
                except:
                    continue
                metadata[words[0]] = {
                    "lon": lon,
                    "lat": lat,
                    "alt": alt,
                    "stationcode": words[2],
                    "country": words[1],
                }

        return metadata

    def get_pollutants(self) -> dict:
        with open(self.DATAFILE, "rb") as f:
            poll = tomllib.load(f)["pollutant"]
        return poll

    def get_default_pollutants(self) -> list[str]:
        with open(self.DATAFILE, "rb") as f:
            poll = tomllib.load(f)["defaults"]["pollutants"]
        return poll

    def make_pollutant_url_list(self, pollutants: list[str]) -> list[str]:
        urls = []
        with open(self.DATAFILE, "rb") as f:
            poll = tomllib.load(f)["pollutant"]
            for key in poll:
                if poll[key] in pollutants:
                    urls.append(self.URL_POLLUTANT + key)

        return urls

    @app.command(name="download")
    def download_default(
        self,
        save_loc: Path,
        dataset: int = DATABASES["VERIFIED"],
        pollutants: list | None = None,
    ) -> None:
        if not save_loc.is_dir():
            save_loc.mkdir(parents=True, exist_ok=True)

        self._copy_metadata_to_folder(save_loc)
        countries = self.get_countries()

        errorfile = open("errors.txt", "w")
        if pollutants is None:
            pollutants = self.get_default_pollutants()

        pbar = tqdm(countries, desc="Countries", disable=None)
        for country in pbar:
            pbar.set_description(f"{country}")
            for poll in tqdm(
                pollutants,
                desc="Pollutants",
                leave=False,
                disable=None,
            ):
                full_loc = save_loc / poll / country
                request = {
                    "countries": [country],
                    "cities": [],
                    "pollutants": self.make_pollutant_url_list(poll),
                    "dataset": dataset,
                    "source": "Api",
                }
                self.download_and_save(request, full_loc)

        errorfile.close()

    def _postprocess_file(self, file: Path, metadata: dict) -> pl.DataFrame:
        poll = self.get_pollutants()

        df = pl.read_parquet(file)
        pollutant = df.row(0)[1]
        station = df.row(0)[0].split("/")[-1]

        if station not in metadata:
            raise ValueError(f"Station {station} does not have float coordinates")

        length = df.shape[0]
        for name in metadata[station]:
            value = metadata[station][name]
            series = pl.Series(name, [value] * length)
            df.insert_column(1, series)

        series = pl.Series("PollutantName", [poll[str(pollutant)]] * length)
        df.insert_column(1, series)

        df = df.with_columns(
            (pl.col("Samplingpoint").str.extract(r"(.*)/.*")).alias("CountryCode")
        )

        return df

    app.command(name="postprocess")

    def postprocess_all_files(self, from_folder: Path, to_folder: Path) -> None:
        metadata = self.get_station_metadata()

        polls = [str(x).split("/")[-1] for x in from_folder.iterdir() if x.is_dir()]
        if not to_folder.is_dir():
            to_folder.mkdir(parents=True, exist_ok=True)

        self._copy_metadata_to_folder(to_folder)
        conversion_error = open(to_folder / "errors.txt", "w")
        error_n = 0
        for poll in tqdm(polls, desc="Pollutant", disable=None):
            countries = [
                str(x).split("/")[-1]
                for x in (from_folder / poll).iterdir()
                if x.is_dir()
            ]
            for country in tqdm(countries, desc="Country", leave=False, disable=None):
                folder = from_folder / poll / country
                new_folder = to_folder / poll / country

                if not new_folder.is_dir():
                    new_folder.mkdir(parents=True, exist_ok=True)

                files = folder.glob("*.parquet")
                for file in tqdm(files, desc="Files", leave=False, disable=None):
                    try:
                        df = self._postprocess_file(file, metadata=metadata)
                        df.write_parquet(new_folder / file.name)

                    except Exception as e:
                        error_n += 1
                        conversion_error.write(
                            f"{error_n}: Error in converting {file} due to {e}\n"
                        )
                        continue
        print(f"Finished with {error_n} errors")
        conversion_error.close()


@app.command(
    name="download",
    help="Downloads the data in a given folder. Data will be orders in folders corresponding to pollutant and country code",
)
def download(
    save_loc: Annotated[
        Path,
        typer.Argument(
            help="Location where the data will be downloaded to. Deprecated!: The reader can now use the downloaded data directly"
        ),
    ],
):
    eead = EEADownloader()
    eead.download_default(save_loc)


@app.command(
    name="postprocess",
    help="Postprocesses the data to make the reading by pyaro faster",
)
def postprocess(
    from_folder: Annotated[
        Path, typer.Argument(help="The folder where the original data is found")
    ],
    to_folder: Annotated[
        Path, typer.Argument(help="Folder where the processes data will be stored")
    ],
):
    eead = EEADownloader()
    eead.postprocess_all_files(from_folder, to_folder)


if __name__ == "__main__":
    # app()

    pollutants = [
        "SO2",
        # "SO4--",
        # "SO4 (H2SO4 aerosols) (SO4--)",
    ]
    eead = EEADownloader()
    eead.download_default(
        Path("/home/danielh/Documents/pyaerocom/test_data/EEA"), pollutants=pollutants
    )

# eead.postprocess_all_files(
#     Path(
#         "/home/danielh/Documents/pyaerocom/pyaro-readers/src/pyaro_readers/eeareader/data"
#     ),
#     Path(
#         "/home/danielh/Documents/pyaerocom/pyaro-readers/src/pyaro_readers/eeareader/renamed"
#     ),
# )
