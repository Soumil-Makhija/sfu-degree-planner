#!/usr/bin/env python3
"""Exercise browser-controller behavior against freshly generated Python results.

Requires Node.js. This uses the deliberately small DOM fixture in test_ui.cjs;
it is not a browser, layout test, or assistive-technology test.
"""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sfu_planner.audit import audit  # noqa: E402
from sfu_planner.catalog import load_catalog  # noqa: E402
from sfu_planner.cli import example, plan_request  # noqa: E402
from sfu_planner.prerequisites import graph  # noqa: E402


def main():
    node = shutil.which("node")
    if not node:
        print("UI checks require Node.js on PATH.", file=sys.stderr)
        return 1
    catalog = load_catalog()
    request = example()
    fixtures = {
        "/api/catalog": catalog,
        "/api/graph": graph(catalog),
        "/api/example": request,
        "/api/plan": plan_request(catalog, request),
        "/api/audit": audit(request["transcript"]),
        "unsatisfiable_plan": plan_request(catalog, {
            "courses": ["CMPT 125"], "transcript": [],
        }),
    }
    with tempfile.TemporaryDirectory(prefix="sfu-ui-check-") as folder:
        fixture = Path(folder) / "api-results.json"
        fixture.write_text(json.dumps(fixtures, allow_nan=False), encoding="utf-8")
        result = subprocess.run(
            [node, str(ROOT / "scripts/test_ui.cjs"), str(fixture)],
            cwd=ROOT,
            check=False,
        )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
