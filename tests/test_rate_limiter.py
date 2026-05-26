from itertools import count
from unittest.mock import patch
from src.pipeline.rate_limiter import RateLimiter, PrawRateMonitor


def test_rate_limiter_should_retry():
    limiter = RateLimiter(max_retries=3)
    assert limiter.should_retry(0) is True
    assert limiter.should_retry(1) is True
    assert limiter.should_retry(2) is True
    assert limiter.should_retry(3) is False


def test_rate_limiter_backoff_delay_calculation():
    limiter = RateLimiter(
        max_retries=3,
        backoff_base=2.0,
        max_backoff=60.0,
        jitter_range=(0.5, 1.5),
    )
    with patch("src.pipeline.rate_limiter.time.sleep") as mock_sleep:
        limiter.backoff(1)
        delay = mock_sleep.call_args[0][0]
        assert 1.5 < delay < 3.0

        limiter.backoff(2)
        delay = mock_sleep.call_args[0][0]
        assert 3.0 < delay < 6.0

        limiter.backoff(5)
        delay = mock_sleep.call_args[0][0]
        assert 25.0 < delay <= 60.0


def test_rate_limiter_wait_enforces_interval():
    limiter = RateLimiter(max_requests_per_minute=30, jitter_range=(1.0, 1.0))
    fake_time = count(0, 1)
    with patch("src.pipeline.rate_limiter.time.time", side_effect=lambda: next(fake_time)),          patch("src.pipeline.rate_limiter.time.sleep") as mock_sleep:
        limiter.wait()
        assert mock_sleep.call_count == 0
        limiter.wait()
        assert mock_sleep.call_count == 1


def test_praw_rate_monitor_record():
    monitor = PrawRateMonitor(target_rate=80)
    for i in range(5):
        monitor.record_request()
    assert monitor._request_count == 5


def test_praw_rate_monitor_ensure_pace_triggers_sleep():
    monitor = PrawRateMonitor(target_rate=80)
    monitor._request_count = 10
    monitor._start_time = 0.0
    with patch("src.pipeline.rate_limiter.time.time", return_value=1.0),          patch("src.pipeline.rate_limiter.time.sleep") as mock_sleep:
        monitor.ensure_pace()
        assert mock_sleep.call_count == 1
        sleep_duration = mock_sleep.call_args[0][0]
        assert sleep_duration > 0


def test_praw_rate_monitor_no_sleep_when_within_target():
    monitor = PrawRateMonitor(target_rate=80)
    monitor._request_count = 10
    monitor._start_time = 0.0
    with patch("src.pipeline.rate_limiter.time.time", return_value=12.0),          patch("src.pipeline.rate_limiter.time.sleep") as mock_sleep:
        monitor.ensure_pace()
        assert mock_sleep.call_count == 0
