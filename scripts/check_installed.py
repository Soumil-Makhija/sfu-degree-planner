#!/usr/bin/env python3
"""Smoke-test the installed CLI, packaged data and HTTP UI outside the checkout."""
import http.client
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    binary = Path(sys.executable).with_name('sfu-plan')
    with tempfile.TemporaryDirectory(prefix='sfu-installed-') as directory:
        completed = subprocess.run([str(binary), 'demo'], cwd=directory, check=True, capture_output=True, text=True)
        result = json.loads(completed.stdout)
        assert result['plan']['status'] == 'satisfiable'
        assert len(result['plan']['schedules']) == 4
        assert not result['audit']['graduation_certified']
        # Separate interpreter plus unrelated cwd: no source package on sys.path.
        code = '''
import http.client,json,threading
from sfu_planner.catalog import load_catalog
from sfu_planner.server import make_server
with make_server(load_catalog(),0) as server:
 thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 try:
  for path in ('/','/app.js','/style.css','/api/catalog'):
   connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
   connection.request('GET',path); response=connection.getresponse()
   assert response.status==200,(path,response.status)
   assert response.read(); connection.close()
 finally:
  server.shutdown();thread.join()
print('Installed HTTP interface and packaged assets passed.')
'''
        check = subprocess.run([sys.executable, '-c', code], cwd=directory, check=True, capture_output=True, text=True)
        print(check.stdout.strip())
        print('Installed CLI: 4 real-data schedules; audit refuses graduation certification.')


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as exc:
        if exc.stderr:
            print(exc.stderr, file=sys.stderr)
        raise
