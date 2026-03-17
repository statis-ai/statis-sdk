#!/usr/bin/env python3
"""Minimal webhook receiver for Statis delivery demos.

Accepts POST requests, prints JSON payloads to stdout. Optionally returns
500 for the first N requests (for retry/DLQ testing).

Usage:
    python examples/webhook_receiver.py [--port 9999] [--fail-first 2]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional


class WebhookHandler(BaseHTTPRequestHandler):
    fail_first: int = 0
    request_count: int = 0

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b""
        WebhookHandler.request_count += 1
        n = WebhookHandler.request_count
        ts = datetime.now(timezone.utc).isoformat()

        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
            print(f"[{ts}] POST #{n} -> {json.dumps(payload, indent=2)}", flush=True)
        except Exception as e:
            print(f"[{ts}] POST #{n} -> (invalid JSON) {body!r}", flush=True)
            print(f"  error: {e}", flush=True)

        if WebhookHandler.fail_first > 0 and n <= WebhookHandler.fail_first:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"simulated failure"}\n')
            print(f"  -> 500 (fail-first {n}/{WebhookHandler.fail_first})", flush=True)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"received":true}\n')

    def log_message(self, format: str, *args: object) -> None:
        # Suppress default request logging; we print in do_POST
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Statis webhook receiver (demo)")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=9999)
    parser.add_argument(
        "--fail-first",
        type=int,
        default=0,
        metavar="N",
        help="Return 500 for the first N requests, then 200 (for retry demo)",
    )
    args = parser.parse_args()

    WebhookHandler.fail_first = args.fail_first
    WebhookHandler.request_count = 0

    server = HTTPServer((args.host, args.port), WebhookHandler)
    print(f"Webhook receiver on http://{args.host}:{args.port}/ (POST)")
    if args.fail_first:
        print(f"  --fail-first {args.fail_first}: first {args.fail_first} request(s) -> 500")
    print("Ctrl+C to stop.\n", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
