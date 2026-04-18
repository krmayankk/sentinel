from __future__ import annotations

from sentinel.core import Context
from sentinel.skills.base import LLMSkill, _RESPONSE_FORMAT

_PROMPT = """\
You are reviewing a pull request diff for change completeness.

Your job: identify changes that are incomplete — where the author changed X but \
did not update Y, creating a gap that will cause a build failure, runtime error, \
data inconsistency, or operational incident.

## Severity guide
- high: will cause a build failure, deployment error, or runtime crash
- medium: degraded or broken functionality that is not immediately fatal
- low: inconsistency that should be fixed but has no immediate consequence

## What to check

**Interface completeness**
- Function or method signature changed → are all call sites in this diff updated?
- Public symbol renamed or removed → are all references updated?
- Struct or class field added or removed → are constructors and usages consistent?

**Configuration completeness**
- Terraform variable added, removed, or renamed → are all module callers updated?
- Required environment variable added → is it referenced in deployment configs, \
Helm values, and documentation?
- Configuration key renamed or removed → are all consumers updated?

**Schema completeness**
- Database column added, removed, or renamed → are the ORM model, migration, \
rollback migration, and application references all consistent?
- Proto, Thrift, or Avro schema changed → is the generated client code \
regenerated and included in this diff?
- OpenAPI spec changed → are generated clients or integration tests updated?

**Operational completeness**
- New Kubernetes workload or service introduced → is there a runbook, alert rule, \
or dashboard config in this diff?
- New required secret or credential introduced → is it referenced in the secret \
store config or deployment manifest?

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
## Custom completeness rules for this repo
{rules}

"""


class ChangeCompletenessSkill(LLMSkill):
    """Checks that a change is complete — consistent across all the places
    that depend on what changed.

    When context.repo_path is set, suspected gaps are verified by searching
    the actual codebase. Findings are only reported when callers are confirmed
    to exist, eliminating speculation.
    """

    name = "change_completeness"

    def _build_prompt(self, diff: str, context: Context) -> str:
        custom_rules_section = ""
        if context.instructions.strip():
            custom_rules_section = _CUSTOM_RULES_SECTION.format(
                rules=context.instructions.strip()
            )
        return _PROMPT.format(diff=diff, custom_rules_section=custom_rules_section)
