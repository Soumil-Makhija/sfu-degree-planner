"""Local CLI. Planning and auditing never call SFU or model APIs."""
import argparse
import json
from pathlib import Path
import sys

from .audit import audit
from .catalog import load_catalog
from .prerequisites import graph
from .solver import solve


def example():
    return {'transcript': [{'course': c, 'grade': 'A', 'institution': 'SFU'}
                           for c in ('CMPT 120', 'MATH 151', 'MACM 101')],
            'courses': ['CMPT 125', 'MATH 152', 'MACM 201'], 'busy': [],
            'max_units': 18, 'travel_minutes': 60, 'limit': 5, 'confirmations': []}


def plan_request(catalog, request):
    if not isinstance(request, dict):
        raise ValueError('request must be a JSON object')
    allowed = {'courses', 'transcript', 'busy', 'max_units', 'travel_minutes', 'limit', 'confirmations'}
    extra = set(request) - allowed
    if extra:
        raise ValueError('unknown request fields: ' + ', '.join(sorted(extra)))
    return solve(catalog, request.get('courses'), request.get('transcript', []),
                 **{k: v for k, v in request.items() if k not in ('courses', 'transcript')})


def read_json(filename):
    target = Path(filename)
    if target.stat().st_size > 1024 * 1024:
        raise ValueError('JSON file exceeds 1 MiB')
    return json.loads(target.read_text(encoding='utf-8'))


def main(argv=None):
    parser = argparse.ArgumentParser(description='Unofficial offline SFU Fall 2026 planner')
    parser.add_argument('--catalog', help='Reviewed catalog snapshot JSON (default: bundled Fall 2026)')
    parser.add_argument('--output', help='Write JSON to this path rather than stdout')
    subs = parser.add_subparsers(dest='command', required=True)
    subs.add_parser('catalog', help='Show source data and complete enrollment bundles')
    subs.add_parser('graph', help='Show prerequisite edges with AND/OR context')
    subs.add_parser('demo', help='Run the real-data offline plan and audit example')
    plan = subs.add_parser('plan', help='Find complete, conflict-free section selections')
    plan.add_argument('--request', required=True, help='JSON request containing courses and transcript')
    audit_parser = subs.add_parser('audit', help='Audit modeled Fall 2026 CS BSc requirements')
    audit_parser.add_argument('--transcript', required=True, help='JSON list or {courses: [...]}')
    serve_parser = subs.add_parser('serve', help='Run local browser UI at 127.0.0.1')
    serve_parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        catalog = load_catalog(args.catalog)
        if args.command == 'serve':
            from .server import serve
            serve(catalog, args.port)
            return 0
        if args.command == 'catalog':
            result = catalog
        elif args.command == 'graph':
            result = graph(catalog)
        elif args.command == 'audit':
            result = audit(read_json(args.transcript))
        elif args.command == 'plan':
            result = plan_request(catalog, read_json(args.request))
        else:
            request = example()
            result = {'example': request, 'plan': plan_request(catalog, request), 'audit': audit(request['transcript'])}
        encoded = json.dumps(result, indent=2, allow_nan=False) + '\n'
        if args.output:
            Path(args.output).write_text(encoded, encoding='utf-8')
        else:
            sys.stdout.write(encoded)
        status = result.get('status', result.get('plan', {}).get('status'))
        return 2 if status in ('unsatisfiable', 'unknown') else 0
    except (OSError, ValueError) as exc:
        parser.exit(1, f'error: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
