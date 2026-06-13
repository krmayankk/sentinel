"""Tests for sentinel.github.format_comment — the PR comment body.

No network. format_comment is a pure string function.
"""
from sentinel.core import Finding, Severity
from sentinel.github import format_comment


def _f(skill="change_completeness", severity=Severity.HIGH, title="t",
       message="m", suggestion="s", file="f.tf", line=1) -> Finding:
    return Finding(skill=skill, severity=severity, title=title,
                   message=message, suggestion=suggestion, file=file, line=line)


def test_comment_clean_run_one_liner():
    md = format_comment({"change_completeness": [], "workflow_security": []})
    assert "✅" in md
    assert "All 2 skill(s) passed" in md
    # Table still present so the per-skill status is visible
    assert "| Skill | Status |" in md
    # No collapsible details when clean
    assert "<details>" not in md


def test_comment_findings_collapsed_under_details():
    findings = [_f(severity=Severity.HIGH, title="A"),
                _f(severity=Severity.MEDIUM, title="B")]
    md = format_comment({"change_completeness": findings,
                          "workflow_security": []})
    # Verdict counts each severity
    assert "1 high" in md
    assert "1 medium" in md
    # Details block exists for the skill with findings
    assert "<details>" in md
    assert "A" in md
    assert "B" in md
    # Clean skill does NOT get a details block
    assert md.count("<details>") == 1


def test_comment_includes_run_url_when_supplied():
    md = format_comment(
        {"change_completeness": []},
        run_url="https://github.com/acme/api/actions/runs/123",
    )
    assert "Full summary on the Actions tab" in md
    assert "https://github.com/acme/api/actions/runs/123" in md


def test_comment_omits_link_when_run_url_missing():
    md = format_comment({"change_completeness": []}, run_url=None)
    assert "Actions tab" not in md


def test_comment_builtin_vs_custom_label():
    md = format_comment({
        "change_completeness": [],
        "cost_attribution": [],  # not in builtin set
    })
    assert "built-in" in md
    assert "custom" in md


def test_comment_severity_order_in_verdict():
    """Verdict severities follow CRITICAL → HIGH → MEDIUM → LOW order."""
    findings = [
        _f(severity=Severity.LOW, title="L"),
        _f(severity=Severity.CRITICAL, title="C"),
        _f(severity=Severity.HIGH, title="H"),
    ]
    md = format_comment({"change_completeness": findings})
    # CRITICAL appears before HIGH appears before LOW in the verdict line
    crit_idx = md.index("1 critical")
    high_idx = md.index("1 high")
    low_idx = md.index("1 low")
    assert crit_idx < high_idx < low_idx
