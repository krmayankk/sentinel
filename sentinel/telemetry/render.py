"""Markdown renderers for telemetry events.

Two views, both Markdown:

* :func:`render_run_summary` — the *just-finished* run. Drives the
  GitHub Actions Job Summary (``$GITHUB_STEP_SUMMARY``) and is the
  human-readable per-run dashboard. Includes finding bodies because
  the reader is investigating right now.

* :func:`render_aggregate` — historical view over persisted events.
  Drives the local ``sentinel telemetry summarize`` CLI. No bodies,
  because bodies are deliberately not persisted (see
  ``sentinel/telemetry/events.py``).

The output is plain GitHub-flavoured Markdown. No HTML except for
``<details>`` collapsibles, which GitHub renders natively. Anything
that consumes Markdown (PR comments, README, the Actions summary
panel) renders it correctly.
"""
from __future__ import annotations

from collections import Counter
from statistics import median
from typing import Iterable

from sentinel.core import Finding, Severity
from sentinel.telemetry.events import Event

_SEV_ORDER = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]
_SEV_ICON = {
    Severity.CRITICAL.value: "🟥",
    Severity.HIGH.value:     "🟧",
    Severity.MEDIUM.value:   "🟨",
    Severity.LOW.value:      "⬜",
}


# -- per-run summary --

def render_run_summary(
    results: dict[str, list[Finding]],
    events: list[Event],
) -> str:
    """Render the just-finished run as a Markdown summary.

    ``results`` carries finding bodies (titles + messages + suggestions).
    ``events`` carries timing and skill error state. Joined by skill name.
    """
    events_by_skill = {ev.skill: ev for ev in events}
    all_findings = [f for fs in results.values() for f in fs]
    sev_counts = _severity_histogram(all_findings)

    lines: list[str] = []
    lines.append("## Sentinel review")
    lines.append("")
    lines.append(_status_line(results, events_by_skill, sev_counts))
    lines.append("")

    lines.append("| Skill | Status | Findings | Duration |")
    lines.append("|---|---|---|---|")
    for name in results:
        ev = events_by_skill.get(name)
        findings = results[name]
        status = _skill_status(findings, ev)
        sev_summary = _row_severity_summary(findings)
        duration = f"{ev.duration_s:.1f}s" if ev else "—"
        lines.append(f"| `{name}` | {status} | {sev_summary} | {duration} |")
    lines.append("")

    for name, findings in results.items():
        ev = events_by_skill.get(name)
        if ev and ev.error:
            lines.extend(_render_error_block(name, ev.error))
        elif findings:
            lines.extend(_render_findings_block(name, findings))
    return "\n".join(lines).rstrip() + "\n"


def _status_line(
    results: dict[str, list[Finding]],
    events_by_skill: dict[str, Event],
    sev_counts: Counter,
) -> str:
    skill_count = len(results)
    error_count = sum(1 for ev in events_by_skill.values() if ev.error)
    finding_count = sum(sev_counts.values())

    if error_count:
        emoji = "❌"
    elif sev_counts.get(Severity.CRITICAL.value) or sev_counts.get(Severity.HIGH.value):
        emoji = "⚠️"
    elif finding_count:
        emoji = "ℹ️"
    else:
        emoji = "✅"

    parts = [f"**{finding_count} finding(s) across {skill_count} skill(s)**"]
    if sev_counts:
        sev_summary = ", ".join(
            f"{sev_counts[s.value]} {s.value}" for s in _SEV_ORDER if sev_counts.get(s.value)
        )
        parts.append(f"— {sev_summary}")
    if error_count:
        parts.append(f"— {error_count} skill error(s)")

    return f"{emoji} " + " ".join(parts)


def _skill_status(findings: list[Finding], ev: Event | None) -> str:
    if ev and ev.error:
        return f"❌ error (`{ev.error}`)"
    if not findings:
        return "✅ clean"
    return f"⚠️ {len(findings)} finding(s)"


def _row_severity_summary(findings: list[Finding]) -> str:
    if not findings:
        return "—"
    counts = _severity_histogram(findings)
    return ", ".join(
        f"{counts[s.value]} {s.value}" for s in _SEV_ORDER if counts.get(s.value)
    )


def _render_findings_block(skill: str, findings: list[Finding]) -> list[str]:
    out: list[str] = []
    out.append(f"<details>")
    out.append(f"<summary><strong><code>{skill}</code></strong> — {len(findings)} finding(s)</summary>")
    out.append("")
    for f in findings:
        icon = _SEV_ICON.get(f.severity.value, "⬜")
        loc = f"`{f.file}:{f.line}`" if f.file else "_(no location)_"
        out.append(f"#### {icon} {f.severity.value.upper()} · {f.title}")
        out.append(f"**File:** {loc}")
        out.append("")
        # Quote the message so multi-line text stays readable.
        out.extend(_quote(f.message))
        out.append("")
        out.append(f"**Suggestion:** {f.suggestion}")
        out.append("")
    out.append("</details>")
    out.append("")
    return out


def _render_error_block(skill: str, error: str) -> list[str]:
    return [
        "<details>",
        f"<summary><strong><code>{skill}</code></strong> — ❌ error</summary>",
        "",
        f"The skill raised `{error}`. See the action logs for the full traceback.",
        "",
        "</details>",
        "",
    ]


def _quote(text: str) -> list[str]:
    return [f"> {line}" if line else ">" for line in text.splitlines()]


# -- historical aggregate --

def render_aggregate(events: list[Event]) -> str:
    """Render a historical aggregate across many events.

    Drives ``sentinel telemetry summarize``. No finding bodies — they
    are not persisted; the user can re-derive them from the PR comment
    when investigating a specific finding.
    """
    if not events:
        return "## Sentinel telemetry\n\n_No events found._\n"

    skill_runs: dict[str, list[Event]] = {}
    for ev in events:
        skill_runs.setdefault(ev.skill, []).append(ev)

    first_ts = min(ev.timestamp for ev in events)
    last_ts = max(ev.timestamp for ev in events)
    sessions = {ev.session_id for ev in events}

    lines: list[str] = []
    lines.append("## Sentinel telemetry")
    lines.append("")
    lines.append(
        f"**{len(events)} event(s)** across **{len(sessions)} session(s)** "
        f"from `{first_ts}` to `{last_ts}`"
    )
    lines.append("")

    lines.append("| Skill | Runs | Errors | Findings | Sev (C/H/M/L) | p50 dur | p95 dur |")
    lines.append("|---|---|---|---|---|---|---|")
    for skill in sorted(skill_runs):
        evs = skill_runs[skill]
        runs = len(evs)
        errors = sum(1 for e in evs if e.error)
        findings = sum(e.finding_count for e in evs)
        sev_hist = Counter()
        for e in evs:
            for f in e.findings:
                sev_hist[f.severity] += 1
        sev_cell = "/".join(
            str(sev_hist.get(s.value, 0)) for s in _SEV_ORDER
        )
        durations = [e.duration_s for e in evs if e.error is None]
        p50 = f"{median(durations):.2f}s" if durations else "—"
        p95 = f"{_p95(durations):.2f}s" if durations else "—"
        lines.append(
            f"| `{skill}` | {runs} | {errors} | {findings} | {sev_cell} | {p50} | {p95} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def _p95(values: Iterable[float]) -> float:
    """Index-based 95th percentile. Good enough at this volume."""
    sorted_v = sorted(values)
    if not sorted_v:
        return 0.0
    idx = min(len(sorted_v) - 1, int(round(0.95 * (len(sorted_v) - 1))))
    return sorted_v[idx]


# -- helpers --

def _severity_histogram(findings: list[Finding]) -> Counter:
    return Counter(f.severity.value for f in findings)
