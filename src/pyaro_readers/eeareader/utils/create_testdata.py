import polars
from pathlib import Path


DATAFOLDER = Path("../data")
OUTPUT_FOLDER = Path("./testdata")

NB_FILES = 1
NB_LINES = 100

countries = ["LU", "NO"]
polls = ["PM10", "SO2"]

for country in countries:
    for poll in polls:
        indir = DATAFOLDER / poll / country
        outdir = OUTPUT_FOLDER / poll / country
        inputfiles = [f for f in (indir).glob("*.parquet")][:NB_FILES]
        if not outdir.is_dir():
            outdir.mkdir(parents=True, exist_ok=True)

        for file in inputfiles:
            data = polars.read_parquet(file)
            if data.is_empty():
                raise ValueError(f"Empty data file {file}")
            outfile = outdir / file.name

            data.head(NB_LINES).write_parquet(outfile)
