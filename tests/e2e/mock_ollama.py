"""
Minimal HTTP server faking the Ollama OpenAI-compatible API.

Endpoint: POST /v1/chat/completions
Returns a valid OpenAI chat completion response with fixed coaching text.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

MOCK_COMMENTARY = (
    "Great effort today! Power was consistent throughout the warmup. "
    "Heart rate stayed in Z2 — ideal for aerobic development. "
    "Keep up the prehab work to stay injury-free."
)


def _make_response(content: str) -> dict:
    return {
        "id": "chatcmpl-mock-001",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "llama3.2",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 512,
            "completion_tokens": 64,
            "total_tokens": 576,
        },
    }


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        body = json.dumps(_make_response(MOCK_COMMENTARY)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_mock_ollama_server(host: str = "127.0.0.1", port: int = 0) -> tuple[HTTPServer, str]:
    """Start mock server on a random port. Returns (server, base_url)."""
    server = HTTPServer((host, port), _Handler)
    actual_port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://{host}:{actual_port}"
