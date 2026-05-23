"""Unit tests for the deterministic eval scorer.

These tests do not call the LLM. They hand-craft Finding objects and expected.json
shapes, then assert the scorer reaches the right verdicts. This is the regression
net for the v0.4 eval harness itself.
"""
from __future__ import annotations

from sentinel.core import Finding, Severity
from sentinel.evals.scorer import (
    Aggregate,
    aggregate,
    derive_verdict,
    matches,
    score_fixture,
)


def _finding(
    skill: str = "change_completeness",
    severity: Severity = Severity.HIGH,
    title: str = "missing caller update",
    message: str = "callers in envs/prod still pass enable_performance_insights",
    suggestion: str = "remove the argument from caller files",
    file: str = "terraform/envs/prod/main.tf",
    line: int = 12,
) -> Finding:
    return Finding(
        skill=skill,
        severity=severity,
        title=title,
        message=message,
        suggestion=suggestion,
        file=file,
        line=line,
    )


# -- matches() --

def test_matches_passes_with_only_skill_and_severity():
    f = _finding()
    assert matches({"skill": "change_completeness", "severity_min": "high"}, f)


def test_matches_rejects_wrong_skill():
    f = _finding(skill="migration_safety")
    assert not matches({"skill": "change_completeness", "severity_min": "high"}, f)


def test_matches_rejects_below_severity_threshold():
    f = _finding(severity=Severity.MEDIUM)
    assert not matches({"skill": "change_completeness", "severity_min": "high"}, f)


def test_matches_allows_above_severity_threshold():
    f = _finding(severity=Severity.CRITICAL)
    assert matches({"skill": "change_completeness", "severity_min": "high"}, f)


def test_match_any_finds_substring_in_title():
    f = _finding(title="missing caller update")
    assert matches({"skill": "change_completeness", "severity_min": "high",
                    "match_any": ["caller"]}, f)


def test_match_any_finds_substring_in_message():
    f = _finding(title="incomplete change", message="envs/prod still passes the removed var")
    assert matches({"skill": "change_completeness", "severity_min": "high",
                    "match_any": ["envs/prod"]}, f)


def test_match_any_finds_substring_in_file():
    f = _finding(title="x", message="y", suggestion="z", file="terraform/envs/prod/main.tf")
    assert matches({"skill": "change_completeness", "severity_min": "high",
                    "match_any": ["envs/prod"]}, f)


def test_match_any_misses_when_no_substring_appears():
    f = _finding(title="x", message="y", suggestion="z", file="a.py")
    assert not matches({"skill": "change_completeness", "severity_min": "high",
                        "match_any": ["caller", "module"]}, f)


def test_match_any_is_case_insensitive():
    f = _finding(title="Missing Caller Update")
    assert matches({"skill": "change_completeness", "severity_min": "high",
                    "match_any": ["caller"]}, f)


def test_title_contains_is_alias_for_match_any():
    f = _finding(title="missing caller update")
    assert matches({"skill": "change_completeness", "severity_min": "high",
                    "title_contains": ["caller"]}, f)


def test_file_contains_requires_match_in_file_field_only():
    # Substring is present in message but NOT in file — file_contains must reject.
    f = _finding(message="envs/prod still passes", file="src/other.py")
    assert not matches({"skill": "change_completeness", "severity_min": "high",
                        "file_contains": ["envs/prod"]}, f)


def test_file_contains_passes_when_file_matches():
    f = _finding(file="terraform/envs/prod/main.tf")
    assert matches({"skill": "change_completeness", "severity_min": "high",
                    "file_contains": ["envs/prod"]}, f)


def test_match_any_and_file_contains_are_anded():
    f = _finding(title="missing caller", file="src/other.py")
    # match_any passes (title), file_contains fails — overall must fail.
    assert not matches({"skill": "change_completeness", "severity_min": "high",
                        "match_any": ["caller"],
                        "file_contains": ["envs/prod"]}, f)


# -- derive_verdict --

def test_verdict_incomplete_when_high_finding_present():
    findings = [_finding(severity=Severity.HIGH)]
    assert derive_verdict(findings) == "incomplete"


def test_verdict_incomplete_when_critical_finding_present():
    findings = [_finding(severity=Severity.CRITICAL)]
    assert derive_verdict(findings) == "incomplete"


def test_verdict_complete_when_only_low_findings():
    findings = [_finding(severity=Severity.LOW), _finding(severity=Severity.MEDIUM)]
    assert derive_verdict(findings) == "complete"


def test_verdict_complete_when_no_findings():
    assert derive_verdict([]) == "complete"


# -- score_fixture --

def test_score_passes_when_must_find_hit_and_verdict_matches():
    expected = {
        "must_find": [
            {"skill": "change_completeness", "severity_min": "high",
             "match_any": ["caller"]},
        ],
        "must_not_find": [],
        "verdict": "incomplete",
    }
    findings = [_finding()]  # high, title="missing caller update"
    score = score_fixture("test", expected, findings)
    assert score.passed
    assert score.verdict_match
    assert all(r.passed for r in score.must_find)


def test_score_fails_when_must_find_missed():
    expected = {
        "must_find": [
            {"skill": "change_completeness", "severity_min": "high",
             "match_any": ["unobtainable_keyword"]},
        ],
        "must_not_find": [],
        "verdict": "incomplete",
    }
    findings = [_finding()]
    score = score_fixture("test", expected, findings)
    assert not score.passed
    assert not score.must_find[0].passed


def test_score_fails_when_must_not_find_triggered():
    expected = {
        "must_find": [],
        "must_not_find": [
            {"skill": "change_completeness", "severity_min": "high",
             "match_any": ["caller"]},
        ],
        "verdict": "incomplete",
    }
    findings = [_finding()]  # this IS the false positive we said must not appear
    score = score_fixture("test", expected, findings)
    assert not score.passed
    assert not score.must_not_find[0].passed
    assert score.must_not_find[0].violating is not None


def test_score_fails_when_verdict_mismatches():
    expected = {
        "must_find": [],
        "must_not_find": [],
        "verdict": "complete",
    }
    findings = [_finding(severity=Severity.HIGH)]  # high → derived verdict = incomplete
    score = score_fixture("test", expected, findings)
    assert not score.passed
    assert score.expected_verdict == "complete"
    assert score.actual_verdict == "incomplete"


def test_score_passes_with_clean_run_and_complete_verdict():
    expected = {"must_find": [], "must_not_find": [], "verdict": "complete"}
    findings: list = []
    score = score_fixture("test", expected, findings)
    assert score.passed


# -- aggregate --

def test_aggregate_counts_passes_and_recall_precision():
    expected_inc = {
        "must_find": [
            {"skill": "change_completeness", "severity_min": "high",
             "match_any": ["caller"]},
        ],
        "must_not_find": [],
        "verdict": "incomplete",
    }
    expected_complete = {"must_find": [], "must_not_find": [], "verdict": "complete"}

    # Fixture A: must_find hit, passes
    a = score_fixture("a", expected_inc, [_finding()])
    # Fixture B: must_find missed, fails
    b = score_fixture("b", expected_inc, [_finding(title="x", message="y", suggestion="z",
                                                   file="other.py")])
    # Fixture C: clean expected, clean produced — passes
    c = score_fixture("c", expected_complete, [])

    agg = aggregate([a, b, c])
    assert isinstance(agg, Aggregate)
    assert agg.total == 3
    assert agg.passed == 2
    assert agg.must_find_total == 2  # a and b each had one must_find
    assert agg.must_find_hit == 1    # only a's hit
    assert agg.recall == 0.5
    # No must_not_find entries anywhere, so precision is the 1.0 default.
    assert agg.precision == 1.0
