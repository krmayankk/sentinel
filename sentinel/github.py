from __future__ import annotations

import requests

from sentinel.core import Finding, Severity

_SEVERITY_LABEL = {
    Severity.CRITICAL: "CRITICAL",
    Severity.HIGH: "HIGH",
    Severity.MEDIUM: "MEDIUM",
    Severity.LOW: "LOW",
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


def _format_comment(findings: list[Finding]) -> str:
    lines = ["**Sentinel**\n"]

    for f in findings:
        label = _SEVERITY_LABEL[f.severity]
        location = f" — `{f.file}:{f.line}`" if f.file and f.line else (f" — `{f.file}`" if f.file else "")
        lines.append(f"**[{label}] {f.title}**{location}")
        lines.append(f.message)
        lines.append(f"_Suggestion: {f.suggestion}_")
        lines.append("")

    critical = sum(1 for f in findings if f.severity == Severity.CRITICAL)
    high = sum(1 for f in findings if f.severity == Severity.HIGH)
    if critical or high:
        blocking = []
        if critical:
            blocking.append(f"{critical} critical")
        if high:
            blocking.append(f"{high} high")
        lines.append(f"**{' and '.join(blocking)} severity** — review before merging.")

    return "\n".join(lines)
