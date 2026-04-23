"""Custom skills loaded from markdown prompt files.

A team writes .sentinel/skills/cost_attribution.md in their repo.
This module wraps that prompt into a Skill that the runner executes
through the same LLM+grep pipeline as built-in skills.
"""
from __future__ import annotations

import os
from pathlib import Path

from sentinel.core import Context
from sentinel.skills.base import LLMSkill, _RESPONSE_FORMAT

_WRAPPER = """\
You are a code reviewer checking a pull request diff.

## Your judgment check
{skill_prompt}

{custom_rules_section}\
## Diff
{diff}

## Instructions
- Only report gaps that will cause a concrete, demonstrable problem.
- If a dependent file is not in this diff and you suspect it should be, set \
`search_for` to the exact string that would appear in any affected caller or \
consumer — the search will be run against the actual codebase to confirm.
- Reference exact file paths and line numbers visible in the diff.
- Return findings ordered by severity, most severe first.

""" + _RESPONSE_FORMAT

_CUSTOM_RULES_SECTION = """\
## Custom rules for this repo
{rules}

"""


class CustomSkill(LLMSkill):
    """A skill defined by a markdown prompt file."""

    def __init__(self, name: str, prompt_text: str, model: str = "claude-sonnet-4-6") -> None:
        super().__init__(model=model)
        self.name = name
        self._prompt_text = prompt_text

    def _build_prompt(self, diff: str, context: Context) -> str:
        custom_rules_section = ""
        if context.instructions.strip():
            custom_rules_section = _CUSTOM_RULES_SECTION.replace(
                "{rules}", context.instructions.strip()
            )
        return (_WRAPPER
            .replace("{skill_prompt}", self._prompt_text)
            .replace("{diff}", diff)
            .replace("{custom_rules_section}", custom_rules_section)
        )


def load_custom_skills(repo_path: str, model: str = "claude-sonnet-4-6") -> list[CustomSkill]:
    """Load all .md files from .sentinel/skills/ in the target repo."""
    skills_dir = os.path.join(repo_path, ".sentinel", "skills")
    if not os.path.isdir(skills_dir):
        return []

    skills = []
    for path in sorted(Path(skills_dir).glob("*.md")):
        name = path.stem  # cost_attribution.md → cost_attribution
        prompt_text = path.read_text().strip()
        if prompt_text:
            skills.append(CustomSkill(name=name, prompt_text=prompt_text, model=model))

    return skills
