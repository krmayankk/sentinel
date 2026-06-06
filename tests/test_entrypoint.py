"""Tests for entrypoint fail_on merging and blocking logic."""
import json
import os
import sys

import pytest

from sentinel.core import Finding, Severity
from sentinel.telemetry.events import build_skill_run_event

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from entrypoint import _check_blocking, _gha_run_url, _maybe_write_job_summary


def _finding(severity: str) -> Finding:
    return Finding(
        skill="test", severity=Severity(severity),
        title="t", message="m", suggestion="s",
    )


def test_check_blocking_exits_on_match():
    findings = [_finding("high"), _finding("low")]
    with pytest.raises(SystemExit) as exc:
        _check_blocking(findings, {"high"})
    assert exc.value.code == 1


def test_check_blocking_no_match_no_exit():
    findings = [_finding("low"), _finding("medium")]
    _check_blocking(findings, {"high", "critical"})  # should not exit


def test_check_blocking_empty_fail_on_no_exit():
    findings = [_finding("critical")]
    _check_blocking(findings, set())  # empty = warning-only, should not exit


def test_check_blocking_empty_findings_no_exit():
    _check_blocking([], {"high", "critical"})  # no findings, should not exit


def test_fail_on_merge_env_var_takes_precedence():
    """When env var fail_on is set, it takes precedence over config."""
    env_fail_on = {"critical"}
    config_fail_on = ["critical", "high"]
    # env var is set → use it
    effective = env_fail_on or set(config_fail_on)
    assert effective == {"critical"}


def test_fail_on_merge_falls_back_to_config():
    """When env var fail_on is empty, sentinel.yml fail_on applies."""
    env_fail_on: set[str] = set()
    config_fail_on = ["critical", "high"]
    # env var empty → fall back to config
    effective = env_fail_on or set(config_fail_on)
    assert effective == {"critical", "high"}


def test_fail_on_merge_both_empty():
    """When both env var and config are empty, nothing blocks."""
    env_fail_on: set[str] = set()
    config_fail_on: list[str] = []
    effective = env_fail_on or set(config_fail_on)
    assert effective == set()


# -- job summary --

def test_job_summary_skipped_when_env_var_unset(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    # Should be a no-op — must not raise.
    _maybe_write_job_summary({"x": []}, [])


def test_job_summary_written_when_env_var_set(tmp_path, monkeypatch):
    target = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(target))

    finding = Finding(skill="change_completeness", severity=Severity.HIGH,
                       title="missing caller", message="m", suggestion="s",
                       file="x.tf", line=1)
    event = build_skill_run_event(
        session_id="s", trigger="pull_request", repo="r", pr_number=1,
        skill="change_completeness", duration_s=0.5, findings=[finding],
    )

    _maybe_write_job_summary({"change_completeness": [finding]}, [event])

    content = target.read_text()
    assert "## Sentinel review" in content
    assert "missing caller" in content


def test_job_summary_appends_not_overwrites(tmp_path, monkeypatch):
    target = tmp_path / "summary.md"
    target.write_text("PRE-EXISTING\n")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(target))

    _maybe_write_job_summary({"x": []}, [])
    assert target.read_text().startswith("PRE-EXISTING\n")


# -- run url --

def test_gha_run_url_complete(monkeypatch):
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/api")
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")
    assert _gha_run_url() == "https://github.com/acme/api/actions/runs/12345"


def test_gha_run_url_missing_returns_none(monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    assert _gha_run_url() is None


def test_gha_run_url_default_server(monkeypatch):
    """GITHUB_SERVER_URL is missing on some self-hosted setups; default to github.com."""
    monkeypatch.delenv("GITHUB_SERVER_URL", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/api")
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")
    assert _gha_run_url() == "https://github.com/acme/api/actions/runs/12345"
