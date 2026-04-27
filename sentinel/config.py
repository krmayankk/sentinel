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
class SkillConfig:
    name: str
    cross_repo: list[str] = field(default_factory=list)
    max_turns: int | None = None  # None = use skill's default


@dataclass
class ModeConfig:
    on_push: list[str] = field(default_factory=list)
    on_merge: list[str] = field(default_factory=list)


@dataclass
class SentinelConfig:
    skill_configs: list[SkillConfig] = field(default_factory=lambda: [SkillConfig(name="change_completeness")])
    fail_on: list[str] = field(default_factory=list)
    routing: list[Route] = field(default_factory=list)
    mode: ModeConfig = field(default_factory=ModeConfig)

    @property
    def skills(self) -> list[str]:
        """Backward-compatible list of skill names."""
        return [sc.name for sc in self.skill_configs]

    def skill_config(self, name: str) -> SkillConfig | None:
        for sc in self.skill_configs:
            if sc.name == name:
                return sc
        return None

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

    def skills_for_mode(self, event_type: str) -> list[str]:
        """Return skill names filtered by execution mode.

        Returns all skills if no mode config exists or event_type is empty.
        """
        if not event_type or (not self.mode.on_push and not self.mode.on_merge):
            return self.skills

        if event_type == "push":
            return self.mode.on_push
        elif event_type == "merge":
            return self.mode.on_merge
        return self.skills


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
    raw_skills = raw.get("skills", ["change_completeness"])
    fail_on = raw.get("fail_on", [])

    # Normalize fail_on: accept both "critical,high" string and ["critical", "high"] list
    if isinstance(fail_on, str):
        fail_on = [s.strip() for s in fail_on.split(",") if s.strip()]

    # Parse skills: accept both strings and dicts with per-skill config
    skill_configs = []
    for entry in raw_skills:
        if isinstance(entry, str):
            skill_configs.append(SkillConfig(name=entry))
        elif isinstance(entry, dict):
            for name, opts in entry.items():
                opts = opts or {}
                cross_repo = [r if isinstance(r, str) else r.get("repo", "") for r in opts.get("cross_repo", [])]
                cross_repo = [r for r in cross_repo if r]
                max_turns = opts.get("max_turns")
                skill_configs.append(SkillConfig(name=name, cross_repo=cross_repo, max_turns=max_turns))

    skill_names = [sc.name for sc in skill_configs]

    routing = []
    for r in raw.get("routing", []):
        routing.append(Route(
            pattern=r["pattern"],
            skills=r.get("skills", skill_names),
            fail_on=r.get("fail_on", []),
        ))

    # Parse mode config
    raw_mode = raw.get("mode", {})
    mode = ModeConfig(
        on_push=raw_mode.get("on_push", []),
        on_merge=raw_mode.get("on_merge", []),
    )

    return SentinelConfig(skill_configs=skill_configs, fail_on=fail_on, routing=routing, mode=mode)
