# Telemetry

Telemetry is how a team answers questions sentinel cannot answer about itself: which findings did reviewers act on, which did they dismiss, which skill is slow, which one is silent. Without telemetry the eval corpus is curated by us and unmoored from what teams actually ship. With it, the corpus grows from production (v0.5 fixture-proposal pipeline, planned), and per-skill precision becomes measurable instead of asserted.

This doc covers the v0.5 first slice: event schema, JSONL sink, and what the runner emits. The fixture-proposal pipeline, feedback URLs, and remote sinks ship later — see [PLAN.md § v0.5](../PLAN.md#v05--learning-from-production-telemetry--history).

---

## What sentinel telemetry is, and is not

| | Sentinel telemetry | LLM observability (Phoenix, Langfuse, Helicone, Braintrust) |
|---|---|---|
| Unit | One *finding* per skill run | One *LLM call* per span |
| Captures | Skill identity, severity, file, line, title, duration | Prompt, response, tokens, latency, cost, tool calls |
| Question | "Did the model do something useful?" | "What did the model do?" |
| Storage | BYO — default is a JSONL file in `.sentinel/telemetry/` | Their backend or self-hosted |

They are **complementary, not competing**. A serious deployment runs both. Sentinel emits OpenTelemetry-compatible spans (planned) so Phoenix/Langfuse users get sentinel traces by wiring an OTLP endpoint — no integration code. Sentinel does not ship its own trace UI.

---

## Enabling telemetry

In `sentinel.yml`:

```yaml
telemetry:
  enabled: true                 # default: false
  path: .sentinel/telemetry     # default; relative to repo root
```

Once enabled, every `sentinel review` and every PR-triggered GHA run writes one event per skill executed. Files are daily-rotated:

```
.sentinel/telemetry/
    events-2026-05-30.jsonl
    events-2026-05-31.jsonl
```

Each line is a single JSON object — grep, jq, tail, ship to S3, commit to a private repo. Sentinel does not prescribe a downstream pipeline.

---

## Event schema

```json
{
  "schema_version": "1",
  "event_type": "skill_run",
  "session_id": "5e7a9c1b2d3f",
  "timestamp": "2026-05-30T23:58:27.589Z",
  "trigger": "pull_request",
  "repo": "acme/api",
  "pr_number": 42,
  "skill": "change_completeness",
  "duration_s": 1.234,
  "finding_count": 1,
  "findings": [
    {
      "id": "6eec644b2a39",
      "skill": "change_completeness",
      "severity": "high",
      "title": "Removed Terraform variable still referenced by 3 environments",
      "file": "envs/prod/main.tf",
      "line": 12
    }
  ],
  "error": null
}
```

| Field | Meaning |
|---|---|
| `schema_version` | Bumped on backwards-incompatible changes. Consumers should pin. |
| `event_type` | `"skill_run"` today. Reserved for future event types (`"feedback_received"`, etc.) without bumping the schema. |
| `session_id` | Stable per `run_skills()` invocation. All per-skill events from one review share it — join to aggregate per-PR stats. |
| `trigger` | `"pull_request"`, `"push"`, `"merge"`, or `"local"` (CLI mode). |
| `pr_number` | Null when the trigger has no PR (local review, scheduled drift). |
| `duration_s` | Wall-clock seconds for the skill, rounded to 3 dp. |
| `finding_count` | Cheap aggregate — same as `len(findings)` for `skill_run` events. |
| `findings[].id` | Stable hash of `(skill, file, line, title)`. Same finding produced next week hashes to the same id — that is what makes feedback attachable. |
| `error` | Exception class name when the skill raised; `null` on clean runs. On error, `findings` is empty (the safe placeholder finding posted to the PR is *not* emitted, so it doesn't pollute aggregates). |

### What is deliberately not in the schema

- **Finding messages and suggestions.** Bodies can quote multi-line code, file contents, or stack traces — emitting them would leak code into the telemetry path. Titles plus file + line are enough identity for a feedback link; bodies are recoverable from the PR comment when a human investigates.
- **Diff content.** Same reason.
- **LLM tokens / cost.** Belongs to the LLM observability layer (Phoenix, Langfuse), not this one. Will be added once sentinel emits OTLP spans.

---

## Privacy and trust

Telemetry is opt-in, and the default sink writes to a file in the team's repo. No data leaves the team's GitHub org unless they explicitly point telemetry at a remote endpoint (HTTP / S3 / Kafka — sinks planned for later).

If a remote sink is added, it must respect the same privacy rule: emit identity, not bodies. The schema enforces this — `Finding.message` and `Finding.suggestion` simply are not fields on `FindingSummary`.

---

## Failure mode

A telemetry write failure must never break a sentinel review. The JSONL sink catches `OSError` (read-only filesystem, disk full, missing permissions), logs `sentinel: telemetry write failed: <reason>` to stderr, and continues. The review completes and the PR is posted as normal.

Other exceptions surface — those would be programming errors, not operator errors, and silently swallowing them would hide bugs.

---

## Pointers

- Code: [`sentinel/telemetry/events.py`](../sentinel/telemetry/events.py), [`sentinel/telemetry/sink.py`](../sentinel/telemetry/sink.py)
- Tests: [`tests/test_telemetry_events.py`](../tests/test_telemetry_events.py), [`tests/test_telemetry_sink.py`](../tests/test_telemetry_sink.py)
- Plan: [`PLAN.md § v0.5`](../PLAN.md#v05--learning-from-production-telemetry--history)
