# Skill design

This is the architectural model for what a skill is, where new skills come from, and how the skill system compounds over time. Reread this when the picture goes blurry.

Sentinel encodes team-specific judgment as **skills**. Each skill is a markdown prompt + an agentic tool-use loop + a typed `Finding` output. The skill is the unit of judgment; the framework is everything that lets skills be discovered, evaluated, routed, and retired without losing accumulated evidence.

---

## The three tiers

Skills live at three levels. The framework supports all three, but most teams start in the middle and grow outward.

| Tier | What it is | Examples | Where it comes from |
|---|---|---|---|
| **Raw** | One narrow rule. Pattern match or one specific check. Cheap, fast, narrow scope. | "CHANGELOG.md updated?", "new endpoint has Prom metric?", "PagerDuty entry exists for new service?" | Mined from recurring reviewer comments, incident postmortems, dismissal patterns |
| **Mid-level (where sentinel ships today)** | Vertical-slice expertise. Reasons about a *class* of judgment across files. | `change_completeness`, `workflow_security`, `migration_safety` | Hand-authored as built-ins; over time, distilled from clusters of raw skills |
| **Meta** | Skills about skills. Judgment over the skill set itself. | `skill_hygiene` (already in this repo), pattern recognisers that propose new raw skills, retirement evaluators | Hand-authored at first; later self-generated as the loop matures |

The three tiers are not competing strategies. They compose: raw skills handle the cheap narrow cases, mid-level skills handle the class-wide judgment, meta skills maintain the skill set itself. Each tier feeds the next.

---

## Lifecycle: signal → skill → fixture

The architectural insight that makes the system *compound* rather than merely accumulate:

```
recurring signal (reviewer comments, incident "would-have-caught" lines,
                  dismissal patterns, autonomous-loop failure patterns)
    │
    ▼
raw skill candidate                ← cheap to ship, narrow, often wrong
    │
    ▼
many raw skills accumulate
    │
    ▼
cluster into a class               ← "these are all flavors of completeness"
    │
    ▼
distil into mid-level skill        ← the framework's vertical-slice expertise
    │
    ▼
raw skills retire from active duty
    │
    ▼
their accumulated test cases
   live on as FIXTURES             ← evidence is never thrown away;
   for the mid-level skill            it just changes role
```

Nothing is wasted. The raw skill paid for itself by accumulating evidence; when the mid-level skill subsumes it, the evidence carries forward as the eval corpus for the new skill. This is what closes the v0.5 fixture-proposal pipeline: candidate skills generate their own test cases as they live, and those cases survive the skill itself.

A reverse path exists too. A mid-level skill that becomes noisy on a specific team's repo can be *replaced* by a narrower raw skill for that team — the same judgment, scoped down. Routing decides which to invoke based on the file pattern.

---

## Model-capability mapping

The three tiers map cleanly onto model capability classes. This is the routing thesis made concrete.

| Tier | Best model class | Why |
|---|---|---|
| Raw | Small / cheap / open-weights (Kimi K2 quantised, DeepSeek, Qwen smaller variants, even rule-based when sufficient) | Pattern matching. Narrow scope. Low reasoning required. Runs cheap, runs everywhere. |
| Mid-level | Mid-tier (Sonnet-class, open mid-size like K2 full or DeepSeek V3) | Cross-file reasoning + judgment, but bounded scope per skill. The sweet spot. |
| Meta | Frontier (Opus / GPT-5.x / Gemini Ultra) | Reasoning over the skill set itself, drafting candidates, judging recurring patterns. Open-ended reasoning. Rare invocations, so cost-per-invocation matters less. |

The router does not need to be intelligent. It needs to know *what tier a skill is*. Raw → cheap. Meta → expensive. Mid → tuned per skill, often the configured default. Cost optimisation falls out by construction.

This also reframes the bake-off: open + harness wins the **raw and mid tiers** at meaningful scale. Frontier still wins the **meta tier** for now. That's a defensible position — not a fight with frontier on its home turf, but a clear delineation of where open suffices.

---

## The fleet generalisation

Sentinel is not the system. It is the **template** every learning agent in the fleet implements:

> Skills (encoded judgment) + eval harness (measure if it works) + telemetry (capture real signal) + meta-loop (signal becomes new skills).

| Agent | "Skills" | "Eval harness" | "Telemetry signal" |
|---|---|---|---|
| Reviewer (sentinel today) | Code judgment skills | Fixtures of bad PRs and clean PRs | Reviewer dismissals + acted-on findings |
| Planner | Decomposition strategies | Past goal-to-plan traces | Did the plan succeed downstream? |
| Implementer | Code-generation patterns | Past PRs (good and bad outcomes) | Did the implementation pass review + tests? |
| Operator | Drift-response playbooks | Past incidents + resolutions | Did the response fix the symptom? |

Same architecture, different domain. Each agent learns from its own outcomes. Each agent's meta-loop produces new skills *for that agent*. Each agent can be model-routed independently.

The fleet does not share weights or models. **They share an architecture for self-improvement.** That is what makes a multi-agent system *compound* instead of just exist — the loop runs in every agent, the loops reinforce each other (a sharper Implementer produces PRs the Reviewer learns from; a sharper Reviewer produces feedback the Implementer learns from), and no single model lock-in can capture the value.

---

## Skill anatomy — what makes a candidate worth promoting

Not every raw skill should graduate. The framework needs an explicit promotion criterion. A candidate skill earns its way up the tiers by clearing four gates:

1. **Eval signal.** It scores well on its own accumulated fixtures (precision + recall above a threshold). If the candidate cannot pass its own eval, it has no business being shipped.
2. **Low dismissal rate.** Telemetry shows reviewers (or downstream systems, in the autonomous case) act on its findings more often than they dismiss them.
3. **Stable behaviour across runs.** Run N=5 times on the same fixture set; verdicts agree. Flaky skills do not promote.
4. **Cross-context evidence.** It fires meaningfully on more than one file pattern, more than one PR, more than one author. A skill that only ever fires on one file is a single-purpose lint, not a class-wide judgment.

Retirement is symmetric. A shipped skill loses its place when:

- Dismissal rate climbs above a threshold over a 30-day window.
- Eval recall drops on the corpus it used to handle.
- A higher-tier skill subsumes it on the eval corpus.

When a skill retires, its fixtures stay. They become test cases for whatever skill takes over the territory.

---

## What this means for sentinel's near-term work

This doc clarifies the priorities that PLAN.md already lists, but in cleaner architectural terms:

- **v0.5 telemetry first slice (shipped):** the signal capture that feeds raw-skill discovery. Without telemetry there is nothing to mine.
- **v0.5 fixture-proposal pipeline (open):** the mechanism that turns raw skills into fixtures when they retire — closes the lifecycle loop.
- **v0.6 LLMProvider (open):** the routing substrate. Without it, you cannot send a raw skill to a cheap model and a meta skill to a frontier one.
- **v0.7 operational agent (open):** opens new signal sources beyond PR review — drift events, incidents — feeding the autonomous-case skill discovery.
- **v0.8 skill authoring + auto-discovery (deferred until production data exists):** the meta-loop that drafts raw skill candidates from accumulated signals. Cannot be built credibly without telemetry from a real workload, which is why it waits behind v0.5–v0.7.

The doc is the architectural North Star. The PLAN milestones are the order of construction. Both stay in sync.

---

## Pointers

- Today's mid-level skills: [`sentinel/skills/`](../sentinel/skills/)
- A meta-skill already in the repo: `.sentinel/skills/skill_hygiene.md`
- Telemetry that captures the raw-signal feed: [`docs/telemetry.md`](telemetry.md)
- Eval harness that gates promotion: [`docs/evals.md`](evals.md)
- Bake-off that proves where open + harness wins: [`docs/bake-off.md`](bake-off.md)
- Strategic frame and milestone order: [`PLAN.md`](../PLAN.md)
