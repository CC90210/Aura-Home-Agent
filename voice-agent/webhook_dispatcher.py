"""
AURA Webhook Dispatcher
========================
Lightweight HTTP server that receives webhook POSTs from Home Assistant
automations and dispatches them to the appropriate AURA feature module.

Runs as a background thread inside the main aura_voice.py process.
Listens on port 5123 (configurable) for incoming POST requests.

HA automations fire webhooks to HA's rest_command.aura_webhook, which
POSTs to this dispatcher at http://localhost:5123/<webhook_id>.

Registered handlers are keyed by the webhook ID string (path segment).
Each handler receives a ``dict`` parsed from the JSON request body.
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable

log = logging.getLogger("aura.webhook")

DEFAULT_PORT = 5123
DEFAULT_HOST = "0.0.0.0"  # Bind to all interfaces so health checks work over LAN


class WebhookHandler(BaseHTTPRequestHandler):
    """Handles incoming webhook POST requests from HA."""

    # Populated by WebhookDispatcher before starting the server.
    # Class-level so all handler instances share the same route table.
    _routes: dict[str, Callable[[dict], None]] = {}

    def do_GET(self) -> None:
        """Handle GET requests — used for health checks."""
        path = self.path.strip("/")
        if path == "health":
            try:
                from health import health_response
                body = health_response()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))
            except Exception as exc:  # noqa: BLE001
                log.error("Health endpoint error: %s", exc)
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status": "error", "detail": "health check failed"}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b"{}"

        try:
            payload: dict = json.loads(body) if body else {}
        except json.JSONDecodeError:
            log.warning("Received malformed JSON body from %s", self.client_address)
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "invalid JSON"}')
            return

        # Strip leading slash to get the webhook ID.
        webhook_id = self.path.strip("/")

        if webhook_id in self._routes:
            log.info("Webhook received: %s", webhook_id)
            try:
                self._routes[webhook_id](payload)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok": true}')
            except Exception as exc:  # noqa: BLE001
                log.error("Webhook handler error for %s: %s", webhook_id, exc, exc_info=True)
                self.send_response(500)
                self.end_headers()
        else:
            log.warning("Unknown webhook: %s", webhook_id)
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        # Route all HTTP server log output through our logger rather than stderr.
        log.debug("HTTP: %s", format % args)


class WebhookDispatcher:
    """
    Manages webhook route registrations and runs an HTTP server in a
    background daemon thread.

    Usage::

        dispatcher = WebhookDispatcher(port=5123)
        dispatcher.register("aura_pulse_check", handle_pulse_check)
        dispatcher.register("aura_ghost_dj", handle_ghost_dj)
        dispatcher.start()   # non-blocking — server runs in background thread

    Parameters
    ----------
    port:
        TCP port to listen on.  Default: 5123.
    """

    def __init__(self, port: int = DEFAULT_PORT, host: str = DEFAULT_HOST) -> None:
        self._port = port
        self._host = host
        self._routes: dict[str, Callable[[dict], None]] = {}
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def register(self, webhook_id: str, handler: Callable[[dict], None]) -> None:
        """Register ``handler`` to be called when ``webhook_id`` is POSTed."""
        self._routes[webhook_id] = handler
        log.info("Registered webhook handler: %s", webhook_id)

    def start(self) -> None:
        """Start the HTTP server in a background daemon thread (non-blocking)."""
        # Push the populated route table into the handler class before binding.
        WebhookHandler._routes = self._routes  # noqa: SLF001 — intentional class-level mutation
        self._server = HTTPServer((self._host, self._port), WebhookHandler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="aura-webhook-dispatcher",
        )
        self._thread.start()
        log.info(
            "Webhook dispatcher listening on %s:%d (%d routes registered)",
            self._host,
            self._port,
            len(self._routes),
        )

    def stop(self) -> None:
        """Shut down the HTTP server gracefully."""
        if self._server:
            self._server.shutdown()
            log.info("Webhook dispatcher stopped.")
