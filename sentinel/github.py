from __future__ import annotations

import requests

from sentinel.core import Finding, Severity

_SEVERITY_ICON = {
    Severity.CRITICAL: "🔴",
    Severity.HIGH:     "🟠",
    Severity.MEDIUM:   "🟡",
    Severity.LOW:      "🔵",
}

# Built-in skills ship with sentinel. Everything else is custom.
_BUILTIN_SKILL_NAMES = {"change_completeness", "workflow_security", "migration_safety"}

_GITHUB_API = "https://api.github.com"
_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def post_findings(
    repo: str,
    pr_number: int,
    results: dict[str, list[Finding]],
    token: str,
) -> None:
    """Post findings as a PR comment grouped by skill."""
    url = f"{_GITHUB_API}/repos/{repo}/issues/{pr_number}/comments"
    headers = {**_HEADERS, "Authorization": f"Bearer {token}"}
    response = requests.post(
        url,
        json={"body": _format_comment(results)},
        headers=headers,
        timeout=15,
    )
    response.raise_for_status()


def _skill_label(name: str) -> str:
    """Return a display label like 'workflow_security (built-in)' or 'cost_check (custom)'."""
    kind = "built-in" if name in _BUILTIN_SKILL_NAMES else "custom"
    return f"{name} ({kind})"


def _format_caller_line(raw: str) -> str:
    """Format a single grep result line as a Markdown list item."""
    entry = raw.lstrip("- ").lstrip("./")
    parts = entry.split(":")
    if len(parts) >= 3:
        path, lineno, content = parts[0], parts[1], ":".join(parts[2:]).strip()
        return f"- `{path}:{lineno}` — `{content}`"
    return f"- `{entry}`"


def _format_comment(results: dict[str, list[Finding]]) -> str:
    blocks: list[str] = ["## Sentinel Review\n"]
    all_findings = [f for findings in results.values() for f in findings]

    # Per-skill sections
    for skill_name, findings in results.items():
        label = _skill_label(skill_name)

        if not findings:
            blocks.append(f"### ✅ {label} — no findings\n")
            continue

        blocks.append(f"### 🔍 {label}\n")

        for f in findings:
            icon = _SEVERITY_ICON[f.severity]
            sev = f.severity.value.upper()
            location = f"`{f.file}:{f.line}`" if f.file and f.line else f"`{f.file}`" if f.file else ""

            header = f"#### {icon} [{sev}] {f.title}"
            if location:
                header += f" &nbsp;·&nbsp; {location}"
            blocks.append(header)

            # Split message into narrative and confirmed callers section
            narrative, _, callers_section = f.message.partition("\n\nConfirmed:")
            blocks.append(narrative.strip())

            if callers_section.strip():
                caller_lines = [
                    line.strip() for line in callers_section.splitlines()
                    if line.strip().startswith("-")
                ]
                count = len(caller_lines)
                caller_md = "\n".join(_format_caller_line(l) for l in caller_lines)
                blocks.append(
                    f"<details>\n"
                    f"<summary>{count} confirmed caller(s) that will break</summary>\n\n"
                    f"{caller_md}\n"
                    f"</details>"
                )

            blocks.append(f"> **Suggestion:** {f.suggestion}")
            blocks.append("")

    # Footer summary
    total = len(all_findings)
    skill_count = len(results)
    passed = sum(1 for f in results.values() if not f)
    failed = skill_count - passed

    if total == 0:
        blocks.append(f"---\n**All {skill_count} skill(s) passed** — no findings.")
    else:
        counts = {s: sum(1 for f in all_findings if f.severity == s) for s in Severity}
        parts = [f"{v} {k.value}" for k, v in counts.items() if v]
        blocks.append("---")
        blocks.append(
            f"**{total} finding(s)** from {failed} of {skill_count} skill(s) "
            f"&nbsp;·&nbsp; {' &nbsp;·&nbsp; '.join(parts)}"
        )

    return "\n".join(blocks)
