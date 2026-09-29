"""Check orchestration without network access or an engine executable."""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from ingestion import prepare
from query import load_knowledge, main, print_result, validation_summary


class HarnessTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
