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

CLI, browser interface and full audit integration are the next milestone.
