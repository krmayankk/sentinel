"""Sentinel telemetry — structured events per skill run.

Telemetry exists so a team can answer questions sentinel cannot answer
about itself: which findings did reviewers act on, which did they
dismiss, which skill is slow, which one is silent. Events are emitted
to a pluggable :class:`Sink`. The default :class:`JSONLSink` writes
one event per line to a daily-rotated file the team owns.

The sentinel runner is the only emitter. Skills do not call telemetry
directly — that keeps each skill a pure judgment function.

What is *not* in scope: per-LLM-call tracing. That belongs to
OpenTelemetry-aware tools (Phoenix, Langfuse, Helicone). See
``PLAN.md`` § v0.5 telemetry layering.
"""
from sentinel.telemetry.events import (
    Event,
    FindingSummary,
    build_skill_run_event,
    finding_id,
    new_session_id,
)
from sentinel.telemetry.sink import (
    CollectorSink,
    JSONLSink,
    NullSink,
    Sink,
    TeeSink,
)

__all__ = [
    "CollectorSink",
    "Event",
    "FindingSummary",
    "JSONLSink",
    "NullSink",
    "Sink",
    "TeeSink",
    "build_skill_run_event",
    "finding_id",
    "new_session_id",
]
