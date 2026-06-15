# Open + harness vs. frontier — bake-off methodology

A protocol for answering, with real numbers on a real workload: **can an open model plus the sentinel harness replace a frontier closed model for code-review-shaped work, and at what quality / token / cost ratio?**

This doc is the methodology. The harness lives in this repo; the workloads live elsewhere (see *Workload sources*). Results land in `docs/bake-off-results/<run-date>/` once the first run completes.

---

## The question

For a given operational AI workload — code review, drift detection, incident triage — does

> **open model + sentinel skills + CLAUDE.md + history RAG + tuned eval corpus**

deliver enough quality at materially better unit economics than

> **frontier closed model + the same harness**

to justify the operational cost of self-hosting, in dimensions a buyer cares about (quality, cost, latency, sovereignty)?

The honest expected outcome is **mixed** — open + harness wins on cost, sovereignty, and team-specific tasks; frontier wins on novel reasoning and cutting-edge tool-use. The value of the bake-off is producing the *table*, not predicting it.

---

## Dimensions

Four axes, measured per skill per provider per run:

| Axis | How measured | What "winning" looks like |
|---|---|---|
| Quality | Deterministic eval (precision, recall, verdict) + LLM-judge rubric (actionability, grounding, calibration) | Within 5% of the strongest provider on the same fixture set. |
| Tokens | Input + output, raw counts | Stable underlying measurement; cost is derived. |
| Latency | Per-skill wall-clock, p50 / p95 | Under SLA bound for the workload (e.g. PR review under 90 s). |
| Cost | Derived. Closed: tokens × current price. Self-hosted: GPU-hours × hardware cost / TPS. | 5–50× cheaper for open models at meaningful volume. |

Cost is intentionally derived, not measured directly — prices change, hardware changes, but token counts and GPU-hours don't.

---

## Backends under test

Start with five. Same skills, same fixtures, same telemetry across all of them. Only the LLM call changes.

| Backend | Role |
|---|---|
| Claude Sonnet (current) | Frontier baseline; what sentinel ships with today. |
| Claude Opus | Frontier upper bound; expensive ceiling. |
| GPT-5.x | Cross-frontier sanity check; rules out Anthropic-specific tuning. |
| Kimi K2 / DeepSeek V3 / Qwen 3 (open, self-hosted) | The contender; one is enough to start, more later. |
| Open model + full harness (CLAUDE.md, custom skills, history RAG) | The actual claim under test. |

The contrast that matters is **#1 vs #5**, not #1 vs #4. A bare open model losing to frontier is uninteresting and expected. An open model *with the harness applied* matching frontier on team-specific tasks is the result worth publishing.

---

## Workload sources

A single workload may not be enough. Diversity matters for credibility — a result on one repo says "this worked once," a result on five different shapes of workload says "this generalises." Start with one, expand.

1. **Primary workload — autonomous inference service** (separate repo). Generates real PRs (Terraform, Helm, Dockerfile, app code), real drift, real incidents. Highest signal for the agentic-infra story.
2. **Secondary workload — sentinel itself**. This repo already reviews its own PRs. Smaller volume, but useful for keeping the bake-off honest against the framework's own evolution.
3. **Future workloads** — additional adopter repos as they come online. ServiceNow internal repos if/when sanctioned; open-source repos that opt in.

The bake-off table publishes per-workload columns so the reader can see whether the result holds across shapes.

---

## Protocol

Per run (daily, or per merge to `main`):

1. For each fixture × backend, run the configured skills via sentinel.
2. Capture: findings (full bodies for the eval; identity only for telemetry), tokens, latency, error class on failure.
3. Score via the deterministic eval (Layer 1) and the LLM judge (Layer 2, when implemented).
4. Aggregate across backends and emit a per-fixture × per-backend table.
5. Roll up across fixtures into a per-backend summary.
6. Append the run to `docs/bake-off-results/<run-date>/`.

Sample size: every fixture × every backend × N runs (default N=5 to bound LLM variance). The eval harness already supports this — what's needed is the per-provider loop in the runner.

---

## Reading the table

Three outcomes are possible. Each is a valid publication.

| Outcome | What to say |
|---|---|
| Open + harness within 5% quality of frontier, 10× cheaper | "For this workload shape, open + harness is the rational default." Strongest case. |
| Open + harness loses on quality but wins on cost | "Mixed; here are the workload shapes where open suffices and the ones where it doesn't." Useful methodology paper. |
| Open + harness loses on both | "Bare open models can't reach frontier yet on this workload; here's what closes the gap." Less satisfying but still credible. |

The version that loses credibility is the one with no honest acknowledgement of the dimensions where frontier wins.

---

## Non-goals

- **Not a leaderboard.** This is a single team's workload measured rigorously. No claim that the same result transfers to unrelated workloads — the whole point of the harness is that it encodes *team-specific* judgment.
- **Not a frontier vs. frontier benchmark.** SWE-Bench, HumanEval, MBPP already exist. This measures something different: how much does the harness layer matter, on a workload that matters.
- **Not a training run.** No fine-tuning, no RL, no LoRA. Only the harness (skills + CLAUDE.md + RAG + evals + telemetry) and the model. Training is a separate question; see `PLAN.md` v2.0+.

---

## Publication

When the first full quarter of data lands:

1. A blog post with the per-workload, per-backend table and methodology.
2. The eval corpus and run-result artifacts in this repo so any reader can reproduce.
3. A talk submission (LLM observability conferences, infra-AI tracks).

The artifact is the methodology + the numbers. The methodology is reusable by any team running its own bake-off; the numbers are evidence the methodology produces credible answers.

---

## Pointers

- The harness: this repo. The skills, the eval, the telemetry, the LLMProvider adapter (v0.6).
- The workload (primary): the autonomous inference service, separate repo.
- The orchestration: Planner / Implementer / Operator agents — separate repo when the work warrants it. Sentinel stays one component (Reviewer + Operator), not the orchestrator. See `PLAN.md` § Non-goals.
- The plan: `PLAN.md` v0.6 (LLMProvider) and v0.7+ are load-bearing for this experiment.
