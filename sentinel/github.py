from __future__ import annotations

import requests

from sentinel.core import Finding, Severity

_SEVERITY_ICON = {
    Severity.CRITICAL: "🔴",
    Severity.HIGH:     "🟠",
    Severity.MEDIUM:   "🟡",
    Severity.LOW:      "🔵",
}

_GITHUB_API = "https://api.github.com"
_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def post_findings(
    repo: str,
    pr_number: int,
    findings: list[Finding],
    token: str,
) -> None:
    """Post findings as a PR comment. No-ops when there is nothing to report."""
    if not findings:
        return

    url = f"{_GITHUB_API}/repos/{repo}/issues/{pr_number}/comments"
    headers = {**_HEADERS, "Authorization": f"Bearer {token}"}
    response = requests.post(
        url,
        json={"body": _format_comment(findings)},
        headers=headers,
        timeout=15,
    )
    response.raise_for_status()


def _format_caller_line(raw: str) -> str:
    """Format a single grep result line as a Markdown list item.

    Input:  "- ./terraform/envs/prod/main.tf:12:  enable_performance_insights = true"
    Output: "- `terraform/envs/prod/main.tf:12` — `enable_performance_insights = true`"
    """
    entry = raw.lstrip("- ").lstrip("./")
    parts = entry.split(":")
    if len(parts) >= 3:
        path, lineno, content = parts[0], parts[1], ":".join(parts[2:]).strip()
        return f"- `{path}:{lineno}` — `{content}`"
    return f"- `{entry}`"


def _format_comment(findings: list[Finding]) -> str:
    blocks: list[str] = ["## Sentinel Review\n"]

    for f in findings:
        icon = _SEVERITY_ICON[f.severity]
        label = f.severity.value.upper()
        location = f"`{f.file}:{f.line}`" if f.file and f.line else f"`{f.file}`" if f.file else ""

        # Header line
        header = f"### {icon} [{label}] {f.title}"
        if location:
            header += f" &nbsp;·&nbsp; {location}"
        blocks.append(header)

        # Split message into narrative and confirmed callers section
        narrative, _, callers_section = f.message.partition("\n\nConfirmed:")
        blocks.append(narrative.strip())

        # Render confirmed callers as a collapsible list
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
    counts = {s: sum(1 for f in findings if f.severity == s) for s in Severity}
    parts = [f"{v} {k.value}" for k, v in counts.items() if v]
    total = len(findings)
    blocks.append("---")
    blocks.append(f"**{total} finding(s)** &nbsp;·&nbsp; {' &nbsp;·&nbsp; '.join(parts)}")

    return "\n".join(blocks)
