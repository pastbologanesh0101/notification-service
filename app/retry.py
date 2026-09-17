"""Pure exponential-backoff math plus a retry-dispatch loop.

``compute_backoff`` has no side effects at all, so it can be unit tested
directly. ``dispatch_with_retry`` accepts an injectable ``sleep_fn`` so
tests never have to wait on a real clock.
"""

import time


def compute_backoff(attempt, base_delay=1.0, factor=2.0, max_delay=30.0):
    """Return the delay (seconds) to wait before retrying ``attempt``.

    ``attempt`` is 1-indexed (the attempt number that just failed).
    Delay grows as ``base_delay * factor ** (attempt - 1)``, capped at
    ``max_delay``.
    """
    if attempt < 1:
        raise ValueError("attempt must be >= 1")
    delay = base_delay * (factor ** (attempt - 1))
    return min(delay, max_delay)


def dispatch_with_retry(
    send_fn,
    max_retries=3,
    base_delay=1.0,
    factor=2.0,
    max_delay=30.0,
    sleep_fn=time.sleep,
):
    """Call ``send_fn()`` (no args), retrying on exception.

    Retries up to ``max_retries`` total attempts, sleeping (via
    ``sleep_fn``) for an exponentially increasing delay between attempts.
    Returns a dict: ``{"status": "sent"|"failed", "attempts": int,
    "delays": [floats used between attempts], "error": str|None}``.
    """
    delays_used = []
    attempts = 0
    last_error = None

    for attempt in range(1, max_retries + 1):
        attempts = attempt
        try:
            send_fn()
            return {
                "status": "sent",
                "attempts": attempts,
                "delays": delays_used,
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001 - we want to catch any sender failure
            last_error = str(exc)
            if attempt < max_retries:
                delay = compute_backoff(attempt, base_delay, factor, max_delay)
                delays_used.append(delay)
                sleep_fn(delay)

    return {
        "status": "failed",
        "attempts": attempts,
        "delays": delays_used,
        "error": last_error,
    }
