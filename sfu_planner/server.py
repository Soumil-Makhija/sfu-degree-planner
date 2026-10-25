"""Single-process loopback-only API; transcripts are neither logged nor stored."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib.resources import files
import json
from urllib.parse import urlsplit

from .audit import audit
from .cli import example, plan_request
from .prerequisites import graph

MAX_BODY = 1024 * 1024


def handler_for(catalog):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # No URLs, request bodies, transcripts or other access logs.

        def reply(self, status, body, content_type='application/json; charset=utf-8'):
            payload = json.dumps(body, allow_nan=False).encode() if isinstance(body, (dict, list)) else body
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(payload)

        def local_request(self):
            allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            host = self.headers.get('Host')
            origin = self.headers.get('Origin')
            if host not in allowed or (origin is not None and origin != f'http://{host}'):
                self.reply(403, {'error': 'Only same-origin loopback requests are accepted'})
                return False
            return True

        def do_GET(self):
            if not self.local_request():
                return
            path = urlsplit(self.path).path
            if path == '/api/catalog':
                self.reply(200, catalog)
            elif path == '/api/graph':
                self.reply(200, graph(catalog))
            elif path == '/api/example':
                self.reply(200, example())
            elif path in ('/', '/app.js', '/style.css'):
                filename = 'index.html' if path == '/' else path[1:]
                content_type = {'index.html': 'text/html; charset=utf-8', 'app.js': 'text/javascript; charset=utf-8', 'style.css': 'text/css; charset=utf-8'}[filename]
                self.reply(200, files('sfu_planner').joinpath('static', filename).read_bytes(), content_type)
            else:
                self.reply(404, {'error': 'Unknown endpoint'})

        def do_POST(self):
            if not self.local_request():
                return
            if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                self.reply(415, {'error': 'Content-Type must be application/json'})
                return
            try:
                length = int(self.headers.get('Content-Length', '-1'))
                if not 0 <= length <= MAX_BODY:
                    self.reply(413, {'error': 'Body must be at most 1 MiB and have Content-Length'})
                    return
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict):
                    raise ValueError('Request must be a JSON object')
                path = urlsplit(self.path).path
                if path == '/api/plan':
                    result = plan_request(catalog, request)
                elif path == '/api/audit':
                    if set(request) != {'transcript'}:
                        raise ValueError('Audit request must contain only transcript')
                    result = audit(request['transcript'])
                else:
                    self.reply(404, {'error': 'Unknown endpoint'})
                    return
                self.reply(200, result)
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
    return Handler


def make_server(catalog, port=8765):
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError('port must be in [0, 65535] (0 chooses a free port)')
    # Serial requests avoid sharing Z3's default context across worker threads.
    return HTTPServer(('127.0.0.1', port), handler_for(catalog))


def serve(catalog, port=8765):
    with make_server(catalog, port) as server:
        print(f'SFU planner: http://127.0.0.1:{server.server_port} (Ctrl-C to stop)', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
