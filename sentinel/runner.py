"""Multi-skill runner.

Replaces the v0.1 hardcoded single-skill call with a framework that:
1. Reads sentinel.yml to determine which skills to run
2. Discovers built-in skills + custom skills from .sentinel/skills/
3. Handles cross-repo checkout for skills that opt in
4. Supports mode filtering (on_push vs on_merge)
5. Returns all findings tagged by skill name
"""
from __future__ import annotations

import os

from sentinel.config import SentinelConfig
from sentinel.core import Context, Finding, Skill
from sentinel.cross_repo import checkout_repos, cleanup_repos
from sentinel.skills.change_completeness import ChangeCompletenessSkill
from sentinel.skills.custom import load_custom_skills
from sentinel.skills.migration_safety import MigrationSafetySkill
from sentinel.skills.workflow_security import WorkflowSecuritySkill

# Registry of built-in skills. New built-in skills are added here.
_BUILTIN_SKILLS: dict[str, type[Skill]] = {
    "change_completeness": ChangeCompletenessSkill,
    "workflow_security": WorkflowSecuritySkill,
    "migration_safety": MigrationSafetySkill,
}


def run_skills(
    diff: str,
    context: Context,
    config: SentinelConfig,
    model: str = "claude-sonnet-4-6",
    event_type: str = "",
) -> dict[str, list[Finding]]:
    """Run all configured skills and return findings grouped by skill name.

    Args:
        event_type: "push", "merge", or "" (run all). Controls mode filtering.

    Returns a dict: {"change_completeness": [...], "cost_attribution": [...]}
    """
    skills = _resolve_skills(config, context.repo_path, model, event_type)

    # Set up cross-repo search paths for skills that opt in
    cross_repo_paths: list[str] = []
    try:
        cross_repo_repos = _collect_cross_repos(config, [s.name for s in skills])
        if cross_repo_repos:
            token = os.environ.get("SENTINEL_CROSS_REPO_TOKEN", os.environ.get("GITHUB_TOKEN", ""))
            cross_repo_paths = checkout_repos(cross_repo_repos, token=token)
            if cross_repo_paths:
                context.extra_search_paths = cross_repo_paths
                print(f"sentinel: cross-repo search enabled for {len(cross_repo_paths)} repo(s)")

        results: dict[str, list[Finding]] = {}
        for skill in skills:
            print(f"sentinel: running {skill.name}...")
            findings = skill.run(diff, context)
            results[skill.name] = findings
            count = len(findings)
            if count:
                print(f"sentinel: {skill.name} → {count} finding(s)")
            else:
                print(f"sentinel: {skill.name} → clean")

        return results
    finally:
        if cross_repo_paths:
            cleanup_repos(cross_repo_paths)


def _collect_cross_repos(config: SentinelConfig, skill_names: list[str]) -> list[str]:
    """Gather all cross_repo entries from skills that will run."""
    repos: list[str] = []
    for name in skill_names:
        sc = config.skill_config(name)
        if sc and sc.cross_repo:
            for repo in sc.cross_repo:
                if repo not in repos:
                    repos.append(repo)
    return repos


def _resolve_skills(
    config: SentinelConfig, repo_path: str, model: str, event_type: str = "",
) -> list[Skill]:
    """Build the list of skills to run from config + discovery + mode filter."""
    # Determine which skill names are allowed for this event type
    allowed_names = config.skills_for_mode(event_type) if event_type else config.skills

    skills: list[Skill] = []

    # Built-in skills listed in config and allowed by mode
    for name in config.skills:
        if name not in allowed_names:
            continue
        cls = _BUILTIN_SKILLS.get(name)
        if cls:
            skills.append(cls(model=model))

    # Custom skills from .sentinel/skills/ in the target repo
    if repo_path:
        custom = load_custom_skills(repo_path, model=model)
        for cs in custom:
            if event_type and cs.name not in allowed_names:
                continue
            if cs.name not in config.skills:
                skills.append(cs)
            elif cs.name not in _BUILTIN_SKILLS:
                skills.append(cs)

    return skills
