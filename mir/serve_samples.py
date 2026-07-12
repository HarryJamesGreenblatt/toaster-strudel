#!/usr/bin/env python
"""serve_samples.py — CORS-enabled static server for local Strudel samples.

The `sample` reproduction mode uses REAL isolated audio (chopped by sampleize.py).
strudel.cc (an https origin) fetches these over CORS, so a plain `http.server`
gets blocked ("No 'Access-Control-Allow-Origin' header"). This server adds the
header so strudel.cc can load them.

COPYRIGHT: only ever serves LOCAL, gitignored, copyright-derived loops. Do not
expose this beyond localhost.

Usage:
    python serve_samples.py [--dir mir/samples] [--port 8123]
Then in Strudel:
    samples({ name: 'http://localhost:8123/name.wav' })
"""
from __future__ import annotations

import argparse
import os
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler


class CORSRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self):  # preflight
        self.send_response(204)
        self.end_headers()


def main() -> int:
    ap = argparse.ArgumentParser(description="CORS static server for local Strudel samples.")
    ap.add_argument("--dir", default="mir/samples")
    ap.add_argument("--port", type=int, default=8123)
    args = ap.parse_args()

    os.makedirs(args.dir, exist_ok=True)
    handler = partial(CORSRequestHandler, directory=os.path.abspath(args.dir))
    httpd = HTTPServer(("", args.port), handler)
    print(f"serving {args.dir} on http://localhost:{args.port}/ (CORS enabled)")
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
