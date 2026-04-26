from __future__ import annotations

from sentinel.core import Context
from sentinel.skills.base import LLMSkill, _RESPONSE_FORMAT

_PROMPT = """\
You are reviewing a pull request for breaking API changes.

Check that when a public API endpoint changes its request or response schema,
the API version has been bumped and backward compatibility is maintained.

{custom_rules_section}\
## Diff
{diff}

""" + _RESPONSE_FORMAT


class APIBreakingChangeSkill(LLMSkill):
    name = "api_breaking_change"

    def _build_prompt(self, diff: str, context: Context) -> str:
        custom_rules_section = ""
        if context.instructions.strip():
            custom_rules_section = context.instructions.strip() + "\n\n"
        return _PROMPT.replace("{diff}", diff).replace(
            "{custom_rules_section}", custom_rules_section
        )
