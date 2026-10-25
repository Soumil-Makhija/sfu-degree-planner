import copy
import unittest

from sfu_planner.audit import audit, load_requirements


def transcript(*courses, grade="A", **metadata):
    return [{"course": cid, "grade": grade, **metadata} for cid in courses]


def checks(result):
    return {item["id"]: item for item in result["checks"]}


class AuditTests(unittest.TestCase):
    def test_current_calendar_contains_actual_fall_2026_changes(self):
        rules = load_requirements()
        self.assertEqual(rules["academic_year"], "Fall 2026")
        self.assertEqual(rules["breadth_areas_required"], 4)
        self.assertIn("CMPT 201", rules["lower_required"])
        self.assertIn("CMPT 210", rules["lower_required"])
        self.assertIn("STAT 271", rules["lower_required"])
        self.assertNotIn("MACM 201", rules["lower_required"])
        self.assertEqual(rules["table_ii"], [])
        self.assertEqual(rules["course_metadata"]["CMPT 295"]["units"], 4)
        self.assertEqual(rules["course_metadata"]["ECON 103"]["designations"], ["Q"])

    def test_empty_transcript_explains_missing_core_and_never_certifies(self):
        result = audit([])
        self.assertEqual(result["status"], "incomplete")
        self.assertFalse(result["graduation_certified"])
        self.assertIn("lower_cmpt_120", result["missing_checks"])
        self.assertTrue(result["manual_review_checks"])
        self.assertEqual(checks(result)["total_units"]["remaining_units"], 120)

    def test_normalizes_identifiers_and_repeated_attempts_count_once(self):
        result = audit(transcript("cmpt120", grade="F") +
                       transcript("CMPT-120", grade="C") + transcript("CMPT 120"))
        check = checks(result)
        self.assertEqual(check["lower_cmpt_120"]["status"], "satisfied")
        self.assertEqual(check["total_units"]["earned_units"], 3)
        self.assertEqual(len(result["counted_courses"]), 1)
        self.assertEqual(len(result["ignored_attempts"]), 2)

    def test_failed_withdrawn_missing_and_unmodeled_grades_are_not_completed(self):
        records = [{"course": "CMPT 120", "grade": grade} for grade in ["F", "N", "W", "IP", "", "P"]]
        result = audit(records)
        self.assertEqual(result["counted_courses"], [])
        self.assertTrue(any("grade 'P'" in issue for issue in result["issues"]))

    def test_D_earns_degree_credit_but_not_wqb_credit(self):
        result = checks(audit(transcript("CMPT 105W", "CMPT 125", grade="D")))
        self.assertEqual(result["lower_cmpt_105w"]["status"], "satisfied")
        self.assertEqual(result["total_units"]["earned_units"], 6)
        self.assertEqual(result["wqb_writing"]["status"], "missing")
        self.assertEqual(result["wqb_quantitative"]["earned_units"], 0)

    def test_transcript_cannot_inflate_official_units_or_designations(self):
        result = audit([{"course": "CMPT 120", "grade": "A", "units": 30, "designations": ["W", "B-Hum"]}])
        check = checks(result)
        self.assertEqual(check["total_units"]["earned_units"], 3)
        self.assertEqual(check["wqb_writing"]["courses"], [])
        self.assertEqual(check["wqb_b_hum"]["candidates"], [])
        self.assertEqual(len(result["issues"]), 2)

    def test_unknown_course_units_are_provisional_even_if_verified_claimed(self):
        records = transcript("ZZZZ 401", "ZZZZ 402", "ZZZZ 403", "ZZZZ 404", units=30,
                             verified=True, designations=["W", "B-Sci"])
        result = audit(records)
        check = checks(result)
        self.assertEqual(check["total_units"]["earned_units"], 0)
        self.assertEqual(check["total_units"]["provisional_units"], 120)
        self.assertEqual(check["total_units"]["status"], "manual_review")
        self.assertEqual(check["wqb_b_sci"]["status"], "missing")

    def test_cross_listed_duplicate_does_not_double_count(self):
        result = audit(transcript("CMPT 476", "MACM 476"))
        self.assertEqual(checks(result)["total_units"]["earned_units"], 3)
        self.assertEqual(len(result["counted_courses"]), 1)
        self.assertTrue(any("Duplicate-credit" in issue for issue in result["issues"]))

    def test_calculus_permission_alternatives_remain_manual(self):
        result = checks(audit(transcript("MATH 154", "MATH 155", grade="B+")))
        self.assertEqual(result["calculus_i"]["status"], "manual_review")
        self.assertEqual(result["calculus_ii"]["status"], "manual_review")
        result = checks(audit(transcript("MATH 154", grade="B")))
        self.assertEqual(result["calculus_i"]["status"], "missing")

    def test_four_distinct_areas_and_mandatory_307_are_required(self):
        complete = transcript("CMPT 307", "CMPT 310", "CMPT 361", "CMPT 303")
        result = checks(audit(complete))["cs_breadth"]
        self.assertEqual(result["status"], "satisfied")
        self.assertEqual(result["earned_areas"], 4)
        self.assertEqual(len(set(result["assignments"].values())), 4)
        same_area = checks(audit(transcript("CMPT 307", "CMPT 308", "CMPT 404", "CMPT 405")))
        self.assertEqual(same_area["cs_breadth"]["status"], "missing")
        without_307 = checks(audit(transcript("CMPT 308", "CMPT 310", "CMPT 361", "CMPT 303")))
        self.assertEqual(without_307["cs_breadth"]["status"], "missing")

    def test_breadth_matching_does_not_reuse_one_course_for_two_areas(self):
        rules = load_requirements()
        rules["concentrations"] = {"theory": ["CMPT 307"], "one": ["CMPT 310"], "two": ["CMPT 310"], "three": ["CMPT 361"]}
        result = checks(audit(transcript("CMPT 307", "CMPT 310", "CMPT 361"), rules))
        self.assertEqual(result["cs_breadth"]["earned_areas"], 3)
        self.assertEqual(result["cs_breadth"]["status"], "missing")

    def test_depth_excludes_special_permission_and_non_cmpt(self):
        result = checks(audit(transcript("CMPT 410", "CMPT 411", "CMPT 413", "CMPT 415", "MACM 401")))
        self.assertEqual(result["depth_units"]["earned_units"], 9)
        self.assertEqual(result["depth_units"]["status"], "missing")
        self.assertEqual(result["depth_permission"]["status"], "manual_review")

    def test_bsc_extra_slots_cannot_double_count_the_30_cmpt_units(self):
        ten = ["CMPT 307", "CMPT 376W", "CMPT 310", "CMPT 361", "CMPT 303",
               "CMPT 354", "CMPT 410", "CMPT 411", "CMPT 413", "CMPT 405"]
        initial = checks(audit(transcript(*ten, "MACM 316")))
        self.assertEqual(initial["upper_cmpt_units"]["status"], "satisfied")
        self.assertEqual(initial["bsc_extra_courses"]["status"], "missing")
        added = checks(audit(transcript(*ten, "MACM 316", "MATH 308", "MATH 340")))
        self.assertEqual(added["bsc_extra_courses"]["status"], "satisfied")
        self.assertNotIn("MACM 316", added["bsc_extra_courses"]["courses"])

    def test_writing_requires_lower_and_upper_sfu_and_c_minus(self):
        self.assertEqual(checks(audit(transcript("CMPT 105W", "CMPT 376W")))["wqb_writing"]["status"], "manual_review")
        records = transcript("CMPT 105W", "CMPT 376W", institution="SFU", grade="C-")
        self.assertEqual(checks(audit(records))["wqb_writing"]["status"], "satisfied")
        records[1]["institution"] = "Other University"
        self.assertNotEqual(checks(audit(records))["wqb_writing"]["status"], "satisfied")

    def test_wqb_breadth_has_separate_additional_courses_and_excludes_major(self):
        courses = ["PHIL 100W", "HUM 130", "PHIL 105", "ECON 105", "BISC 101", "PHYS 120"]
        result = checks(audit(transcript(*courses, "CMPT 120")))
        self.assertEqual(result["wqb_b_hum"]["status"], "satisfied")
        self.assertEqual(result["wqb_b_soc"]["status"], "satisfied")
        self.assertEqual(result["wqb_b_sci"]["status"], "satisfied")
        self.assertEqual(result["wqb_additional"]["status"], "missing")
        result = checks(audit(transcript(*courses, "MATH 151", "MATH 152")))
        selected = []
        for key in ["wqb_b_hum", "wqb_b_soc", "wqb_b_sci", "wqb_additional"]:
            self.assertEqual(result[key]["status"], "satisfied")
            selected += result[key]["courses"]
        self.assertEqual(len(selected), len(set(selected)))

    def test_multi_b_designation_course_is_used_only_once(self):
        rules = copy.deepcopy(load_requirements())
        rules["course_metadata"]["ARCH 131"]["designations"] = ["B-Soc", "B-Sci"]
        result = checks(audit(transcript("PHIL 100W", "HUM 130", "PHIL 105", "ARCH 131", "BISC 101", "MATH 151", "MATH 152"), rules))
        selected = sum((result[k]["courses"] for k in ["wqb_b_hum", "wqb_b_soc", "wqb_b_sci", "wqb_additional"]), [])
        self.assertEqual(len(selected), len(set(selected)))
        self.assertLess(sum(result[k]["status"] == "satisfied" for k in ["wqb_b_hum", "wqb_b_soc", "wqb_b_sci", "wqb_additional"]), 4)

    def test_all_modeled_requirements_can_match_but_not_certify_graduation(self):
        rules = load_requirements()
        # Synthetic completion fixture using real reviewed calendar courses.
        courses = rules["lower_required"] + ["MATH 151", "MATH 152", "MATH 232", "MACM 316"]
        courses += ["CMPT 307", "CMPT 376W", "CMPT 310", "CMPT 361", "CMPT 303", "CMPT 354", "CMPT 410", "CMPT 411", "CMPT 413", "CMPT 405"]
        courses += ["MATH 308", "MATH 340", "MACM 401", "MACM 442", "MATH 343"]
        courses += ["PHIL 100W", "HUM 130", "PHIL 105", "ECON 105", "BISC 101", "PHYS 120", "ECON 103", "ARCH 131"]
        # Add electives so the overall total also reaches 120.
        courses += ["CMPT 308", "CMPT 373", "CMPT 383", "CMPT 384", "CMPT 403"]
        result = audit(transcript(*courses, institution="SFU"))
        self.assertEqual(result["missing_checks"], [])
        self.assertEqual(result["status"], "manual_review")
        self.assertFalse(result["graduation_certified"])
        self.assertGreaterEqual(checks(result)["total_units"]["earned_units"], 120)

    def test_invalid_input_has_actionable_errors(self):
        for invalid in [{}, "CMPT 120", ["CMPT 120"], [{"course": "bad"}],
                        [{"course": "CMPT 120", "units": -1}], [{"course": "CMPT 120", "units": float("nan")}],
                        [{"course": "CMPT 120", "units": True}],
                        [{"course": "CMPT 120", "grade": "A", "designations": 3}],
                        [{"course": "CMPT 120", "grade": "A", "designations": [["W"]]}],
                        [{"course": "CMPT 120", "grade": "A", "designations": "W"}],
                        [{"course": "CMPT 120", "grade": ["A"]}],
                        [{"course": "CMPT 120", "institution": None}],
                        [{"course": "CMPT 120", "transfer": "false"}]]:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    audit(invalid)


if __name__ == "__main__":
    unittest.main()
