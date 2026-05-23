"""Text + JSON formatters for eval results.

Console output for humans, JSON for CI artifacts.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from sentinel.core import Finding
from sentinel.evals.runner import FixtureRun
from sentinel.evals.scorer import Aggregate, aggregate


_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def format_console(runs: list[FixtureRun]) -> str:
    """One block per fixture, then an aggregate line. Uses ANSI colors."""
    lines: list[str] = []
    lines.append("")
    lines.append(f"{_BOLD}sentinel eval{_RESET}")
    lines.append("")

    for run in runs:
        score = run.score
        status = f"{_GREEN}PASS{_RESET}" if score.passed else f"{_RED}FAIL{_RESET}"
        lines.append(f"  {status}  {_BOLD}{score.fixture}{_RESET}  "
                     f"{_DIM}({run.duration_s:.1f}s){_RESET}")

        for r in score.must_find:
            if r.passed:
                lines.append(f"      {_GREEN}✓{_RESET} must_find  "
                             f"{_DIM}{_summarize_expectation(r.expected)}{_RESET}")
            else:
                lines.append(f"      {_RED}✗{_RESET} must_find  "
                             f"{_summarize_expectation(r.expected)}")

        for r in score.must_not_find:
            if r.passed:
                lines.append(f"      {_GREEN}✓{_RESET} must_not_find  "
                             f"{_DIM}{_summarize_expectation(r.expected)}{_RESET}")
            else:
                lines.append(f"      {_RED}✗{_RESET} must_not_find triggered  "
                             f"{_summarize_expectation(r.expected)}")
                if r.violating is not None:
                    lines.append(f"         {_DIM}offender: [{r.violating.severity.value}] "
                                 f"{r.violating.title} @ {r.violating.file}{_RESET}")

        verdict_color = _GREEN if score.verdict_match else _RED
        verdict_mark = "✓" if score.verdict_match else "✗"
        lines.append(f"      {verdict_color}{verdict_mark}{_RESET} verdict  "
                     f"{_DIM}expected={score.expected_verdict} actual={score.actual_verdict}{_RESET}")
        lines.append("")

    agg = aggregate([r.score for r in runs])
    lines.append("─" * 56)
    lines.append(_aggregate_line(agg, runs))
    lines.append("")
    return "\n".join(lines)


def _aggregate_line(agg: Aggregate, runs: list[FixtureRun]) -> str:
    total_dur = sum(r.duration_s for r in runs)
    color = _GREEN if agg.passed == agg.total else (_YELLOW if agg.passed else _RED)
    return (
        f"  {color}{agg.passed}/{agg.total} fixtures passed{_RESET}  "
        f"{_DIM}recall={agg.recall:.0%} precision={agg.precision:.0%} "
        f"verdict_match={agg.verdict_match}/{agg.total} "
        f"total={total_dur:.1f}s{_RESET}"
    )


def _summarize_expectation(expectation: dict) -> str:
    skill = expectation.get("skill", "?")
    sev = expectation.get("severity_min", "?")
    needles = expectation.get("match_any") or expectation.get("title_contains") or []
    file_needles = expectation.get("file_contains") or []
    parts = [f"{skill} ≥{sev}"]
    if needles:
        parts.append(f"match_any={needles}")
    if file_needles:
        parts.append(f"file_contains={file_needles}")
    return "  ".join(parts)


def to_json(runs: list[FixtureRun]) -> str:
    """Machine-readable report for CI artifacts."""
    agg = aggregate([r.score for r in runs])
    payload: dict[str, Any] = {
        "summary": {
            "total": agg.total,
            "passed": agg.passed,
            "recall": round(agg.recall, 4),
            "precision": round(agg.precision, 4),
            "verdict_match": agg.verdict_match,
            "must_find_total": agg.must_find_total,
            "must_find_hit": agg.must_find_hit,
            "must_not_find_total": agg.must_not_find_total,
            "must_not_find_clean": agg.must_not_find_clean,
        },
        "fixtures": [
            {
                "name": r.score.fixture,
                "passed": r.score.passed,
                "duration_s": round(r.duration_s, 3),
                "expected_verdict": r.score.expected_verdict,
                "actual_verdict": r.score.actual_verdict,
                "verdict_match": r.score.verdict_match,
                "must_find": [
                    {
                        "expected": mfr.expected,
                        "matched": _finding_summary(mfr.matched),
                        "passed": mfr.passed,
                    }
                    for mfr in r.score.must_find
                ],
                "must_not_find": [
                    {
                        "expected": mnfr.expected,
                        "violating": _finding_summary(mnfr.violating),
                        "passed": mnfr.passed,
                    }
                    for mnfr in r.score.must_not_find
                ],
                "findings": [_finding_summary(f) for f in r.score.findings],
            }
            for r in runs
        ],
    }
    return json.dumps(payload, indent=2)


def _finding_summary(f: Finding | None) -> dict | None:
    if f is None:
        return None
    return {
        "skill": f.skill,
        "severity": f.severity.value,
        "title": f.title,
        "file": f.file,
        "line": f.line,
    }
