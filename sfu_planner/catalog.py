"""Strict validation and loading of the bundled, offline SFU course snapshot."""
from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
import re

COURSE_PATTERN = re.compile(r"[A-Z]{2,6} \d{3}[A-Z]?")
GRADES = {"A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D", "P"}
DEFAULT_CATALOG = Path(__file__).resolve().parents[1] / "data" / "catalog.json"
if not DEFAULT_CATALOG.is_file():
    DEFAULT_CATALOG = Path(__file__).resolve().parent / "data" / "catalog.json"


class CatalogError(ValueError):
    """The snapshot cannot safely be used for planning."""


def require(condition, message):
    if not condition:
        raise CatalogError(message)


def text(value, label):
    require(isinstance(value, str) and bool(value.strip()), f"{label} must be nonempty text")


def course_id(value, label):
    require(isinstance(value, str) and COURSE_PATTERN.fullmatch(value) is not None,
            f"{label} must be a normalized course ID")


def unique_strings(values, label, allow_empty=True):
    require(isinstance(values, list), f"{label} must be a list")
    require(allow_empty or values, f"{label} cannot be empty")
    for value in values:
        text(value, label)
    require(len(values) == len(set(values)), f"{label} contains duplicates")


def expression(value, depth=0):
    require(depth <= 20, "Prerequisite expression is too deeply nested")
    require(isinstance(value, dict), "Prerequisite must be an expression object")
    keys = set(value)
    if keys in ({"all"}, {"any"}):
        kind = next(iter(keys))
        require(isinstance(value[kind], list), f"{kind} expression must contain a list")
        require(kind != "any" or value[kind], "any expression cannot be empty")
        for child in value[kind]:
            expression(child, depth + 1)
    elif keys == {"course", "min_grade"}:
        course_id(value["course"], "Prerequisite course")
        require(value["min_grade"] in GRADES, "Unknown prerequisite minimum grade")
    elif keys == {"manual"}:
        text(value["manual"], "Manual prerequisite")
    else:
        raise CatalogError(f"Unsupported prerequisite expression keys: {sorted(keys)}")


def validate_meeting(meeting: dict) -> dict:
    """Validate shared time/date fields, including user-created busy periods.

    Campus, component and kind are required separately for catalog meetings.
    """
    require(isinstance(meeting, dict), "Meeting must be an object")
    days = meeting.get("days")
    require(isinstance(days, list) and days and all(type(day) is int and 0 <= day <= 6 for day in days),
            "Meeting days must be weekday integers 0..6")
    require(len(days) == len(set(days)), "Meeting contains duplicate weekdays")
    start, end = meeting.get("start"), meeting.get("end")
    require(type(start) is int and type(end) is int and 0 <= start < end <= 1440,
            "Meeting times must be increasing minutes in 0..1440")
    try:
        start_date = date.fromisoformat(meeting["start_date"])
        end_date = date.fromisoformat(meeting["end_date"])
    except (KeyError, ValueError, TypeError) as exc:
        raise CatalogError("Meeting needs valid ISO start/end dates") from exc
    require(start_date <= end_date, "Meeting end date precedes start date")
    # A short date range must contain at least one of the declared weekdays.
    duration = (end_date - start_date).days
    require(duration >= 6 or any((start_date.weekday() + delta) % 7 in days for delta in range(duration + 1)),
            "Meeting dates contain no declared weekday")
    return meeting


def validate_catalog(data: dict) -> dict:
    """Validate safety-relevant structure, return the same JSON-compatible value.

    Metadata fields may be added without changing this schema. Prerequisite
    operators are allowlisted so an unknown rule never becomes automatic consent.
    """
    require(isinstance(data, dict), "Catalog must be an object")
    require(isinstance(data.get("term"), str) and re.fullmatch(r"\d{4}-(spring|summer|fall)", data["term"]),
            "Catalog term must be YYYY-season")
    require(data.get("timezone") == "America/Vancouver", "Catalog timezone must be America/Vancouver")
    source = data.get("source")
    require(isinstance(source, dict), "Catalog source provenance is required")
    text(source.get("name"), "Source name")
    text(source.get("base_url"), "Source URL")
    text(source.get("fetched_at"), "Source fetch time")
    try:
        require(datetime.fromisoformat(source["fetched_at"]).tzinfo is not None,
                "Source fetch time must include timezone")
    except ValueError as exc:
        raise CatalogError("Source fetch time must be ISO-8601") from exc
    courses = data.get("courses")
    require(isinstance(courses, list) and courses, "Catalog must contain courses")
    ids = set()
    for item in courses:
        require(isinstance(item, dict), "Course must be an object")
        code = item.get("id")
        course_id(code, "Course ID")
        require(code not in ids, f"Duplicate course ID: {code}")
        ids.add(code)
        text(item.get("title"), f"{code} title")
        units = item.get("units")
        require(type(units) in (int, float) and 0 < units <= 30, f"{code} has invalid units")
        expression(item.get("prerequisite"))
        require(isinstance(item.get("prerequisite_text"), str), f"{code} needs original prerequisite text")
        unique_strings(item.get("prerequisite_review", []), f"{code} prerequisite review")
        exclusions = item.get("credit_exclusions", [])
        unique_strings(exclusions, f"{code} credit exclusions")
        for exclusion in exclusions:
            course_id(exclusion, "Credit exclusion")
        ranges = item.get("credit_exclusion_ranges", [])
        require(isinstance(ranges, list), "Credit exclusion ranges must be a list")
        for excluded_range in ranges:
            require(isinstance(excluded_range, dict) and set(excluded_range) == {"subject", "min_number", "max_number"},
                    "Malformed credit exclusion range")
            require(isinstance(excluded_range["subject"], str) and re.fullmatch(r"[A-Z]{2,6}", excluded_range["subject"]),
                    "Malformed credit exclusion subject")
            require(type(excluded_range["min_number"]) is int and type(excluded_range["max_number"]) is int
                    and 100 <= excluded_range["min_number"] <= excluded_range["max_number"] <= 999,
                    "Malformed credit exclusion numeric range")
        sections = item.get("sections")
        require(isinstance(sections, list) and sections, f"{code} has no enrollment bundles")
        section_ids = set()
        for section in sections:
            require(isinstance(section, dict), "Section must be an object")
            section_id = section.get("id")
            text(section_id, "Section ID")
            require(section_id not in section_ids, f"Duplicate section ID in {code}: {section_id}")
            section_ids.add(section_id)
            unique_strings(section.get("source_urls"), "Section source URLs", allow_empty=False)
            components = section.get("components")
            require(isinstance(components, list) and components, f"{code}/{section_id} needs components")
            component_ids = []
            for component in components:
                require(isinstance(component, dict), "Component must be an object")
                text(component.get("id"), "Component ID")
                text(component.get("associated_class"), "Component linkage")
                require(component.get("kind") in {"LEC", "LAB", "TUT", "SEM"}, "Unsupported component kind")
                component_ids.append(component["id"])
            require(len(component_ids) == len(set(component_ids)), "Duplicate component in enrollment bundle")
            require(section_id == "+".join(component_ids), "Bundle ID must identify all components")
            require(components[0]["kind"] in {"LEC", "SEM"}, "Bundle must begin with lecture or seminar")
            lecture_group = components[0]["associated_class"]
            for component in components[1:]:
                require(component["kind"] in {"LAB", "TUT"}, "Secondary component must be lab or tutorial")
                require(component["associated_class"] in {lecture_group, "9999"}, "Component is linked to another lecture")
            meetings = section.get("meetings")
            require(isinstance(meetings, list) and meetings, f"{code}/{section_id} has no scheduled meetings")
            seen_meetings = set()
            scheduled_components = set()
            for meeting in meetings:
                validate_meeting(meeting)
                require(isinstance(meeting, dict), "Meeting must be an object")
                days = meeting.get("days")
                require(isinstance(days, list) and days and all(type(day) is int and 0 <= day <= 6 for day in days),
                        "Meeting days must be weekday integers 0..6")
                require(len(days) == len(set(days)), "Meeting contains duplicate weekdays")
                start, end = meeting.get("start"), meeting.get("end")
                require(type(start) is int and type(end) is int and 0 <= start < end <= 1440,
                        "Meeting times must be increasing minutes in 0..1440")
                try:
                    start_date, end_date = date.fromisoformat(meeting["start_date"]), date.fromisoformat(meeting["end_date"])
                except (KeyError, ValueError, TypeError) as exc:
                    raise CatalogError("Meeting needs valid ISO start/end dates") from exc
                require(start_date <= end_date, "Meeting end date precedes start date")
                require(start_date.year == int(data["term"][:4]) and end_date.year == start_date.year,
                        "Meeting dates do not match catalog year")
                text(meeting.get("campus"), "Meeting campus")
                require(meeting.get("kind") in {"LEC", "LAB", "TUT", "SEM", "EXAM"}, "Unsupported meeting kind")
                require(meeting.get("component") in component_ids, "Meeting references an unknown component")
                scheduled_components.add(meeting["component"])
                signature = json.dumps(meeting, sort_keys=True)
                require(signature not in seen_meetings, "Duplicate meeting in enrollment bundle")
                seen_meetings.add(signature)
            require(set(component_ids) == scheduled_components, "A required component has no meetings")
    return data


def load_catalog(path: str | Path | None = None) -> dict:
    """Load and validate a snapshot; loading never accesses the network."""
    target = Path(path) if path is not None else DEFAULT_CATALOG
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CatalogError(f"Cannot read catalog {target}: {exc}") from exc
    return validate_catalog(data)
