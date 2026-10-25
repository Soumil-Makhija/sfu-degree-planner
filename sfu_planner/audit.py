"""Explain a bounded Fall 2026 SFU CS BSc audit; never certify graduation."""

from __future__ import annotations

import itertools
import json
import math
import re
from importlib.resources import files
from pathlib import Path


GRADES = {"A+": 4.33, "A": 4, "A-": 3.67, "B+": 3.33, "B": 3,
          "B-": 2.67, "C+": 2.33, "C": 2, "C-": 1.67,
          "D": 1, "F": 0, "N": 0}
NON_CREDIT = {"F", "FD", "N", "W", "WE", "WD", "AU", "IP", "DE", "GN"}


def load_requirements(path=None):
    """Load a reviewed rules snapshot, or a caller-provided JSON file."""
    if path is not None:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    source = Path(__file__).resolve().parent.parent / "data" / "requirements.json"
    if source.is_file():
        return json.loads(source.read_text(encoding="utf-8"))
    return json.loads(files("sfu_planner").joinpath("data/requirements.json").read_text())


def _course(value):
    if not isinstance(value, str):
        raise ValueError("Each transcript course must be a course identifier string")
    match = re.fullmatch(r"\s*([A-Za-z]+)[ -]*(\d{3}[A-Za-z]?)\s*", value)
    if not match:
        raise ValueError(f"Invalid course identifier: {value!r}; expected e.g. CMPT 120")
    return f"{match[1].upper()} {match[2].upper()}"


def _units(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Units must be a finite nonnegative number")
    if not math.isfinite(value) or value < 0 or value > 30:
        raise ValueError("Units must be finite and between 0 and 30")
    return value


def _records(transcript, rules):
    if isinstance(transcript, dict):
        transcript = transcript.get("courses", transcript.get("transcript"))
    if not isinstance(transcript, list):
        raise ValueError("Transcript must be a list of course records or {'courses': [...]}")
    if len(transcript) > 500:
        raise ValueError("Transcript is limited to 500 course attempts")
    chosen, ignored, issues = {}, [], []
    for index, item in enumerate(transcript):
        if not isinstance(item, dict):
            raise ValueError(f"Transcript record {index + 1} must be an object")
        cid = _course(item.get("course", item.get("id")))
        if "grade" in item and not isinstance(item["grade"], str):
            raise ValueError(f"{cid}: grade must be a string")
        if "institution" in item and not isinstance(item["institution"], str):
            raise ValueError(f"{cid}: institution must be a string")
        if "transfer" in item and not isinstance(item["transfer"], bool):
            raise ValueError(f"{cid}: transfer must be a JSON boolean")
        if "designations" in item and (not isinstance(item["designations"], list)
                or any(not isinstance(d, str) for d in item["designations"])):
            raise ValueError(f"{cid}: designations must be a list of strings")
        grade = item.get("grade", "").strip().upper()
        supplied = _units(item["units"]) if "units" in item else 0
        if grade in NON_CREDIT or grade == "":
            ignored.append({"course": cid, "reason": "No completed credit-bearing grade", "grade": grade})
            continue
        if grade not in GRADES:
            issues.append(f"{cid}: grade {grade!r} needs official credit interpretation; excluded")
            ignored.append({"course": cid, "reason": "Unmodeled grade", "grade": grade})
            continue
        if GRADES[grade] <= 0:
            continue
        metadata = rules["course_metadata"].get(cid)
        known = metadata is not None
        units = _units(metadata["units"]) if known else supplied
        if known and "units" in item and units != supplied:
            issues.append(f"{cid}: supplied {supplied} units differ from calendar {units}; calendar units used")
        if not known:
            issues.append(f"{cid}: absent from reviewed course metadata; {units} supplied units are provisional")
        designations = set(metadata.get("designations", [])) if known else set()
        if item.get("designations") and set(item["designations"]) != designations:
            issues.append(f"{cid}: supplied designations are not used; reviewed calendar designations govern")
        institution = str(item.get("institution", "")).strip().upper()
        transfer = bool(item.get("transfer", False)) or (institution not in {"", "SFU", "SIMON FRASER UNIVERSITY"})
        if transfer:
            issues.append(f"{cid}: transfer credit and WQB articulation require review")
            # A course-equivalent identifier is not evidence of a W transfer designation.
            designations = set()
        record = {"course": cid, "grade": grade, "units": units, "known": known,
                  "level": int(cid.split()[1][:3]), "designations": designations,
                  "at_sfu": institution in {"SFU", "SIMON FRASER UNIVERSITY"} and not transfer,
                  "transfer": transfer}
        previous = chosen.get(cid)
        # Higher grade represents a repeat; never add units across attempts.
        if previous is None or GRADES[grade] > GRADES[previous["grade"]]:
            if previous:
                ignored.append({"course": cid, "reason": "Repeated course; counted once"})
            chosen[cid] = record
        else:
            ignored.append({"course": cid, "reason": "Repeated course; counted once"})
    for group in rules.get("duplicate_credit_groups", []):
        found = [chosen[c] for c in group if c in chosen]
        if len(found) > 1:
            # Prefer the highest grade, then largest official units, then identifier.
            keep = sorted(found, key=lambda r: (-GRADES[r["grade"]], -r["units"], r["course"]))[0]
            for record in found:
                if record is keep:
                    continue
                del chosen[record["course"]]
                ignored.append({"course": record["course"], "reason": f"Duplicate-credit alternative to {keep['course']}"})
            issues.append("Duplicate-credit alternatives supplied: " + ", ".join(r["course"] for r in found))
    return chosen, ignored, sorted(set(issues))


def _breadth_matching(records, areas, required_course):
    """Maximum distinct course/area matching, reserving CMPT 307's area."""
    assignment = {}
    if required_course in records:
        area = next((a for a, courses in areas.items() if required_course in courses), None)
        if area:
            assignment[area] = required_course
    reserved = set(assignment)

    def add(cid, seen):
        for area, courses in areas.items():
            if area in seen or area in reserved or cid not in courses:
                continue
            seen.add(area)
            previous = assignment.get(area)
            if previous is None or add(previous, seen):
                assignment[area] = cid
                return True
        return False

    for cid in sorted(records):
        if cid != required_course:
            add(cid, set())
    return assignment


def _breadth_pairs(records):
    """Allocate each course to at most one B bucket; return best valid coverage.

    Reviewed snapshot courses are all at least three units, so valid breadth
    allocations need exactly two courses per bucket. Smaller-unit metadata must
    be reviewed rather than silently treated as a complete allocation.
    """
    candidates = {k: [] for k in ("B-Hum", "B-Soc", "B-Sci", "additional")}
    for cid, record in records.items():
        if (cid.startswith("CMPT ") or not record["known"] or record["transfer"]
                or GRADES[record["grade"]] < GRADES["C-"] or record["units"] < 3):
            continue
        for bucket in candidates:
            if bucket == "additional" or bucket in record["designations"]:
                candidates[bucket].append(cid)
    # Designated buckets first; additional breadth gets separate leftover courses.
    order = sorted(candidates, key=lambda k: (k == "additional", len(candidates[k]), k))
    best = {}

    def search(index, used, result):
        nonlocal best
        if len(result) > len(best):
            best = dict(result)
        if len(best) == 4 or index == len(order) or len(result) + len(order) - index <= len(best):
            return
        bucket = order[index]
        available = [c for c in candidates[bucket] if c not in used]
        for pair in itertools.combinations(available, 2):
            result[bucket] = list(pair)
            search(index + 1, used | set(pair), result)
            del result[bucket]
            if len(best) == 4:
                return
        search(index + 1, used, result)

    search(0, set(), {})
    return best, candidates


def audit(transcript, requirements=None):
    """Return explainable satisfied/missing/manual_review checks.

    Supplied transcript grades describe completion, not institutional verification.
    Unknown course units are shown provisionally and cannot satisfy verified totals.
    A fully modeled match still returns manual_review because official GPA,
    residency, transfer, cohort applicability and approval are outside this model.
    """
    rules = requirements if requirements is not None else load_requirements()
    records, ignored, issues = _records(transcript, rules)
    checks = []

    def check(id_, label, status, **details):
        checks.append({"id": id_, "label": label, "status": status, **details})

    for prefix, key in (("lower", "lower_required"), ("upper", "upper_required"), ("bsc", "bsc_required")):
        for cid in rules[key]:
            check(f"{prefix}_{cid.lower().replace(' ', '_')}", cid,
                  "satisfied" if cid in records else "missing", courses=[cid] if cid in records else [],
                  missing=[] if cid in records else [cid])
    for alternative in rules["alternatives"]:
        found = sorted(set(alternative["courses"]) & records.keys())
        permission = sorted(set(alternative.get("permission_alternatives", [])) & records.keys())
        eligible = [c for c in permission if GRADES[records[c]["grade"]] >= GRADES[alternative.get("permission_min_grade", "B+")]]
        status = "satisfied" if found else "manual_review" if eligible else "missing"
        check(alternative["id"], alternative["label"], status, courses=found or eligible,
              alternatives=alternative["courses"], permission_alternatives=alternative.get("permission_alternatives", []),
              note="Permission alternatives require B+ or better and school permission; never automatically approved.")

    def unit_check(id_, label, predicate, target):
        relevant = [r for r in records.values() if predicate(r)]
        verified = sum(r["units"] for r in relevant if r["known"])
        provisional = sum(r["units"] for r in relevant)
        status = "satisfied" if verified >= target else "manual_review" if provisional >= target else "missing"
        check(id_, label, status, earned_units=verified, provisional_units=provisional,
              required_units=target, remaining_units=max(0, target - verified),
              courses=sorted(r["course"] for r in relevant))

    unit_check("total_units", "Total degree units", lambda r: True, rules["minimum_units"])
    upper = lambda r: 300 <= r["level"] < 500
    upper_cmpt = lambda r: upper(r) and r["course"].startswith("CMPT ")
    unit_check("upper_units", "Upper division units", upper, rules["minimum_upper_units"])
    unit_check("upper_cmpt_units", "Upper division CMPT units", upper_cmpt, rules["minimum_upper_cmpt_units"])
    unit_check("depth_units", "400-level CMPT depth units", lambda r: upper_cmpt(r) and r["level"] >= 400 and r["course"] not in rules["depth_excluded"], rules["minimum_depth_units"])
    excluded = sorted(set(records) & set(rules["depth_excluded"]))
    if excluded:
        check("depth_permission", "Excluded depth courses need special permission", "manual_review",
              courses=excluded, note="Excluded from depth units; this tool does not approve permission.")

    matching = _breadth_matching(records, rules["concentrations"], rules["breadth_required_course"])
    breadth_ok = len(matching) >= rules["breadth_areas_required"] and rules["breadth_required_course"] in records
    check("cs_breadth", "Four distinct courses across four Table I areas, including CMPT 307",
          "satisfied" if breadth_ok else "missing", earned_areas=len(matching),
          required_areas=rules["breadth_areas_required"], assignments=matching,
          missing_required_course=[] if rules["breadth_required_course"] in records else [rules["breadth_required_course"]])

    allowed = set(rules["table_ii"] + rules["table_iii"])
    for courses in rules["concentrations"].values():
        allowed.update(courses)
    # MACM 316 has its own mandatory BSc slot, so cannot occupy an extra slot too.
    extra_candidates = sorted((allowed & records.keys()) - set(rules["bsc_required"]))
    cmpt_units = sum(r["units"] for r in records.values() if r["known"] and upper_cmpt(r))
    extras = next((list(pair) for pair in itertools.combinations(extra_candidates, 2)
                   if cmpt_units - sum(records[c]["units"] for c in pair if upper_cmpt(records[c])) >= rules["minimum_upper_cmpt_units"]), [])
    check("bsc_extra_courses", "Two Table I/II/III courses beyond the 30 CMPT units and MACM 316",
          "satisfied" if extras else "missing", courses=extras, candidates=extra_candidates,
          note="Separate courses are reserved for the two extra slots; 30 CMPT units must remain.")

    wqb_records = {c: r for c, r in records.items() if r["known"] and not r["transfer"] and GRADES[r["grade"]] >= GRADES["C-"]}
    writing = [c for c, r in wqb_records.items() if "W" in r["designations"] and r["units"] >= 3]
    lower_w = [c for c in writing if records[c]["level"] < 300]
    upper_w = [c for c in writing if upper_cmpt(records[c])]
    at_sfu = [c for c in upper_w if records[c]["at_sfu"]]
    w_status = "satisfied" if lower_w and at_sfu else "manual_review" if upper_w and len(writing) >= 2 else "missing"
    check("wqb_writing", "Writing: lower W plus upper CMPT W at SFU, each at least 3 units", w_status,
          courses=sorted(writing), lower_courses=lower_w, upper_sfu_courses=at_sfu,
          note="Transfer W designations and exceptions require review; specify institution='SFU' for upper W residency.")
    quantitative = [c for c, r in wqb_records.items() if "Q" in r["designations"]]
    q_units = sum(records[c]["units"] for c in quantitative)
    check("wqb_quantitative", "Quantitative: two courses totaling at least 6 units",
          "satisfied" if len(quantitative) >= 2 and q_units >= 6 else "missing",
          courses=sorted(quantitative), earned_units=q_units, required_units=6, required_courses=2)
    allocation, candidates = _breadth_pairs(wqb_records)
    for bucket in ("B-Hum", "B-Soc", "B-Sci", "additional"):
        selected = allocation.get(bucket, [])
        check(f"wqb_{bucket.lower().replace('-', '_')}", f"Breadth {bucket}: two separate courses outside CMPT, at least 6 units",
              "satisfied" if selected else "missing", courses=selected,
              candidates=sorted(candidates[bucket]), earned_units=sum(records[c]["units"] for c in selected),
              required_units=6, required_courses=2,
              note="Each course can occupy only one breadth bucket; allocation maximizes completed buckets.")

    if issues:
        check("transcript_review", "Transcript assumptions and metadata need review", "manual_review", issues=issues)
    for index, label in enumerate(rules["manual_review"]):
        check(f"official_review_{index + 1}", label, "manual_review")
    missing = [c["id"] for c in checks if c["status"] == "missing"]
    manual = [c["id"] for c in checks if c["status"] == "manual_review"]
    return {"academic_year": rules["academic_year"], "program": rules["program"],
            "status": "incomplete" if missing else "manual_review", "graduation_certified": False,
            "checks": checks, "missing_checks": missing, "manual_review_checks": manual,
            "counted_courses": sorted(records), "ignored_attempts": ignored, "issues": issues,
            "sources": rules["sources"], "requirements_reviewed_on": rules["reviewed_on"],
            "disclaimer": "Unofficial planning audit using supplied completion records. SFU determines credit, applicability and graduation; modeled matches do not certify graduation."}
