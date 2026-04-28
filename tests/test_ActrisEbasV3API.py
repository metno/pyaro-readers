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

    def initial_query(self):
        q = {
            "search": {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "match": {
                                    "variables.variable_name": "ozone mass concentration"
                                }
                            }
                        ]
                    }
                }
            }
        }
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
        # payload = {"search": {"query": query, "from": start, "size": page_size}}

        while start < total:
            payload = {"search": {"query": query, "from": start, "size": page_size}}
            try:
                r = requests.post(
                    BASE_API_URL + "/api/metadata/search", json=payload, timeout=30
                )
                r.raise_for_status()
                h = r.json().get("response", {}).get("hits", {})
                total = h.get("total", {}).get("value", 0)
                batch = h.get("hits", [])
                if not batch:
                    break
                hits.extend(batch)
                start += len(batch)

                result = r.json()
            except requests.RequestException as e:
                result = {"error": str(e)}
        return result

    def test_query(self):
        r = self.initial_query()
        assert (
            r["response"]["hits"]["total"]["value"] > 0
        ), "No hits found for the query"
