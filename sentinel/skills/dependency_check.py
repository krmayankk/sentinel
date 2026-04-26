from __future__ import annotations

from sentinel.core import Context
from sentinel.skills.base import LLMSkill, _RESPONSE_FORMAT

_PROMPT = """\
You are reviewing a pull request for dependency issues.

Check that when a dependency is added or upgraded, it is compatible with
the existing dependency tree and does not introduce known vulnerabilities.

{custom_rules_section}\
## Diff
{diff}

""" + _RESPONSE_FORMAT


class DependencyCheckSkill(LLMSkill):
    name = "dependency_check"

    def _build_prompt(self, diff: str, context: Context) -> str:
        custom_rules_section = ""
        if context.instructions.strip():
            custom_rules_section = context.instructions.strip() + "\n\n"
        return _PROMPT.replace("{diff}", diff).replace(
            "{custom_rules_section}", custom_rules_section
        )
