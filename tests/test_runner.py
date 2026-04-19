"""Tests for sentinel.runner — skill resolution, discovery, and mode filtering."""
import os
import tempfile

from sentinel.config import SentinelConfig, SkillConfig, ModeConfig
from sentinel.runner import _resolve_skills


def _config(names: list[str], **kwargs) -> SentinelConfig:
    """Helper to build a SentinelConfig from a list of skill names."""
    return SentinelConfig(
        skill_configs=[SkillConfig(name=n) for n in names],
        **kwargs,
    )


def test_resolve_builtin_only():
    config = _config(["change_completeness"])
    skills = _resolve_skills(config, "", "claude-sonnet-4-6")
    assert len(skills) == 1
    assert skills[0].name == "change_completeness"


def test_resolve_unknown_builtin_ignored():
    config = _config(["change_completeness", "nonexistent_skill"])
    skills = _resolve_skills(config, "", "claude-sonnet-4-6")
    assert len(skills) == 1
    assert skills[0].name == "change_completeness"


def test_resolve_custom_skills():
    with tempfile.TemporaryDirectory() as d:
        skills_dir = os.path.join(d, ".sentinel", "skills")
        os.makedirs(skills_dir)
        with open(os.path.join(skills_dir, "cost_check.md"), "w") as f:
            f.write("Check that all AWS resources have a cost_center tag.")

        config = _config(["change_completeness"])
        skills = _resolve_skills(config, d, "claude-sonnet-4-6")

        names = [s.name for s in skills]
        assert "change_completeness" in names
        assert "cost_check" in names
        assert len(skills) == 2


def test_resolve_no_custom_dir():
    with tempfile.TemporaryDirectory() as d:
        config = _config(["change_completeness"])
        skills = _resolve_skills(config, d, "claude-sonnet-4-6")
        assert len(skills) == 1


def test_resolve_empty_custom_file_skipped():
    with tempfile.TemporaryDirectory() as d:
        skills_dir = os.path.join(d, ".sentinel", "skills")
        os.makedirs(skills_dir)
        with open(os.path.join(skills_dir, "empty.md"), "w") as f:
            f.write("")  # empty prompt

        config = _config(["change_completeness"])
        skills = _resolve_skills(config, d, "claude-sonnet-4-6")
        assert len(skills) == 1  # empty skill not loaded


def test_resolve_workflow_security():
    config = _config(["workflow_security"])
    skills = _resolve_skills(config, "", "claude-sonnet-4-6")
    assert len(skills) == 1
    assert skills[0].name == "workflow_security"


def test_resolve_migration_safety():
    config = _config(["migration_safety"])
    skills = _resolve_skills(config, "", "claude-sonnet-4-6")
    assert len(skills) == 1
    assert skills[0].name == "migration_safety"


def test_resolve_all_builtins():
    config = _config(["change_completeness", "workflow_security", "migration_safety"])
    skills = _resolve_skills(config, "", "claude-sonnet-4-6")
    names = {s.name for s in skills}
    assert names == {"change_completeness", "workflow_security", "migration_safety"}


def test_mode_filter_push():
    config = _config(
        ["change_completeness", "workflow_security", "migration_safety"],
        mode=ModeConfig(on_push=["workflow_security", "change_completeness"], on_merge=["migration_safety"]),
    )
    skills = _resolve_skills(config, "", "claude-sonnet-4-6", event_type="push")
    names = {s.name for s in skills}
    assert names == {"workflow_security", "change_completeness"}


def test_mode_filter_merge():
    config = _config(
        ["change_completeness", "workflow_security", "migration_safety"],
        mode=ModeConfig(on_push=["workflow_security"], on_merge=["migration_safety"]),
    )
    skills = _resolve_skills(config, "", "claude-sonnet-4-6", event_type="merge")
    names = {s.name for s in skills}
    assert names == {"migration_safety"}


def test_mode_filter_none_runs_all():
    config = _config(
        ["change_completeness", "workflow_security"],
        mode=ModeConfig(on_push=["workflow_security"], on_merge=["change_completeness"]),
    )
    skills = _resolve_skills(config, "", "claude-sonnet-4-6", event_type="")
    names = {s.name for s in skills}
    assert names == {"change_completeness", "workflow_security"}
