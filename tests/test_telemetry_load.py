"""Tests for sentinel.telemetry.load — JSONL reader."""
import json

from sentinel.telemetry.events import build_skill_run_event
from sentinel.telemetry.load import load_events


def _line(skill="x", timestamp="2026-05-30T12:00:00.000Z", session_id="s"):
    ev = build_skill_run_event(
        session_id=session_id, trigger="", repo="r", pr_number=None,
        skill=skill, duration_s=0.0, findings=[], timestamp=timestamp,
    )
    return json.dumps(ev.to_dict())


def test_load_returns_empty_when_dir_missing(tmp_path):
    assert load_events(tmp_path / "nonexistent") == []


def test_load_returns_empty_when_dir_has_no_event_files(tmp_path):
    (tmp_path / "unrelated.txt").write_text("hi")
    assert load_events(tmp_path) == []


def test_load_reads_one_file(tmp_path):
    (tmp_path / "events-2026-05-30.jsonl").write_text(_line(skill="a") + "\n")
    events = load_events(tmp_path)
    assert len(events) == 1
    assert events[0].skill == "a"


def test_load_reads_multiple_files_in_chronological_order(tmp_path):
    (tmp_path / "events-2026-05-31.jsonl").write_text(_line(skill="day2") + "\n")
    (tmp_path / "events-2026-05-30.jsonl").write_text(_line(skill="day1") + "\n")
    events = load_events(tmp_path)
    assert [e.skill for e in events] == ["day1", "day2"]


def test_load_skips_blank_lines(tmp_path):
    (tmp_path / "events-2026-05-30.jsonl").write_text(
        _line(skill="a") + "\n\n" + _line(skill="b") + "\n"
    )
    events = load_events(tmp_path)
    assert [e.skill for e in events] == ["a", "b"]


def test_load_skips_malformed_line_continues(tmp_path, capsys):
    (tmp_path / "events-2026-05-30.jsonl").write_text(
        _line(skill="a") + "\n"
        "{not valid json\n"
        + _line(skill="b") + "\n"
    )
    events = load_events(tmp_path)
    assert [e.skill for e in events] == ["a", "b"]
    err = capsys.readouterr().err
    assert "malformed" in err
