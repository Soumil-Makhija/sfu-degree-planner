# SFU degree planner

Plan a real SFU term and inspect degree progress locally. This independent tool
combines an official **Fall 2026** course-outline snapshot, an explicit graded
prerequisite graph, a Z3 section-selection solver, and a transparent
**Computing Science BSc** audit. No account or paid model access is required.

The snapshot contains **10 courses, 52 complete section bundles and 69 factual
API fixtures**. Degree rules use a separate reviewed calendar model with 94
course metadata entries. This is an unofficial planning aid; SFU determines
registration, awarded credit and graduation.

## Run it

Python 3.11+ is required. The test matrix covers Linux and macOS; Z3 is installed
from PyPI. Node 24 is only needed for the UI logic checks, not to run the app.

```sh
git clone https://github.com/Soumil-Makhija/sfu-degree-planner.git
cd sfu-degree-planner
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/sfu-plan serve --port 8765
```

Open **http://127.0.0.1:8765** and choose **Load example**. The synthetic transcript
has CMPT 120, MATH 151 and MACM 101 completed with A grades. The real Fall 2026
CMPT 125 + MACM 201 + MATH 152 request produces **four** feasible schedules.
Inspect the linked lab, dated meetings, final exams and source links. Switch to
Degree audit to see outstanding requirements, or Prerequisites to follow the
graph's AND/OR paths. Edit course selections, transcript, busy meetings, travel
buffer and unit limit, then generate again.

The server listens only on loopback, accepts same-origin browser requests, logs
no transcript/access contents, and does not persist your records. Planning and
auditing use packaged local data. Setup and explicit data refresh need network
access. Stop the server with Ctrl-C.

## CLI and shareable JSON

```sh
.venv/bin/sfu-plan demo
.venv/bin/sfu-plan --output plan.json plan --request examples/request.json
.venv/bin/sfu-plan --output audit.json audit --transcript examples/transcript.json
.venv/bin/sfu-plan --output graph.json graph
.venv/bin/sfu-plan catalog
```

`--output` and optional `--catalog PATH` precede the subcommand. All commands
emit structured JSON. CLI exits 0 for completed commands, 2 for impossible or
unknown planning results, 1 for invalid input. An audit's `incomplete` or
`manual_review` status appears in JSON and does not change the exit code.
Never share a report containing private records without reviewing its contents.

A plan request:

```json
{
  "courses": ["CMPT 125", "MATH 152", "MACM 201"],
  "transcript": [
    {"course": "CMPT 120", "grade": "A", "institution": "SFU"},
    {"course": "MATH 151", "grade": "A", "institution": "SFU"},
    {"course": "MACM 101", "grade": "A", "institution": "SFU"}
  ],
  "busy": [], "max_units": 18, "travel_minutes": 60, "limit": 5,
  "confirmations": []
}
```

Use canonical IDs and completed grades for planning. The audit also accepts a
`{"courses": [...]}` wrapper and normalizes identifiers. Unknown course units
remain provisional. Reviewed calendar units/designations override supplied
metadata; unknown designations are never guessed. P/CR grades cannot establish
a C- prerequisite, and require separate interpretation in the degree audit.

Busy meetings use local minutes after midnight and weekday numbers 0–6:

```json
{"days":[0],"start":720,"end":780,"start_date":"2026-09-09",
 "end_date":"2026-12-07","campus":"Burnaby","kind":"LEC"}
```

## What is enforced

- Exactly one complete enrollment bundle for every requested course, including
  a linked lab/tutorial of each required kind. Missing meeting data is rejected.
- Dated weekly time collisions and date-specific final-exam conflicts. Adjacent
  same-campus meetings are allowed; differing campuses require the supplied
  travel buffer, default 60 minutes. The buffer is a planning assumption.
- Explicit AND/OR prerequisites, minimum grades, credit exclusions, unit limits
  and busy periods. Manual conditions fail closed unless the exact condition
  string is supplied in `confirmations`. These user assumptions appear in output.
- Stable lexicographic schedule enumeration; infeasible requests return an
  unsatisfiable subset of constraints. That subset is explanatory, not promised
  minimal or canonical. Solver timeouts return `unknown`, never infeasibility.
- Fall 2026 CS BSc core and alternatives; 120 total / 45 upper / 30 upper-CMPT
  units; four distinct Table I breadth areas including CMPT 307; 12 depth units;
  BSc extra-course allocation; WQB grades and separate breadth allocations.

The audit always retains official-review checks. A `satisfied` item means the
supplied completion evidence matches that modeled rule. `manual_review` for the
whole audit means no modeled check is missing; **it never certifies graduation**.
See [the academic model](docs/academic-model.md) for precise rules and exceptions.

## Provenance and architecture

Official sources: [course-outline API](https://www.sfu.ca/outlines/help/api.html),
[Fall 2026 CS major](https://www.sfu.ca/students/calendar/2026/fall/programs/computing-science/major/bachelor-of-science-or-bachelor-of-arts.html),
and [Fall 2026 WQB](https://www.sfu.ca/students/calendar/2026/fall/fees-and-regulations/enrolment/WQB.html).
[Data notes](data/README.md) explain factual projections, response/projection
SHA-256 hashes, reviewed prerequisites and linked optional workshops.

`catalog.py` validates the local snapshot. `prerequisites.py` evaluates explicit
expressions and emits graph edges. `solver.py` encodes bundle choices/conflicts
in Z3 and enumerates stable solutions. `audit.py` assigns degree evidence without
reusing incompatible slots. `cli.py` shares that engine with the loopback API in
`server.py`. The HTML/CSS/JavaScript interface has no runtime frontend dependencies.

```sh
# No network: verify hashes, rule text and deterministic normalization.
python3 scripts/fetch_sfu.py --offline
# Explicit live refresh of the same ten-course Fall 2026 scope.
python3 scripts/fetch_sfu.py
# Review changes, then copy normalized data into wheel resources.
python3 scripts/sync_package_data.py
python3 scripts/sync_package_data.py --check
```

A changed prerequisite/restriction text stops refresh until its reviewed mapping
is updated. It is not automatically parsed into a registration decision. Refresh
is for maintainers; inspect the diff and all rules before publishing new data.

## Validation

```sh
.venv/bin/python -m pip install build
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q sfu_planner scripts
node --check sfu_planner/static/app.js
.venv/bin/python scripts/check_ui.py
.venv/bin/python -m build --wheel
.venv/bin/python -m pip install --no-deps --force-reinstall dist/*.whl
.venv/bin/python scripts/check_installed.py
```

The suite compares Z3 results with exhaustive enumeration for 64 small cases,
checks actual date boundaries and travel gaps, verifies official-source fixtures,
checks real-data schedules and exams, tests distinct requirement allocation,
and exercises CLI/HTTP errors. The UI check executes real app event handlers
against real Python-generated payloads in a **minimal DOM harness**. It verifies
logic, not browser layout or assistive technology. Installed-wheel smoke checks
run from a separate temporary directory. CI runs these checks on Python 3.11 and
3.14 on Linux and macOS. Visual browser QA was unavailable in the initial build
session; no browser-rendering pass is claimed.

## Limits

- Only the ten listed course offerings in Fall 2026 can be scheduled. No live
  seats, waitlists, registration, future-term forecasting or multi-term degree
  optimization. There is no automatic whole-catalog ingestion.
- First-degree, single-major CS BSc audit only; BA, honours, other programs and
  cohorts are unsupported. The 94-course metadata subset is not the full SFU
  calendar. Unknown credits cannot silently satisfy reviewed unit requirements.
- Official transcript authenticity, transfer equivalencies, substitutions,
  historical exclusions, special permissions, official GPAs, residency and
  calendar applicability remain human-review requirements.
- Passed-course retakes are excluded from planning; the audit counts repeated
  identifiers once. Co-requisites and arbitrary natural-language prerequisites
  are not inferred. Manual conditions remain explicit.
- Weekly ranges do not subtract holidays or instructor/Canvas exceptions;
  optional Math workshops are shown separately. Travel is a fixed same-day
  campus buffer, not a journey-time model; cross-midnight travel is unsupported.
- Results depend on supplied facts and the reviewed source snapshot. An
  internally consistent custom catalog is not proof of accurate academic data.
  Finite solver/audit tests do not establish institutional correctness.

Code is MIT licensed; third-party factual data retains its provenance. No SFU
affiliation, institutional approval, user-count or adoption claims are made.
