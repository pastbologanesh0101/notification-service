"""Channel senders.

- ``send_email_mock`` never contacts a real email provider. It just
  returns a record of what "would have been sent" — suitable for a
  portfolio demo with no API keys.
- ``send_webhook`` performs a real HTTP POST to a caller-supplied URL,
  so it can be pointed at a local test server in tests, or a real
  webhook endpoint in normal use.
- ``send_in_app`` represents the in-app/log channel: the notification is
  already persisted to the ``notifications`` table by the caller, so this
  function simply acknowledges that.
"""

import requests


class WebhookError(Exception):
    """Raised when a webhook POST fails (network error or non-2xx status)."""


def send_email_mock(recipient, subject, body):
    return {
        "provider": "mock-email",
        "recipient": recipient,
        "subject": subject,
        "body": body,
    }


def send_in_app(recipient, body):
    return {
        "provider": "in-app",
        "recipient": recipient,
        "body": body,
    }


def send_webhook(url, payload, timeout=5):
    try:
        response = requests.post(url, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise WebhookError(f"webhook request failed: {exc}") from exc

    if response.status_code >= 300:
        raise WebhookError(f"webhook returned status {response.status_code}")

    return response
