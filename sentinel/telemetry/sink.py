"""Telemetry sinks.

The :class:`Sink` protocol is intentionally tiny so a team can replace
the default JSONL writer with anything — HTTP POST, S3 append, Kafka
producer, OTLP exporter — without touching the runner.

The runner calls ``sink.emit(event)`` once per skill run. Sinks must
not raise: a telemetry failure must never break a sentinel review.
Implementations log to stderr and continue.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

from sentinel.telemetry.events import Event


class Sink(Protocol):
    def emit(self, event: Event) -> None: ...


class NullSink:
    """Default when telemetry is disabled. Drops every event."""

    def emit(self, event: Event) -> None:
        return None


class JSONLSink:
    """Append events to a daily-rotated JSONL file.

    Path layout: ``{base_dir}/events-YYYY-MM-DD.jsonl``. The date
    prefix comes from ``event.timestamp`` so back-dated events go to
    the right file (useful for replay) and concurrent runs across a
    midnight boundary do the right thing without coordination.

    One line per event, no pretty printing — JSONL is meant to be
    grepped, tailed, and streamed. Compact separators keep the file
    small enough to commit to a telemetry repo without bloat.
    """

    def __init__(self, base_dir: str | Path) -> None:
        self._base = Path(base_dir)

    def emit(self, event: Event) -> None:
        try:
            self._base.mkdir(parents=True, exist_ok=True)
            day = event.timestamp[:10]  # "YYYY-MM-DD"
            path = self._base / f"events-{day}.jsonl"
            line = json.dumps(asdict(event), separators=(",", ":"), ensure_ascii=False)
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as exc:
            # A broken disk or read-only volume must not block a review.
            print(f"sentinel: telemetry write failed: {exc}", file=sys.stderr)


class CollectorSink:
    """Capture every emitted event in memory.

    Used to build the per-run summary without re-reading the JSONL
    file: the runner emits, the entrypoint reads back from
    :attr:`events` to render. Independent of any persistent sink.
    """

    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


class TeeSink:
    """Fan out one emit to many sinks.

    Each child sink is called in order. A child raising would break
    later children, but child sinks are not expected to raise — see
    the contract on :class:`Sink`. The composition itself adds no
    error handling so a misbehaving child is still discoverable in
    tests.
    """

    def __init__(self, *sinks: Sink) -> None:
        self._sinks = sinks

    def emit(self, event: Event) -> None:
        for sink in self._sinks:
            sink.emit(event)
