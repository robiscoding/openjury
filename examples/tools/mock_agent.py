"""Minimal OpenAI-compatible mock agent for local OpenJury examples.

Returns deterministic chat completion JSON so you can run basic_usage/,
batch_eval/, and other examples without deploying a real agent.

Usage:
    python mock_agent.py --port 8080

Then in another terminal:
    export AGENT_API_KEY=demo
    python ../basic_usage/basic_jury_run.py
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

DEFAULT_RESPONSE = (
    "To reset your password, go to Settings → Security → Reset Password. "
    "You'll receive a confirmation email within a few minutes. "
    "If you don't see it, check your spam folder or contact support."
)


class MockAgentHandler(BaseHTTPRequestHandler):
    response_text: str = DEFAULT_RESPONSE

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        if length:
            self.rfile.read(length)

        payload: dict[str, Any] = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": self.response_text,
                    }
                }
            ]
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[mock-agent] {self.address_string()} {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenJury mock agent server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--response",
        default=DEFAULT_RESPONSE,
        help="Text returned in choices[0].message.content",
    )
    args = parser.parse_args()

    MockAgentHandler.response_text = args.response
    server = HTTPServer((args.host, args.port), MockAgentHandler)
    url = f"http://{args.host}:{args.port}/v1/chat/completions"
    print(f"Mock agent listening on {url}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
