"""Integration tests — run actual skills against eval fixtures with real LLM calls.

These tests require ANTHROPIC_API_KEY to be set. They are skipped when the key
is not available, so the unit test suite always passes without an API key.

Each test loads a fixture (diff.patch, context.json, expected.json, repo/),
runs the configured skills via the eval runner, and asserts the scorer
returns a passing FixtureScore. The deterministic scorer is the same one
that powers `sentinel eval run` — these tests double as the end-to-end check
for the v0.4 harness.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from sentinel.evals.runner import run_fixture

FIXTURES_DIR = Path(__file__).parent.parent / "evals" / "fixtures"

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set — skipping LLM integration tests",
)


def _assert_fixture_passes(name: str) -> None:
    run = run_fixture(FIXTURES_DIR / name)
    score = run.score

    failures: list[str] = []
    for r in score.must_find:
        if not r.passed:
            failures.append(
                f"must_find unmet: {r.expected.get('rationale', r.expected)}"
            )
    for r in score.must_not_find:
        if not r.passed:
            failures.append(
                f"must_not_find violated by {r.violating.skill}/{r.violating.severity.value}: "
                f"{r.violating.title}"
            )
    if not score.verdict_match:
        failures.append(
            f"verdict mismatch: expected={score.expected_verdict} actual={score.actual_verdict}"
        )

    if failures:
        findings_summary = [
            (f.skill, f.severity.value, f.title) for f in score.findings
        ]
        details = "\n  ".join(failures)
        raise AssertionError(
            f"Fixture {name} failed:\n  {details}\n"
            f"Produced findings: {findings_summary}"
        )


class TestFixtures:
    """Run each eval fixture as an integration test via the v0.4 harness."""

    def test_terraform_variable_removed(self):
        _assert_fixture_passes("terraform_variable_removed")

    def test_gha_privilege_escalation(self):
        _assert_fixture_passes("gha_privilege_escalation")

    def test_unsafe_migration(self):
        _assert_fixture_passes("unsafe_migration")

    def test_cross_repo(self):
        _assert_fixture_passes("cross_repo")
