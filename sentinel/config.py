from __future__ import annotations

import os
from dataclasses import dataclass, field

import yaml


@dataclass
class Route:
    pattern: str
    skills: list[str]
    fail_on: list[str] = field(default_factory=list)


@dataclass
class SentinelConfig:
    skills: list[str] = field(default_factory=lambda: ["change_completeness"])
    fail_on: list[str] = field(default_factory=list)
    routing: list[Route] = field(default_factory=list)

    def skills_for_file(self, path: str) -> list[str] | None:
        """Return the skill list for a file path based on routing rules.

        Returns None if no routing rule matches (caller should use the
        top-level skills list).
        """
        from fnmatch import fnmatch

        for route in self.routing:
            if fnmatch(path, route.pattern):
                return route.skills
        return None


def load_config(repo_path: str = "") -> SentinelConfig:
    """Load sentinel.yml from the repo root.

    Returns default config when the file does not exist — backward
    compatible with v0.1 repos that have no sentinel.yml.
    """
    candidates = [
        os.path.join(repo_path, "sentinel.yml") if repo_path else "sentinel.yml",
        os.path.join(repo_path, ".sentinel.yml") if repo_path else ".sentinel.yml",
    ]

    for path in candidates:
        if os.path.isfile(path):
            with open(path) as f:
                raw = yaml.safe_load(f) or {}
            return _parse(raw)

    return SentinelConfig()


def _parse(raw: dict) -> SentinelConfig:
    skills = raw.get("skills", ["change_completeness"])
    fail_on = raw.get("fail_on", [])

    # Normalize fail_on: accept both "critical,high" string and ["critical", "high"] list
    if isinstance(fail_on, str):
        fail_on = [s.strip() for s in fail_on.split(",") if s.strip()]

    routing = []
    for r in raw.get("routing", []):
        routing.append(Route(
            pattern=r["pattern"],
            skills=r.get("skills", skills),
            fail_on=r.get("fail_on", []),
        ))

    return SentinelConfig(skills=skills, fail_on=fail_on, routing=routing)
