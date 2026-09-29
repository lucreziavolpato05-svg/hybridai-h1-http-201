"""Offline checks for the SBB/FrameX integration boundaries."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse

from ingestion.connector import fetch_records
from ingestion.emiter import emit_records
from ingestion.ingest import ingest_platforms, main, source_batches
from ingestion.normalizer import normalize_records


def record(**overrides):
    result = {
        "fid": 35288249, "bps_name": " Aadorf  ", "bps": "AD",
        "bpuic": "8506013", "dst_id": 6013, "p_nr": "1/2",
        "perrontyp": "Mittelperron", "p_lange": 323,
        "z_schienenfrei": "ja", "geopos": {"lat": 47.488, "lon": 8.903},
    }
    result.update(overrides)
    return result


def response(records, total=None):
    return io.BytesIO(json.dumps({
        "total_count": len(records) if total is None else total, "results": records,
    }).encode())


class ConnectorTests(unittest.TestCase):
    def test_pagination_and_offline_cache(self):
        records = [record(fid=index) for index in range(103)]
        with tempfile.TemporaryDirectory() as folder:
            with patch("ingestion.connector.urlopen", side_effect=[response(records[:100], 103), response(records[100:], 103)]) as request:
                self.assertEqual(fetch_records(raw_dir=Path(folder)), records)
                offsets = [parse_qs(urlparse(call.args[0].full_url).query)["offset"] for call in request.call_args_list]
                self.assertEqual(offsets, [["0"], ["100"]])
            with patch("ingestion.connector.urlopen", side_effect=AssertionError("network used")):
                self.assertEqual(fetch_records(raw_dir=Path(folder)), records)

    def test_sample_is_not_used_as_full_dataset_and_refresh_replaces_it(self):
        with tempfile.TemporaryDirectory() as folder:
            raw_dir = Path(folder)
            with patch("ingestion.connector.urlopen", return_value=response([record()], 2)):
                self.assertEqual(len(fetch_records(limit=1, raw_dir=raw_dir)), 1)
            with patch("ingestion.connector.urlopen", return_value=response([record(), record(fid=2)])) as request:
                self.assertEqual(len(fetch_records(raw_dir=raw_dir)), 2)
                request.assert_called_once()
            with patch("ingestion.connector.urlopen", return_value=response([record(p_lange=400)], 2)):
                self.assertEqual(fetch_records(limit=1, raw_dir=raw_dir, refresh=True)[0]["p_lange"], 400)

    def test_failed_refresh_preserves_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            raw_dir = Path(folder)
            with patch("ingestion.connector.urlopen", return_value=response([record()])):
                fetch_records(raw_dir=raw_dir)
            with patch("ingestion.connector.urlopen", side_effect=URLError("offline")):
                with self.assertRaises(RuntimeError):
                    fetch_records(raw_dir=raw_dir, refresh=True)
            self.assertEqual(fetch_records(raw_dir=raw_dir), [record()])

    def test_incomplete_or_changed_download_is_not_cached(self):
        for pages in ([response([], 1)], [response([record()], 2), response([record(fid=2)], 3)]):
            with self.subTest(), tempfile.TemporaryDirectory() as folder:
                with patch("ingestion.connector.urlopen", side_effect=pages):
                    with self.assertRaises(RuntimeError):
                        fetch_records(raw_dir=Path(folder))
                self.assertFalse(list(Path(folder).rglob("*.json")))

    def test_zero_and_invalid_limits_do_not_request(self):
        with patch("ingestion.connector.urlopen") as request:
            self.assertEqual(fetch_records(limit=0), [])
            with self.assertRaises(ValueError):
                fetch_records(limit=-1)
            request.assert_not_called()

    def test_corrupt_cache_has_recovery_instruction(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "perron" / "all.json"
            path.parent.mkdir()
            path.write_text('{"results": []}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "--refresh"):
                fetch_records(raw_dir=Path(folder))


class NormalizationTests(unittest.TestCase):
    def test_types_whitespace_and_ids(self):
        platform = normalize_records([record(p_lange="323", z_schienenfrei=" NEIN ")])[0]
        self.assertEqual(platform.identifier, "platform_35288249")
        self.assertEqual(platform.station_identifier, "station_8506013")
        self.assertEqual(platform.station_name, "Aadorf")
        self.assertEqual(platform.platform_number, "1/2")
        self.assertEqual(platform.structural_length_m, 323)
        self.assertIs(platform.rail_free_access, False)

    def test_missing_is_distinct_from_zero_and_false(self):
        source = emit_records(normalize_records([record(p_lange=0, z_schienenfrei="nein", geopos=None)]))
        self.assertIn("[structuralLengthM -> 0.0].", source)
        self.assertIn("[railFreeAccess -> false].", source)
        self.assertNotIn("latitude", source)
        self.assertNotIn("structuralLengthM", emit_records(normalize_records([record(p_lange=None)])))

    def test_invalid_fields_fail_with_record_context(self):
        for overrides in ({"p_lange": -1}, {"p_lange": "NaN"}, {"fid": None},
                          {"fid": "a.b"}, {"z_schienenfrei": "maybe"},
                          {"geopos": {"lat": 91}}, {"p_lange": True}):
            with self.subTest(overrides=overrides), self.assertRaisesRegex(ValueError, "Record 0"):
                normalize_records([record(**overrides)])

    def test_deduplication_and_conflicting_identity(self):
        self.assertEqual(len(normalize_records([record(), record()])), 1)
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            normalize_records([record(), record(p_lange=1)])


class EmissionAndIngestTests(unittest.TestCase):
    def test_string_escaping_and_unquoted_station_reference(self):
        source = emit_records(normalize_records([record(bps_name='Zürich "HB" \\ West')]))
        self.assertIn('[name -> "Zürich \\"HB\\" \\\\ West"].', source)
        self.assertIn("[station -> station_8506013].", source)
        self.assertNotIn("world open", source)

    def test_add_preserves_existing_program(self):
        client = Mock()
        platforms = normalize_records([record()])
        self.assertEqual(ingest_platforms(client, platforms), 1)
        client.add.assert_called_once_with(source=emit_records(platforms))
        client.load.assert_not_called()

    def test_batches_fit_wire_budget_and_preserve_statements(self):
        source = emit_records(normalize_records([record(bps_name='é"\\' * 10)]))
        batches = list(source_batches(source, max_bytes=300))
        self.assertGreater(len(batches), 1)
        self.assertEqual("".join(batches), source)
        for batch in batches:
            wire = json.dumps({"command": "add", "id": 1, "source": batch}, ensure_ascii=False) + "\n"
            self.assertLessEqual(len(wire.encode()), 300)
            self.assertTrue(batch.endswith(".\n"))

    def test_empty_input_does_not_add(self):
        client = Mock()
        self.assertEqual(ingest_platforms(client, []), 0)
        client.add.assert_not_called()

    def test_dry_run_generates_file_without_engine(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "platforms.fx"
            with patch("ingestion.ingest.fetch_records", return_value=[record()]), patch("ingestion.ingest.Client") as client:
                self.assertEqual(main(["--dry-run", "--output", str(output)]), 0)
                client.assert_not_called()
            self.assertTrue(output.read_text(encoding="utf-8").startswith("world open.\n"))


if __name__ == "__main__":
    unittest.main()
