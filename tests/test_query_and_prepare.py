"""Check orchestration without network access or an engine executable."""

import io
import tempfile
import unittest
from datetime import date
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from ingestion import prepare
from query import load_knowledge, main, print_result, validation_summary


class HarnessTests(unittest.TestCase):
    def test_line_preparation_does_not_turn_freight_markers_into_station_junctions(self):
        raw = [{"bpuic": uic, "linie": line} for uic in (8500123, 8515338) for line in (100, 900)]
        source, count = prepare._line_facts(raw, date(2026, 9, 29), swiss_uics={"8500123"})
        self.assertEqual(count, 2)
        self.assertIn("station_8500123", source)
        self.assertNotIn("station_8515338", source)

    def test_validation_summary_preserves_unknown_and_violation_counts(self):
        summary = validation_summary({
            "constraint_checks": [{"status": "unknown"}, {"status": "violated"}],
            "schema_checks": [{"status": "satisfied"}, {"status": "unknown"}],
            "violations": [f"violation_{i}" for i in range(20)],
        })
        self.assertEqual(summary["constraint_checks"], {"unknown": 1, "violated": 1})
        self.assertEqual(summary["violation_count"], 20)
        self.assertEqual(len(summary["first_10_violations"]), 10)

    def test_load_combines_local_files_in_one_staged_program(self):
        with tempfile.TemporaryDirectory() as folder:
            ontology, first, second = [Path(folder) / name for name in ("ontology.fx", "a.fx", "b.fx")]
            ontology.write_text("world open.", encoding="utf-8")
            first.write_text("a:Thing.", encoding="utf-8")
            second.write_text("b:Thing.", encoding="utf-8")
            client = Mock()
            load_knowledge(client, ontology, [first, second])
            client.load_program.assert_called_once_with(source="world open.\na:Thing.\nb:Thing.")

    def test_prints_status_for_all_result_shapes(self):
        for result in ({"status": "unknown"}, {"status": "true"}, {"status": "false"},
                       {"status": "bindings", "bindings": [{"S": "station_8500123"}]}):
            with self.subTest(result=result), redirect_stdout(io.StringIO()) as output:
                print_result("?- ?S:StopPoint.", result)
            self.assertIn(f"status: {result['status']}", output.getvalue())
            self.assertIn("bindings:", output.getvalue())

    def test_custom_query_and_explanation_reach_engine(self):
        with patch("query.Client") as factory, patch("query.load_knowledge", return_value={"facts": 1}), redirect_stdout(io.StringIO()):
            client = factory.return_value.__enter__.return_value
            client.query.return_value = {"status": "unknown"}
            client.explain.return_value = {"status": "unknown"}
            self.assertEqual(main(["--query", "?- missing:StopPoint.", "--explain", "missing:StopPoint"]), 0)
            client.query.assert_called_once_with("?- missing:StopPoint.")
            client.explain.assert_called_once_with("missing:StopPoint")

    def test_prepare_dataset_selection_and_positive_wifi_file(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("ingestion.prepare.fetch_dataset_records", return_value=[{"bpuic": 8500123}]) as fetch, redirect_stdout(io.StringIO()):
                self.assertEqual(prepare.main(["--datasets", "wifi", "--output-dir", folder]), 0)
                self.assertEqual(fetch.call_args.args, ("wifistation",))
                self.assertEqual(fetch.call_args.kwargs["order_by"], "bpuic")
            path = Path(folder) / "wifi.fx"
            self.assertEqual(path.read_text(encoding="utf-8"), "world open.\nstation_8500123[hasWifi -> true].\n")
            self.assertEqual(len(list(Path(folder).iterdir())), 1)

    def test_default_preparation_uses_one_raw_directory_for_all_datasets(self):
        with tempfile.TemporaryDirectory() as folder:
            raw_dir = Path(folder) / "raw"
            output_dir = Path(folder) / "facts"
            with patch("ingestion.prepare.fetch_records", return_value=[]) as platforms, \
                 patch("ingestion.prepare.fetch_dataset_records", return_value=[]) as generic, \
                 patch("ingestion.prepare.fetch_dataset_export", return_value=[]) as export, \
                 patch("ingestion.connector.urlopen", side_effect=AssertionError("unit tests must be offline")), \
                 redirect_stdout(io.StringIO()):
                self.assertEqual(prepare.main(["--raw-dir", str(raw_dir), "--output-dir", str(output_dir)]), 0)
            platforms.assert_called_once_with(raw_dir=raw_dir, limit=None, refresh=False)
            self.assertEqual([call.args[0] for call in generic.call_args_list], [
                "dienststellen-gemass-opentransportdataswiss", "wifistation",
                "dienststellen-gemass-opentransportdataswiss", "haltestelle-wartehallen",
                "passagierfrequenz", "linie-mit-betriebspunkten", "sektortafel",
            ])
            export.assert_called_once_with("ist-daten-sbb", where='produkt_id = "Zug"',
                                           raw_dir=raw_dir, refresh=False)
            for call in generic.call_args_list:
                self.assertEqual(call.kwargs["raw_dir"], raw_dir)
                self.assertEqual(call.kwargs["limit"], None)
                self.assertFalse(call.kwargs["refresh"])
            self.assertEqual(sorted(path.name for path in output_dir.iterdir()), [
                "lines.fx", "passengers.fx", "platforms.fx", "sector_boards.fx",
                "service_points.fx", "stop_events.fx", "waiting_halls.fx", "wifi.fx",
            ])

    def test_service_points_is_canonical_dataset_name_and_didok_remains_an_alias(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("ingestion.prepare.fetch_dataset_records", return_value=[]), redirect_stdout(io.StringIO()):
                self.assertEqual(prepare.main(["--datasets", "service_points", "didok",
                                               "--output-dir", folder]), 0)
            self.assertEqual(sorted(path.name for path in Path(folder).iterdir()), ["service_points.fx"])


if __name__ == "__main__":
    unittest.main()
