"""Sentinel entrypoint.

Three modes:

  Local review (development and demo):
    sentinel review --diff <path> --repo-path <path> [--env <path>] [--claude-md <path>]

  Eval (v0.4 deterministic checker):
    sentinel eval run [--fixtures-dir <path>] [--fixture <name>] [--json] [--env <path>]

  GHA (triggered by action.yml):
    All configuration comes from environment variables.
    Findings appear as inline annotations on the PR diff.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from sentinel.config import load_config
from sentinel.core import Context, Finding, Severity
from sentinel.github import post_findings
from sentinel.preprocess import filter_noise, truncate_diff
from sentinel.runner import run_skills


def main() -> None:
    args = _parse_args()
    model = os.environ.get("SENTINEL_MODEL", "claude-sonnet-4-6")
    fail_on = {s.strip() for s in os.environ.get("SENTINEL_FAIL_ON", "").split(",") if s.strip()}
    event_type = os.environ.get("SENTINEL_EVENT_TYPE", "")

    if args.command == "review":
        if args.env:
            _load_env_file(args.env)
        event_type = getattr(args, "event_type", "") or event_type
        _run_local(args, model, fail_on, event_type)
    elif args.command == "eval":
        if getattr(args, "env", None):
            _load_env_file(args.env)
        _run_eval(args, model, event_type)
    else:
        _run_gha(model, fail_on, event_type)


# -- modes --

def _run_local(args: argparse.Namespace, model: str, fail_on: set[str], event_type: str = "") -> None:
    _require_env("ANTHROPIC_API_KEY")

    with open(args.diff) as f:
        raw_diff = f.read()

    instructions = ""
    if args.claude_md:
        with open(args.claude_md) as f:
            instructions = f.read()

    diff = truncate_diff(filter_noise(raw_diff))
    if not diff.strip():
        print("sentinel: nothing to review after filtering noise.")
        sys.exit(0)

    repo_path = args.repo_path or ""
    config = load_config(repo_path)

    # Merge fail_on: env var (action input) takes precedence; fall back to sentinel.yml
    effective_fail_on = fail_on or set(config.fail_on)

    context = Context(
        repo="local",
        pr_number=0,
        instructions=instructions,
        repo_path=repo_path,
    )

    results = run_skills(diff, context, config, model=model, event_type=event_type)
    all_findings = _flatten(results)
    _print_findings(results, source=args.diff)

    _check_blocking(all_findings, effective_fail_on)


def _run_gha(model: str, fail_on: set[str], event_type: str = "") -> None:
    github_token = _require_env("GITHUB_TOKEN")
    repo = _require_env("GITHUB_REPOSITORY")
    pr_number = int(_require_env("PR_NUMBER"))
    _require_env("ANTHROPIC_API_KEY")

    # GITHUB_WORKSPACE is always set in GHA — it's the checked-out repo root.
    repo_path = os.environ.get("GITHUB_WORKSPACE", "")
    config = load_config(repo_path)

    # Merge fail_on: env var (action input) takes precedence; fall back to sentinel.yml
    effective_fail_on = fail_on or set(config.fail_on)

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

    results = run_skills(diff, context, config, model=model, event_type=event_type)
    all_findings = _flatten(results)

    _print_findings(results, source=f"{repo}#{pr_number}")
    _emit_gha_annotations(all_findings)
    post_findings(repo, pr_number, results, github_token)

    _check_blocking(all_findings, effective_fail_on)


def _run_eval(args: argparse.Namespace, model: str, event_type: str) -> None:
    """Run fixtures through the deterministic scorer and report.

    Exits non-zero if any fixture fails — designed to gate CI on prompt regressions.
    """
    _require_env("ANTHROPIC_API_KEY")

    # Import lazily so `sentinel review` doesn't pay the import cost.
    from sentinel.evals.report import format_console, to_json
    from sentinel.evals.runner import discover_fixtures, run_all

    fixtures_dir = Path(args.fixtures_dir)
    if not fixtures_dir.exists():
        print(f"sentinel: fixtures directory not found: {fixtures_dir}", file=sys.stderr)
        sys.exit(2)

    only = [args.fixture] if args.fixture else None
    if only and not (fixtures_dir / args.fixture).exists():
        print(f"sentinel: fixture not found: {args.fixture}", file=sys.stderr)
        sys.exit(2)

    available = [p.name for p in discover_fixtures(fixtures_dir)]
    if not available:
        print(f"sentinel: no fixtures found under {fixtures_dir}", file=sys.stderr)
        sys.exit(2)

    runs = run_all(fixtures_dir, model=model, event_type=event_type, only=only)

    if args.json:
        print(to_json(runs))
    else:
        print(format_console(runs))

    failed = sum(1 for r in runs if not r.score.passed)
    if failed:
        sys.exit(1)


def _check_blocking(findings: list[Finding], fail_on: set[str]) -> None:
    """Exit with code 1 if any findings match blocking severity levels."""
    if not fail_on:
        return
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
        print(f"::{level}{file_part}::[{f.skill}] {f.title} — {message}")


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


def _flatten(results: dict[str, list]) -> list[Finding]:
    """Flatten per-skill results into a single findings list."""
    return [f for findings in results.values() for f in findings]


def _print_findings(results: dict[str, list], source: str) -> None:
    print(f"\n{_BOLD}sentinel{_RESET} — {_DIM}{source}{_RESET}\n")

    all_findings = _flatten(results)

    for skill_name, findings in results.items():
        if not findings:
            print(f"  {_DIM}[{skill_name}] PASS — no findings{_RESET}")
            continue

        print(f"  {_BOLD}[{skill_name}]{_RESET}")
        for f in findings:
            color = _SEV_COLOR.get(f.severity, "")
            loc = f"  {_DIM}{f.file}:{f.line}{_RESET}" if f.file else ""
            print(f"  {color}{_BOLD}[{f.severity.value.upper()}] {f.title}{_RESET}{loc}")
            for line in f.message.splitlines():
                print(f"    {line}")
            print(f"    {_DIM}Suggestion: {f.suggestion}{_RESET}")
            print()

    if not all_findings:
        print(f"\n  No findings across {len(results)} skill(s).\n")
        return

    counts = {s: sum(1 for f in all_findings if f.severity == s) for s in Severity}
    summary = ", ".join(f"{v} {k.value}" for k, v in counts.items() if v)
    print(f"{'─' * 48}")
    print(f"{len(all_findings)} finding(s) across {len(results)} skill(s): {summary}\n")


# -- helpers --

def _git_diff() -> str:
    base = os.environ.get("SENTINEL_BASE_REF", "origin/main")
    result = subprocess.run(
        ["git", "diff", f"{base}...HEAD"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def _load_instructions() -> str:
    """Load reviewer instructions from CLAUDE.md if present.

    Teams write repo-specific guidance in CLAUDE.md. Sentinel injects
    this as high-priority context so the reviewer enforces your conventions,
    not just generic patterns.
    """
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
    review.add_argument("--event-type", metavar="TYPE", default="", help="Event type: push, merge, or empty (run all)")

    eval_cmd = sub.add_parser("eval", help="Run skills against fixtures and score deterministically")
    eval_sub = eval_cmd.add_subparsers(dest="eval_command")
    run_cmd = eval_sub.add_parser("run", help="Run all fixtures (or one with --fixture)")
    run_cmd.add_argument("--fixtures-dir", metavar="PATH", default="evals/fixtures",
                         help="Directory containing fixture subdirectories")
    run_cmd.add_argument("--fixture", metavar="NAME", default="",
                         help="Run a single named fixture instead of all")
    run_cmd.add_argument("--json", action="store_true",
                         help="Emit JSON report instead of human-readable console output")
    run_cmd.add_argument("--env", metavar="PATH", help="Path to a .env file")
    args = parser.parse_args()

    if args.command == "eval" and not getattr(args, "eval_command", None):
        eval_cmd.print_help()
        sys.exit(2)
    return args


if __name__ == "__main__":
    main()
