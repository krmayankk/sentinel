"""Shared LLM+grep verification pipeline used by all skills."""
from __future__ import annotations

import abc
import json
import re
import subprocess

import anthropic

from sentinel.core import Context, Finding, Severity, Skill

_RESPONSE_FORMAT = """\
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

_EXCLUDE_DIRS = [
    ".git", ".venv", "venv", "node_modules", "dist", "build",
    "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    ".sentinel-action",
]


class LLMSkill(Skill):
    """Base class for skills that use the LLM → parse → grep verify pipeline.

    Subclasses implement _build_prompt(). Everything else is shared.
    """

    def __init__(self, model: str = "claude-sonnet-4-6", max_tokens: int = 1024) -> None:
        self._client = anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens

    @abc.abstractmethod
    def _build_prompt(self, diff: str, context: Context) -> str: ...

    def run(self, diff: str, context: Context) -> list[Finding]:
        prompt = self._build_prompt(diff, context)
        raw = self._call_llm(prompt)
        findings = self._parse(raw)

        if context.repo_path:
            findings = _verify(findings, self.name, context.repo_path, diff=diff)

        return findings

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


def _verify(
    findings: list[Finding], skill_name: str, repo_path: str, diff: str = ""
) -> list[Finding]:
    """For each finding with a search term, grep the repo to confirm or dismiss."""
    changed_files = _changed_files(diff)
    verified: list[Finding] = []

    for f in findings:
        if not f.search_for:
            verified.append(f)
            continue

        matches = _grep(f.search_for, repo_path, exclude_files=changed_files)
        if not matches:
            continue  # no callers found — dismiss

        file_list = "\n".join(f"  - {m}" for m in matches)
        f.message = (
            f"{f.message}\n\n"
            f"Confirmed: found {len(matches)} caller(s) in the codebase "
            f"that will break:\n{file_list}"
        )
        if f.severity not in (Severity.CRITICAL, Severity.HIGH):
            f.severity = Severity.HIGH

        verified.append(f)

    return verified


def _grep(term: str, repo_path: str, exclude_files: set[str] | None = None) -> list[str]:
    exclude_args = [f"--exclude-dir={d}" for d in _EXCLUDE_DIRS]
    result = subprocess.run(
        ["grep", "-rn", *exclude_args, term, "."],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        return []

    matches = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        file_path = line.split(":")[0].lstrip("./")
        if exclude_files and file_path in exclude_files:
            continue
        matches.append(line)

    return matches


def _changed_files(diff: str) -> set[str]:
    changed: set[str] = set()
    for line in diff.splitlines():
        if line.startswith("diff --git"):
            parts = line.split(" ")
            if len(parts) >= 4:
                changed.add(parts[-1].lstrip("b/"))
    return changed
