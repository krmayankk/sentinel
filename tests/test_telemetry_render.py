"""Tests for sentinel.telemetry.render — Markdown summaries.

No I/O, no network. Pure string assertions.
"""
from sentinel.core import Finding, Severity
from sentinel.telemetry.events import build_skill_run_event
from sentinel.telemetry.render import render_aggregate, render_run_summary


def _f(skill="change_completeness", severity=Severity.HIGH, title="t",
       message="m", suggestion="s", file="f.tf", line=1) -> Finding:
    return Finding(skill=skill, severity=severity, title=title,
                   message=message, suggestion=suggestion, file=file, line=line)


def _ev(skill="change_completeness", duration_s=1.0, findings=None, error=None,
        timestamp="2026-05-30T12:00:00.000Z", session_id="s"):
    return build_skill_run_event(
        session_id=session_id, trigger="pull_request", repo="acme/api",
        pr_number=42, skill=skill, duration_s=duration_s,
        findings=findings or [], error=error, timestamp=timestamp,
    )


# -- render_run_summary --

def test_run_summary_all_clean():
    results = {"change_completeness": [], "workflow_security": []}
    events = [_ev("change_completeness"), _ev("workflow_security")]
    md = render_run_summary(results, events)
    assert "## Sentinel review" in md
    assert "✅" in md
    assert "0 finding(s) across 2 skill(s)" in md
    assert "✅ clean" in md
    # No collapsible details when clean
    assert "<details>" not in md


def test_run_summary_with_findings_table():
    results = {
        "change_completeness": [_f(severity=Severity.HIGH, title="missing caller")],
        "workflow_security": [],
    }
    events = [_ev("change_completeness", findings=results["change_completeness"]),
              _ev("workflow_security")]
    md = render_run_summary(results, events)
    assert "⚠️" in md
    assert "1 finding(s) across 2 skill(s)" in md
    assert "1 high" in md
    assert "`change_completeness`" in md
    assert "`workflow_security`" in md
    # Skill with findings → details block
    assert "<details>" in md
    assert "missing caller" in md


def test_run_summary_includes_finding_body_and_suggestion():
    results = {"change_completeness": [_f(message="this is the body",
                                          suggestion="this is the suggestion")]}
    events = [_ev("change_completeness", findings=results["change_completeness"])]
    md = render_run_summary(results, events)
    assert "this is the body" in md
    assert "this is the suggestion" in md


def test_run_summary_quotes_multiline_message():
    results = {"change_completeness": [_f(message="line one\nline two\n\nline four")]}
    events = [_ev("change_completeness", findings=results["change_completeness"])]
    md = render_run_summary(results, events)
    # Each line gets prefixed with "> " (or just ">") so the quote stays a quote.
    assert "> line one" in md
    assert "> line two" in md
    assert "> line four" in md


def test_run_summary_error_block_replaces_findings():
    results = {"change_completeness": []}
    events = [_ev("change_completeness", error="RateLimitError")]
    md = render_run_summary(results, events)
    assert "❌" in md
    assert "RateLimitError" in md
    assert "1 skill error(s)" in md


def test_run_summary_severity_histogram_only_lists_present():
    """When only HIGH findings exist, don't show 'medium 0'."""
    results = {"change_completeness": [_f(severity=Severity.HIGH),
                                       _f(severity=Severity.HIGH)]}
    events = [_ev("change_completeness", findings=results["change_completeness"])]
    md = render_run_summary(results, events)
    assert "2 high" in md
    assert "medium" not in md.lower() or "0 medium" not in md


def test_run_summary_duration_rounded():
    results = {"change_completeness": []}
    events = [_ev("change_completeness", duration_s=12.6789)]
    md = render_run_summary(results, events)
    assert "12.7s" in md


# -- render_aggregate --

def test_aggregate_empty():
    md = render_aggregate([])
    assert "No events found" in md


def test_aggregate_groups_by_skill():
    events = [
        _ev("change_completeness", duration_s=1.0),
        _ev("change_completeness", duration_s=3.0,
            findings=[_f(severity=Severity.HIGH)]),
        _ev("workflow_security", duration_s=2.0, error="RuntimeError"),
    ]
    md = render_aggregate(events)
    assert "3 event(s)" in md
    assert "`change_completeness`" in md
    assert "`workflow_security`" in md
    # Errors are tracked separately
    assert " 1 " in md  # the error count cell for workflow_security


def test_aggregate_severity_counts_in_table():
    events = [
        _ev("x", findings=[_f(severity=Severity.CRITICAL)]),
        _ev("x", findings=[_f(severity=Severity.HIGH), _f(severity=Severity.HIGH)]),
        _ev("x", findings=[_f(severity=Severity.MEDIUM)]),
    ]
    md = render_aggregate(events)
    # Sev (C/H/M/L) format
    assert "1/2/1/0" in md


def test_aggregate_p50_excludes_errors():
    """Failed runs should not count toward latency percentiles."""
    events = [
        _ev("x", duration_s=1.0),
        _ev("x", duration_s=2.0),
        _ev("x", duration_s=99.0, error="Boom"),
    ]
    md = render_aggregate(events)
    # p50 = median of [1.0, 2.0] = 1.5
    assert "1.50s" in md


def test_aggregate_handles_zero_clean_runs():
    """All runs errored → p50/p95 must not divide by zero."""
    events = [_ev("x", duration_s=1.0, error="A"), _ev("x", duration_s=2.0, error="B")]
    md = render_aggregate(events)
    assert "—" in md  # dash for both p50 and p95
