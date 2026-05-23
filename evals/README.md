# Evals

Fixtures for measuring sentinel's review quality. Each fixture is a realistic scenario derived from the class of change that causes real incidents.

The v0.4 harness (`sentinel eval run`) loads every fixture, runs the configured skills, and scores the produced findings against `expected.json` using a deterministic checker — no LLM in the scoring path. Same findings + same fixture always produce the same score.

The LLM-as-judge layer (rubric scoring on actionability, grounding, calibration) is a follow-up. The deterministic checker alone catches the gross regression modes: skill silent, skill firing on the wrong file, severity flipped, verdict reversed.

> **New to this?** Read [`docs/evals.md`](../docs/evals.md) first — it walks through a worked example end-to-end (the LLM step, the scorer step, what "deterministic" actually means, and why the fixtures are static). This README is the operational reference for fixture authors.

## Running

```bash
# all fixtures
sentinel eval run

# one fixture
sentinel eval run --fixture terraform_variable_removed

# machine-readable JSON output for CI artifacts
sentinel eval run --json
```

The harness exits non-zero if any fixture fails. Wire that into CI to gate prompt regressions.

## Adding a fixture

```
evals/fixtures/<scenario-name>/
    diff.patch      — the git diff sentinel will review
    context.json    — repo, pr_number, instructions, scenario description
    expected.json   — what sentinel must find, must not find, and the expected verdict
    repo/           — surrounding code so grep/read_file tools work during the skill run
```

## `expected.json` schema

```json
{
  "must_find": [
    {
      "skill": "change_completeness",
      "severity_min": "high",
      "match_any": ["enable_performance_insights", "caller"],
      "file_contains": ["envs/"],
      "rationale": "why this finding must be present (documentation only — ignored by scorer)"
    }
  ],
  "must_not_find": [
    {
      "skill": "change_completeness",
      "severity_min": "medium",
      "match_any": ["count = 0"],
      "rationale": "scaffolding resources with count=0 should not be flagged"
    }
  ],
  "verdict": "incomplete"
}
```

### Field reference

| Field | Required | Meaning |
|---|---|---|
| `skill` | yes (inside each entry) | The skill name that must (or must not) produce this finding |
| `severity_min` | yes (inside each entry) | Minimum severity: `low` < `medium` < `high` < `critical` |
| `match_any` | no | Substrings — at least one must appear somewhere in `title + message + suggestion + file` (case-insensitive). Use this for the *concept* the finding should mention. |
| `file_contains` | no | Substrings — at least one must appear in the finding's `file` field specifically. Use this for location grading: did the finding point at the right file? |
| `title_contains` | no | Back-compat alias for `match_any`. New fixtures should use `match_any`. |
| `rationale` | no | Free-text documentation. Ignored by the scorer; helps humans understand the intent. |
| `verdict` | yes (top-level) | `incomplete` (findings at HIGH+ expected) or `complete` (no HIGH+ findings expected). Derived verdict uses HIGH+CRITICAL as the threshold. |

### How a fixture passes

A fixture passes when **all three** of:

1. Every `must_find` is satisfied by at least one produced finding (skill, severity, and any substring/location constraints all match).
2. No `must_not_find` is triggered (no produced finding matches any of them).
3. The derived verdict from the findings matches the expected verdict.

### Why we grade on `match_any` / `file_contains` and not pure title keywords

The original sketch graded on `title_contains` only. That's brittle — a correct finding worded differently fails the test, producing noise on the measurement itself. The finding's value is whether it points the engineer at the actual problem: that's location, severity, and which skill caught it. Title wording is style — it's something the LLM judge will score later, not the deterministic checker.

`match_any` widens the haystack to title + message + suggestion + file, so style-of-wording doesn't break the check. `file_contains` is the explicit location-grading field for cases where pointing at the right file is what matters.

## Current fixtures

| Fixture | Scenario | Skills |
|---|---|---|
| `terraform_variable_removed` | Terraform module variable removed; callers not updated | change_completeness |
| `gha_privilege_escalation` | Workflow uses `pull_request_target` + head checkout + script run | workflow_security |
| `unsafe_migration` | `CREATE INDEX` without `CONCURRENTLY` on a large table | migration_safety |
| `cross_repo` | Proto field changed; downstream consumer in another repo not updated | change_completeness (with cross_repo) |

Target for v0.4: ~15 curated fixtures covering each built-in skill. Long-term, the corpus is grown from production telemetry (v0.5).
