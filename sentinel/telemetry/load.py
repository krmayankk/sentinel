"""Load persisted telemetry events from JSONL files.

Used by the summarize CLI and any external tool that wants to
re-render the historical view. Malformed lines are skipped with a
warning rather than aborting — a single corrupt write should not
make months of history unreadable.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from sentinel.telemetry.events import Event


def load_events(base_dir: str | Path) -> list[Event]:
    """Load every event from ``{base_dir}/events-*.jsonl``.

    Returns an empty list when the directory does not exist. Files are
    read in lexicographic order, which is also chronological because
    of the ``events-YYYY-MM-DD.jsonl`` layout.
    """
    base = Path(base_dir)
    if not base.is_dir():
        return []

    events: list[Event] = []
    for path in sorted(base.glob("events-*.jsonl")):
        try:
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(Event.from_dict(json.loads(line)))
                except (json.JSONDecodeError, KeyError) as exc:
                    print(
                        f"sentinel: telemetry skipped malformed line {path.name}:{lineno}: {exc}",
                        file=sys.stderr,
                    )
        except OSError as exc:
            print(f"sentinel: telemetry could not read {path}: {exc}", file=sys.stderr)

    return events
