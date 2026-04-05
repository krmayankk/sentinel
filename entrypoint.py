"""Sentinel entrypoint.

Two modes:

  Local (development and demo):
    sentinel review --diff <path> --repo-path <path> [--env <path>] [--claude-md <path>]

  GHA (triggered by action.yml):
    All configuration comes from environment variables.
    Findings appear as inline annotations on the PR diff.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

from sentinel.core import Context, Severity
from sentinel.github import post_findings
from sentinel.preprocess import filter_noise, truncate_diff
from sentinel.skills.change_completeness import ChangeCompletenessSkill


def main() -> None:
    args = _parse_args()
    model = os.environ.get("SENTINEL_MODEL", "claude-sonnet-4-6")
    fail_on = {s.strip() for s in os.environ.get("SENTINEL_FAIL_ON", "").split(",") if s.strip()}

    if args.command == "review":
        if args.env:
            _load_env_file(args.env)
        _run_local(args, model, fail_on)
    else:
        _run_gha(model, fail_on)


# -- modes --

def _run_local(args: argparse.Namespace, model: str, fail_on: set[str]) -> None:
    _require_env("ANTHROPIC_API_KEY")

    with open(args.diff) as f:
        raw_diff = f.read()

    instructions = ""
    if args.instructions:
        with open(args.instructions) as f:
            instructions = f.read()

    diff = truncate_diff(filter_noise(raw_diff))
    if not diff.strip():
        print("sentinel: nothing to review after filtering noise.")
        sys.exit(0)

    context = Context(
        repo="local",
        pr_number=0,
        instructions=instructions,
        repo_path=args.repo_path or "",
    )

    findings = ChangeCompletenessSkill(model=model).run(diff, context)
    _print_findings(findings, source=args.diff)

    if fail_on:
        blocking = [f for f in findings if f.severity.value in fail_on]
        if blocking:
            print(f"\nsentinel: {len(blocking)} finding(s) at blocking severity.")
            sys.exit(1)


def _run_gha(model: str, fail_on: set[str]) -> None:
    github_token = _require_env("GITHUB_TOKEN")
    repo = _require_env("GITHUB_REPOSITORY")
    pr_number = int(_require_env("PR_NUMBER"))
    _require_env("ANTHROPIC_API_KEY")

    # GITHUB_WORKSPACE is always set in GHA — it's the checked-out repo root.
    repo_path = os.environ.get("GITHUB_WORKSPACE", "")

    diff = truncate_diff(filter_noise(_git_diff()))
    if not diff.strip():
        print("sentinel: nothing to review after filtering noise.")
        sys.exit(0)

    context = Context(
        repo=repo,
        pr_number=pr_number,
        instructions=_load_instructions(),
        repo_path=repo_path,
    )

    findings = ChangeCompletenessSkill(model=model).run(diff, context)

    _print_findings(findings, source=f"{repo}#{pr_number}")
    _emit_gha_annotations(findings)
    post_findings(repo, pr_number, findings, github_token)

    if fail_on:
        blocking = [f for f in findings if f.severity.value in fail_on]
        if blocking:
            print(f"\nsentinel: {len(blocking)} finding(s) at blocking severity. Failing.")
            sys.exit(1)


# -- GHA annotations --
# These appear as inline warnings/errors on the PR diff in GitHub's UI.

def _emit_gha_annotations(findings: list) -> None:
    for f in findings:
        level = "error" if f.severity in (Severity.CRITICAL, Severity.HIGH) else "warning"
        file_part = f",file={f.file},line={f.line}" if f.file and f.line else ""
        # Newlines in the message break the annotation format — collapse them.
        message = f.message.replace("\n", " ")
        print(f"::{level}{file_part}::{f.title} — {message}")


# -- output --

_SEV_COLOR = {
    Severity.CRITICAL: "\033[91m",
    Severity.HIGH:     "\033[93m",
    Severity.MEDIUM:   "\033[94m",
    Severity.LOW:      "\033[37m",
}
_RESET = "\033[0m"
_DIM   = "\033[2m"
_BOLD  = "\033[1m"


def _print_findings(findings: list, source: str) -> None:
    print(f"\n{_BOLD}sentinel{_RESET} — change completeness — {_DIM}{source}{_RESET}\n")

    if not findings:
        print("  No completeness gaps found.\n")
        return

    for f in findings:
        color = _SEV_COLOR.get(f.severity, "")
        loc = f"  {_DIM}{f.file}:{f.line}{_RESET}" if f.file else ""
        print(f"{color}{_BOLD}[{f.severity.value.upper()}] {f.title}{_RESET}{loc}")
        # Indent multi-line messages for readability
        for line in f.message.splitlines():
            print(f"  {line}")
        print(f"  {_DIM}Suggestion: {f.suggestion}{_RESET}")
        print()

    counts = {s: sum(1 for f in findings if f.severity == s) for s in Severity}
    summary = ", ".join(f"{v} {k.value}" for k, v in counts.items() if v)
    print(f"{'─' * 48}")
    print(f"{len(findings)} finding(s): {summary}\n")


# -- helpers --

def _git_diff() -> str:
    base = os.environ.get("SENTINEL_BASE_REF", "origin/main")
    result = subprocess.run(
        ["git", "diff", f"{base}...HEAD"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def _load_instructions() -> str:
    try:
        with open("CLAUDE.md") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def _load_env_file(path: str) -> None:
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"sentinel: required environment variable {name!r} is not set.", file=sys.stderr)
        sys.exit(1)
    return value


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sentinel",
        description="AI agents for your software delivery pipeline.",
    )
    sub = parser.add_subparsers(dest="command")
    review = sub.add_parser("review", help="Review a diff for completeness gaps")
    review.add_argument("--diff",      metavar="PATH", help="Path to a diff/patch file (local mode)")
    review.add_argument("--repo-path", metavar="PATH", help="Repo root to search for callers (local mode)")
    review.add_argument("--env",       metavar="PATH", help="Path to a .env file")
    review.add_argument("--claude-md", metavar="PATH", help="Path to a CLAUDE.md file")
    return parser.parse_args()


if __name__ == "__main__":
    main()
