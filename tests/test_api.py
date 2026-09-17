import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app import create_app


class _RecordingOKHandler(BaseHTTPRequestHandler):
    """A minimal local HTTP server that accepts POSTs and returns 200."""

    received = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            self.__class__.received.append(json.loads(raw))
        except ValueError:
            self.__class__.received.append(raw)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, format, *args):  # silence default request logging
        pass


@pytest.fixture
def local_webhook_server():
    _RecordingOKHandler.received = []
    server = HTTPServer(("127.0.0.1", 0), _RecordingOKHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    try:
        yield f"http://127.0.0.1:{port}/webhook", _RecordingOKHandler.received
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def client():
    app = create_app(testing=True, sleep_fn=lambda delay: None)
    with app.test_client() as test_client:
        yield test_client


def test_email_channel_records_sent_notification_without_calling_real_provider(client):
    resp = client.post(
        "/notifications",
        json={
            "recipient": "ada@example.com",
            "channel": "email",
            "template_name": "welcome",
            "template_vars": {
                "user_name": "Ada",
                "product_name": "TransportLab",
                "email": "ada@example.com",
            },
        },
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["status"] == "sent"
    assert data["channel"] == "email"
    assert "Ada" in data["rendered_body"]


def test_in_app_channel_is_stored_and_retrievable(client):
    resp = client.post(
        "/notifications",
        json={
            "recipient": "grace@example.com",
            "channel": "in_app",
            "template_name": "order_shipped",
            "template_vars": {
                "user_name": "Grace",
                "order_id": "ORD-1",
                "carrier": "FastShip",
                "tracking_url": "https://track.example.com/ORD-1",
                "eta": "2026-09-20",
                "product_name": "Acme",
            },
        },
    )
    assert resp.status_code == 201
    assert resp.get_json()["status"] == "sent"


def test_webhook_dispatch_succeeds_against_local_test_server(client, local_webhook_server):
    webhook_url, received = local_webhook_server

    resp = client.post(
        "/notifications",
        json={
            "recipient": "ops@example.com",
            "channel": "webhook",
            "template_name": "password_reset",
            "template_vars": {
                "user_name": "Ops",
                "product_name": "Acme",
                "reset_link": "https://acme.example.com/reset/abc",
                "expires_in_minutes": 15,
            },
            "webhook_url": webhook_url,
        },
    )

    assert resp.status_code == 201
    data = resp.get_json()
    assert data["status"] == "sent"
    assert data["attempts"] == 1
    assert len(received) == 1
    assert received[0]["recipient"] == "ops@example.com"


def test_webhook_dispatch_failure_retries_then_marks_failed(client):
    sleeps_recorded = []
    app = create_app(
        testing=True,
        sleep_fn=sleeps_recorded.append,
        max_retries=3,
    )
    with app.test_client() as retrying_client:
        resp = retrying_client.post(
            "/notifications",
            json={
                "recipient": "unreachable@example.com",
                "channel": "webhook",
                "template_name": "welcome",
                "template_vars": {
                    "user_name": "Nobody",
                    "product_name": "Acme",
                    "email": "unreachable@example.com",
                },
                # Nothing listens on this port - the connection is refused quickly.
                "webhook_url": "http://127.0.0.1:1/webhook",
            },
        )

    assert resp.status_code == 502
    data = resp.get_json()
    assert data["status"] == "failed"
    assert data["attempts"] == 3
    assert data["error"] is not None
    # Exponential backoff: 2 sleeps between 3 attempts, no real waiting occurred.
    assert sleeps_recorded == [1.0, 2.0]


def test_notification_history_returns_only_matching_recipient(client):
    client.post(
        "/notifications",
        json={
            "recipient": "alice@example.com",
            "channel": "in_app",
            "template_name": "welcome",
            "template_vars": {
                "user_name": "Alice",
                "product_name": "Acme",
                "email": "alice@example.com",
            },
        },
    )
    client.post(
        "/notifications",
        json={
            "recipient": "bob@example.com",
            "channel": "in_app",
            "template_name": "welcome",
            "template_vars": {
                "user_name": "Bob",
                "product_name": "Acme",
                "email": "bob@example.com",
            },
        },
    )
    client.post(
        "/notifications",
        json={
            "recipient": "alice@example.com",
            "channel": "in_app",
            "template_name": "order_shipped",
            "template_vars": {
                "user_name": "Alice",
                "order_id": "ORD-9",
                "carrier": "FastShip",
                "tracking_url": "https://track.example.com/ORD-9",
                "eta": "2026-09-21",
                "product_name": "Acme",
            },
        },
    )

    resp = client.get("/notifications/alice@example.com")
    assert resp.status_code == 200
    records = resp.get_json()
    assert len(records) == 2
    assert {r["template_name"] for r in records} == {"welcome", "order_shipped"}
    assert all(r["recipient"] == "alice@example.com" for r in records)


def test_notification_history_empty_for_unknown_recipient(client):
    resp = client.get("/notifications/nobody@example.com")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_unknown_template_name_is_rejected_with_clear_error(client):
    resp = client.post(
        "/notifications",
        json={
            "recipient": "ada@example.com",
            "channel": "email",
            "template_name": "not_a_real_template",
            "template_vars": {},
        },
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data
    assert "not_a_real_template" in data["error"]


def test_unknown_channel_is_rejected(client):
    resp = client.post(
        "/notifications",
        json={
            "recipient": "ada@example.com",
            "channel": "carrier_pigeon",
            "template_name": "welcome",
            "template_vars": {},
        },
    )
    assert resp.status_code == 400
    assert "carrier_pigeon" in resp.get_json()["error"]


def test_missing_required_fields_rejected(client):
    resp = client.post("/notifications", json={"channel": "email"})
    assert resp.status_code == 400
    assert "error" in resp.get_json()
