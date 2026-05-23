"""Fixture runner — loads a fixture directory, runs skills, scores results.

The LLM is invoked inside the skill loop, not in scoring. This module is the
adapter between the on-disk fixture format and the skill runner.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from sentinel.config import load_config
from sentinel.core import Context, Finding
from sentinel.evals.scorer import FixtureScore, score_fixture
from sentinel.runner import run_skills


@dataclass
class FixtureRun:
    """Result of running one fixture: the score plus runtime metadata."""
    score: FixtureScore
    duration_s: float
    findings_by_skill: dict[str, list[Finding]] = field(default_factory=dict)


def _load_fixture(fixture_path: Path) -> tuple[dict, str, dict]:
    """Load context.json, diff.patch, expected.json from a fixture directory."""
    with (fixture_path / "context.json").open() as fh:
        context_json = json.load(fh)
    with (fixture_path / "diff.patch").open() as fh:
        diff = fh.read()
    with (fixture_path / "expected.json").open() as fh:
        expected = json.load(fh)
    return context_json, diff, expected


def run_fixture(
    fixture_path: Path,
    model: str = "claude-sonnet-4-6",
    event_type: str = "",
) -> FixtureRun:
    """Run all configured skills against a fixture and score the result."""
    name = fixture_path.name
    context_json, diff, expected = _load_fixture(fixture_path)

    repo_dir = fixture_path / "repo"
    repo_path = str(repo_dir) if repo_dir.exists() else ""

    config = load_config(repo_path)
    context = Context(
        repo=context_json.get("repo", "fixture"),
        pr_number=context_json.get("pr_number", 0),
        instructions=context_json.get("instructions", ""),
        repo_path=repo_path,
    )

    started = time.monotonic()
    results = run_skills(diff, context, config, model=model, event_type=event_type)
    duration = time.monotonic() - started

    flat = [f for fs in results.values() for f in fs]
    score = score_fixture(name, expected, flat)
    return FixtureRun(score=score, duration_s=duration, findings_by_skill=results)


def discover_fixtures(fixtures_dir: Path) -> list[Path]:
    """Return all fixture directories under fixtures_dir, sorted."""
    if not fixtures_dir.exists():
        return []
    return sorted(p for p in fixtures_dir.iterdir() if p.is_dir() and (p / "expected.json").exists())


def run_all(
    fixtures_dir: Path,
    model: str = "claude-sonnet-4-6",
    event_type: str = "",
    only: list[str] | None = None,
) -> list[FixtureRun]:
    """Run every fixture under fixtures_dir.

    Args:
        only: optional allow-list of fixture names to run.
    """
    runs: list[FixtureRun] = []
    for path in discover_fixtures(fixtures_dir):
        if only and path.name not in only:
            continue
        runs.append(run_fixture(path, model=model, event_type=event_type))
    return runs
