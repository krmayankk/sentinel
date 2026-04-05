from __future__ import annotations

import json
import re
import subprocess

import anthropic

from sentinel.core import Context, Finding, Severity, Skill

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

## Response
Return valid JSON only — no prose, no markdown fences:
{{
  "findings": [
    {{
      "severity": "high|medium|low",
      "title": "short descriptive title",
      "message": "what is missing and why it matters, with exact file paths from the diff",
      "suggestion": "concrete step to resolve this",
      "file": "path/to/the/changed/file",
      "line": 0,
      "search_for": "exact string to grep for in the repo, or empty string if not applicable"
    }}
  ],
  "summary": "one sentence — what was found or confirmed complete"
}}
"""

_CUSTOM_RULES_SECTION = """\
## Custom completeness rules for this repo
{rules}

"""


class ChangeCompletenessSkill(Skill):
    """Checks that a change is complete — consistent across all the places
    that depend on what changed.

    When context.repo_path is set, suspected gaps are verified by searching
    the actual codebase. Findings are only reported when callers are confirmed
    to exist, eliminating speculation.
    """

    name = "change_completeness"

    def __init__(self, model: str = "claude-sonnet-4-6", max_tokens: int = 1024) -> None:
        self._client = anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens

    def run(self, diff: str, context: Context) -> list[Finding]:
        prompt = self._build_prompt(diff, context)
        raw = self._call_llm(prompt)
        findings = self._parse(raw)

        if context.repo_path:
            findings = self._verify(findings, context.repo_path, diff=diff)

        return findings

    # -- private --

    def _build_prompt(self, diff: str, context: Context) -> str:
        custom_rules_section = ""
        if context.claude_md.strip():
            custom_rules_section = _CUSTOM_RULES_SECTION.format(
                rules=context.claude_md.strip()
            )
        return _PROMPT.format(diff=diff, custom_rules_section=custom_rules_section)

    def _call_llm(self, prompt: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def _parse(self, raw: str) -> list[Finding]:
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return [
                Finding(
                    skill=self.name,
                    severity=Severity.LOW,
                    title="Sentinel could not parse the model response",
                    message="The model returned a response that is not valid JSON.",
                    suggestion="Check the raw model output in the action logs.",
                )
            ]

        findings: list[Finding] = []
        for item in data.get("findings", []):
            try:
                findings.append(
                    Finding(
                        skill=self.name,
                        severity=Severity(item["severity"]),
                        title=item["title"],
                        message=item["message"],
                        suggestion=item["suggestion"],
                        file=item.get("file", ""),
                        line=item.get("line", 0),
                        search_for=item.get("search_for", ""),
                    )
                )
            except (KeyError, ValueError):
                continue

        return findings

    def _verify(self, findings: list[Finding], repo_path: str, diff: str = "") -> list[Finding]:
        """For each finding that has a search term, grep the repo.

        - Callers found   → finding confirmed; message updated with exact files;
                            severity elevated to high if it was lower (confirmed
                            breakage is always at least high)
        - No callers found → finding dismissed (change was actually complete)
        - No search term  → finding passes through as-is
        """
        changed_files = _changed_files(diff)
        verified: list[Finding] = []

        for f in findings:
            if not f.search_for:
                verified.append(f)
                continue

            matches = _grep(f.search_for, repo_path, exclude_files=changed_files)
            if not matches:
                continue  # search confirms no affected callers — dismiss

            file_list = "\n".join(f"  - {m}" for m in matches)
            f.message = (
                f"{f.message}\n\n"
                f"Confirmed: found {len(matches)} caller(s) in the codebase "
                f"that will break:\n{file_list}"
            )
            # A confirmed breaking change is at least high severity.
            if f.severity not in (Severity.CRITICAL, Severity.HIGH):
                f.severity = Severity.HIGH

            verified.append(f)

        return verified


def _grep(term: str, repo_path: str, exclude_files: set[str] | None = None) -> list[str]:
    """Return file:line matches for term within repo_path.

    Files that are part of the diff itself are excluded — they are the source
    of the change, not callers that need to be updated.
    """
    result = subprocess.run(
        ["grep", "-rn", "--exclude-dir=.git", term, "."],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):  # 1 = no matches, anything else is an error
        return []

    matches = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        # line format: "./path/to/file.tf:12:content"
        file_path = line.split(":")[0].lstrip("./")
        if exclude_files and file_path in exclude_files:
            continue
        matches.append(line)

    return matches


def _changed_files(diff: str) -> set[str]:
    """Extract the set of file paths changed in the diff.

    These are excluded from grep results — they are the files being updated,
    not callers that need attention.
    """
    changed: set[str] = set()
    for line in diff.splitlines():
        # "diff --git a/terraform/modules/rds/variables.tf b/terraform/modules/rds/variables.tf"
        if line.startswith("diff --git"):
            parts = line.split(" ")
            if len(parts) >= 4:
                # strip the leading "b/" prefix
                changed.add(parts[-1].lstrip("b/"))
    return changed
