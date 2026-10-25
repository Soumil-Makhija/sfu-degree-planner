# SFU degree planner

An independent local planner using an official **Fall 2026** SFU course-outline
snapshot. The planning core selects complete lecture/lab/tutorial bundles with
Z3, respects dated weekly meetings and final exams, checks explicit graded
prerequisites, and explains impossible requests. No SFU affiliation or approval.

## Core example

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python - <<'PY'
from sfu_planner.catalog import load_catalog
from sfu_planner.solver import solve
completed = [{'course': code, 'grade': 'A'}
             for code in ['CMPT 120', 'MATH 151', 'MACM 101']]
result = solve(load_catalog(), ['CMPT 125', 'MATH 152', 'MACM 201'], completed)
print(result['status'])
print([(s['course'], s['id']) for s in result['schedules'][0]['sections']])
PY
.venv/bin/python -m unittest discover -s tests -v
```

The snapshot covers ten courses and 52 section bundles; it does not imply seats
are available or that offerings repeat in other terms. Required secondary
components and exams are included. Optional workshops are recorded separately.
Manual predicates fail closed unless their exact condition is explicitly
confirmed. Academic decisions, transfer credits and substitutions need human
review. A feasible timetable is not authorization to register.

Source: [SFU course-outline API](https://www.sfu.ca/outlines/help/api.html).
Factual source projections and hashes live in `data/sources/` and
`data/manifest.json`. Rebuild the normalized catalog offline with
`python scripts/fetch_sfu.py --offline`; refresh explicitly by omitting `--offline`.

## Local CLI and interface

```sh
.venv/bin/sfu-plan demo
.venv/bin/sfu-plan --output plan.json plan --request request.json
.venv/bin/sfu-plan audit --transcript transcript.json
.venv/bin/sfu-plan graph
.venv/bin/sfu-plan serve --port 8765
```

Open `http://127.0.0.1:8765` for the browser interface. Transcripts stay in
browser/server memory: no persistence, telemetry or transcript logs. Planning
uses the bundled snapshot without network access. Close the server with Ctrl-C.

A request example (grades are synthetic):

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

The example has four complete schedules. CLI exit codes: 0 for completed
commands, 2 for impossible or unknown planning results, 1 for invalid input.
The audit's `incomplete`/`manual_review` statuses are reported in JSON; no audit
certifies graduation. See [the academic model](docs/academic-model.md) for
covered rules, transfer treatment and official-review requirements.

Schedules require one bundle for every requested course. Semester units,
busy periods and inter-campus travel time are enforced. `confirmations` contains
exact manual-condition strings; those assumptions appear in results and do not
constitute institutional verification. This planner does not plan retakes.
