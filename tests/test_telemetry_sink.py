"""Tests for sentinel.telemetry.sink — JSONL writer and null sink.

No LLM, no network. Uses pytest's tmp_path for isolated filesystem.
"""
import json
import os

import pytest

from sentinel.telemetry.events import build_skill_run_event
from sentinel.telemetry.sink import JSONLSink, NullSink


def _event(*, timestamp="2026-05-30T12:00:00.000Z", skill="x", session_id="s"):
    return build_skill_run_event(
        session_id=session_id, trigger="", repo="r", pr_number=None,
        skill=skill, duration_s=0.0, findings=[], timestamp=timestamp,
    )


# -- NullSink --

def test_null_sink_emits_nothing(tmp_path):
    sink = NullSink()
    sink.emit(_event())
    # Files: none expected; tmp_path stays empty
    assert list(tmp_path.iterdir()) == []


# -- JSONLSink --

def test_jsonl_sink_writes_one_line(tmp_path):
    sink = JSONLSink(tmp_path)
    sink.emit(_event(timestamp="2026-05-30T12:00:00.000Z"))

    files = list(tmp_path.iterdir())
    assert len(files) == 1
    assert files[0].name == "events-2026-05-30.jsonl"

    lines = files[0].read_text().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["skill"] == "x"


def test_jsonl_sink_creates_missing_directory(tmp_path):
    target = tmp_path / "nested" / "telemetry"
    assert not target.exists()
    sink = JSONLSink(target)
    sink.emit(_event())
    assert target.is_dir()
    assert any(target.iterdir())


def test_jsonl_sink_appends_to_existing_file(tmp_path):
    sink = JSONLSink(tmp_path)
    sink.emit(_event(skill="a"))
    sink.emit(_event(skill="b"))
    sink.emit(_event(skill="c"))

    files = list(tmp_path.iterdir())
    assert len(files) == 1
    lines = files[0].read_text().splitlines()
    assert len(lines) == 3
    assert [json.loads(line)["skill"] for line in lines] == ["a", "b", "c"]


def test_jsonl_sink_daily_rotation(tmp_path):
    """Events on different days land in different files."""
    sink = JSONLSink(tmp_path)
    sink.emit(_event(timestamp="2026-05-30T23:59:59.000Z", skill="late"))
    sink.emit(_event(timestamp="2026-05-31T00:00:01.000Z", skill="early"))

    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ["events-2026-05-30.jsonl", "events-2026-05-31.jsonl"]

    late = (tmp_path / "events-2026-05-30.jsonl").read_text().strip()
    early = (tmp_path / "events-2026-05-31.jsonl").read_text().strip()
    assert json.loads(late)["skill"] == "late"
    assert json.loads(early)["skill"] == "early"


def test_jsonl_sink_writes_compact_json(tmp_path):
    """Compact separators keep telemetry files small enough to commit."""
    sink = JSONLSink(tmp_path)
    sink.emit(_event())
    line = next(tmp_path.iterdir()).read_text().splitlines()[0]
    # No spaces after commas or colons in compact form
    assert ", " not in line
    assert ": " not in line


def test_jsonl_sink_swallows_write_failures(tmp_path, capsys):
    """A read-only filesystem must not break a sentinel review."""
    target = tmp_path / "readonly"
    target.mkdir()
    # Strip write bit so mkdir(...exist_ok=True) succeeds but file open fails.
    os.chmod(target, 0o500)
    try:
        sink = JSONLSink(target)
        # Must not raise.
        sink.emit(_event())
    finally:
        os.chmod(target, 0o700)

    err = capsys.readouterr().err
    assert "telemetry write failed" in err


@pytest.mark.parametrize("date_part", ["2026-01-01", "2099-12-31"])
def test_jsonl_sink_date_prefix_drives_filename(tmp_path, date_part):
    sink = JSONLSink(tmp_path)
    sink.emit(_event(timestamp=f"{date_part}T00:00:00.000Z"))
    names = [p.name for p in tmp_path.iterdir()]
    assert names == [f"events-{date_part}.jsonl"]
