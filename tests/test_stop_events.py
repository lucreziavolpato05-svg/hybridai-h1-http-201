"""Offline train grouping, ordering and export-cache regression tests."""

import io
import json
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch

from ingestion.connector import fetch_dataset_export
from ingestion.stop_events import emit_records, normalize_records


def event(uic=8500123, time="10:00", **overrides):
    record = dict(betriebstag="2026-09-28", betreiber_id="85:11", fahrt_bezeichner="trip-a",
                  produkt_id="Zug", bpuic=uic, verkehrsmittel_text="IC", faellt_aus_tf=False,
                  durchfahrt_tf=False, ankunftszeit=f"2026-09-28T{time}:00", abfahrtszeit=None)
    record.update(overrides)
    return record


class EventTests(unittest.TestCase):
    def test_order_is_within_operator_date_and_journey(self):
        raw = [event(8500124, "10:10"), event(), event(fahrt_bezeichner="trip-b"),
               event(betreiber_id="85:22"), event(betriebstag="2026-09-29", ankunftszeit="2026-09-29T10:00:00")]
        records = normalize_records(raw)
        by_id = {row.identifier: row for row in records}
        self.assertEqual(sum(row.next_event is not None for row in records), 1)
        for row in records:
            if row.next_event:
                following = by_id[row.next_event]
                self.assertEqual(row.journey, following.journey)
                self.assertLess(row.scheduled, following.scheduled)
        self.assertEqual(records, normalize_records(list(reversed(raw))))

    def test_midnight_and_terminal_departure(self):
        rows = normalize_records([event(8500124, ankunftszeit="2026-09-29T00:03:00"),
                                  event(ankunftszeit=None, abfahrtszeit="2026-09-28T23:59:00")])
        self.assertEqual(rows[0].next_event, rows[1].identifier)

    def test_cancelled_and_foreign_calls_are_not_removed_from_chain(self):
        rows = normalize_records([event(), event(8000123, "10:05", faellt_aus_tf=True), event(8500124, "10:10")])
        source = emit_records(rows, swiss_uics={"8500123", "8500124"})
        self.assertEqual(rows[0].next_event, rows[1].identifier)
        self.assertEqual(rows[1].next_event, rows[2].identifier)
        self.assertNotIn("atStopPoint -> station_8000123", source)
        self.assertIn("cancelled -> true", source)
        self.assertNotIn("nonStopTo", source)
        self.assertNotIn("actuallyStops", source)

    def test_unknown_flags_are_not_false(self):
        rows = normalize_records([event(faellt_aus_tf=None, durchfahrt_tf=None)])
        source = emit_records(rows, swiss_uics={"8500123"})
        self.assertNotIn("cancelled", source)
        self.assertNotIn("passesThrough", source)

    def test_float_uic_and_boolean_strings(self):
        row = normalize_records([event(bpuic=8500123.0, faellt_aus_tf="false", durchfahrt_tf="true")])[0]
        self.assertEqual(row.uic, "8500123")
        self.assertIs(row.cancelled, False)
        self.assertIs(row.passes_through, True)

    def test_ambiguous_order_disables_links(self):
        with self.assertWarnsRegex(UserWarning, "uncertain journeys"):
            rows = normalize_records([event(), event(8500124), event(8500125, "10:10")])
        self.assertTrue(all(row.next_event is None for row in rows))

    def test_bad_row_never_stitches_a_gap(self):
        with warnings.catch_warnings(record=True):
            rows = normalize_records([event(), event(8500124, ankunftszeit="bad"), event(8500125, "10:10")])
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row.next_event is None for row in rows))

    def test_missing_group_identity_is_fatal(self):
        with self.assertRaises(ValueError):
            normalize_records([event(fahrt_bezeichner=None)])

    def test_duplicate_calls_collapse_and_repeat_visits_remain_distinct(self):
        rows = normalize_records([event(), event(), event(time="10:10")])
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0].identifier, rows[1].identifier)


class ExportTests(unittest.TestCase):
    def test_full_export_and_offline_cache(self):
        rows = [event()]
        count = {"total_count": 1, "results": rows}
        payloads = [io.BytesIO(json.dumps(value).encode()) for value in (count, rows, count)]
        with tempfile.TemporaryDirectory() as folder:
            with patch("ingestion.connector.urlopen", side_effect=payloads) as request:
                self.assertEqual(fetch_dataset_export("events", raw_dir=Path(folder)), rows)
                self.assertIn("/exports/json?limit=-1", request.call_args_list[1].args[0].full_url)
            with patch("ingestion.connector.urlopen", side_effect=AssertionError("network")):
                self.assertEqual(fetch_dataset_export("events", raw_dir=Path(folder)), rows)

    def test_incomplete_export_is_not_cached(self):
        values = ({"total_count": 2, "results": []}, [event()], {"total_count": 2, "results": []})
        with tempfile.TemporaryDirectory() as folder:
            with patch("ingestion.connector.urlopen", side_effect=[io.BytesIO(json.dumps(value).encode()) for value in values]):
                with self.assertRaisesRegex(ValueError, "Incomplete"):
                    fetch_dataset_export("events", raw_dir=Path(folder))
            self.assertFalse(list(Path(folder).rglob("*.json")))


if __name__ == "__main__":
    unittest.main()
