"""Shared agentic skill pipeline used by all skills.

Every skill is an agent. The diff is the first input. The LLM can explore
the codebase with tools (grep, read_file, list_files) before producing
findings. max_turns controls how deep the exploration goes:

  max_turns=0  → diff-only, single LLM call, no tools
  max_turns=3  → light exploration (one grep, read a couple of files)
  max_turns=10 → deep analysis (follow dependency chains)

The LLM decides whether to use tools based on what it sees in the diff.
If it's confident from the diff alone, it returns findings immediately.
"""
from __future__ import annotations

import abc
import json
import os
import re
import subprocess

import anthropic

from sentinel.core import Context, Finding, Severity, Skill

def _extract_json(raw: str) -> dict | None:
    """Extract a JSON object from a model response, handling common LLM quirks.

    Tries in order:
    1. Direct parse (response is pure JSON)
    2. Strip markdown fences (```json ... ```)
    3. Find first { ... } block in the response
    """
    text = raw.strip()

    # 1. Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Strip markdown fences
    fenced = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    fenced = re.sub(r"\s*```\s*$", "", fenced, flags=re.MULTILINE)
    try:
        return json.loads(fenced)
    except json.JSONDecodeError:
        pass

    # 3. Find the first JSON object in the response
    brace_start = text.find("{")
    if brace_start >= 0:
        depth = 0
        for i in range(brace_start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[brace_start:i + 1])
                    except json.JSONDecodeError:
                        break

    return None


_RESPONSE_FORMAT = """\
## Response
Return valid JSON only — no prose, no markdown fences:
{
  "findings": [
    {
      "severity": "high|medium|low|critical",
      "title": "short descriptive title",
      "message": "what is missing and why it matters, with exact file paths",
      "suggestion": "concrete step to resolve this",
      "file": "path/to/the/changed/file",
      "line": 0
    }
  ],
  "summary": "one sentence — what was found or confirmed complete"
}
"""

_EXCLUDE_DIRS = [
    ".git", ".venv", "venv", "node_modules", "dist", "build",
    "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    ".sentinel-action",
]

# -- Tool definitions for the agentic loop --

_TOOLS = [
    {
        "name": "grep",
        "description": (
            "Search for a string or pattern in the repository. "
            "Returns matching lines with file paths and line numbers. "
            "Use this to find callers, references, registrations, or any code "
            "that depends on what changed in the diff."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The string or pattern to search for",
                },
                "path": {
                    "type": "string",
                    "description": "Subdirectory to search in (relative to repo root). Default: search entire repo.",
                    "default": ".",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "read_file",
        "description": (
            "Read the contents of a file in the repository. "
            "Use this to see full context around a grep match, check if something "
            "is registered, or read a config file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to repo root",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_files",
        "description": (
            "List files in a directory. Use this to check if a file exists "
            "(e.g. a test file, a fixture directory, a config file)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path relative to repo root. Default: repo root.",
                    "default": ".",
                },
            },
            "required": ["path"],
        },
    },
]

_MAX_GREP_RESULTS = 30
_MAX_FILE_SIZE = 15000  # chars


def _execute_tool(
    tool_name: str,
    tool_input: dict,
    search_paths: list[str],
) -> str:
    """Execute a tool call against the repo and return the result as a string."""
    if tool_name == "grep":
        return _tool_grep(tool_input["pattern"], tool_input.get("path", "."), search_paths)
    elif tool_name == "read_file":
        return _tool_read_file(tool_input["path"], search_paths)
    elif tool_name == "list_files":
        return _tool_list_files(tool_input.get("path", "."), search_paths)
    else:
        return f"Unknown tool: {tool_name}"


def _tool_grep(pattern: str, path: str, search_paths: list[str]) -> str:
    """Grep across all search paths."""
    all_matches: list[str] = []
    for repo_path in search_paths:
        search_dir = os.path.join(repo_path, path) if path != "." else repo_path
        if not os.path.isdir(search_dir):
            continue
        exclude_args = [f"--exclude-dir={d}" for d in _EXCLUDE_DIRS]
        result = subprocess.run(
            ["grep", "-rn", *exclude_args, pattern, "."],
            cwd=search_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.strip():
                    all_matches.append(line.lstrip("./"))
    if not all_matches:
        return f"No matches found for '{pattern}'"
    if len(all_matches) > _MAX_GREP_RESULTS:
        return "\n".join(all_matches[:_MAX_GREP_RESULTS]) + f"\n... ({len(all_matches) - _MAX_GREP_RESULTS} more matches)"
    return "\n".join(all_matches)


def _tool_read_file(path: str, search_paths: list[str]) -> str:
    """Read a file from the first search path where it exists."""
    for repo_path in search_paths:
        full_path = os.path.join(repo_path, path)
        if os.path.isfile(full_path):
            try:
                content = open(full_path).read()
                if len(content) > _MAX_FILE_SIZE:
                    return content[:_MAX_FILE_SIZE] + f"\n... (truncated, {len(content)} chars total)"
                return content
            except Exception as e:
                return f"Error reading {path}: {e}"
    return f"File not found: {path}"


def _tool_list_files(path: str, search_paths: list[str]) -> str:
    """List files in a directory across search paths."""
    all_entries: list[str] = []
    for repo_path in search_paths:
        full_path = os.path.join(repo_path, path) if path != "." else repo_path
        if os.path.isdir(full_path):
            for entry in sorted(os.listdir(full_path)):
                entry_path = os.path.join(full_path, entry)
                suffix = "/" if os.path.isdir(entry_path) else ""
                if entry not in _EXCLUDE_DIRS:
                    all_entries.append(f"{entry}{suffix}")
    if not all_entries:
        return f"Directory not found or empty: {path}"
    return "\n".join(all_entries)


class LLMSkill(Skill):
    """Base class for all skills. Every skill is an agentic loop.

    The diff is the first input. The LLM can call grep, read_file, and
    list_files to explore the codebase. max_turns controls how many
    tool-use rounds are allowed. The LLM decides whether to use tools
    based on what it sees in the diff.

    Subclasses implement _build_prompt() to define what the skill checks for.
    """

    # Default max_turns. Override in subclass or config.
    max_turns: int = 0

    def __init__(self, model: str = "claude-sonnet-4-6", max_tokens: int = 4096, max_turns: int | None = None) -> None:
        self._client = anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens
        if max_turns is not None:
            self.max_turns = max_turns

    @abc.abstractmethod
    def _build_prompt(self, diff: str, context: Context) -> str: ...

    def run(self, diff: str, context: Context) -> list[Finding]:
        prompt = self._build_prompt(diff, context)

        # Build search paths for tools
        search_paths: list[str] = []
        if context.repo_path:
            search_paths.append(context.repo_path)
        search_paths.extend(context.extra_search_paths)

        # No repo access or max_turns=0: single call, no tools
        if not search_paths or self.max_turns <= 0:
            raw = self._call_llm_simple(prompt)
            return self._parse(raw)

        # Agentic loop with tools
        return self._run_agentic(prompt, search_paths)

    def _call_llm_simple(self, prompt: str) -> str:
        """Single LLM call without tools."""
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def _run_agentic(self, prompt: str, search_paths: list[str]) -> list[Finding]:
        """Tool-use loop. The LLM explores the repo and returns findings."""
        messages = [{"role": "user", "content": prompt}]
        turns_used = 0
        # Agentic calls need more room for reasoning + tool results + final JSON
        agentic_max_tokens = max(self._max_tokens, 8192)

        while turns_used <= self.max_turns:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=agentic_max_tokens,
                messages=messages,
                tools=_TOOLS,
            )

            # Check if the model wants to use tools
            if response.stop_reason == "tool_use":
                # Process all tool calls in this response
                tool_results = []
                assistant_content = response.content  # preserve full assistant message

                for block in response.content:
                    if block.type == "tool_use":
                        result = _execute_tool(block.name, block.input, search_paths)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                        turns_used += 1

                # Add assistant message and tool results to conversation
                messages.append({"role": "assistant", "content": assistant_content})
                messages.append({"role": "user", "content": tool_results})

                # If we've hit the budget, force a final response without tools
                if turns_used >= self.max_turns:
                    response = self._client.messages.create(
                        model=self._model,
                        max_tokens=agentic_max_tokens,
                        messages=messages,
                    )
                    return self._parse(self._extract_text(response))
            else:
                # Model returned text (findings) — done
                return self._parse(self._extract_text(response))

        # Should not reach here, but safety fallback
        return []

    def _extract_text(self, response) -> str:
        """Extract text content from a response that may contain mixed blocks."""
        parts = []
        for block in response.content:
            if hasattr(block, "text"):
                parts.append(block.text)
        raw = "\n".join(parts)
        # If we can't extract JSON, log what we got for debugging
        if not _extract_json(raw):
            print(f"sentinel: [{self.name}] raw model response ({len(raw)} chars): {raw[:500]}")
        return raw

    def _parse(self, raw: str) -> list[Finding]:
        data = _extract_json(raw)
        if data is None:
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
                    )
                )
            except (KeyError, ValueError):
                continue

        return findings
