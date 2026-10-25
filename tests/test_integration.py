import contextlib
import http.client
import io
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

from sfu_planner.catalog import load_catalog
from sfu_planner.cli import example, plan_request
from sfu_planner.server import make_server
from sfu_planner.solver import meetings_conflict


class Integration(unittest.TestCase):
    def test_real_demo_has_complete_nonconflicting_bundles_and_exams(self):
        catalog = load_catalog()
        result = plan_request(catalog, example())
        self.assertEqual(result['status'], 'satisfiable')
        self.assertEqual(len(result['schedules']), 4)
        self.assertTrue(result['exhausted'])
        for schedule in result['schedules']:
            self.assertEqual({s['course'] for s in schedule['sections']}, set(example()['courses']))
            meetings = [m for s in schedule['sections'] for m in s['meetings']]
            self.assertTrue(any(m['kind'] == 'EXAM' for m in meetings))
            for a, b in itertools.combinations(meetings, 2):
                self.assertFalse(meetings_conflict(a, b, 60))
        missing = {**example(), 'transcript': []}
        self.assertEqual(plan_request(catalog, missing)['status'], 'unsatisfiable')
        with self.assertRaises(ValueError):
            plan_request(catalog, {**example(), 'typo': True})

    def test_cli_runs_separate_process_and_returns_actionable_exit_codes(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'result.json'
            def run(*args):
                return subprocess.run([sys.executable, '-m', 'sfu_planner', *args], text=True, capture_output=True)
            demo = run('--output', str(output), 'demo')
            self.assertEqual(demo.returncode, 0, demo.stderr)
            self.assertEqual(json.loads(output.read_text())['plan']['status'], 'satisfiable')
            request = Path(temporary) / 'request.json'
            request.write_text(json.dumps({**example(), 'max_units': 3}))
            impossible = run('plan', '--request', str(request))
            self.assertEqual(impossible.returncode, 2, impossible.stderr)
            self.assertEqual(json.loads(impossible.stdout)['status'], 'unsatisfiable')
            request.write_text('{bad json')
            invalid = run('plan', '--request', str(request))
            self.assertEqual(invalid.returncode, 1)
            self.assertIn('error:', invalid.stderr)
            self.assertNotIn('Traceback', invalid.stderr)


class LocalAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(load_catalog(), 0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        data = json.dumps(body) if body is not None else None
        connection.request(method, path, data, headers or {'Content-Type': 'application/json'})
        response = connection.getresponse()
        result = response.read()
        connection.close()
        return response.status, response.headers, result

    def test_api_plan_audit_graph_and_example(self):
        code, headers, payload = self.request('GET', '/api/catalog')
        self.assertEqual(code, 200)
        self.assertEqual(len(json.loads(payload)['courses']), 10)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        code, _, payload = self.request('POST', '/api/plan', example())
        self.assertEqual(code, 200)
        self.assertEqual(len(json.loads(payload)['schedules']), 4)
        code, _, payload = self.request('POST', '/api/audit', {'transcript': example()['transcript']})
        self.assertEqual(code, 200)
        self.assertFalse(json.loads(payload)['graduation_certified'])
        code, _, payload = self.request('GET', '/api/graph')
        self.assertEqual(code, 200)
        self.assertGreater(len(json.loads(payload)['edges']), 10)
        self.assertEqual(json.loads(self.request('GET', '/api/example')[2]), example())

    def test_static_app_assets_are_served_with_matching_references(self):
        code, headers, html = self.request('GET', '/')
        self.assertEqual(code, 200)
        self.assertIn(b'href="/style.css"', html)
        self.assertIn(b'src="/app.js"', html)
        self.assertIn('frame-ancestors', headers['Content-Security-Policy'])
        for asset in ('/app.js', '/style.css'):
            code, headers, payload = self.request('GET', asset)
            self.assertEqual(code, 200)
            self.assertGreater(len(payload), 100)
        self.assertNotIn(b'https://', html)

    def test_malformed_and_cross_origin_requests_are_rejected(self):
        for bad in ({}, {'courses': [{}]}, {'courses': ['CMPT 120'], 'transcript': [{'course': 'CMPT 120', 'grade': []}]}):
            self.assertEqual(self.request('POST', '/api/plan', bad)[0], 400)
        self.assertEqual(self.request('POST', '/api/audit', {'transcript': [{'course': 'CMPT 120', 'designations': [{}]}]})[0], 400)
        self.assertEqual(self.request('POST', '/api/audit', {'typo': []})[0], 400)
        self.assertEqual(self.request('POST', '/api/plan', {}, {'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(self.request('POST', '/api/plan', {}, {'Content-Type': 'application/json', 'Origin': 'https://foreign.example'})[0], 403)
        self.assertEqual(self.request('GET', '/api/catalog', headers={'Host': 'foreign.example'})[0], 403)
        self.assertEqual(self.request('GET', '/not-found')[0], 404)
        self.assertEqual(self.request('GET', '/../../README.md')[0], 404)
