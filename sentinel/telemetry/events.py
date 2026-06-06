"""Telemetry event schema.

One event per skill run. The payload is intentionally narrow:

- Identity (skill, file, line, title) is captured so feedback can be
  attached to a specific finding later.
- Severity, duration, and finding count are captured so per-skill
  aggregates are cheap.
- Finding **messages and suggestions are deliberately omitted** —
  bodies can quote multi-line code, paths, or stack traces. Titles
  carry enough identity for a feedback link; bodies are recoverable
  from the PR comment when a human investigates.

Schema is versioned. Bump :data:`SCHEMA_VERSION` on any
backwards-incompatible change to event shape.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from sentinel.core import Finding

SCHEMA_VERSION = "1"


def finding_id(skill: str, file: str, line: int, title: str) -> str:
    """Stable, repo-portable identifier for a finding.

    Same (skill, file, line, title) tuple always hashes to the same
    id, so a finding produced today and the same finding produced
    next week can be recognised across runs — this is what makes
    feedback ("user dismissed it") attachable.

    Line shifts when surrounding code changes will produce a new id;
    that's acceptable for v1 — the alternative (semantic hashing of
    the title alone) collides too aggressively.
    """
    payload = f"{skill}|{file}|{line}|{title}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]


def new_session_id() -> str:
    """One id per sentinel invocation; ties per-skill events together."""
    return uuid.uuid4().hex[:12]


def utc_now_iso() -> str:
    """Timezone-aware UTC timestamp in ISO 8601 with trailing 'Z'.

    Trailing 'Z' is chosen over '+00:00' for compactness and because
    every JSONL consumer in the world parses it.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


@dataclass
class FindingSummary:
    id: str
    skill: str
    severity: str
    title: str
    file: str = ""
    line: int = 0

    @classmethod
    def from_finding(cls, f: Finding) -> "FindingSummary":
        return cls(
            id=finding_id(f.skill, f.file, f.line, f.title),
            skill=f.skill,
            severity=f.severity.value,
            title=f.title,
            file=f.file,
            line=f.line,
        )

    @classmethod
    def from_dict(cls, d: dict) -> "FindingSummary":
        return cls(
            id=d["id"], skill=d["skill"], severity=d["severity"],
            title=d["title"], file=d.get("file", ""), line=d.get("line", 0),
        )


@dataclass
class Event:
    schema_version: str
    event_type: str           # "skill_run" today; reserved for future event types
    session_id: str
    timestamp: str            # ISO 8601 UTC, see :func:`utc_now_iso`
    trigger: str              # "pull_request" | "push" | "merge" | "local" | ""
    repo: str
    pr_number: int | None
    skill: str
    duration_s: float
    finding_count: int
    findings: list[FindingSummary] = field(default_factory=list)
    error: str | None = None  # populated when the skill raised an exception

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        return cls(
            schema_version=d["schema_version"],
            event_type=d["event_type"],
            session_id=d["session_id"],
            timestamp=d["timestamp"],
            trigger=d["trigger"],
            repo=d["repo"],
            pr_number=d.get("pr_number"),
            skill=d["skill"],
            duration_s=d["duration_s"],
            finding_count=d["finding_count"],
            findings=[FindingSummary.from_dict(f) for f in d.get("findings", [])],
            error=d.get("error"),
        )


def build_skill_run_event(
    *,
    session_id: str,
    trigger: str,
    repo: str,
    pr_number: int | None,
    skill: str,
    duration_s: float,
    findings: list[Finding],
    error: str | None = None,
    timestamp: str | None = None,
) -> Event:
    """Compose a skill-run event. Pure function — no I/O."""
    return Event(
        schema_version=SCHEMA_VERSION,
        event_type="skill_run",
        session_id=session_id,
        timestamp=timestamp or utc_now_iso(),
        trigger=trigger,
        repo=repo,
        pr_number=pr_number,
        skill=skill,
        duration_s=round(duration_s, 3),
        finding_count=len(findings),
        findings=[FindingSummary.from_finding(f) for f in findings],
        error=error,
    )
