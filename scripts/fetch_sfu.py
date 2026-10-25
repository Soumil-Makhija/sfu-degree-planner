#!/usr/bin/env python3
"""Refresh a deliberately small, auditable SFU Fall 2026 course snapshot.

Only factual fields are retained from the public outline API. Every fixture has
the SHA-256 of the original HTTP response and of the retained projection.
Run --offline to rebuild/verify normalization without any network access.
"""
from __future__ import annotations

import argparse
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import re
import sys
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
API = "https://www.sfu.ca/bin/wcm/course-outlines?2026/fall/"
COURSES = ("cmpt/120", "cmpt/125", "cmpt/225", "cmpt/276", "cmpt/295",
           "macm/101", "macm/201", "math/151", "math/152", "math/232")
DAYS = {"Mo": 0, "Tu": 1, "We": 2, "Th": 3, "Fr": 4, "Sa": 5, "Su": 6}
GRADES = ("A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D", "P")


def course(code: str, grade: str = "C-") -> dict:
    return {"course": code, "min_grade": grade}


def any_courses(*codes: str, grade: str = "C-") -> dict:
    return {"any": [course(code, grade) for code in codes]}


def rules() -> dict:
    """Human reviewed expressions for these ten courses; not a text parser."""
    return {
        "CMPT 120": {"all": []},
        "CMPT 125": any_courses("CMPT 120", "CMPT 130"),
        "CMPT 225": {"any": [
            {"all": [course("MACM 101"), any_courses("CMPT 125", "CMPT 129", "CMPT 135")]},
            {"all": [course("ENSC 251"), course("ENSC 252")]}]},
        "CMPT 276": {"all": [
            {"manual": "One W course with a minimum grade of C- must be verified."},
            course("CMPT 225"),
            {"any": [course("MACM 101"), {"all": [course("ENSC 251"), course("ENSC 252")]}]},
            {"any": [course("MATH 151"), course("MATH 150"),
                     course("MATH 154", "B+"), course("MATH 157", "B+")]}]},
        "CMPT 295": {"any": [
            {"all": [course("MACM 101"), any_courses("CMPT 125", "CMPT 135")]},
            {"all": [course("MATH 151"), course("CMPT 102"),
                     {"manual": "Applied Physics program membership must be verified."}]}]},
        "MACM 101": {"any": [
            {"manual": "BC Pre-Calculus 12, BC Calculus 12, or an accepted equivalent must be verified."},
            # The source specifies no minimum letter grade for this course.
            any_courses("MATH 100", "MATH 150", "MATH 151", "MATH 154", "MATH 157", grade="D")]},
        "MACM 201": {"any": [course("MATH 141", "D"), course("MACM 101", "D"),
            {"all": [course("ENSC 251", "D"), any_courses("MATH 232", "MATH 240", grade="D")]}]},
        "MATH 151": {"any": [
            {"manual": "Pre-Calculus 12 or an accepted equivalent with grade A or higher must be verified."},
            course("MATH 100", "B"), course("MATH 110", "A")]},
        "MATH 152": {"any": [any_courses("MATH 150", "MATH 151"),
                                     any_courses("MATH 154", "MATH 157", grade="B")]},
        "MATH 232": {"any": [any_courses("MATH 150", "MATH 151", "MACM 101"),
                                     any_courses("MATH 154", "MATH 157", grade="B")]},
    }


EXCLUSIONS = {
    "CMPT 120": ["CMPT 102", "CMPT 128", "CMPT 130", "CMPT 166", "CMPT 125", "CMPT 129", "CMPT 135"],
    "CMPT 125": ["CMPT 126", "CMPT 129", "CMPT 135"],
    "CMPT 276": ["CMPT 275"],
    "MATH 151": ["MATH 150", "MATH 154", "MATH 157"],
    "MATH 152": ["MATH 155", "MATH 158"],
    "MATH 232": ["MATH 240"],
}


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def encoded(value) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def factual_projection(payload):
    if isinstance(payload, list):
        return payload  # The listing contains only course/section facts.
    if not isinstance(payload, dict) or "info" not in payload:
        raise ValueError("Unexpected SFU outline response")
    keep = ("section", "units", "title", "type", "classNumber", "prerequisites",
            "corequisites", "number", "outlinePath", "term", "dept", "notes")
    return {"info": {key: payload["info"].get(key, "") for key in keep},
            "courseSchedule": payload.get("courseSchedule", []),
            "examSchedule": payload.get("examSchedule", [])}


def fetch(path: str, directory: Path) -> dict:
    url = API + path
    request = Request(url, headers={"User-Agent": "SFU-degree-planner/1.0 (public factual snapshot)"})
    with urlopen(request, timeout=30) as response:
        raw = response.read()
    projection = factual_projection(json.loads(raw))
    retained = encoded(projection)
    filename = path.replace("/", "_") + ".json"
    (directory / filename).write_bytes(retained)
    return {"url": url, "fixture": "sources/" + filename,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "response_sha256": sha(raw), "fixture_sha256": sha(retained),
            "projection": "Only section/identity/prerequisite/meeting facts; prose and personnel omitted."}


def minute(value: str) -> int:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", value)
    if not match:
        raise ValueError(f"Unsupported time: {value!r}")
    return int(match[1]) * 60 + int(match[2])


def iso_date(value: str) -> str:
    # Ignore server timezone abbreviation; SFU supplies local calendar dates.
    parts = value.split()
    return datetime.strptime(" ".join(parts[1:3] + parts[-1:]), "%b %d %Y").date().isoformat()


def meetings(detail: dict, component: str, include_exams: bool) -> list:
    result = []
    rows = list(detail["courseSchedule"])
    if include_exams:
        rows += detail["examSchedule"]
    for row in rows:
        # Unscheduled/TBA times cannot enter a solver as an empty schedule.
        if not row.get("days") or not row.get("startTime") or not row.get("endTime"):
            raise ValueError(f"Unscheduled component: {component}")
        normalized = {"days": [DAYS[day.strip()] for day in row["days"].split(",")],
                       "start": minute(row["startTime"]), "end": minute(row["endTime"]),
                       "start_date": iso_date(row["startDate"]), "end_date": iso_date(row["endDate"]),
                       "campus": row["campus"],
                       "kind": "EXAM" if row.get("isExam") else row["sectionCode"],
                       "component": component}
        # The official API repeats exam rows for multiple physical rooms. The
        # planner models time/campus, so identical facts represent one meeting.
        if normalized not in result:
            result.append(normalized)
    if not result:
        raise ValueError(f"No meetings available for {component}")
    return result


def build(data_dir: Path) -> dict:
    manifest = json.loads((data_dir / "manifest.json").read_text())
    reviewed_rules = json.loads((data_dir / "reviewed_rules.json").read_text())
    records = {record["url"].removeprefix(API): record for record in manifest["sources"]}
    for record in manifest["sources"]:
        raw = (data_dir / record["fixture"]).read_bytes()
        if sha(raw) != record["fixture_sha256"]:
            raise ValueError(f"Fixture checksum mismatch: {record['fixture']}")

    def read(path):
        return json.loads((data_dir / records[path]["fixture"]).read_text())

    result = {"term": "2026-fall", "timezone": "America/Vancouver", "schema_version": 1,
              "source": {"name": "Simon Fraser University public course outlines API",
                         "base_url": API, "fetched_at": manifest["fetched_at"],
                         "manifest": "manifest.json"},
              "notes": [
                  "Ten-course curated Fall 2026 snapshot, not the full SFU catalog or live seat availability.",
                  "Each section is a complete lecture plus one linked required LAB/TUT of each listed kind.",
                  "Optional OPL workshops are listed in optional_components and excluded from enrollment bundles.",
                  "Final exams are included as date-specific EXAM meetings; holidays are not modeled.",
                  "Manual prerequisites require advisor verification; no equivalencies or waivers are inferred."],
              "courses": []}
    for path in COURSES:
        listing = read(path)
        lectures = [item for item in listing if item["classType"] == "e"]
        if not lectures:
            raise ValueError(f"No enrollment sections for {path}")
        first_info = read(path + "/" + lectures[0]["value"])["info"]
        code = first_info["dept"] + " " + first_info["number"]
        reviewed = reviewed_rules.get(code)
        if reviewed != {"prerequisite_text": first_info["prerequisites"], "restriction_text": first_info["notes"]}:
            raise ValueError(f"Prerequisite or restriction changed; human rule review required: {code}")
        output = {"id": code, "title": first_info["title"], "units": float(first_info["units"]),
                  "prerequisite": rules()[code], "prerequisite_text": first_info["prerequisites"],
                  "prerequisite_review": [], "credit_exclusions": EXCLUSIONS.get(code, []),
                  "credit_exclusion_ranges": [{"subject": "CMPT", "min_number": 200, "max_number": 999}]
                      if code == "CMPT 125" else [],
                  "restriction_text": first_info["notes"], "sections": [],
                  "calendar_url": "https://www.sfu.ca/students/calendar/2026/fall/courses/" + path + "/",
                  "source_urls": [API + path],
                  "optional_components": [item for item in listing if item["sectionCode"] == "OPL"]}
        for lecture in lectures:
            groups = {}
            for secondary in listing:
                if secondary["classType"] == "e" or secondary["sectionCode"] == "OPL":
                    continue
                if secondary["sectionCode"] not in ("LAB", "TUT"):
                    raise ValueError(f"Unsupported component kind: {secondary}")
                if secondary["associatedClass"] in (lecture["associatedClass"], "9999"):
                    groups.setdefault(secondary["sectionCode"], []).append(secondary)
            for choice in itertools.product(*groups.values()):
                components = [lecture, *choice]
                section = {"id": "+".join(item["text"] for item in components),
                           "components": [{"id": item["text"], "kind": item["sectionCode"],
                                           "associated_class": item["associatedClass"]} for item in components],
                           "meetings": [], "source_urls": []}
                for index, item in enumerate(components):
                    detail_path = path + "/" + item["value"]
                    detail = read(detail_path)
                    if detail["info"]["prerequisites"] != first_info["prerequisites"]:
                        raise ValueError(f"Section-specific prerequisite differs: {detail_path}")
                    if detail["info"].get("corequisites"):
                        raise ValueError(f"Unhandled corequisite: {detail_path}")
                    section["meetings"].extend(meetings(detail, item["text"], include_exams=index == 0))
                    section["source_urls"].append(API + detail_path)
                output["sections"].append(section)
        result["courses"].append(output)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Verify fixtures and rebuild without network")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args(argv)
    directory = args.data_dir / "sources"
    directory.mkdir(parents=True, exist_ok=True)
    if not args.offline:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            listing_records = list(executor.map(lambda path: fetch(path, directory), COURSES))
            detail_paths = []
            for path, record in zip(COURSES, listing_records):
                listing = json.loads((args.data_dir / record["fixture"]).read_text())
                detail_paths += [path + "/" + item["value"] for item in listing if item["sectionCode"] != "OPL"]
            records = listing_records + list(executor.map(lambda path: fetch(path, directory), detail_paths))
        manifest = {"fetched_at": datetime.now(timezone.utc).isoformat(), "sources": records}
        (args.data_dir / "manifest.json").write_bytes(encoded(manifest))
    catalog = build(args.data_dir)
    sys.path.insert(0, str(ROOT))
    from sfu_planner.catalog import validate_catalog
    validate_catalog(catalog)
    (args.data_dir / "catalog.json").write_bytes(encoded(catalog))
    count = sum(len(item["sections"]) for item in catalog["courses"])
    print(f"Validated {len(catalog['courses'])} courses and {count} complete enrollment bundles.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
