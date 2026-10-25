# SFU Fall 2026 factual snapshot

`catalog.json` contains ten courses and 52 complete enrollment bundles acquired
from the [official SFU Course Outlines API](https://www.sfu.ca/outlines/help/api.html).
`manifest.json` records every requested URL, UTC acquisition time, original
response SHA-256, retained fixture SHA-256, and the projection applied.
`sources/` contains the actual API fields needed to reproduce this dataset.
Long course descriptions, policies, teaching materials and staff contact details
are deliberately omitted. Original response hashes identify what was fetched;
fixture hashes verify the retained factual projection. Original full responses
are not distributed, so their hashes cannot be rechecked from this repository.

The curated courses are CMPT 120, 125, 225, 276, 295; MACM 101, 201; and
MATH 151, 152, 232. Course records link to the Fall 2026 calendar as well as the
underlying section API URLs. This is not live enrollment or seat availability.

## Enrollment and meeting interpretation

The API's `associatedClass` links secondary LAB/TUT sections to lectures.
Each planner section includes the lecture plus one compatible component of
every required kind in that listing. A MACM 101 section therefore always
includes its tutorial; CMPT 125/225/295 always include their labs.

The OPL entries for MACM 201 and MATH 151/152/232 are retained as
`optional_components`. They are not part of the mandatory bundle.
SFU describes its [Math Workshops and Open Labs](https://www.sfu.ca/math/undergraduate/current-students/workshops.html)
as drop-in support, including these courses. The API exposes those OPL entries
under a separate association (`200`), rather than an enrollment lecture group.

Meetings retain local calendar dates, weekday sets, campus and start/end minutes.
Final exams appear as `EXAM` meetings with one calendar date. When the API lists
multiple identical room allocations for an exam, normalization keeps one
time/campus meeting. MATH 232 D100 has two consecutive lecture date ranges;
both are preserved. Holidays, closures and Canvas schedule exceptions are not
modeled. API campus fields do not supply building-level travel information.

## Prerequisite review and refresh

`scripts/fetch_sfu.py` contains human reviewed boolean expressions for this
small snapshot. `reviewed_rules.json` records the exact prerequisite/restriction
text against which those expressions were reviewed. A refresh fails if the
official text changes, so it cannot quietly reuse a stale expression.
Source text remains visible in each normalized course.

Known letter-grade and course rules are machine evaluated. High school
equivalencies, the CMPT 276 writing-course prerequisite, and the Applied Physics
alternative for CMPT 295 are explicit manual conditions. Completing an unrelated
OR branch never grants those conditions. Credit exclusions include the CMPT 125
restriction for previously completed CMPT courses numbered 200 or higher.
Where SFU specifies no minimum letter grade, a completed passing course is
represented by minimum `D`; no C- threshold is invented.

Run from the repository root:

```sh
python scripts/fetch_sfu.py             # retrieve current official facts
python scripts/fetch_sfu.py --offline   # verify fixture hashes and rebuild
python -m unittest discover -s tests -p test_catalog.py -v
```

The online refresh accesses only the official public SFU API. Offline rebuild
never accesses the network and must reproduce `catalog.json` exactly. A future
term or expanded course list requires explicit rule and source review; this
script does not claim to parse arbitrary prerequisite prose.
