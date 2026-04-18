"""Multi-skill runner.

Replaces the v0.1 hardcoded single-skill call with a framework that:
1. Reads sentinel.yml to determine which skills to run
2. Discovers built-in skills + custom skills from .sentinel/skills/
3. Runs matched skills against the diff
4. Returns all findings tagged by skill name
"""
from __future__ import annotations

from sentinel.config import SentinelConfig
from sentinel.core import Context, Finding, Skill
from sentinel.skills.change_completeness import ChangeCompletenessSkill
from sentinel.skills.custom import load_custom_skills

# Registry of built-in skills. New built-in skills are added here.
_BUILTIN_SKILLS: dict[str, type[Skill]] = {
    "change_completeness": ChangeCompletenessSkill,
}


def run_skills(
    diff: str,
    context: Context,
    config: SentinelConfig,
    model: str = "claude-sonnet-4-6",
) -> dict[str, list[Finding]]:
    """Run all configured skills and return findings grouped by skill name.

    Returns a dict: {"change_completeness": [...], "cost_attribution": [...]}
    """
    skills = _resolve_skills(config, context.repo_path, model)

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


def _resolve_skills(
    config: SentinelConfig, repo_path: str, model: str
) -> list[Skill]:
    """Build the list of skills to run from config + discovery."""
    skills: list[Skill] = []

    # Built-in skills listed in config
    for name in config.skills:
        cls = _BUILTIN_SKILLS.get(name)
        if cls:
            skills.append(cls(model=model))

    # Custom skills from .sentinel/skills/ in the target repo
    if repo_path:
        custom = load_custom_skills(repo_path, model=model)
        # Only include custom skills that are listed in config.skills,
        # OR include all of them if config.skills doesn't filter customs
        # (a custom skill exists = team wants it to run)
        for cs in custom:
            if cs.name not in config.skills:
                # Custom skill not explicitly listed — include it anyway.
                # The team put the file there; they want it to run.
                skills.append(cs)
            elif cs.name not in _BUILTIN_SKILLS:
                # Listed in config and not a built-in — it's a custom skill reference
                skills.append(cs)

    return skills
