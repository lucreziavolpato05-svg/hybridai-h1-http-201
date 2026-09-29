"""The acceptance report must distinguish evidence, unknown and date changes."""
import unittest
from acceptance import QUESTIONS, evaluate, projection


class AcceptanceTests(unittest.TestCase):
    def test_all_official_questions_have_unique_ids(self):
        expected = {f"1.{n}" for n in range(1, 8)} | {f"2.{n}" for n in range(1, 7)} | {f"3.{n}" for n in range(1, 6)}
        self.assertEqual({row[0] for row in QUESTIONS}, expected)
        self.assertEqual(len(QUESTIONS), 18)

    def test_missing_answers_cannot_pass_as_date_difference(self):
        self.assertEqual(evaluate("1.4", {"status": "unknown"}, ["2026-09-28"])[0], "FAIL")

    def test_executed_live_answers_are_marked_against_reference_day(self):
        result = {"status": "bindings", "bindings": [{"Category": '"IC"'}]}
        self.assertEqual(evaluate("1.4", result, ["2026-09-28"])[0], "LIVE-DATA DIFFERENCE")
        self.assertEqual(evaluate("1.4", result, ["2026-09-27"])[0], "PASS")

    def test_negative_wifi_requires_unknown(self):
        self.assertEqual(evaluate("1.7", {"status": "unknown"}, [])[0], "PASS")
        self.assertEqual(evaluate("1.7", {"status": "false"}, [])[0], "FAIL")

    def test_literal_projection_deduplicates_proof_witnesses(self):
        result = {"bindings": [{"N": '"Bern"', "D": "20001.0"}] * 2}
        self.assertEqual(projection(result, "N", "D"), {("Bern", 20001.0)})
