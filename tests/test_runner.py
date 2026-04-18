"""Tests for sentinel.runner — skill resolution and discovery."""
import os
import tempfile

from sentinel.config import SentinelConfig
from sentinel.runner import _resolve_skills


def test_resolve_builtin_only():
    config = SentinelConfig(skills=["change_completeness"])
    skills = _resolve_skills(config, "", "claude-sonnet-4-6")
    assert len(skills) == 1
    assert skills[0].name == "change_completeness"


def test_resolve_unknown_builtin_ignored():
    config = SentinelConfig(skills=["change_completeness", "nonexistent_skill"])
    skills = _resolve_skills(config, "", "claude-sonnet-4-6")
    assert len(skills) == 1
    assert skills[0].name == "change_completeness"


def test_resolve_custom_skills():
    with tempfile.TemporaryDirectory() as d:
        skills_dir = os.path.join(d, ".sentinel", "skills")
        os.makedirs(skills_dir)
        with open(os.path.join(skills_dir, "cost_check.md"), "w") as f:
            f.write("Check that all AWS resources have a cost_center tag.")

        config = SentinelConfig(skills=["change_completeness"])
        skills = _resolve_skills(config, d, "claude-sonnet-4-6")

        names = [s.name for s in skills]
        assert "change_completeness" in names
        assert "cost_check" in names
        assert len(skills) == 2


def test_resolve_no_custom_dir():
    with tempfile.TemporaryDirectory() as d:
        config = SentinelConfig(skills=["change_completeness"])
        skills = _resolve_skills(config, d, "claude-sonnet-4-6")
        assert len(skills) == 1


def test_resolve_empty_custom_file_skipped():
    with tempfile.TemporaryDirectory() as d:
        skills_dir = os.path.join(d, ".sentinel", "skills")
        os.makedirs(skills_dir)
        with open(os.path.join(skills_dir, "empty.md"), "w") as f:
            f.write("")  # empty prompt

        config = SentinelConfig(skills=["change_completeness"])
        skills = _resolve_skills(config, d, "claude-sonnet-4-6")
        assert len(skills) == 1  # empty skill not loaded
