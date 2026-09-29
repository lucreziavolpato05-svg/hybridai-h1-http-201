"""Offline schema and unknown-value regressions for the remaining sources."""
import unittest

from ingestion import lines, passengers, sector_boards, waiting_halls


class RemainingAdapterTests(unittest.TestCase):
    def test_waiting_status_and_distinct_installations(self):
        raw = [{"bpuic": 8503000, "status": status, "km": i}
               for i, status in enumerate(("BESTEHEND", "PROJEKTIERT NEU", "PROJEKTIERT ABBRUCH"))]
        records = waiting_halls.normalize_records(raw + [raw[0]])
        self.assertEqual(len(records), 3)
        source = waiting_halls.emit_records(records)
        for row in raw:
            self.assertIn(f'status -> "{row["status"]}"', source)
        self.assertEqual(source.count("atStopPoint -> station_8503000"), 3)
        self.assertNotIn("hasWaitingHall", source)

    def test_frequency_uses_dtv_and_string_years(self):
        rows = [{"uic": 8503000.0, "jahr_annee_anno": year,
                 "dtv_tjm_tgm": 20001, "dwv_tmjo_tfm": 99999}
                for year in ("2018", "2024", "2025")]
        source = passengers.emit_records(passengers.normalize_records(rows))
        for year in ("2018", "2024", "2025"):
            self.assertIn(f'observedFrequency("{year}") -> 20001.0', source)
        self.assertNotIn("99999", source)
        self.assertNotIn("busyIn", source)

    def test_missing_frequency_is_not_zero(self):
        raw = {"uic": 8503000, "jahr_annee_anno": "2024", "dtv_tjm_tgm": None}
        self.assertEqual(passengers.normalize_records([raw]), [])
        raw["dtv_tjm_tgm"] = 0
        self.assertEqual(passengers.normalize_records([raw])[0].daily_traffic, 0)

    def test_conflicting_frequency_is_omitted(self):
        raw = {"uic": 8503000, "jahr_annee_anno": "2024", "dtv_tjm_tgm": 20}
        with self.assertWarns(UserWarning):
            self.assertEqual(passengers.normalize_records([raw, {**raw, "dtv_tjm_tgm": 30}]), [])

    def test_line_membership_deduplicates_and_retains_labels(self):
        raw = {"bpuic": 8503000, "linie": 900}
        rows = lines.normalize_records([raw, raw, {**raw, "linie": 100}])
        source = lines.emit_records(rows)
        self.assertEqual(source.count("servedByLine"), 2)
        self.assertIn('line_900[label -> "900"]', source)
        self.assertNotIn("Junction", source)

    def test_sector_customer_track_and_missing_front(self):
        rows = sector_boards.normalize_records([
            {"fid": 123, "bpuic": "8503000", "kundengleisnummer": "3", "sektor_vorderseite": "A"},
            {"fid": 124, "bpuic": "8503000", "kundengleisnummer": "3", "sektor_vorderseite": None},
        ])
        source = sector_boards.emit_records(rows)
        self.assertIn('sectorboard_123[trackNumber -> "3"]', source)
        self.assertIn('sectorboard_123[sectorFront -> "A"]', source)
        self.assertNotIn('sectorboard_124[sectorFront', source)

    def test_missing_uic_is_never_guessed(self):
        for adapter in (lines, passengers, sector_boards, waiting_halls):
            with self.subTest(adapter=adapter.__name__), self.assertWarns(UserWarning):
                self.assertEqual(adapter.normalize_records([{}]), [])
