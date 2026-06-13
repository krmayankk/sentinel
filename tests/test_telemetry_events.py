"""Tests for sentinel.telemetry.events — schema, hashing, composition.

No LLM, no I/O. Pure data transformations.
"""
import json
import re

from sentinel.core import Finding, Severity
from sentinel.telemetry.events import (
    SCHEMA_VERSION,
    Event,
    FindingSummary,
    build_skill_run_event,
    finding_id,
    new_session_id,
    utc_now_iso,
)


# -- finding_id --

def test_finding_id_is_stable():
    a = finding_id("change_completeness", "envs/prod/main.tf", 42, "Removed variable still referenced")
    b = finding_id("change_completeness", "envs/prod/main.tf", 42, "Removed variable still referenced")
    assert a == b


def test_finding_id_distinguishes_skill():
    a = finding_id("change_completeness", "f", 1, "t")
    b = finding_id("workflow_security", "f", 1, "t")
    assert a != b


def test_finding_id_distinguishes_file():
    a = finding_id("s", "a.tf", 1, "t")
    b = finding_id("s", "b.tf", 1, "t")
    assert a != b


def test_finding_id_distinguishes_line():
    a = finding_id("s", "f", 1, "t")
    b = finding_id("s", "f", 2, "t")
    assert a != b


def test_finding_id_distinguishes_title():
    a = finding_id("s", "f", 1, "title one")
    b = finding_id("s", "f", 1, "title two")
    assert a != b


def test_finding_id_is_short_hex():
    fid = finding_id("s", "f", 1, "t")
    assert len(fid) == 12
    assert re.fullmatch(r"[0-9a-f]{12}", fid)


# -- session id and timestamp --

def test_new_session_id_format():
    sid = new_session_id()
    assert len(sid) == 12
    assert re.fullmatch(r"[0-9a-f]{12}", sid)


def test_new_session_id_is_unique():
    assert len({new_session_id() for _ in range(100)}) == 100


def test_utc_now_iso_is_parseable_and_zulu():
    ts = utc_now_iso()
    # Form: 2026-05-30T23:58:27.589Z
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", ts), ts


# -- FindingSummary --

def _f(skill="change_completeness", severity=Severity.HIGH, title="t",
       file="envs/prod/main.tf", line=12) -> Finding:
    return Finding(skill=skill, severity=severity, title=title,
                   message="long body that must not be emitted",
                   suggestion="long suggestion that must not be emitted",
                   file=file, line=line)


def test_finding_summary_from_finding_copies_identity_only():
    fs = FindingSummary.from_finding(_f())
    assert fs.skill == "change_completeness"
    assert fs.severity == "high"
    assert fs.title == "t"
    assert fs.file == "envs/prod/main.tf"
    assert fs.line == 12
    assert fs.id == finding_id("change_completeness", "envs/prod/main.tf", 12, "t")


def test_finding_summary_omits_body_fields():
    fs = FindingSummary.from_finding(_f())
    # message/suggestion are deliberately not part of the schema
    assert not hasattr(fs, "message")
    assert not hasattr(fs, "suggestion")


# -- build_skill_run_event --

def test_build_skill_run_event_basic():
    ev = build_skill_run_event(
        session_id="abc123",
        trigger="pull_request",
        repo="acme/api",
        pr_number=42,
        skill="change_completeness",
        duration_s=1.23456789,
        findings=[_f()],
    )
    assert ev.schema_version == SCHEMA_VERSION
    assert ev.event_type == "skill_run"
    assert ev.session_id == "abc123"
    assert ev.trigger == "pull_request"
    assert ev.repo == "acme/api"
    assert ev.pr_number == 42
    assert ev.skill == "change_completeness"
    # Duration is rounded to 3 dp so JSONL stays compact and readable.
    assert ev.duration_s == 1.235
    assert ev.finding_count == 1
    assert len(ev.findings) == 1
    assert ev.error is None


def test_build_skill_run_event_no_findings():
    ev = build_skill_run_event(
        session_id="s", trigger="", repo="r", pr_number=None,
        skill="x", duration_s=0.1, findings=[],
    )
    assert ev.finding_count == 0
    assert ev.findings == []


def test_build_skill_run_event_with_error():
    ev = build_skill_run_event(
        session_id="s", trigger="", repo="r", pr_number=None,
        skill="x", duration_s=0.1, findings=[], error="RateLimitError",
    )
    assert ev.error == "RateLimitError"


def test_build_skill_run_event_uses_supplied_timestamp():
    ts = "2026-05-30T12:00:00.000Z"
    ev = build_skill_run_event(
        session_id="s", trigger="", repo="r", pr_number=None,
        skill="x", duration_s=0.0, findings=[], timestamp=ts,
    )
    assert ev.timestamp == ts


# -- Event serialization --

def test_event_to_dict_is_json_round_trippable():
    ev = build_skill_run_event(
        session_id="s", trigger="pull_request", repo="acme/api",
        pr_number=1, skill="x", duration_s=0.5, findings=[_f()],
    )
    line = json.dumps(ev.to_dict())
    parsed = json.loads(line)
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["skill"] == "x"
    assert parsed["findings"][0]["severity"] == "high"
    assert parsed["findings"][0]["id"] == ev.findings[0].id


def test_event_dict_does_not_leak_finding_body():
    ev = build_skill_run_event(
        session_id="s", trigger="", repo="r", pr_number=None,
        skill="x", duration_s=0.0, findings=[_f()],
    )
    blob = json.dumps(ev.to_dict())
    assert "long body that must not be emitted" not in blob
    assert "long suggestion that must not be emitted" not in blob
