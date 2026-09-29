"""Synthetic schema fixtures; no internet or FrameX executable required."""

import unittest
from datetime import date

from ingestion import didok, wifi
from ingestion.normalizer import normalize_record as normalize_platform

AS_OF = date(2026, 9, 29)


def service_point(**overrides):
    record = {
        "number": 8500123, "numbershort": 123, "designationofficial": " Test   Station ",
        "isocountrycode": "CH", "stoppoint": "true", "meansoftransport": "TRAIN|TRAM",
        "cantonabbreviation": "TI", "validfrom": "2020-01-01", "validto": "9999-12-31",
    }
    record.update(overrides)
    return record


class DidokTests(unittest.TestCase):
    def normalize(self, **overrides):
        return didok.normalize_record(service_point(**overrides), as_of=AS_OF)

    def test_schema_mapping_and_whitespace(self):
        point = self.normalize()
        self.assertEqual(point.uic, "8500123")
        self.assertEqual(point.identifier, "station_8500123")
        self.assertEqual(point.designation, "Test Station")
        self.assertEqual(point.canton, "TI")
        self.assertEqual(set(point.modes), {"TRAIN", "TRAM"})

    def test_only_positive_swiss_passenger_rail_scope(self):
        for overrides in ({"isocountrycode": "DE"}, {"isocountrycode": None},
                          {"stoppoint": "false"}, {"stoppoint": None},
                          {"meansoftransport": "BUS"}, {"meansoftransport": "TRAM"},
                          {"meansoftransport": None}):
            with self.subTest(overrides=overrides):
                self.assertIsNone(self.normalize(**overrides))
        self.assertEqual(self.normalize(meansoftransport="RACK_RAILWAY").modes, ("RACK_RAILWAY",))

    def test_missing_optional_fields_emit_no_invented_values(self):
        point = self.normalize(designationofficial=None, cantonabbreviation=None)
        source = didok.emit_records([point])
        self.assertIn("station_8500123:StopPoint.", source)
        self.assertNotIn("designation", source)
        self.assertNotIn("inCanton", source)
        self.assertNotIn("false", source)

    def test_missing_uic_never_falls_back_to_short_number_or_name(self):
        for value in (None, "", 123):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.normalize(number=value)

    def test_malformed_fields_are_rejected(self):
        for overrides in ({"number": True}, {"number": 8500123.0}, {"number": "8500123]."},
                          {"designationofficial": []}, {"cantonabbreviation": "XX"},
                          {"meansoftransport": ["TRAIN"]}, {"meansoftransport": "TRAIN|UNKNOWN"},
                          {"stoppoint": "maybe"}, {"validto": "not-a-date"},
                          {"validfrom": "2029-01-01", "validto": "2020-01-01"}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.normalize(**overrides)

    def test_validity_date_is_inclusive_and_explicit(self):
        self.assertIsNone(self.normalize(validto="2026-09-28"))
        self.assertIsNone(self.normalize(validfrom="2026-09-30"))
        self.assertIsNotNone(self.normalize(validfrom="2026-09-29", validto="2026-09-29"))
        self.assertIsNotNone(self.normalize(validfrom=None, validto=None))

    def test_deduplication_and_conflicts(self):
        self.assertEqual(len(didok.normalize_records([service_point(), service_point()], as_of=AS_OF)), 1)
        with self.assertRaisesRegex(ValueError, "DiDok record 1.*Conflicting"):
            didok.normalize_records([service_point(), service_point(cantonabbreviation="ZH")], as_of=AS_OF)

    def test_emission_is_base_facts_and_unquoted_references(self):
        source = didok.emit_records([self.normalize(designationofficial='Test "Rail" \\ Stop')])
        self.assertIn('[designation -> "Test \\"Rail\\" \\\\ Stop"].', source)
        self.assertIn("canton_ti:Canton.", source)
        self.assertIn("station_8500123[inCanton -> canton_ti].", source)
        self.assertIn("station_8500123[servesMode -> mode_train].", source)
        self.assertIn("station_8500123[servesMode -> mode_tram].", source)
        self.assertNotIn(":Interchange", source)
        self.assertNotIn(":LongDistanceStation", source)


class WifiTests(unittest.TestCase):
    def test_inventory_presence_is_positive_evidence(self):
        point = wifi.normalize_record({"bpuic": 8500123, "standort": " Test  Station "})
        self.assertEqual(point.location, "Test Station")
        self.assertEqual(wifi.emit_records([point]), "station_8500123[hasWifi -> true].\n")

    def test_missing_location_does_not_destroy_positive_evidence(self):
        point = wifi.normalize_record({"bpuic": "8500123"})
        self.assertIsNone(point.location)
        self.assertIn("hasWifi -> true", wifi.emit_records([point]))

    def test_absence_does_not_emit_false_or_negative_facts(self):
        self.assertEqual(wifi.emit_records(wifi.normalize_records([])), "")
        source = wifi.emit_records(wifi.normalize_records([{"bpuic": 8500123}]))
        self.assertNotIn("false", source)
        self.assertNotIn("NOT", source)
        self.assertNotIn("station_8500999", source)
        self.assertNotIn("designation", source)

    def test_missing_identity_is_reported_and_not_guessed_from_location(self):
        for value in (None, "", " "):
            with self.subTest(value=value), self.assertWarnsRegex(UserWarning, "missing bpuic"):
                self.assertEqual(wifi.normalize_records([{"bpuic": value, "standort": "Test Station"}]), [])

    def test_malformed_identity_is_rejected(self):
        for value in (123, True, 8500123.0, "8500123].", "abcdefgh"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "WiFi record 0"):
                wifi.normalize_records([{"bpuic": value}])
        with self.assertRaises(ValueError):
            wifi.normalize_record({"bpuic": 8500123, "standort": {}})

    def test_multiple_access_points_collapse_to_station_evidence(self):
        points = wifi.normalize_records([{"bpuic": 8500123, "standort": "A"},
                                         {"bpuic": "8500123", "standort": "B"}])
        self.assertEqual(len(points), 1)
        self.assertEqual(wifi.emit_records(points).count("hasWifi"), 1)

    def test_all_three_adapters_share_identity(self):
        platform = normalize_platform({"fid": 123, "bpuic": "8500123"})
        stop = didok.normalize_record(service_point(), as_of=AS_OF)
        access = wifi.normalize_record({"bpuic": 8500123})
        self.assertEqual(platform.station_identifier, stop.identifier)
        self.assertEqual(stop.identifier, access.identifier)


if __name__ == "__main__":
    unittest.main()
