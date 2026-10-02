#!/usr/bin/env python3
"""Serve the last complete build; rebuild source edits without watching outputs."""
from __future__ import annotations
import argparse
import hashlib
import http.server
import json
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORT = 8765


def source_fingerprint(root: Path) -> str:
    """Only authoring inputs trigger builds; build/dist outputs never do."""
    files = set(root.glob('*.py')) | set(root.glob('*.yaml'))
    files.add(root / 'podglad_szablon.html')
    for directory in ('modules', 'config', 'src', 'scripts', 'geodesy'):
        folder = root / directory
        if folder.exists():
            files.update(path for path in folder.rglob('*')
                         if path.is_file() and path.suffix in ('.py', '.yaml', '.yml'))
    digest = hashlib.sha256()
    for path in sorted(files):
        if path.is_file():
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


class BuildCoordinator:
    def __init__(self, root=ROOT, scope='interior', runner=None, clock=time.monotonic):
        self.root, self.scope = Path(root), scope
        self.runner = runner or subprocess.run
        self.clock = clock
        self.signature = source_fingerprint(self.root)
        self.pending_signature = self.signature
        self.pending_since = self.clock()
        self.version = (self.root / 'build/current/index.html').stat().st_mtime_ns if (self.root / 'build/current/index.html').exists() else 0
        self.building = False
        self.error = None
        self.lock = threading.Lock()

    def poll(self):
        signature = source_fingerprint(self.root)
        with self.lock:
            if signature != self.pending_signature:
                self.pending_signature, self.pending_since = signature, self.clock()
            if not self.building and signature != self.signature and self.clock() - self.pending_since >= .6:
                # Record even a failed attempt: unchanged invalid YAML must not loop.
                self.signature, self.building, self.error = signature, True, None
                threading.Thread(target=self._build, daemon=True).start()
            return {'version': self.version, 'building': self.building, 'error': self.error}

    def _build(self):
        try:
            result = self.runner([sys.executable, str(self.root / 'scripts/build.py'), '--scope', self.scope],
                                 cwd=self.root, capture_output=True, text=True)
            with self.lock:
                if result.returncode:
                    self.error = (result.stderr or result.stdout or 'Przebudowa nie powiodła się.')[-4000:]
                else:
                    self.version = max(self.version + 1, time.time_ns())
        except Exception as exc:
            with self.lock:
                self.error = str(exc)
        finally:
            with self.lock:
                self.building = False


def handler_for(coordinator):
    class LiveHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(coordinator.root / 'build/current'), **kwargs)

        def do_GET(self):
            if self.path.rstrip('/') == '/api/version':
                data = json.dumps(coordinator.poll()).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            super().do_GET()

        def log_message(self, format, *args):
            if args and 'api/version' in str(args[0]):
                return
            super().log_message(format, *args)
    return LiveHandler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', choices=('interior', 'full'), default='interior')
    parser.add_argument('--port', type=int, default=PORT)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    # Always start from a fresh successful build, then serve its atomic output.
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/build.py'), '--scope', args.scope], cwd=ROOT)
    if result.returncode:
        raise SystemExit(result.returncode)
    coordinator = BuildCoordinator(scope=args.scope)
    server = http.server.ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(coordinator))
    url = f'http://127.0.0.1:{server.server_port}/'
    print(f'Podgląd: {url} · YAML/Python → przebudowa → odświeżenie', flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
