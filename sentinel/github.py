"""GitHub PR comment posting.

The PR comment is intentionally terse: a verdict line, per-skill
status badges with finding counts, and a link to the full Job Summary
on the Actions tab. The dense per-finding rendering used to live here
and made comments look noisy; that content now lives on the Actions
tab via ``$GITHUB_STEP_SUMMARY``. Inline annotations on the diff are
unchanged — they're the right surface for per-line context.

Findings still appear in the comment body, but collapsed inside
``<details>`` blocks per skill so the default view stays clean.
"""
from __future__ import annotations

import requests

from sentinel.core import Finding, Severity

_SEVERITY_ICON = {
    Severity.CRITICAL: "🟥",
    Severity.HIGH:     "🟧",
    Severity.MEDIUM:   "🟨",
    Severity.LOW:      "⬜",
}

_SEV_ORDER = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]

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
    run_url: str | None = None,
) -> None:
    """Post the run summary as a PR issue comment.

    ``run_url`` (when supplied) is rendered as a link to the Actions
    tab so reviewers can open the full Job Summary in one click.
    """
    url = f"{_GITHUB_API}/repos/{repo}/issues/{pr_number}/comments"
    headers = {**_HEADERS, "Authorization": f"Bearer {token}"}
    response = requests.post(
        url,
        json={"body": format_comment(results, run_url=run_url)},
        headers=headers,
        timeout=15,
    )
    response.raise_for_status()


def format_comment(
    results: dict[str, list[Finding]],
    run_url: str | None = None,
) -> str:
    """Render the PR comment body."""
    all_findings = [f for findings in results.values() for f in findings]
    counts = {s: sum(1 for f in all_findings if f.severity == s) for s in Severity}

    lines: list[str] = ["## Sentinel review"]
    lines.append("")
    lines.append(_verdict_line(len(all_findings), len(results), counts))
    lines.append("")

    lines.append("| Skill | Status | Findings |")
    lines.append("|---|---|---|")
    for skill_name, findings in results.items():
        label = _skill_label(skill_name)
        status = "✅ clean" if not findings else f"⚠️ {len(findings)}"
        sev_summary = _severity_summary(findings)
        lines.append(f"| {label} | {status} | {sev_summary} |")
    lines.append("")

    for skill_name, findings in results.items():
        if findings:
            lines.extend(_findings_collapsible(skill_name, findings))

    if run_url:
        lines.append("")
        lines.append(f"📊 [Full summary on the Actions tab →]({run_url})")

    return "\n".join(lines)


def _verdict_line(total: int, skill_count: int, counts: dict[Severity, int]) -> str:
    if total == 0:
        return f"✅ **All {skill_count} skill(s) passed** — no findings."
    parts = [f"{counts[s]} {s.value}" for s in _SEV_ORDER if counts[s]]
    return f"⚠️ **{total} finding(s) across {skill_count} skill(s)** — {', '.join(parts)}"


def _severity_summary(findings: list[Finding]) -> str:
    if not findings:
        return "—"
    counts = {s: sum(1 for f in findings if f.severity == s) for s in Severity}
    return ", ".join(f"{counts[s]} {s.value}" for s in _SEV_ORDER if counts[s])


def _skill_label(name: str) -> str:
    kind = "built-in" if name in _BUILTIN_SKILL_NAMES else "custom"
    return f"`{name}` ({kind})"


def _findings_collapsible(skill: str, findings: list[Finding]) -> list[str]:
    out = [
        "<details>",
        f"<summary><strong>{_skill_label(skill)}</strong> — {len(findings)} finding(s)</summary>",
        "",
    ]
    for f in findings:
        icon = _SEVERITY_ICON[f.severity]
        loc = f"`{f.file}:{f.line}`" if f.file and f.line else (f"`{f.file}`" if f.file else "")
        header = f"#### {icon} [{f.severity.value.upper()}] {f.title}"
        if loc:
            header += f" &nbsp;·&nbsp; {loc}"
        out.append(header)
        out.append(f.message.strip())
        out.append("")
        out.append(f"> **Suggestion:** {f.suggestion}")
        out.append("")
    out.append("</details>")
    out.append("")
    return out
