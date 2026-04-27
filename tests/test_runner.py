"""Tests for sentinel.runner — skill resolution, discovery, and mode filtering."""
import os
import tempfile

from sentinel.config import SentinelConfig, SkillConfig, ModeConfig
from sentinel.core import Context, Finding, Severity, Skill
from sentinel.runner import _resolve_skills, run_skills


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


# -- routing tests --

_WORKFLOW_DIFF = """\
diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
index abc..def 100644
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -1 +1 @@
-old
+new
"""

_MIGRATION_DIFF = """\
diff --git a/migrations/0042_add_col.sql b/migrations/0042_add_col.sql
new file mode 100644
--- /dev/null
+++ b/migrations/0042_add_col.sql
@@ -0,0 +1 @@
+ALTER TABLE users ADD COLUMN verified BOOLEAN;
"""

_PYTHON_DIFF = """\
diff --git a/src/app.py b/src/app.py
index abc..def 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1 +1 @@
-old
+new
"""

_MIXED_DIFF = _WORKFLOW_DIFF + _MIGRATION_DIFF


def _routed_config():
    from sentinel.config import Route
    return _config(
        ["change_completeness", "workflow_security", "migration_safety"],
        routing=[
            Route(pattern=".github/workflows/**", skills=["workflow_security"]),
            Route(pattern="migrations/**", skills=["migration_safety"]),
        ],
    )


def test_routing_workflow_only():
    config = _routed_config()
    skills = _resolve_skills(config, "", "claude-sonnet-4-6", diff=_WORKFLOW_DIFF)
    names = {s.name for s in skills}
    assert names == {"workflow_security"}


def test_routing_migration_only():
    config = _routed_config()
    skills = _resolve_skills(config, "", "claude-sonnet-4-6", diff=_MIGRATION_DIFF)
    names = {s.name for s in skills}
    assert names == {"migration_safety"}


def test_routing_mixed_diff():
    config = _routed_config()
    skills = _resolve_skills(config, "", "claude-sonnet-4-6", diff=_MIXED_DIFF)
    names = {s.name for s in skills}
    assert names == {"workflow_security", "migration_safety"}


def test_routing_unmatched_file_falls_back():
    """Files not matching any route trigger the top-level skills list."""
    config = _routed_config()
    skills = _resolve_skills(config, "", "claude-sonnet-4-6", diff=_PYTHON_DIFF)
    names = {s.name for s in skills}
    # src/app.py doesn't match any route → falls back to all configured skills
    assert "change_completeness" in names


def test_routing_no_routes_runs_all():
    """No routing config → all configured skills run regardless of diff."""
    config = _config(["change_completeness", "workflow_security"])
    skills = _resolve_skills(config, "", "claude-sonnet-4-6", diff=_WORKFLOW_DIFF)
    names = {s.name for s in skills}
    assert names == {"change_completeness", "workflow_security"}


def test_max_turns_from_config():
    """Per-skill max_turns in sentinel.yml is passed to the skill instance."""
    config = SentinelConfig(
        skill_configs=[SkillConfig(name="change_completeness", max_turns=10)],
    )
    skills = _resolve_skills(config, "", "claude-sonnet-4-6")
    assert len(skills) == 1
    assert skills[0].max_turns == 10


def test_max_turns_default_when_not_set():
    """When max_turns is not set in config, skill uses its class default."""
    config = _config(["change_completeness"])
    skills = _resolve_skills(config, "", "claude-sonnet-4-6")
    assert len(skills) == 1
    assert skills[0].max_turns == 5  # ChangeCompletenessSkill default


def test_routing_empty_diff_runs_all():
    config = _routed_config()
    skills = _resolve_skills(config, "", "claude-sonnet-4-6", diff="")
    names = {s.name for s in skills}
    assert names == {"change_completeness", "workflow_security", "migration_safety"}


# -- exception isolation tests --

class _CrashingSkill(Skill):
    name = "crasher"
    def run(self, diff, context):
        raise RuntimeError("boom")


class _GoodSkill(Skill):
    name = "good"
    def run(self, diff, context):
        return [Finding(skill="good", severity=Severity.LOW,
                        title="found", message="m", suggestion="s")]


def test_failing_skill_does_not_block_others(monkeypatch):
    """A skill that raises should not prevent other skills from running."""
    config = _config(["change_completeness"])
    context = Context(repo="test", pr_number=0)

    # Patch _resolve_skills to return our test skills
    monkeypatch.setattr(
        "sentinel.runner._resolve_skills",
        lambda *a, **kw: [_CrashingSkill(), _GoodSkill()],
    )

    results = run_skills("fake diff", context, config)

    # Crasher should have an error finding with safe message (no raw exception)
    assert "crasher" in results
    assert len(results["crasher"]) == 1
    assert "exception" in results["crasher"][0].title.lower()
    assert "boom" not in results["crasher"][0].message  # raw exception not exposed

    # Good skill should have run successfully
    assert "good" in results
    assert len(results["good"]) == 1
    assert results["good"][0].title == "found"
