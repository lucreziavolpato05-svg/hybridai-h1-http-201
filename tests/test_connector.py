"""Offline checks for reusable API access and cache isolation."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from ingestion.connector import fetch_dataset_records


def response(records, total=None):
    return io.BytesIO(json.dumps({"total_count": len(records) if total is None else total,
                                "results": records}).encode())


class DatasetConnectorTests(unittest.TestCase):
    def test_no_platform_field_is_assumed(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("ingestion.connector.urlopen", return_value=response([{"bpuic": 8500123}])) as request:
                records = fetch_dataset_records("wifistation", raw_dir=Path(folder))
            self.assertEqual(records, [{"bpuic": 8500123}])
            url = urlparse(request.call_args.args[0].full_url)
            self.assertTrue(url.path.endswith("/wifistation/records"))
            self.assertNotIn("order_by", parse_qs(url.query))

    def test_filters_and_order_are_encoded_and_cache_isolated(self):
        with tempfile.TemporaryDirectory() as folder:
            raw_dir = Path(folder)
            options = {"order_by": "number", "where": 'isocountrycode = "CH"'}
            with patch("ingestion.connector.urlopen", return_value=response([{"number": 8500123}])) as request:
                fetch_dataset_records("didok", raw_dir=raw_dir, **options)
                parameters = parse_qs(urlparse(request.call_args.args[0].full_url).query)
                self.assertEqual(parameters["where"], [options["where"]])
                self.assertEqual(parameters["order_by"], ["number"])
            with patch("ingestion.connector.urlopen", side_effect=AssertionError("network used")):
                self.assertEqual(fetch_dataset_records("didok", raw_dir=raw_dir, **options), [{"number": 8500123}])
            for dataset, order, where in (("didok", "number desc", options["where"]),
                                           ("didok", "number", None), ("other", "number", options["where"])):
                with patch("ingestion.connector.urlopen", return_value=response([])) as request:
                    self.assertEqual(fetch_dataset_records(dataset, raw_dir=raw_dir, order_by=order, where=where), [])
                    request.assert_called_once()
            self.assertEqual(len(list(raw_dir.rglob("*.json"))), 4)

    def test_generic_pagination_and_limit(self):
        records = [{"number": i} for i in range(101)]
        with tempfile.TemporaryDirectory() as folder:
            with patch("ingestion.connector.urlopen", side_effect=[response(records[:100], 200), response(records[100:], 200)]) as request:
                self.assertEqual(fetch_dataset_records("didok", order_by="number", limit=101, raw_dir=Path(folder)), records)
                last_query = parse_qs(urlparse(request.call_args.args[0].full_url).query)
                self.assertEqual(last_query["offset"], ["100"])
                self.assertEqual(last_query["limit"], ["1"])

    def test_rejects_unsafe_dataset_ids_and_empty_options(self):
        with patch("ingestion.connector.urlopen") as request:
            for dataset in ("../perron", "a/b", "", "a?limit=1", None):
                with self.subTest(dataset=dataset), self.assertRaises(ValueError):
                    fetch_dataset_records(dataset)
            for options in ({"order_by": ""}, {"where": 4}, {"limit": -1}):
                with self.subTest(options=options), self.assertRaises(ValueError):
                    fetch_dataset_records("didok", **options)
            self.assertEqual(fetch_dataset_records("didok", limit=0), [])
            request.assert_not_called()

    def test_full_dataset_does_not_silently_truncate_at_api_window(self):
        def page(request, **kwargs):
            offset = int(parse_qs(urlparse(request.full_url).query)["offset"][0])
            return response([{"number": i} for i in range(offset, offset + 100)], 10001)
        with tempfile.TemporaryDirectory() as folder, patch("ingestion.connector.urlopen", side_effect=page):
            with self.assertRaisesRegex(ValueError, "exports API"):
                fetch_dataset_records("large", raw_dir=Path(folder))
            self.assertFalse(list(Path(folder).rglob("*.json")))


if __name__ == "__main__":
    unittest.main()
