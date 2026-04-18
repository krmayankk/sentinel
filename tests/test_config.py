"""Tests for sentinel.config — YAML parsing, defaults, routing."""
import os
import tempfile

from sentinel.config import SentinelConfig, load_config, _parse


def test_default_config():
    config = load_config("")
    assert config.skills == ["change_completeness"]
    assert config.fail_on == []
    assert config.routing == []


def test_parse_minimal():
    config = _parse({})
    assert config.skills == ["change_completeness"]
    assert config.fail_on == []


def test_parse_full():
    config = _parse({
        "skills": ["change_completeness", "contract_drift"],
        "fail_on": ["critical", "high"],
        "routing": [
            {"pattern": "terraform/**", "skills": ["change_completeness"]},
        ],
    })
    assert config.skills == ["change_completeness", "contract_drift"]
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
