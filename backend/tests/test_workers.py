from __future__ import annotations

from app.workers.worker import WorkerSettings, _minute_schedule, _retry_delay


def test_worker_settings_register_expected_jobs() -> None:
    function_names = {func.__name__ for func in WorkerSettings.functions}
    assert function_names == {
        "refresh_all_markets_job",
        "fill_risk_assessment_pnl_job",
        "nightly_backtest_job",
        "compute_radar_snapshot_job",
    }
    cron_names = {job.name for job in WorkerSettings.cron_jobs}
    assert cron_names == {
        "market_refresh",
        "risk_assessment_pnl_fill",
        "nightly_backtest",
        "radar_snapshot",
    }


def test_worker_schedule_and_retry_backoff() -> None:
    assert _minute_schedule(30) == {0, 30}
    assert _minute_schedule(90) == 0
    assert _retry_delay({"job_try": 1}) == 30
    assert _retry_delay({"job_try": 4}) == 240
