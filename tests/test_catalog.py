"""Offline provenance, enrollment linkage and malformed-input regressions."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from sfu_planner.catalog import CatalogError, load_catalog, validate_catalog, validate_meeting

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
spec = importlib.util.spec_from_file_location("fetch_sfu", ROOT / "scripts" / "fetch_sfu.py")
fetch_sfu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch_sfu)


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog(DATA / "catalog.json")

    def changed(self, edit):
        value = deepcopy(self.catalog)
        edit(value)
        return value

    def test_real_snapshot_rebuilds_exactly_without_network(self):
        self.assertEqual(fetch_sfu.build(DATA), self.catalog)
        self.assertEqual(len(self.catalog["courses"]), 10)
        self.assertEqual(sum(len(c["sections"]) for c in self.catalog["courses"]), 52)

    def test_tutorials_and_labs_are_in_every_required_bundle(self):
        courses = {c["id"]: c for c in self.catalog["courses"]}
        expected = {"CMPT 125": ("LAB", 4), "CMPT 225": ("LAB", 12),
                    "CMPT 295": ("LAB", 5), "MACM 101": ("TUT", 19)}
        for code, (kind, count) in expected.items():
            with self.subTest(course=code):
                self.assertEqual(len(courses[code]["sections"]), count)
                for section in courses[code]["sections"]:
                    self.assertEqual([c["kind"] for c in section["components"]], ["LEC", kind])
                    for component in section["components"]:
                        self.assertTrue(any(m["component"] == component["id"] for m in section["meetings"]))

    def test_optional_workshops_are_explicit_not_silent_missing_tutorials(self):
        course = next(c for c in self.catalog["courses"] if c["id"] == "MATH 151")
        self.assertEqual([c["sectionCode"] for c in course["optional_components"]], ["OPL", "OPL"])
        self.assertTrue(all(len(s["components"]) == 1 for s in course["sections"]))

    def test_exam_and_split_date_facts_survive_normalization(self):
        course = next(c for c in self.catalog["courses"] if c["id"] == "MATH 232")
        section = course["sections"][0]
        lectures = [m for m in section["meetings"] if m["kind"] == "LEC"]
        self.assertEqual(lectures[0]["end_date"], "2026-10-17")
        self.assertEqual(lectures[1]["start_date"], "2026-10-18")
        self.assertTrue(any(m["kind"] == "EXAM" and m["start_date"] == m["end_date"] for m in section["meetings"]))

    def test_fixtures_have_verified_source_and_projection_hashes(self):
        manifest = json.loads((DATA / "manifest.json").read_text())
        self.assertGreater(len(manifest["sources"]), 50)
        for source in manifest["sources"]:
            self.assertTrue(source["url"].startswith(fetch_sfu.API))
            self.assertEqual(len(source["response_sha256"]), 64)
            self.assertEqual(fetch_sfu.sha((DATA / source["fixture"]).read_bytes()), source["fixture_sha256"])

    def test_tampered_fixture_cannot_be_rebuilt(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            shutil.copytree(DATA / "sources", target / "sources")
            shutil.copyfile(DATA / "manifest.json", target / "manifest.json")
            shutil.copyfile(DATA / "reviewed_rules.json", target / "reviewed_rules.json")
            fixture = next((target / "sources").glob("*.json"))
            fixture.write_text("{}")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                fetch_sfu.build(target)

    def test_changed_official_rules_require_review_before_rebuild(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            shutil.copytree(DATA / "sources", target / "sources")
            shutil.copyfile(DATA / "manifest.json", target / "manifest.json")
            reviewed = json.loads((DATA / "reviewed_rules.json").read_text())
            reviewed["CMPT 120"]["prerequisite_text"] = "A previous, no longer valid rule."
            (target / "reviewed_rules.json").write_text(json.dumps(reviewed))
            with self.assertRaisesRegex(ValueError, "human rule review required"):
                fetch_sfu.build(target)

    def test_unknown_prerequisite_operator_is_rejected(self):
        value = self.changed(lambda c: c["courses"][0].update(prerequisite={"probably": True}))
        with self.assertRaisesRegex(CatalogError, "Unsupported prerequisite"):
            validate_catalog(value)

    def test_duplicate_course_and_section_ids_are_rejected(self):
        value = deepcopy(self.catalog)
        value["courses"].append(deepcopy(value["courses"][0]))
        with self.assertRaisesRegex(CatalogError, "Duplicate course"):
            validate_catalog(value)
        value = deepcopy(self.catalog)
        value["courses"][0]["sections"].append(deepcopy(value["courses"][0]["sections"][0]))
        with self.assertRaisesRegex(CatalogError, "Duplicate section"):
            validate_catalog(value)

    def test_wrong_tutorial_linkage_is_rejected(self):
        value = deepcopy(self.catalog)
        section = value["courses"][1]["sections"][0]
        section["components"][1]["associated_class"] = "99"
        with self.assertRaisesRegex(CatalogError, "another lecture"):
            validate_catalog(value)

    def test_silent_missing_component_meetings_are_rejected(self):
        value = deepcopy(self.catalog)
        section = value["courses"][1]["sections"][0]
        section["meetings"] = [m for m in section["meetings"] if m["kind"] != "LAB"]
        with self.assertRaisesRegex(CatalogError, "required component has no meetings"):
            validate_catalog(value)

    def test_dates_times_and_weekdays_are_validated_for_busy_periods(self):
        base = {"days": [0, 2], "start": 600, "end": 660,
                "start_date": "2026-09-09", "end_date": "2026-12-07"}
        self.assertEqual(validate_meeting(base), base)
        invalid = [{"days": [True]}, {"days": [7]}, {"days": [0, 0]}, {"start": 660},
                   {"end": 1441}, {"start_date": "September"}, {"end_date": "2026-01-01"},
                   {"days": [0], "start_date": "2026-09-09", "end_date": "2026-09-09"}]
        for edit in invalid:
            with self.subTest(edit=edit), self.assertRaises(CatalogError):
                validate_meeting({**base, **edit})

    def test_manual_rules_and_credit_exclusions_are_preserved(self):
        courses = {c["id"]: c for c in self.catalog["courses"]}
        self.assertIn("manual", courses["CMPT 276"]["prerequisite"]["all"][0])
        self.assertEqual(courses["CMPT 125"]["credit_exclusion_ranges"],
                         [{"subject": "CMPT", "min_number": 200, "max_number": 999}])
        self.assertIn("CMPT 125", courses["CMPT 120"]["credit_exclusions"])

    def test_missing_file_and_malformed_json_are_clear_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "catalog.json"
            with self.assertRaisesRegex(CatalogError, "Cannot read catalog"):
                load_catalog(target)
            target.write_text("{broken")
            with self.assertRaisesRegex(CatalogError, "Cannot read catalog"):
                load_catalog(target)


if __name__ == "__main__":
    unittest.main()
