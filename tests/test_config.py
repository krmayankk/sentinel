"""Tests for sentinel.config — YAML parsing, defaults, routing, per-skill config, mode."""
import os
import tempfile

from sentinel.config import SentinelConfig, SkillConfig, ModeConfig, load_config, _parse


def test_default_config():
    """Default config when no sentinel.yml exists."""
    with tempfile.TemporaryDirectory() as d:
        config = load_config(d)
        assert config.skills == ["change_completeness"]
        assert config.fail_on == []
        assert config.routing == []


def test_parse_minimal():
    config = _parse({})
    assert config.skills == ["change_completeness"]
    assert config.fail_on == []


def test_parse_full():
    config = _parse({
        "skills": ["change_completeness", "workflow_security"],
        "fail_on": ["critical", "high"],
        "routing": [
            {"pattern": "terraform/**", "skills": ["change_completeness"]},
        ],
    })
    assert config.skills == ["change_completeness", "workflow_security"]
    assert config.fail_on == ["critical", "high"]
    assert len(config.routing) == 1
    assert config.routing[0].pattern == "terraform/**"
    assert config.routing[0].skills == ["change_completeness"]


def test_parse_fail_on_string():
    """fail_on can be a comma-separated string or a list."""
    config = _parse({"fail_on": "critical,high"})
    assert config.fail_on == ["critical", "high"]


def test_routing_match():
    config = _parse({
        "routing": [
            {"pattern": "terraform/**", "skills": ["change_completeness"]},
            {"pattern": ".github/workflows/**", "skills": ["workflow_security"]},
        ],
    })
    assert config.skills_for_file("terraform/modules/rds/main.tf") == ["change_completeness"]
    assert config.skills_for_file(".github/workflows/ci.yml") == ["workflow_security"]
    assert config.skills_for_file("src/app.py") is None


def test_load_from_file():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "sentinel.yml"), "w") as f:
            f.write("skills: [change_completeness]\nfail_on: [critical]\n")
        config = load_config(d)
        assert config.skills == ["change_completeness"]
        assert config.fail_on == ["critical"]


def test_load_missing_file():
    with tempfile.TemporaryDirectory() as d:
        config = load_config(d)
        assert config.skills == ["change_completeness"]


# -- per-skill config (cross_repo) --

def test_parse_skill_as_dict():
    config = _parse({
        "skills": [
            {"change_completeness": {"cross_repo": ["my-org/consumer-service"]}},
        ],
    })
    assert config.skills == ["change_completeness"]
    sc = config.skill_config("change_completeness")
    assert sc is not None
    assert sc.cross_repo == ["my-org/consumer-service"]


def test_parse_skill_mixed_string_and_dict():
    config = _parse({
        "skills": [
            "workflow_security",
            {"change_completeness": {"cross_repo": ["org/repo-a", "org/repo-b"]}},
            "migration_safety",
        ],
    })
    assert config.skills == ["workflow_security", "change_completeness", "migration_safety"]
    assert config.skill_config("workflow_security").cross_repo == []
    assert config.skill_config("change_completeness").cross_repo == ["org/repo-a", "org/repo-b"]
    assert config.skill_config("migration_safety").cross_repo == []


def test_parse_cross_repo_with_repo_key():
    """cross_repo entries can be strings or dicts with a 'repo' key."""
    config = _parse({
        "skills": [
            {"change_completeness": {"cross_repo": [{"repo": "org/svc"}]}},
        ],
    })
    assert config.skill_config("change_completeness").cross_repo == ["org/svc"]


def test_parse_max_turns():
    config = _parse({
        "skills": [
            {"change_completeness": {"max_turns": 10}},
            "workflow_security",
        ],
    })
    assert config.skill_config("change_completeness").max_turns == 10
    assert config.skill_config("workflow_security").max_turns is None


def test_parse_max_turns_not_set():
    config = _parse({
        "skills": [
            {"change_completeness": {"cross_repo": ["org/repo"]}},
        ],
    })
    assert config.skill_config("change_completeness").max_turns is None


def test_skill_config_lookup_missing():
    config = _parse({"skills": ["change_completeness"]})
    assert config.skill_config("nonexistent") is None


def test_backward_compat_string_skills():
    """Plain string skills still work exactly as before."""
    config = _parse({"skills": ["change_completeness", "workflow_security"]})
    assert config.skills == ["change_completeness", "workflow_security"]
    for name in config.skills:
        sc = config.skill_config(name)
        assert sc is not None
        assert sc.cross_repo == []


# -- mode config --

def test_parse_mode():
    config = _parse({
        "skills": ["change_completeness", "migration_safety"],
        "mode": {
            "on_push": ["change_completeness"],
            "on_merge": ["migration_safety"],
        },
    })
    assert config.mode.on_push == ["change_completeness"]
    assert config.mode.on_merge == ["migration_safety"]


def test_skills_for_mode_push():
    config = _parse({
        "skills": ["change_completeness", "migration_safety"],
        "mode": {
            "on_push": ["change_completeness"],
            "on_merge": ["migration_safety"],
        },
    })
    assert config.skills_for_mode("push") == ["change_completeness"]


def test_skills_for_mode_merge():
    config = _parse({
        "skills": ["change_completeness", "migration_safety"],
        "mode": {
            "on_push": ["change_completeness"],
            "on_merge": ["migration_safety"],
        },
    })
    assert config.skills_for_mode("merge") == ["migration_safety"]


def test_skills_for_mode_empty_returns_all():
    config = _parse({
        "skills": ["change_completeness", "migration_safety"],
        "mode": {
            "on_push": ["change_completeness"],
            "on_merge": ["migration_safety"],
        },
    })
    assert config.skills_for_mode("") == ["change_completeness", "migration_safety"]


def test_skills_for_mode_no_config_returns_all():
    config = _parse({"skills": ["change_completeness", "migration_safety"]})
    assert config.skills_for_mode("push") == ["change_completeness", "migration_safety"]


# -- telemetry config --

def test_telemetry_disabled_by_default():
    config = _parse({})
    assert config.telemetry.enabled is False
    assert config.telemetry.path == ".sentinel/telemetry"


def test_telemetry_enabled_with_default_path():
    config = _parse({"telemetry": {"enabled": True}})
    assert config.telemetry.enabled is True
    assert config.telemetry.path == ".sentinel/telemetry"


def test_telemetry_custom_path():
    config = _parse({
        "telemetry": {"enabled": True, "path": "/var/lib/sentinel/events"},
    })
    assert config.telemetry.path == "/var/lib/sentinel/events"


def test_telemetry_block_with_only_path_stays_disabled():
    """Forgetting enabled: true is a no-op; opt-in must be explicit."""
    config = _parse({"telemetry": {"path": "/tmp/sentinel"}})
    assert config.telemetry.enabled is False


def test_telemetry_null_block_uses_defaults():
    """telemetry: null in YAML must not crash."""
    config = _parse({"telemetry": None})
    assert config.telemetry.enabled is False
    assert config.telemetry.path == ".sentinel/telemetry"
