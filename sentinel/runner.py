"""Multi-skill runner.

Replaces the v0.1 hardcoded single-skill call with a framework that:
1. Reads sentinel.yml to determine which skills to run
2. Routes skills based on which files changed in the diff
3. Discovers built-in skills + custom skills from .sentinel/skills/
4. Handles cross-repo checkout for skills that opt in
5. Supports mode filtering (on_push vs on_merge)
6. Returns all findings tagged by skill name
"""
from __future__ import annotations

import os
import re

from sentinel.config import SentinelConfig
from sentinel.core import Context, Finding, Severity, Skill
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
    skills = _resolve_skills(config, context.repo_path, model, event_type, diff)

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
            try:
                findings = skill.run(diff, context)
            except Exception as exc:
                print(f"sentinel: {skill.name} → error: {exc}")
                results[skill.name] = [
                    Finding(
                        skill=skill.name,
                        severity=Severity.LOW,
                        title=f"Skill {skill.name} failed with an exception",
                        message=str(exc),
                        suggestion="Check the action logs for the full traceback.",
                    )
                ]
                continue
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


def _skills_for_diff(config: SentinelConfig, diff: str) -> set[str] | None:
    """Determine which skills to run based on changed files and routing rules.

    Returns None if no routing rules exist (run all configured skills).
    Returns a set of skill names when routing rules match changed files.
    For files that don't match any route, the top-level skills list applies.
    """
    if not config.routing:
        return None

    changed = _changed_files(diff)
    if not changed:
        return None

    matched_skills: set[str] = set()
    for path in changed:
        routed = config.skills_for_file(path)
        if routed:
            matched_skills.update(routed)
        else:
            # No route matched this file — fall back to top-level skills
            matched_skills.update(config.skills)

    return matched_skills


def _changed_files(diff: str) -> set[str]:
    """Extract file paths from a unified diff."""
    changed: set[str] = set()
    for line in diff.splitlines():
        if line.startswith("diff --git"):
            parts = line.split(" ")
            if len(parts) >= 4:
                changed.add(parts[-1].lstrip("b/"))
    return changed


def _resolve_skills(
    config: SentinelConfig, repo_path: str, model: str,
    event_type: str = "", diff: str = "",
) -> list[Skill]:
    """Build the list of skills to run from config + routing + discovery + mode filter."""
    # 1. Mode filter: which skills are allowed for this event type
    allowed_by_mode = set(config.skills_for_mode(event_type) if event_type else config.skills)

    # 2. Routing filter: which skills are relevant to the changed files
    routed = _skills_for_diff(config, diff)

    skills: list[Skill] = []
    seen: set[str] = set()

    # Built-in skills: must be in config, allowed by mode, and (if routing exists) routed
    for name in config.skills:
        if name not in allowed_by_mode:
            continue
        if routed is not None and name not in routed:
            continue
        cls = _BUILTIN_SKILLS.get(name)
        if cls and name not in seen:
            sc = config.skill_config(name)
            max_turns = sc.max_turns if sc else None
            skills.append(cls(model=model, max_turns=max_turns))
            seen.add(name)

    # Custom skills from .sentinel/skills/ in the target repo
    # Custom skills always run — they're opt-in by definition (added to the repo).
    # Routing only filters built-in skills; custom skills bypass it.
    if repo_path:
        custom = load_custom_skills(repo_path, model=model)
        if custom:
            print(f"sentinel: discovered {len(custom)} custom skill(s): {', '.join(cs.name for cs in custom)}")
        for cs in custom:
            if cs.name in seen:
                continue
            if event_type and cs.name not in allowed_by_mode:
                continue
            skills.append(cs)
            seen.add(cs.name)

    if routed is not None and skills:
        print(f"sentinel: routing → {', '.join(s.name for s in skills)} (based on changed files)")

    return skills
