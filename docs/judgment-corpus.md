# Judgment corpus — evaluating models as reviewers, at scale

**Status: design. Not built.** This spec supersedes and expands the seed in
[`model-eval-from-mined-fixtures.md`](model-eval-from-mined-fixtures.md). It is written to be
severable: you can build it inside sentinel, or lift it standalone as (a) a scraper that builds
the corpus and (b) an evaluator that runs any model against it.

**The instrument, one sentence:** mine thousands of well-reviewed open-source repos for moments
where judgment was exercised on a code change — a reviewer caught something, or an outcome
(revert, hotfix, incident) proved something was missed — freeze each moment as a replayable case,
and run any model through the fixed sentinel harness against the corpus to answer: **is this
open-weight model good enough to be a reviewer, at what cost, versus the frontier?**

---

## The key synthesis — the whole design in five steps

1. **In sentinel today:** a model reads `(diff + context)` and produces **findings**; a
   human-written `expected.json` grades them. The model never writes the answer key.
2. **The corpus flips the key's author, not the pipeline:** `expected.json` is *mined* — human
   review comments that provably changed code, and outcomes (reverts, hotfixes, incidents), are
   transcribed into answer keys at scale. History authors the key; no model, no skill.
3. **Arms 0–1 — grade any model against history:** hand the same historical `(diff + repo-at-SHA)`
   to a new model, compare **its findings** to the mined key. This has almost nothing to do with
   sentinel — only the fixture format, the three-tool harness, and the deterministic scorer are
   borrowed (~500 lines, deliberately severable).
4. **Arm 2 — same cheat sheet, every student.** Split the corpus in time: a *study half* and an
   *exam half*. A frontier model reads the study half **once** and writes skills from it — a
   cheat sheet of encoded judgment. Then **every model takes the exam half carrying that same
   cheat sheet**, produces findings, and is graded — as always — against the mined key. Compare
   *scores*, never findings-to-findings. The question: does a cheap model with the cheat sheet
   score as well as a frontier model without one? That is sentinel's moat claim, made
   falsifiable.
5. **Arm 3 — every student writes a cheat sheet.** Each model takes a turn as the *author*: it
   reads the study half and writes its own skill set. A **fixed executor model** then takes the
   exam once per cheat sheet; each skill set's exam score (against the same mined key) is its
   author's score. This grades models as skill *writers*. Not "did it derive the same skills" —
   skills are graded by **effect**, never text similarity; two differently-worded skills that
   catch the same misses are equal.

One rule holds everywhere: **the mined key is the only referee.** Models are never graded
against each other's output — every arm grades findings against `expected.json` and compares
scores. Each rung of the ladder holds everything below it fixed, so the deltas between rungs are
the measured value of one layer: the model's raw judgment (0), hand-authored skills (0→1), mined
skills (1→2), and skill authorship (3).

---

## How this differs from backtest (same engine, different variable)

|  | [`backtest.md`](backtest.md) | Judgment corpus (this spec) |
|---|---|---|
| Scope | One repo's history | Thousands of repos |
| What varies | The skills (certify them for this repo) | The **model** (harness and skills held fixed) |
| What's held fixed | The model | The skills + tools + scorer |
| Question answered | "Does sentinel work on *my* repo?" | "Does model X work as a *reviewer*, vs. model Y?" |
| Consumer | An adopting team | Model evaluation — the office use case, the bake-off, eventually a public leaderboard |
| Label source | Outcomes (reverts, hotfixes, incidents) | Outcomes **+ review threads** (what expert humans caught) |

Shared machinery: the miner, the replay harness (worktree at merge-base + `run_skills`), the
deterministic scorer, the telemetry accounting. New machinery: repo selection, review-thread
mining, corpus packaging, the multi-model evaluator, contamination bookkeeping.

The property that makes this a *clean* model comparison (from the original seed doc, still the
core insight): the harness externalizes navigation to the model — three fixed read-only tools, a
fixed `(diff, context)` interface, a fixed deterministic scorer. A score delta between two models
isolates **model judgment capability** with less scaffolding confound than generation benchmarks,
where agent framework differences dominate. And the task itself is the one public benchmarks
skip: every major benchmark grades code *writing* (the repo's test suite grades for free);
almost nothing grades code *judging*, because the answer key had to be hand-built. Here it is
mined.

---

## The two label families

### Family A — outcome labels (what reality caught)

Identical to backtest mining: reverted PRs, hotfixed PRs, incident-linked PRs as positives;
long-clean merged PRs as negatives. See backtest.md § Mining. Strong labels, but sparse per repo
and biased toward what *escaped* human review — they measure the model against reality's residue.

### Family B — review labels (what expert humans caught) — the richer vein

High-review-culture repos (kubernetes, rust, postgres mirrors, cpython, terraform providers…)
contain millions of review comments. A tiny fraction are judgment: a human read the diff,
reasoned about blast radius / compatibility / operational consequence, said so, and **the author
changed the code in response**. That last clause is the label.

Extraction contract — a case is minted only when all four hold:

1. A review comment thread anchors to a diff region of a PR that later merged, and the **comment
   author is not the PR author** — self-review annotations are explanations, not judgment labels.
2. **Commits pushed to the PR after the comment modified the commented region** (GitHub's
   review-thread → position mapping + subsequent commit diffs). Comment → code change is the
   causal receipt; comments that changed nothing are opinions, not labels.
3. A classifier (LLM, then human-audited sample) **tags — it does not filter**. Every surviving
   comment gets a class from a fixed taxonomy: the judgment classes (blast radius, API/wire
   compatibility, migration/operational safety, missing-consumer-update, security interaction,
   convention violation with stated consequence) **and the non-judgment catches reviewers also
   make** (correctness-bug, concurrency, error-handling, performance). Only noise is dropped —
   style nits, naming bikesheds, questions, praise, bot comments (dominant by volume; author-type
   + text-pattern filters first, classifier second). The corpus keeps every tagged class; which
   slices count toward a report is a query-time choice. Sentinel's headline number is the
   judgment slice — the thesis under test — but the instrument covers the full review surface,
   and the office use case should score all classes.
4. The pre-comment state is reconstructable: `diff` = base…(last commit before the comment),
   `repo` = merge-base checkout. The model sees exactly what the human reviewer saw.

The task: given that pre-review diff and repo, does the model flag the region the human flagged,
for the right class of reason, at a defensible severity? The human's comment text (never shown to
the model) becomes the grading key.

Family B is what makes famous repos the right mining bed: k/k's review culture *is* a corpus of
senior-engineer judgment, sitting in public, labeled by causality, and nobody has harvested it as
an answer key.

---

## One case, end to end — the precise mechanics

The single most-asked question about this design: does the scraper track every file's versions
and diff them across commits? **No. Git already is that database.** The scraper never
reconstructs history itself — it only ever asks git two things: `checkout(SHA)` (materialize the
tree as it was) and `diff(A...B)` (any change between two points). The GitHub API's job is only
to supply the *anchors* — which SHAs and which regions matter. Concretely, for one Family-B case:

1. **Scrape (API, no git):** PR #841, base SHA `B`, commits `c1..c6`, merged (squash) at time M.
   Review thread: comment by a non-author at time t, and the API gives us the three anchor fields
   that make everything else mechanical — `path` (the file), `line`/position (the region), and
   `original_commit_id` (= `c3`, the exact commit the reviewer was looking at). Plus thread
   resolution state and replies.
2. **Causal check (git, pure code):** did any commit in `c4..c6` (after t) touch `path` near the
   commented region? Answer via `git diff c3..c6 -- <path>` intersected with the region. Yes →
   the comment provably changed the code → candidate case. (Squash-merged repos delete branches,
   but GitHub permanently keeps every PR's commits under `refs/pull/841/head` — one
   `git fetch origin 'refs/pull/841/head'` and `c1..c6` exist locally. This works on PRs of any
   age; git history and PR refs don't expire.)
3. **Freeze the case:** `diff.patch` = `git diff B...c3` (exactly what the reviewer saw, *before*
   the fix), `case.json` records `repo URL + B + c3`, `expected.json` = must_find at `path` /
   region with the comment's class, `grading.json` = the comment text (hidden from models, used
   by the judge layer). **No skill and no model authors `expected.json`** — the human reviewer
   already evaluated this diff when it was live; minting merely transcribes that verdict (and,
   for Family A, the revert/fix's touched paths) into the scorer's format. The answer key's
   author is history, not an LLM.
4. **Evaluate (existing sentinel pipeline, unchanged):** materialize `repo/` =
   `clone --filter=blob:none` + `checkout B` (cached per repo, shared across that repo's cases);
   run `run_skills(diff, context)` exactly as sentinel runs today — the model explores with
   grep/read_file/list_files rooted at the checkout; findings come back as JSON.
5. **Grade:** the existing deterministic scorer matches findings against `expected.json` (right
   file/region, sufficient severity); the judge layer checks reason-match against the hidden
   comment. Nothing about how skills execute changed — only where the answer key came from.

Family-A cases are the same shape with different anchors: `B` = merge-base, freeze point = merge
SHA, expected region = what the revert/hotfix later touched.

At thousands-of-repos scale the only new engineering is logistics, not parsing: shallow/partial
clones on demand, an LRU cache of materialized checkouts, and resumable API cursors. There is no
custom diff engine, no per-file version tracking, no AST parsing anywhere in the pipeline.

## Pipeline

### Stage 1 — repo selection (deterministic + one curation pass)

Criteria, scored mechanically from GH API: OSI license; ≥ N merged PRs/year with ≥ M% carrying
human review comments (review culture proxy); active in the last 90 days; language/domain
spread enforced by quota (systems, web, infra/IaC, data, ML) so the corpus doesn't collapse into
"Go microservices"; deliberate inclusion of infra-heavy repos (terraform modules, helm charts,
operators) because that's sentinel's home domain. Target: **~200–1000 repos** for mining;
"thousands" is a ceiling, not a requirement — quality bar beats repo count, and Stage 3 yield
per repo drops fast outside high-review-culture projects.

### Stage 2 — scrape (no LLM)

GraphQL API (REST burns rate limits at this volume): merged PRs in window → review threads with
positions → PR commits with timestamps → revert/hotfix linkage. Persist raw to
`corpus/raw/<org>__<repo>/*.jsonl.zst`. Idempotent and resumable (cursor per repo); a full run at
1000 repos is days of polite API traffic, so the scraper is a long-running job, not a script.
Rate budget, token pool, and retry/backoff are part of the design, not afterthoughts.

### Stage 3 — case minting (LLM classifier + filters)

Family A: same labeler as backtest. Family B: bot/style filters → judgment classifier → causal
check (region modified post-comment) → reconstruct pre-comment state. Dedup near-identical cases
(same repo, same file, same comment class) — review culture repeats itself, and a corpus where
40 cases are "you forgot to update the generated client" measures memorization of one lesson.

Expected yield (order of magnitude, to be validated in the pilot): high-culture repos give
~5–50 Family-B cases per 1000 PRs after filtering. 200 repos × a few years ≈ **2,000–10,000
candidate cases → curate to a benchmark set of ~1,000** with per-class and per-domain balance,
plus a held-back private split (see *Contamination*).

### Stage 4 — packaging

A case never redistributes the repo (license + size). Stored:

```
cases/<id>/
  case.json      # repo URL, base SHA, head SHA, label family + class, difficulty tier,
                 #   created_at (for cutoff slicing), license, provenance URLs
  diff.patch     # the PR diff at the case's freeze point (fair-use scale excerpt)
  expected.json  # sentinel scorer schema: must_find (file_contains from the flagged region /
                 #   fix-touched paths, severity_min, class), must_not_find for clean cases
  grading.json   # NOT shown to models: human comment text / revert message, for the judge layer
```

`repo/` is materialized at eval time: `git clone --filter=blob:none` + checkout SHA, cached
locally. The corpus repo itself stays small (patches + JSON); the evaluator needs network + disk
on first run. Cases from deleted/force-pushed repos get tombstoned by a periodic validity check.

### Stage 5 — the evaluator

```
judgment-eval run --corpus ./cases --model <id> --provider anthropic|openai-compat|bedrock
                  [--slice post-2026-01] [--class migration_safety] [--max-cases N] [--seed S]
judgment-eval compare run1/ run2/          # the bake-off table
```

- **Provider seam is the hard dependency** — sentinel's `LLMProvider` (v0.6, still unbuilt). An
  OpenAI-compatible adapter covers every serious open-weight serving stack (vLLM, SGLang, TGI),
  which means **the eval runs against the GPU inference service directly** — the corpus is the
  natural first production workload for the ephemeral-RunPod platform, and the bake-off's
  quality × tokens × latency × cost table fills from one command.
- Fixed harness per case: same skill prompts, same three tools, same `max_turns`, temperature
  pinned, N=3 repeats on a subsample to report variance (flaky judgment is a finding about the
  model).
- Scoring: **Layer 1** — existing deterministic scorer against `expected.json` (did it flag the
  right place at sufficient severity; did it stay quiet on clean cases). **Layer 2** — LLM judge
  from a *different model family* grades semantic match against `grading.json` (did it catch it
  *for the human's reason*), actionability, calibration; judge gated against a ~50-case
  human-graded gold set before its scores count (the v0.4 Layer-2 design, finally with a reason
  to exist).

### Stage 5b — the two evaluation arms

The same corpus supports a ladder of experiments, and they answer different questions:

- **Arm 0 — bare reviewer (the true baseline).** No skills at all: one fixed generic prompt
  ("review this diff for judgment-class problems; verify with tools before reporting") + the
  three read-only tools + the JSON findings contract. Nobody writes any judgment content —
  this is the purest model-isolation measurement, immune to skill-coverage gaps (a mined case
  about a topic no built-in skill covers still gets a fair shot). Cheapest arm; run it on
  everything.
- **Arm 1 — built-in skills.** Model + sentinel's *generic hand-authored built-ins* (the ones in
  `sentinel/skills/` today — written by sentinel's maintainers, identical for every model).
  Measures the model inside the harness a team would actually deploy. This is the
  model-shopping question: "is open-weight X a competent reviewer in sentinel, out of the box?"
  Caveat the report must carry: Arm 1 recall is upper-bounded by built-in skill *coverage* —
  cases outside any built-in's territory are scored, but the Arm0→Arm1 delta on them is
  attributed to the skill layer, not the model.
- **Arm 2 — model + derived skills.** Skill derivation ([`backtest.md`](backtest.md) § Deriving
  new skills) runs **once**, by a single designated deriver model (frontier-class), on the
  corpus's **training split** — mined judgment becomes a fixed set of encoded skill files. Then
  every model under test runs **with that same skill set installed**, on the **held-out split**.
  The variable is still only the executor model; what changed vs. Arm 1 is that the harness now
  carries mined judgment. This measures whether a cheap model can *execute* encoded judgment —
  the framework's central claim: open model + mined skills ≥ frontier model running bare. The
  split discipline is mandatory — deriving skills from the cases you grade on measures leakage,
  not judgment.

To be explicit about what Arm 2 is **not**: it is not "did each model derive the same skills"
(that's a different experiment — see Arm 3), and it is not "did the model pick the right skill
to fire" (skill routing in sentinel is deterministic by file glob, never a model decision).

- **Arm 3 (optional, later) — vary the deriver.** Hold the executor fixed; let each model *write*
  the skills from the training split; grade the resulting skill sets on the held-out split. This
  measures meta-tier capability — judgment *about* judgment — the tier
  [`skill-design.md`](skill-design.md) predicts stays frontier-only the longest. Run it only once
  Arms 1–2 are producing stable numbers; it inherits all their machinery.

Arms 0–1 are the office instrument and ship first (no derivation machinery needed). Arm 2 is the
bake-off's sovereignty thesis made falsifiable — and it is not a one-shot "was derivation
correct" check; it's a standing instrument with three recurring uses: (a) **model-churn
regression** — every model swap re-runs Arm 2 to verify accumulated skills still transfer
(PLAN.md's portability commitment, as a checkbox instead of a claim); (b) **fleet economics** —
it locates the skill tier at which cheap-model-plus-skills suffices, which prices the autonomous
gate at agent-commit volume; (c) **moat decay tracking** — the Arm0→Arm2 delta re-measured per
model generation shows when the skill layer is being absorbed into base models, quarters before
adoption data would. The arms form a ladder — each rung adds one layer
of scaffolding, so the *deltas between rungs* are the measured value of each layer: Arm0→Arm1 =
what hand-authored skills add, Arm1→Arm2 = what mined skills add, Arm 3 = whether a model can
mint that value itself. One table, per model, per rung — that table is simultaneously the model
buying guide and the empirical defense of sentinel's entire skill thesis (if Arm0→Arm2 deltas
are ~0 for frontier models, the thesis is wrong and we'd want to know).

### Stage 6 — the report

Per model: recall by label family and judgment class, false-positive rate on clean cases,
location precision, severity calibration, judge scores, tokens per verdict, latency p50/p95,
tool-turns used (a model that needs 9 greps to find what another sees in 2 is measurably more
expensive at equal recall), derived $/1k-verdicts for both API pricing and GPU-hours. The
per-class breakdown is the buying guide: an open model may match frontier on migration-safety
(pattern-adjacent) while trailing badly on cross-file completeness (navigation-heavy) — exactly
the raw/mid/meta routing split [`skill-design.md`](skill-design.md) predicts, now with numbers.

---

## Contamination — the problem that decides credibility

Public repos are in every model's training set; a model may "remember" the review or the revert.
Untreated, the corpus measures recall of memorized GitHub, and any strong claim dies on this.

1. **Every case carries `created_at`**; every eval run declares the model's knowledge cutoff and
   scores the **post-cutoff slice** as the headline number. Pre-cutoff scores are reported
   separately, labeled contaminated-possible. The pre/post *gap* is itself a published metric —
   it estimates memorization, and a model with a large gap is flagged as such.
2. **Rolling refresh:** the scraper re-runs monthly; new cases enter dated slices. The benchmark
   is a *living* instrument (LiveBench-style) — this is also the saturation answer: when models
   max out old slices, fresh slices keep discriminating.
3. **Private split:** ~20% of cases (and for office use, cases mined from private org repos —
   uncontaminated by construction) never publish. Public leaderboard submissions are spot-checked
   against the private split; a public/private divergence is evidence of benchmark gaming.

---

## Ethics and legality

- Mining public review threads is analysis of public data; fine. **Publishing** requires care:
  cases carry provenance links rather than reproducing full threads; reviewer identities are
  dropped from `grading.json` (the judgment matters, not the name).
- Never publish present-tense findings lists for named repos ("here are k/k's current
  violations") — corpus cases are historical, already-fixed moments. Anything security-flavored
  and possibly still live goes through disclosure, not a dataset.
- License: only OSI-licensed repos; diffs are excerpt-scale; `repo/` is fetched by the evaluator
  from the origin, never redistributed. Each case records its license.

---

## Sizing and cost

Pilot (validate yield + grading quality): 10 repos, ~100 cases, 2 models — a weekend of scraping,
~$50–100 of eval tokens.

Full v1: ~1,000 curated cases. One model, one full pass: ~1,000 × (prompt ~2k + diff ~4k +
agentic turns ~15k avg) ≈ **~20M input tokens** per model — real money on frontier APIs and
exactly the argument for running open-weight contenders on your own GPUs. Scraping compute is
trivial; API-time and politeness dominate.

Mining cost breakdown (the LLM touches only classification, and only survivors): scraping is
$0 (rate-limited time, not money); deterministic filters + the causal check are pure code. At
200 repos ≈ 1M raw comments → filters + causality leave ~50–100k candidates → ~1.5k tokens each
through a Haiku-class classifier ≈ 100–200M tokens ≈ **$200–500 once**, then ~monthly increments
at a fraction of that. Pilot scale: under $20. The corpus is cheap to build; evaluating models
against it is where the budget goes — which is the right way around for an instrument meant to
be re-run against every new model release.

---

## Fit with sentinel

Reused: mining logic (backtest B1), replay harness, deterministic scorer + `expected.json`
schema, fixture directory format (a corpus case is a fixture with extra metadata), telemetry
accounting, the LLM-judge design from v0.4. New: `corpus/select.py`, `corpus/scrape.py` (GraphQL,
resumable), `corpus/mint.py` (classifier + causal check), `corpus/package.py`, `judgment-eval`
CLI (or `sentinel corpus …` subcommands), the `LLMProvider` seam (v0.6 — the one sentinel change
this spec forces, and it was already committed).

Severability: the corpus format depends only on the `expected.json` schema and the three-tool
harness contract, both of which are small and stable. Lifting this into its own repo later costs
a vendored scorer and tool-executor — deliberately kept import-light for that reason.

Sequencing vs. onboard/backtest: **build backtest first** (O1 in [`onboard.md`](onboard.md)).
It debugs the shared engine on one repo where you can hand-verify every label, and its four
precondition bug-fixes are the same ones this spec needs. The corpus is the same machinery
pointed outward — start its pilot the week backtest produces its first trustworthy receipt.

## Build order

- **C1 — pilot miner:** 10 high-culture repos, Family B extraction end-to-end, hand-audit 50
  cases for label quality. *Go/no-go: is the causal-check yield clean enough?*
- **C2 — evaluator on the pilot:** LLMProvider seam + OpenAI-compat adapter; run Sonnet vs. one
  open-weight model (via the GPU inference service); first comparison table. **This is the
  office deliverable** — everything after it is scale and rigor.
- **C3 — scale + curate:** 200 repos, dedup, class/domain balancing, difficulty tiers, ~1,000
  cases, private split.
- **C4 — judge layer + gold set:** different-family judge, 50-case human gold set, variance
  reporting.
- **C5 — living benchmark:** monthly slices, contamination dashboard, public leaderboard — only
  if C2–C4 prove the instrument is worth defending in public.

## Open questions

1. Family B severity: human comments rarely state severity — infer from comment class + what the
   fix touched, or grade Family B on detection + reason-match only and leave calibration to
   Family A? (Lean: the latter; don't invent labels.)
2. Difficulty tiers: by tool-turns-needed (measured from a strong model's trace), by human
   grading, or by how many models fail it? (Lean: failure-count — self-calibrating as models
   improve.)
3. Multi-language grading parity: does the scorer's file/region matching behave equally across
   monorepo layouts (k/k's vendor dirs, bazel outputs)? Needs pilot data.
4. Whether office/private-repo cases and public cases can share one corpus format with a
   `visibility` field, or need separate stores. (Lean: one format, two stores.)
