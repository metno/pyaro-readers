from textwrap import (
    shorten,
)  # 'shorten' is used to reduce the size of the source parameter
from urllib.parse import quote
import requests

import os
import unittest
import logging

logger = logging.getLogger(__name__)

BASE_API_URL = "https://dev-actris-md.nilu.no/"


class TestActrisEbasTimeSeriesReader(unittest.TestCase):
    log_file = os.getenv("PYAEROCOM_LOG_FILE")
    if log_file is not None:
        log_file = f"actrisebas.log"
        # log_file = f"/home/jang/tmp/logging/pyaerocom.log"
    logging.basicConfig(filename=log_file, level=logging.DEBUG)
    logger.info("Started")
    variable_name = "ozone mass concentration"

    def query(self):
        query = {
            "bool": {
                "must": [
                    {
                        "term": {
                            "dataset_metadata.repository.repository_id.keyword": "In-Situ"
                        }
                    },
                    {"term": {"variables.variable_name.keyword": self.variable_name}},
                ]
            }
        }
        hits, start, total = [], 0, 1
        page_size = 20

        iter = 0
        while start < total:
            payload = {"search": {"query": query, "from": start, "size": page_size}}
            try:
                r = requests.post(
                    BASE_API_URL + "/api/metadata/search", json=payload, timeout=30
                )
                r.raise_for_status()
                h = r.json().get("response", {}).get("hits", {})
                if iter == 0:
                    total = h.get("total", {}).get("value", 0)
                    iter += 1
                batch = h.get("hits", [])
                if not batch:
                    break
                hits.extend(batch)
                start += len(batch)

            except requests.RequestException as e:
                hits = {"error": str(e)}
        return hits, total

    def test_query(self):
        list_of_hits, total_hits = self.query()
        assert total_hits > 0, "No hits found for the query"
        if total_hits > 0:
            assert type(list_of_hits) == list
