#!/usr/bin/env python3
"""Run a lightweight local HTTP server for the Puzzle Viewer web application.

Usage:
    python scripts/puzzle_server.py
"""
import http.server
import os
from pathlib import Path
import socketserver
import subprocess
import sys

PUZZLE_DIR = Path('/sdcard/Download/Dom_Lazienka_R07_Puzzle')
PORT = 8080

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUZZLE_DIR), **kwargs)

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Cache-Control', 'no-cache, must-revalidate')
        super().end_headers()

def main():
    if not PUZZLE_DIR.exists():
        print(f"Błąd: Katalog {PUZZLE_DIR} nie istnieje!", file=sys.stderr)
        sys.exit(1)

    os.chdir(str(PUZZLE_DIR))
    with ThreadedTCPServer(("", PORT), Handler) as httpd:
        url = f"http://localhost:{PORT}"
        print(f"\n=======================================================")
        print(f"🚀 KREATOR PUZZLI ŁAZIENKI DZIAŁA!")
        print(f"👉 Otwórz w przeglądarce: {url}")
        print(f"   (Wszystkie 84 płytki, podgląd na żywo, eksport PNG)")
        print(f"=======================================================\n")
        print("Naciśnij Ctrl+C, aby zatrzymać serwer.\n")

        try:
            subprocess.run(['termux-open-url', url], capture_output=True)
        except Exception:
            pass

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nZatrzymano serwer.")

if __name__ == '__main__':
    main()
