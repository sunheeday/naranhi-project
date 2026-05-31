import unittest

from app.translation.validators import validate_hard_facts_by_code


class TranslationValidatorsTest(unittest.TestCase):
    def test_validation_accepts_date_range_boundary_expansion(self):
        result = validate_hard_facts_by_code(
            {
                "hard_facts": {
                    "dates": [
                        {"normalized": "2026-05-18 ~ 2026-05-22"},
                        {"normalized": "2026-05-20"},
                    ],
                },
            },
            {
                "hard_facts": {
                    "dates": [
                        {"normalized": "2026-05-18"},
                        {"normalized": "2026-05-20"},
                        {"normalized": "2026-05-22"},
                    ],
                },
            },
        )

        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["mismatches"], [])

    def test_validation_accepts_contacts_when_numbers_and_email_match(self):
        result = validate_hard_facts_by_code(
            {
                "hard_facts": {
                    "contacts": [
                        {"raw_text": "교무실 031-8077-3510"},
                        {"raw_text": "행정실 031-8077-3500"},
                        {
                            "raw_text": "경기도교육연구원 부연구위원 배정현 ☎031-8012-0940, praxis@gie.re."
                        },
                    ],
                },
            },
            {
                "hard_facts": {
                    "contacts": [
                        {"normalized": "031-8077-3510"},
                        {"normalized": "031-8077-3500"},
                        {"normalized": "031-8012-0940"},
                        {"normalized": "praxis@gie.re"},
                    ],
                },
            },
        )

        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["mismatches"], [])

    def test_validation_accepts_grade_target_when_grade_matches(self):
        result = validate_hard_facts_by_code(
            {
                "hard_facts": {
                    "grade_class_targets": [
                        {"normalized": "2nd Grade Parents"},
                    ],
                },
            },
            {
                "hard_facts": {
                    "grade_class_targets": [
                        {"normalized": "2"},
                    ],
                },
            },
        )

        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["mismatches"], [])

    def test_validation_still_fails_for_new_unmatched_date(self):
        result = validate_hard_facts_by_code(
            {
                "hard_facts": {
                    "dates": [{"normalized": "2026-05-18"}],
                },
            },
            {
                "hard_facts": {
                    "dates": [
                        {"normalized": "2026-05-18"},
                        {"normalized": "2026-05-30"},
                    ],
                },
            },
        )

        self.assertEqual(result["verdict"], "FAIL")
        self.assertTrue(
            any(item["field"] == "dates" for item in result["mismatches"]),
        )


if __name__ == "__main__":
    unittest.main()
