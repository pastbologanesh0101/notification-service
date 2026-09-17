# Notification Service

A small, self-contained multi-channel notification dispatch service built
with Flask and SQLite. It renders Jinja2 templates, dispatches them through
one of three channels (mock email, real webhook, in-app/log), retries
failed dispatches with exponential backoff, and exposes an API to query a
recipient's notification history.

This is a portfolio/demo project: the email channel is a **mock** (it never
contacts a real email provider or requires an API key). The webhook channel
performs **real** HTTP POST requests, so it can be pointed at any HTTP
endpoint, including a local test server.

## Architecture

```
app/
  __init__.py     -> create_app() application factory
  db.py           -> sqlite3 connection + schema setup
  templating.py   -> Jinja2 rendering of templates/*.txt, with clear
                     errors for unknown templates / missing variables
  channels.py     -> send_email_mock, send_webhook, send_in_app
  retry.py        -> compute_backoff (pure) + dispatch_with_retry
                     (injectable sleep_fn, no real waiting in tests)
  routes.py       -> HTTP API: POST /notifications, GET /notifications/<recipient>
templates/
  welcome.txt
  password_reset.txt
  order_shipped.txt
tests/
  test_templating.py  -> template rendering + error cases
  test_retry.py       -> pure backoff math + retry loop behavior
  test_api.py         -> full Flask test-client integration tests
```

### Data model

A single `notifications` table (SQLite) records every dispatch attempt:

| column         | meaning                                      |
|-----------------|-----------------------------------------------|
| recipient       | who the notification is for                  |
| channel         | `email` \| `webhook` \| `in_app`              |
| template_name   | which template was rendered                   |
| rendered_body   | the fully rendered notification text          |
| status          | `sent` or `failed`                            |
| attempts        | how many dispatch attempts were made          |
| error           | last error message, if any                    |
| created_at / updated_at | ISO-8601 timestamps                  |

The app factory (`create_app(testing=True)`) opens a single sqlite3
connection per app instance (a temp/in-memory DB in tests, or
`notifications.db` otherwise). Because SQLite's `:memory:` database is
private to the connection that opened it, the service intentionally reuses
one connection for the app's lifetime rather than opening a new one per
request — this keeps the in-memory test database consistent across
requests within a test.

## Channels

- **email (mock)** — `send_email_mock()` never makes a network call. It just
  returns (and the API records) what "would have been sent": recipient,
  subject/template name, and rendered body. Always succeeds.
- **webhook** — `send_webhook(url, payload)` performs a real
  `requests.post(url, json=payload)`. A non-2xx response or a network error
  (e.g. connection refused) raises `WebhookError`, which triggers the retry
  logic. Pass `webhook_url` in the request body, or configure
  `WEBHOOK_DEFAULT_URL` via `create_app(webhook_default_url=...)`.
- **in_app** — `send_in_app()` represents the in-app/log channel. The
  notification is already persisted in the `notifications` table by the
  time it "dispatches", so this call always succeeds; the notification is
  later retrievable via the history endpoint.

## Templating

Templates live in `templates/*.txt` and use standard Jinja2 syntax
(`{{ variable }}`). Three are bundled: `welcome`, `password_reset`, and
`order_shipped`. `render_notification(template_name, template_vars)`:

- Raises `UnknownTemplateError` (surfaced as HTTP 400) if the template file
  doesn't exist, listing the available templates.
- Raises `TemplateRenderError` (also HTTP 400) if a variable the template
  references was not supplied (Jinja2's `StrictUndefined` mode).

## Retry logic

`app/retry.py` splits the concern in two:

- `compute_backoff(attempt, base_delay=1.0, factor=2.0, max_delay=30.0)` is
  a pure function: `delay = base_delay * factor ** (attempt - 1)`, capped
  at `max_delay`. No side effects, fully unit-testable.
- `dispatch_with_retry(send_fn, max_retries=3, sleep_fn=time.sleep, ...)`
  calls `send_fn()`, and on exception, sleeps (via the injectable
  `sleep_fn`) for the computed backoff before retrying, up to
  `max_retries` total attempts. After the last failed attempt it returns
  `status="failed"` with the last error message — no further retries.

Because `sleep_fn` is injectable, tests replace it with a function that
just records the delay values instead of blocking, so the retry/backoff
tests run instantly while still asserting the exact schedule
(e.g. `[1.0, 2.0, 4.0]` for a 4-attempt run with `factor=2.0`).

## API

### `POST /notifications`

```json
{
  "recipient": "ada@example.com",
  "channel": "webhook",
  "template_name": "password_reset",
  "template_vars": {
    "user_name": "Ada",
    "product_name": "Acme",
    "reset_link": "https://acme.example.com/reset/abc123",
    "expires_in_minutes": 15
  },
  "webhook_url": "https://example.com/hooks/notify"
}
```

Returns the stored notification record (`201` if it ended up `sent`, `502`
if it ended up `failed` after retries), including `status`, `attempts`,
`error`, and `rendered_body`.

### `GET /notifications/<recipient>`

Returns a JSON array of that recipient's notification history, newest
first.

## Running it

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py           # starts on http://127.0.0.1:5000
```

Example:

```bash
curl -X POST http://127.0.0.1:5000/notifications \
  -H "Content-Type: application/json" \
  -d '{
        "recipient": "ada@example.com",
        "channel": "email",
        "template_name": "welcome",
        "template_vars": {
          "user_name": "Ada",
          "product_name": "Acme",
          "email": "ada@example.com"
        }
      }'

curl http://127.0.0.1:5000/notifications/ada@example.com
```

## Running the tests

```bash
pip install -r requirements.txt pytest
pytest -v
```

Tests cover: template variable substitution, unknown-template rejection,
mock email recording a sent notification, webhook dispatch succeeding
against a local in-process test HTTP server, webhook failure retrying with
the correct exponential backoff schedule and ultimately being marked
`failed` after the max retry count (with an injected no-op clock, so no
test actually sleeps), and notification-history queries returning the
correct records per recipient.

CI runs the same test suite on Python 3.11 and 3.12 via
`.github/workflows/tests.yml` on every push and pull request.

## License

MIT — see [LICENSE](LICENSE).
