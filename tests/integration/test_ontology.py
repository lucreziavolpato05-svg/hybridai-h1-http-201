"""Offline ontology integration tests. Require FRAMEX_BINARY or framex on PATH.

Run separately: python -m unittest discover -s tests/integration -v
"""

import os
import shutil
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from framex import Client
from ingestion import didok, wifi
from ingestion.emiter import emit_records as emit_platforms
from ingestion.normalizer import normalize_records as normalize_platforms

ROOT = Path(__file__).resolve().parents[2]
BINARY = os.environ.get("FRAMEX_BINARY") or shutil.which("framex")


@unittest.skipUnless(BINARY, "integration test requires FRAMEX_BINARY or framex on PATH")
class OntologyTests(unittest.TestCase):
    def setUp(self):
        self.client = Client(binary=BINARY, retain_transcript=False)
        self.addCleanup(self.client.close)
        self.client.load((ROOT / "ontology.fx").read_text(encoding="utf-8"))

    def assert_status(self, goal, expected="true"):
        self.assertEqual(self.client.query(f"?- {goal}.")["status"], expected, goal)

    def test_platform_compatibility_and_strict_length_threshold(self):
        self.client.add(source='''
            station_test:LegacyNamedStation[name -> "Test"].
            platform_test:Platform[station -> station_test; number -> "1/2"; structuralLengthM -> 539.0].
            platform_boundary:Platform[structuralLengthM -> 320.0].
            platform_missing:Platform.
        ''')
        for goal in (
            "station_test:StopPoint", 'station_test[designation -> "Test"]',
            "platform_test[atStopPoint -> station_test]",
            'platform_test[platformNumber -> "1/2"]',
            "platform_test[platformLength -> 539.0]", "platform_test:LongPlatform",
            "station_test[hasLongPlatform -> true]",
        ):
            self.assert_status(goal)
        self.assert_status("platform_boundary:LongPlatform", "unknown")
        self.assert_status("platform_missing:LongPlatform", "unknown")

    def test_busy_in_year_preserves_argument_type_and_threshold(self):
        self.client.add(source='''
            busy[observedFrequency("2025") -> 25000; observedFrequency("2024") -> 1000].
            quiet[observedFrequency("2025") -> 20000].
            numeric[observedFrequency(2025) -> 25000].
        ''')
        self.assert_status('busy[busyIn("2025") -> true]')
        self.assert_status("busy:BusyStation")
        self.assert_status('busy[busyIn("2024") -> true]', "unknown")
        self.assert_status('quiet[busyIn("2025") -> true]', "unknown")
        self.assert_status("numeric[busyIn(2025) -> true]")
        self.assert_status('numeric[busyIn("2025") -> true]', "unknown")

    def test_didok_designation_is_not_overwritten_by_platform_name(self):
        self.client.add(source='''
            station_test:Station[name -> "Zurich HB"].
            station_test:StopPoint[designation -> "Zürich HB"].
        ''')
        self.assert_status('station_test[designation -> "Zürich HB"]')
        self.assert_status('station_test[designation -> "Zurich HB"]', "unknown")
        self.assertEqual(self.client.validate()["violations"], [])

    def test_junction_requires_distinct_lines(self):
        self.client.add(source='''
            junction[servedByLine -> {line_one, line_two}].
            single[servedByLine -> line_one].
            single[servedByLine -> line_one].
        ''')
        self.assert_status("junction:Junction")
        self.assert_status("single:Junction", "unknown")

    def test_interchange_requires_both_positive_modes(self):
        self.client.add(source='''
            interchange[servesMode -> {mode_train, mode_tram}].
            rail_only[servesMode -> mode_train].
        ''')
        self.assert_status("interchange:Interchange")
        self.assert_status("rail_only:Interchange", "unknown")

    def test_actual_stop_and_category_require_explicit_false_flags(self):
        self.client.add(source='''
            actual:StopEvent[atStopPoint -> station_actual; category -> "IC"; cancelled -> false; passesThrough -> false].
            cancelled:StopEvent[atStopPoint -> station_cancelled; category -> "IC"; cancelled -> true; passesThrough -> false].
            passing:StopEvent[atStopPoint -> station_passing; category -> "IC"; cancelled -> false; passesThrough -> true].
            missing:StopEvent[atStopPoint -> station_missing; category -> "IC"; cancelled -> false].
        ''')
        self.assert_status("actual[actuallyStops -> true]")
        self.assert_status('station_actual[servedByCategory -> "IC"]')
        for name in ("cancelled", "passing", "missing"):
            self.assert_status(f"{name}[actuallyStops -> true]", "unknown")
            self.assert_status(f'station_{name}[servedByCategory -> "IC"]', "unknown")

    def test_non_stop_adjacent_actual_stops(self):
        self.client.add(source='''
            a:StopEvent[atStopPoint -> station_a; cancelled -> false; passesThrough -> false; nextStop -> b].
            b:StopEvent[atStopPoint -> station_b; cancelled -> false; passesThrough -> false; nextStop -> c].
            c:StopEvent[atStopPoint -> station_c; cancelled -> false; passesThrough -> false].
        ''')
        self.assert_status("station_a[nonStopTo -> station_b]")
        self.assert_status("station_a[nonStopTo -> station_c]", "unknown")
        self.assert_status("station_b[nonStopTo -> station_a]", "unknown")

    def test_non_stop_skips_pass_through(self):
        self.check_intermediate("cancelled -> false; passesThrough -> true", "true")

    def test_non_stop_skips_cancelled_event(self):
        self.check_intermediate("cancelled -> true; passesThrough -> false", "true")

    def test_non_stop_does_not_skip_unknown_event(self):
        self.check_intermediate("cancelled -> false", "unknown")

    def check_intermediate(self, flags, expected):
        self.client.add(source=f'''
            a:StopEvent[atStopPoint -> station_a; cancelled -> false; passesThrough -> false; nextStop -> intermediate].
            intermediate:StopEvent[atStopPoint -> station_intermediate; {flags}; nextStop -> b].
            b:StopEvent[atStopPoint -> station_b; cancelled -> false; passesThrough -> false].
        ''')
        self.assert_status("station_a[nonStopTo -> station_b]", expected)
        self.assert_status("station_a[nonStopTo -> station_intermediate]", "unknown")
        self.assert_status("station_intermediate[nonStopTo -> station_b]", "unknown")

    def test_non_stop_skips_mixed_chain(self):
        self.client.add(source='''
            a:StopEvent[atStopPoint -> station_a; cancelled -> false; passesThrough -> false; nextStop -> passing].
            passing:StopEvent[passesThrough -> true; nextStop -> cancelled].
            cancelled:StopEvent[cancelled -> true; nextStop -> b].
            b:StopEvent[atStopPoint -> station_b; cancelled -> false; passesThrough -> false].
        ''')
        self.assert_status("station_a[nonStopTo -> station_b]")

    def test_long_distance_configuration_and_derived_membership(self):
        for category in ("IC", "IR", "EC", "ICE", "TGV", "NJ", "RJX"):
            with self.subTest(category=category):
                self.assertEqual(self.client.query(f'?- ?K:LongDistanceCategory[label -> "{category}"].')["status"], "bindings")
                self.client.add(source=f'station_{category.lower()}[servedByCategory -> "{category}"].')
                self.assert_status(f"station_{category.lower()}:LongDistanceStation")
        self.client.add(source='local[servedByCategory -> "S"].')
        self.assert_status("local:LongDistanceStation", "unknown")

    def test_missing_wifi_is_unknown_including_explicit_negation(self):
        self.client.add(source="station_unknown:LongDistanceStation.")
        self.assert_status("station_unknown[hasWifi -> true]", "unknown")
        self.assert_status("station_unknown[hasWifi -> false]", "unknown")
        self.assert_status("station_unknown:LongDistanceStation AND NOT station_unknown[hasWifi -> true]", "unknown")
        self.assert_status("?S:LongDistanceStation AND NOT ?S[hasWifi -> true]", "unknown")

    def test_dataset_adapters_join_and_derive_offline(self):
        points = didok.normalize_records([{
            "number": 8500123, "designationofficial": "Synthetic Rail", "isocountrycode": "CH",
            "stoppoint": "true", "meansoftransport": "TRAIN|TRAM", "cantonabbreviation": "TI",
        }], as_of=date(2026, 9, 29))
        platforms = normalize_platforms([{
            "fid": 123, "bpuic": "8500123", "bps_name": "Synthetic Rail",
            "p_nr": "1/2", "p_lange": 400,
        }])
        access = wifi.normalize_records([{"bpuic": 8500123}])
        with patch("ingestion.connector.urlopen", side_effect=AssertionError("no network during reasoning")):
            self.client.add(source=didok.emit_records(points) + emit_platforms(platforms) + wifi.emit_records(access))
            self.assert_status("station_8500123:Interchange")
            self.assert_status("station_8500123[hasPlatform -> platform_123; hasWifi -> true; inCanton -> canton_ti]")
            self.assert_status("platform_123:LongPlatform")
            self.assert_status("station_8500999[hasWifi -> false]", "unknown")
            explanation = self.client.explain("platform_123:LongPlatform")
            self.assertIn("Derived by rule", explanation)
            self.assertIn("structuralLengthM", explanation)

    def test_actual_category_derives_long_distance_station(self):
        self.client.add(source='''
            actual:StopEvent[atStopPoint -> station_actual; category -> "TGV"; cancelled -> false; passesThrough -> false].
            cancelled:StopEvent[atStopPoint -> station_cancelled; category -> "TGV"; cancelled -> true; passesThrough -> false].
        ''')
        self.assert_status("station_actual:LongDistanceStation")
        self.assert_status("station_cancelled:LongDistanceStation", "unknown")


if __name__ == "__main__":
    unittest.main()
