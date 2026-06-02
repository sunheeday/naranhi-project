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

    def test_validation_accepts_phone_international_vs_national_form(self):
        # n01: source national 032-320-0096, target rendered as +82 32-320-0096
        result = validate_hard_facts_by_code(
            {
                "hard_facts": {
                    "contacts": [
                        {"raw_text": "인천광역시교육청 안전복지과"},
                        {"normalized": "032-320-0096"},
                    ],
                },
            },
            {
                "hard_facts": {
                    "contacts": [
                        {"normalized": "+82 32-320-0096"},
                    ],
                },
            },
        )
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["mismatches"], [])

    def test_validation_accepts_org_name_only_contact(self):
        # An org name with no number/email must not gate the deterministic check.
        result = validate_hard_facts_by_code(
            {"hard_facts": {"contacts": [{"raw_text": "인천광역시교육청 안전복지과"}]}},
            {"hard_facts": {"contacts": [{"raw_text": "Incheon Office of Education"}]}},
        )
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["mismatches"], [])

    def test_validation_accepts_free_equals_zero_krw(self):
        # n06: source fee "Free"/"무료", target extractor emits "0 KRW".
        result = validate_hard_facts_by_code(
            {"hard_facts": {"fees": [{"raw_text": "무료", "normalized": "Free"}]}},
            {"hard_facts": {"fees": [{"normalized": "0 KRW"}]}},
        )
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["mismatches"], [])

    def test_validation_accepts_free_equals_arabic_majjani(self):
        result = validate_hard_facts_by_code(
            {"hard_facts": {"fees": [{"normalized": "Free"}]}},
            {"hard_facts": {"fees": [{"normalized": "مجانية"}]}},
        )
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["mismatches"], [])

    def test_validation_accepts_free_equals_fully_supported(self):
        # n06: source "무료"/"free"; target describes the funding model instead.
        result = validate_hard_facts_by_code(
            {"hard_facts": {"fees": [{"normalized": "Free"}]}},
            {
                "hard_facts": {
                    "fees": [
                        {
                            "normalized": "Fully supported by the Incheon Metropolitan City Office of Education"
                        }
                    ]
                }
            },
        )
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["mismatches"], [])

    def test_validation_still_fails_for_changed_fee_amount(self):
        result = validate_hard_facts_by_code(
            {"hard_facts": {"fees": [{"normalized": "30,000 KRW"}]}},
            {"hard_facts": {"fees": [{"normalized": "13,000 KRW"}]}},
        )
        self.assertEqual(result["verdict"], "FAIL")
        self.assertTrue(any(m["field"] == "fees" for m in result["mismatches"]))

    def test_validation_accepts_url_trailing_slash_and_host_case(self):
        result = validate_hard_facts_by_code(
            {"hard_facts": {"urls": [{"normalized": "https://forms.gle/aeS2a3oEiPR3VcJb7"}]}},
            {"hard_facts": {"urls": [{"normalized": "https://Forms.gle/aeS2a3oEiPR3VcJb7/"}]}},
        )
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["mismatches"], [])

    def test_validation_still_fails_for_changed_url_path(self):
        result = validate_hard_facts_by_code(
            {"hard_facts": {"urls": [{"normalized": "https://forms.gle/aaaa"}]}},
            {"hard_facts": {"urls": [{"normalized": "https://forms.gle/bbbb"}]}},
        )
        self.assertEqual(result["verdict"], "FAIL")
        self.assertTrue(any(m["field"] == "urls" for m in result["mismatches"]))

    # ------------------------------------------------------------------
    # Iter-002 Change Set #1: dates / times / grade_class_targets symmetry
    # ------------------------------------------------------------------

    def test_validation_ignores_academic_year_token(self):
        # n02: source "2026학년도" (normalized None) is a non-absolute token and
        # must not gate; the absolute dates match.
        result = validate_hard_facts_by_code(
            {
                "hard_facts": {
                    "dates": [
                        {"raw_text": "2026학년도", "normalized": None},
                        {"normalized": "2026-01"},
                        {"normalized": "2026-06-01"},
                        {"normalized": "2026-10-19~2026-10-21"},
                        {"normalized": "2026-05-27"},
                    ],
                    "deadlines": [{"normalized": "2026-06-01"}],
                },
            },
            {
                "hard_facts": {
                    "dates": [
                        {"normalized": "2026-01"},
                        {"normalized": "2026-05-27"},
                        {"normalized": "2026-10-19"},
                        {"normalized": "2026-10-21"},
                    ],
                    "deadlines": [{"normalized": "2026-06-01"}],
                },
            },
        )
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["mismatches"], [])

    def test_validation_ignores_bare_year_and_year_month(self):
        # n05: bare years "2026"/"2027" and "2026-06" are non-absolute; the only
        # absolute date 2026-05-29 sits in the deadline on the target side.
        result = validate_hard_facts_by_code(
            {
                "hard_facts": {
                    "dates": [
                        {"normalized": "2026"},
                        {"normalized": "2026-05-29"},
                        {"normalized": "2026-06-12"},
                        {"normalized": "2026-06"},
                        {"normalized": "2027"},
                    ],
                    "deadlines": [{"normalized": "2026-05-29 17:30"}],
                },
            },
            {
                "hard_facts": {
                    "dates": [
                        {"normalized": "2026"},
                        {"normalized": "2026-06"},
                        {"normalized": "2026-06-12"},
                        {"normalized": "2027"},
                    ],
                    "deadlines": [{"normalized": "2026-05-29 17:30"}],
                },
            },
        )
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["mismatches"], [])

    def test_validation_accepts_date_migrated_between_dates_and_deadlines(self):
        # An absolute date filed under "dates" on the source but under
        # "deadlines" on the target must not be reported as missing.
        result = validate_hard_facts_by_code(
            {"hard_facts": {"dates": [{"normalized": "2026-06-01"}], "deadlines": []}},
            {"hard_facts": {"dates": [], "deadlines": [{"normalized": "2026-06-01"}]}},
        )
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["mismatches"], [])

    def test_validation_ignores_duration_keeps_clock_times(self):
        # n06: target adds a duration "40 minutes" (redundant with the clock
        # range) and re-files 09:00/18:00; the clock times all match.
        result = validate_hard_facts_by_code(
            {
                "hard_facts": {
                    "times": [
                        {"normalized": "09:00"},
                        {"normalized": "18:00"},
                        {"normalized": "19:30 - 20:10"},
                        {"normalized": "20:30 - 21:10"},
                    ],
                },
            },
            {
                "hard_facts": {
                    "times": [
                        {"normalized": "09:00"},
                        {"normalized": "18:00"},
                        {"normalized": "19:30 to 20:10"},
                        {"normalized": "20:30 to 21:10"},
                        {"normalized": "40 minutes"},
                    ],
                },
            },
        )
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["mismatches"], [])

    def test_validation_still_fails_for_changed_clock_time(self):
        # A genuine clock-time change must still fail.
        result = validate_hard_facts_by_code(
            {"hard_facts": {"times": [{"normalized": "19:30 - 20:10"}]}},
            {"hard_facts": {"times": [{"normalized": "19:30 - 21:10"}]}},
        )
        self.assertEqual(result["verdict"], "FAIL")
        self.assertTrue(any(m["field"] == "times" for m in result["mismatches"]))

    def test_validation_separates_class_labels_from_target_grades(self):
        # n06: source class rows carry full grade lists (1-6); target renders the
        # class labels separately plus "grades 1, 2, 3" / "grades 4, 5, 6".
        # Class labels (A반 / Class A) must not pollute the grade comparison and
        # all six grades must be extracted on both sides.
        result = validate_hard_facts_by_code(
            {
                "hard_facts": {
                    "grade_class_targets": [
                        {"normalized": "Elementary school students in Incheon"},
                        {"normalized": "Class A - lower grades (1st, 2nd, 3rd grade)"},
                        {"normalized": "Class B - higher grades (4th, 5th, 6th grade)"},
                    ],
                },
            },
            {
                "hard_facts": {
                    "grade_class_targets": [
                        {"normalized": "Class A"},
                        {"normalized": "Class B"},
                        {"normalized": "Elementary school students in Incheon City"},
                        {"normalized": "grades 1, 2, 3"},
                        {"normalized": "grades 4, 5, 6"},
                    ],
                },
            },
        )
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["mismatches"], [])

    def test_validation_ignores_prose_only_eligibility_targets(self):
        # n05: descriptive eligibility entries have no numeric grade; Korean
        # source vs translated language must not gate.
        result = validate_hard_facts_by_code(
            {
                "hard_facts": {
                    "grade_class_targets": [
                        {"raw_text": "시민기자단 30명"},
                        {"raw_text": "인천 관내 거주 만 13세 ~ 19세 미만 청소년"},
                        {"raw_text": "학생기자단 60명"},
                    ],
                },
            },
            {
                "hard_facts": {
                    "grade_class_targets": [
                        {"normalized": "any adult citizen in Incheon"},
                        {"normalized": "youth residing in Incheon, aged 13-19"},
                    ],
                },
            },
        )
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["mismatches"], [])

    def test_validation_still_fails_for_dropped_target_grade(self):
        # A genuine target-grade omission must still fail (missing direction).
        result = validate_hard_facts_by_code(
            {"hard_facts": {"grade_class_targets": [{"normalized": "grades 1, 2, 3"}]}},
            {"hard_facts": {"grade_class_targets": [{"normalized": "grade 1 only"}]}},
        )
        self.assertEqual(result["verdict"], "FAIL")
        self.assertTrue(
            any(m["field"] == "grade_class_targets" for m in result["mismatches"])
        )

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
