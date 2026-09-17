import datetime
import time

from flask import Blueprint, current_app, jsonify, request

from .channels import send_email_mock, send_in_app, send_webhook
from .db import row_to_dict
from .retry import dispatch_with_retry
from .templating import TemplateRenderError, UnknownTemplateError, render_notification

bp = Blueprint("notifications", __name__)

VALID_CHANNELS = {"email", "webhook", "in_app"}


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@bp.route("/notifications", methods=["POST"])
def create_notification():
    data = request.get_json(silent=True) or {}
    recipient = data.get("recipient")
    channel = data.get("channel")
    template_name = data.get("template_name")
    template_vars = data.get("template_vars") or {}
    webhook_url = data.get("webhook_url")

    if not recipient or not channel or not template_name:
        return (
            jsonify({"error": "recipient, channel, and template_name are required"}),
            400,
        )

    if channel not in VALID_CHANNELS:
        return (
            jsonify(
                {
                    "error": f"Unknown channel: '{channel}'. Valid channels: "
                    f"{', '.join(sorted(VALID_CHANNELS))}"
                }
            ),
            400,
        )

    try:
        body = render_notification(template_name, template_vars)
    except UnknownTemplateError as exc:
        return jsonify({"error": str(exc)}), 400
    except TemplateRenderError as exc:
        return jsonify({"error": str(exc)}), 400

    conn = current_app.db_conn
    timestamp = _now()
    cursor = conn.execute(
        "INSERT INTO notifications "
        "(recipient, channel, template_name, rendered_body, status, attempts, error, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (recipient, channel, template_name, body, "pending", 0, None, timestamp, timestamp),
    )
    conn.commit()
    notification_id = cursor.lastrowid

    max_retries = current_app.config.get("MAX_RETRIES", 3)
    sleep_fn = current_app.config.get("SLEEP_FN", time.sleep)

    if channel == "email":
        result = dispatch_with_retry(
            lambda: send_email_mock(recipient, template_name, body),
            max_retries=1,
            sleep_fn=sleep_fn,
        )
    elif channel == "in_app":
        result = dispatch_with_retry(
            lambda: send_in_app(recipient, body),
            max_retries=1,
            sleep_fn=sleep_fn,
        )
    else:  # webhook
        target = webhook_url or current_app.config.get("WEBHOOK_DEFAULT_URL")
        if not target:
            result = {
                "status": "failed",
                "attempts": 0,
                "delays": [],
                "error": "No webhook_url provided and no WEBHOOK_DEFAULT_URL configured",
            }
        else:
            payload = {
                "recipient": recipient,
                "template_name": template_name,
                "body": body,
                "notification_id": notification_id,
            }
            result = dispatch_with_retry(
                lambda: send_webhook(target, payload),
                max_retries=max_retries,
                sleep_fn=sleep_fn,
            )

    conn.execute(
        "UPDATE notifications SET status=?, attempts=?, error=?, updated_at=? WHERE id=?",
        (result["status"], result["attempts"], result["error"], _now(), notification_id),
    )
    conn.commit()

    record = row_to_dict(
        conn.execute("SELECT * FROM notifications WHERE id=?", (notification_id,)).fetchone()
    )
    status_code = 201 if result["status"] == "sent" else 502
    return jsonify(record), status_code


@bp.route("/notifications/<recipient>", methods=["GET"])
def get_history(recipient):
    conn = current_app.db_conn
    rows = conn.execute(
        "SELECT * FROM notifications WHERE recipient=? ORDER BY created_at DESC, id DESC",
        (recipient,),
    ).fetchall()
    return jsonify([row_to_dict(r) for r in rows])
