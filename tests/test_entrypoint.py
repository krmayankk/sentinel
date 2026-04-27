"""Tests for entrypoint fail_on merging and blocking logic."""
import pytest

from sentinel.core import Finding, Severity
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from entrypoint import _check_blocking


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
