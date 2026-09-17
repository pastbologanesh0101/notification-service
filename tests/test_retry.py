import pytest

from app.retry import compute_backoff, dispatch_with_retry


def test_compute_backoff_schedule_is_exponential():
    assert compute_backoff(1, base_delay=1.0, factor=2.0) == 1.0
    assert compute_backoff(2, base_delay=1.0, factor=2.0) == 2.0
    assert compute_backoff(3, base_delay=1.0, factor=2.0) == 4.0
    assert compute_backoff(4, base_delay=1.0, factor=2.0) == 8.0


def test_compute_backoff_is_capped_at_max_delay():
    assert compute_backoff(10, base_delay=1.0, factor=2.0, max_delay=5.0) == 5.0


def test_compute_backoff_rejects_non_positive_attempt():
    with pytest.raises(ValueError):
        compute_backoff(0)


def test_dispatch_with_retry_succeeds_on_first_try_with_no_delay():
    calls = []
    sleeps = []

    def send_fn():
        calls.append(1)

    result = dispatch_with_retry(send_fn, max_retries=3, sleep_fn=sleeps.append)

    assert result["status"] == "sent"
    assert result["attempts"] == 1
    assert sleeps == []  # no retries needed, so no sleeping at all


def test_dispatch_with_retry_uses_exponential_backoff_between_attempts():
    attempts_made = {"count": 0}
    sleeps = []

    def always_fails():
        attempts_made["count"] += 1
        raise RuntimeError("boom")

    result = dispatch_with_retry(
        always_fails,
        max_retries=4,
        base_delay=1.0,
        factor=2.0,
        sleep_fn=sleeps.append,
    )

    assert result["status"] == "failed"
    assert result["attempts"] == 4
    # 4 attempts means 3 sleeps in between, following 1, 2, 4 backoff.
    assert sleeps == [1.0, 2.0, 4.0]
    assert "boom" in result["error"]


def test_dispatch_with_retry_marks_failed_after_max_retries_with_no_real_sleep():
    sleeps = []

    def always_fails():
        raise RuntimeError("target unreachable")

    result = dispatch_with_retry(
        always_fails,
        max_retries=3,
        sleep_fn=sleeps.append,  # records instead of actually sleeping
    )

    assert result["status"] == "failed"
    assert result["attempts"] == 3
    assert len(sleeps) == 2  # sleeps happen between attempts, not after the last one


def test_dispatch_with_retry_succeeds_after_transient_failures():
    attempts_made = {"count": 0}
    sleeps = []

    def fails_twice_then_succeeds():
        attempts_made["count"] += 1
        if attempts_made["count"] < 3:
            raise RuntimeError("transient error")

    result = dispatch_with_retry(fails_twice_then_succeeds, max_retries=5, sleep_fn=sleeps.append)

    assert result["status"] == "sent"
    assert result["attempts"] == 3
    assert sleeps == [1.0, 2.0]
