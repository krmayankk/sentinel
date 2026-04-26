"""Custom skills loaded from markdown prompt files.

A team writes .sentinel/skills/cost_attribution.md in their repo.
This module wraps that prompt into a Skill that the runner executes
through the same agentic pipeline as built-in skills.

Custom skills support optional YAML frontmatter for configuration:

    ---
    max_turns: 3
    ---
    Check that every new AWS resource has a cost_center tag...

Without frontmatter, custom skills default to max_turns=3 (light exploration).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from sentinel.core import Context
from sentinel.skills.base import LLMSkill, _RESPONSE_FORMAT

_WRAPPER = """\
You are a code reviewer checking a pull request diff.

## Your judgment check
{skill_prompt}

You have access to tools to explore the codebase. Use them to verify your \
hypotheses — grep for references, read files to check registrations or \
configurations, list directories to confirm expected files exist. Base your \
findings on evidence from the actual codebase, not speculation.

{custom_rules_section}\
## Diff
{diff}

## Instructions
- Use the available tools to verify before reporting.
- Only report gaps that will cause a concrete, demonstrable problem.
- Include evidence from the codebase in your findings.
- Reference exact file paths and line numbers.
- Return findings ordered by severity, most severe first.

""" + _RESPONSE_FORMAT

_CUSTOM_RULES_SECTION = """\
## Custom rules for this repo
{rules}

"""


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter from a markdown file.

    Returns (config_dict, remaining_text).
    If no frontmatter, returns ({}, original_text).
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        return {}, text

    frontmatter = match.group(1)
    body = text[match.end():]
    config: dict = {}
    for line in frontmatter.splitlines():
        line = line.strip()
        if ":" in line and not line.startswith("#"):
            key, _, value = line.partition(":")
            value = value.strip()
            # Parse simple types
            if value.isdigit():
                config[key.strip()] = int(value)
            elif value.lower() in ("true", "false"):
                config[key.strip()] = value.lower() == "true"
            else:
                config[key.strip()] = value
    return config, body


class CustomSkill(LLMSkill):
    """A skill defined by a markdown prompt file."""

    def __init__(self, name: str, prompt_text: str, model: str = "claude-sonnet-4-6",
                 max_turns: int = 3) -> None:
        super().__init__(model=model, max_turns=max_turns)
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
        raw_text = path.read_text().strip()
        if not raw_text:
            continue
        config, prompt_text = _parse_frontmatter(raw_text)
        name = path.stem  # cost_attribution.md → cost_attribution
        max_turns = config.get("max_turns", 3)
        skills.append(CustomSkill(name=name, prompt_text=prompt_text, model=model,
                                  max_turns=max_turns))

    return skills
