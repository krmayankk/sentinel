from __future__ import annotations

from sentinel.core import Context
from sentinel.skills.base import LLMSkill, _RESPONSE_FORMAT

_PROMPT = """\
You are reviewing a pull request diff for change completeness.

Your job: identify changes that are incomplete — where the author changed X but \
did not update Y, creating a gap that will cause a build failure, runtime error, \
data inconsistency, or operational incident.

You have access to tools to explore the codebase. Use them to verify your \
hypotheses — grep for callers of changed functions, read files to check \
registrations, list directories to confirm test files exist. Base your \
findings on evidence from the actual codebase, not speculation.

## Severity guide
- critical: will cause data loss, security vulnerability, or production outage
- high: will cause a build failure, deployment error, or runtime crash
- medium: degraded or broken functionality that is not immediately fatal
- low: inconsistency that should be fixed but has no immediate consequence

## What to check

**Interface completeness**
- Function or method signature changed → use grep to find all call sites. Are they updated?
- Public symbol renamed or removed → grep for the old name. Any remaining references?
- Struct or class field added or removed → are constructors and usages consistent?

**Configuration completeness**
- Terraform variable added, removed, or renamed → grep for the variable name across envs/
- Required environment variable added → is it referenced in deployment configs?
- Configuration key renamed or removed → grep for the old key name

**Schema completeness**
- Database column added, removed, or renamed → are the ORM model, migration, \
rollback migration, and application references all consistent?
- Proto, Thrift, or Avro schema changed → is the generated client code updated?
- OpenAPI spec changed → are generated clients or integration tests updated?

**Operational completeness**
- New Kubernetes workload or service introduced → is there a runbook, alert rule, \
or dashboard config?
- New required secret or credential introduced → is it referenced in the secret \
store config or deployment manifest?

{custom_rules_section}\
## Diff
{diff}

## Instructions
- VERIFY BEFORE REPORTING. Every finding must be backed by tool evidence. \
If you think a registration exists, read the file to confirm. If you think \
a test file exists, list the directory or grep for it. Do NOT use words like \
"likely", "probably", or "may" — if you haven't confirmed it with a tool, \
it is not a finding.
- CRITICAL: If your investigation CONFIRMS the code is correct (e.g. you \
grepped and found the function exists, or read the file and the wiring is \
present), do NOT file a finding. A confirmed-correct check is a success, \
not a finding. Only file findings for confirmed gaps — things you verified \
are actually missing or broken.
- Only report gaps that will cause a concrete, demonstrable problem.
- Include the tool evidence in your findings (e.g. "read runner.py and confirmed \
3 callers of old_name that were not updated").
- Reference exact file paths and line numbers.
- Return findings ordered by severity, most severe first.

""" + _RESPONSE_FORMAT

_CUSTOM_RULES_SECTION = """\
## Custom completeness rules for this repo
{rules}

"""


class ChangeCompletenessSkill(LLMSkill):
    """Checks that a change is complete — consistent across all the places
    that depend on what changed.

    Uses agentic tool-use loop: the LLM explores the codebase with grep,
    read_file, and list_files to verify its hypotheses. Findings are based
    on evidence from the actual code, not speculation.
    """

    name = "change_completeness"
    max_turns = 5

    def _build_prompt(self, diff: str, context: Context) -> str:
        custom_rules_section = ""
        if context.instructions.strip():
            custom_rules_section = _CUSTOM_RULES_SECTION.replace(
                "{rules}", context.instructions.strip()
            )
        return _PROMPT.replace("{diff}", diff).replace(
            "{custom_rules_section}", custom_rules_section
        )
