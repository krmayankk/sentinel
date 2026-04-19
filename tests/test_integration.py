"""Integration tests — run actual skills against eval fixtures with real LLM calls.

These tests require ANTHROPIC_API_KEY to be set. They are skipped when the key
is not available, so the unit test suite always passes without an API key.

Each test loads a fixture (diff.patch, context.json, expected.json, repo/),
runs the skill, and asserts that the findings match the expected.json criteria.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from sentinel.config import load_config
from sentinel.core import Context, Severity
from sentinel.runner import run_skills

FIXTURES_DIR = Path(__file__).parent.parent / "evals" / "fixtures"

# Skip all tests in this module if no API key
pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set — skipping LLM integration tests",
)

_SEVERITY_ORDER = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "critical": 3,
}


def _load_fixture(name: str) -> tuple[str, dict, dict, str]:
    """Load a fixture by name. Returns (diff, context_data, expected, repo_path)."""
    fixture_dir = FIXTURES_DIR / name
    diff = (fixture_dir / "diff.patch").read_text()
    context_data = json.loads((fixture_dir / "context.json").read_text())
    expected = json.loads((fixture_dir / "expected.json").read_text())
    repo_path = str(fixture_dir / "repo")
    return diff, context_data, expected, repo_path


def _check_must_find(findings: list, rule: dict) -> bool:
    """Check if at least one finding matches a must_find rule."""
    for f in findings:
        # Check skill match
        if rule.get("skill") and f.skill != rule["skill"]:
            continue

        # Check minimum severity
        if rule.get("severity_min"):
            min_sev = _SEVERITY_ORDER.get(rule["severity_min"], 0)
            actual_sev = _SEVERITY_ORDER.get(f.severity.value, 0)
            if actual_sev < min_sev:
                continue

        # Check title contains any of the keywords
        if rule.get("title_contains"):
            title_lower = f.title.lower()
            message_lower = f.message.lower()
            text = title_lower + " " + message_lower
            if not any(kw.lower() in text for kw in rule["title_contains"]):
                continue

        return True

    return False


def _run_fixture(name: str):
    """Load a fixture, run skills, and assert expectations."""
    diff, ctx_data, expected, repo_path = _load_fixture(name)

    config = load_config(repo_path)
    context = Context(
        repo=ctx_data.get("repo", "test/repo"),
        pr_number=ctx_data.get("pr_number", 0),
        instructions=ctx_data.get("instructions", ""),
        repo_path=repo_path,
    )

    results = run_skills(diff, context, config, model="claude-sonnet-4-6")
    all_findings = [f for findings in results.values() for f in findings]

    for rule in expected.get("must_find", []):
        assert _check_must_find(all_findings, rule), (
            f"must_find rule not satisfied: {rule.get('rationale', rule)}\n"
            f"Findings: {[(f.skill, f.severity.value, f.title) for f in all_findings]}"
        )

    for rule in expected.get("must_not_find", []):
        assert not _check_must_find(all_findings, rule), (
            f"must_not_find rule violated: {rule.get('rationale', rule)}\n"
            f"Findings: {[(f.skill, f.severity.value, f.title) for f in all_findings]}"
        )

    if expected.get("verdict") == "incomplete":
        assert len(all_findings) > 0, "Expected incomplete verdict but got no findings"
    elif expected.get("verdict") == "complete":
        assert len(all_findings) == 0, (
            f"Expected complete verdict but got {len(all_findings)} finding(s): "
            f"{[(f.skill, f.severity.value, f.title) for f in all_findings]}"
        )


class TestFixtures:
    """Run each eval fixture as an integration test."""

    def test_terraform_variable_removed(self):
        _run_fixture("terraform_variable_removed")

    def test_gha_privilege_escalation(self):
        _run_fixture("gha_privilege_escalation")

    def test_unsafe_migration(self):
        _run_fixture("unsafe_migration")
