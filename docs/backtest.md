# Backtest — proof of judgment

**Status: design. Not built. This is the keystone doc — it unifies three open problems into one mechanism.**

> **Delivery vehicle:** the user-facing flow that composes this engine into a one-command adoption
> product — profile the repo, select skills, backtest, seed baseline, derive skills, open the
> onboarding PR — is specified in [`onboard.md`](onboard.md). This doc is the engine; that doc is
> the product. The B-numbers below map onto onboard.md's O-slices.

Every gap named in [`state-of-sentinel.md`](state-of-sentinel.md) — no wow demo, no production
reliability data, no outside adopter, no certification story for the autonomous gate — is the same
gap: **sentinel has never been scored against reality.** Only against fixtures we wrote for
ourselves. The eval harness proves prompts don't regress; it cannot prove the judgment is worth
anything on a repo we didn't curate.

The fix is already latent in this repo, split across three docs that were never connected:

- [`model-eval-from-mined-fixtures.md`](model-eval-from-mined-fixtures.md) — git history as answer key (seed, unbuilt)
- `PLAN.md` v0.5.5 — provenance classification: caught / missed / never-reviewed (designed, unbuilt)
- `PLAN.md` v0.7.5 — the autonomous gate needs a measured trust basis (designed, unbuilt)

Connected, they are one feature:

> **`sentinel backtest` — replay skills over the repo's own git history, where the outcomes are
> already known, and report what sentinel would have caught and what it would have wrongly blocked.**

Git is a labeled dataset nobody uses. Every revert, every hotfix, every incident-linked PR, every
reviewer comment that forced a fix before merge — that's ground truth about which changes were
unwise, recorded for free, sitting in every repo on earth. Sentinel's `(diff, context) → findings`
interface is already shaped to consume it: a merged PR is a diff; the repo at the parent commit is
the context; the outcome is the label.

---

## Why this is the keystone

One mechanism resolves four milestones that are currently blocked on each other:

| Blocked thing | How backtest unblocks it |
|---|---|
| **Adoption (the wow demo)** | A stranger runs `sentinel backtest` on *their* repo and gets a personalized receipt in ~30 minutes: "of your last 200 merged PRs, 9 were later reverted or hotfixed; sentinel flags 5 at high+, with a 3% false-block rate on the clean ones." No trust in us required, no waiting weeks for PRs to flow. This replaces the case study we don't have with a case study the adopter generates themselves. |
| **Eval corpus growth (v0.5)** | Every true positive and every false block from a backtest is a candidate fixture with a real diff, real repo state, and an outcome-backed label. The fixture-proposal pipeline no longer waits for production users — history *is* production. 4 fixtures becomes 40 in one afternoon. |
| **Gate certification (v0.7.5)** | The autonomous merge gate stops being a policy assertion and becomes an empirical claim: "block at the severity tier where backtested recall on revert-class changes is ≥ X and false-block rate on the clean set is ≤ Y." No other framework can state its gate's operating point. Before an agent commit is trusted to auto-merge, the gate is backtested on that repo — certification, not vibes. |
| **The bake-off / model eval (v0.6, [`bake-off.md`](bake-off.md))** | The backtest corpus is the bake-off's workload. Run Sonnet, Opus, GPT, and an open model through the same replayed history and the "open + harness vs frontier" table fills itself with numbers a buyer believes, because the labels came from real outcomes, not our expectations. |

And it produces the one asset that is industry-level rather than project-level — see *The benchmark
nobody has* below.

---

## Mining the labels

Three positive classes and one negative class, all extractable from any repo with `git log` and the
GitHub API. This is deliberately adjacent to the SZZ algorithm from defect-prediction research —
the mining is not novel and we should not pretend it is. What's novel is what it's used for
(certifying an LLM reviewer, not training a defect model) and that it ships as a self-serve CLI.

**Positive: reverted.** `git log --grep='^Revert'` plus GitHub's revert-PR linkage. The reverted
PR is the unwise change; the revert is the receipt. Strongest label, lowest noise.

**Positive: hotfixed.** A PR whose touched files/hunks were modified again within N hours–days by a
commit matching fix-shaped signals (branch name, `fix:`/`hotfix` message, linked bug issue). Noisier
than reverts; weight accordingly.

**Positive: reviewer-caught.** PRs where a human review comment forced additional commits before
merge. These never became incidents *because a human caught them* — which is exactly the judgment
sentinel claims to encode. The comment text tells you what the judgment was; the pre-comment diff is
the test case. This class is the antidote to survivor bias: without it, backtest only measures what
slipped past humans, which understates what judgment-review is worth.

**Positive: incident-linked.** Issues labeled `postmortem`/`incident` that reference a causal PR.
Rare, but each one is gold — these become permanent fixtures.

**Negative: clean.** Merged, never reverted, untouched by fix-shaped commits for M days, no
incident link. This set measures the false-block rate — and for a gate, the false-block rate is the
adoption-killing number, more than recall. A gate that would have blocked 15% of your clean PRs is
dead on arrival regardless of what it catches.

---

## Replay mechanics

Per labeled PR, exactly the pipeline that already exists — this is the payoff of the
trigger-decoupled design; `Skill.run(diff, context)` doesn't change at all:

1. `diff.patch` = `git diff <merge-base>...<head>` of the historical PR.
2. `repo/` = worktree checked out at the merge-base — the skill sees what the reviewer saw, not the
   fixed present. (`git worktree add` makes this cheap; no re-clone.)
3. Run the routed skills through the normal runner, telemetry on.
4. Score: for positives, did any skill produce a high+ finding pointing at the file/symbol the
   revert or fix later touched? (Same location-based matching the deterministic scorer already
   uses — `match_any` on the fix's touched paths.) For negatives, did anything fire at or above the
   gate threshold?

Output is one report, three numbers plus receipts:

```
sentinel backtest --since 12mo

  Mined: 214 merged PRs → 6 reverted, 11 hotfixed, 23 reviewer-caught, 158 clean, 16 excluded
  Catchable (judgment-class, after triage): 6 + 7 + 19 = 32

  Recall on catchable positives:   19/32  (59%)   ← by class: reverts 4/6, hotfix 4/7, reviewer 11/19
  False-block rate on clean set:   5/158  (3.2%)  at fail_on: [critical, high]
  Gate operating point:            fail_on [critical] → recall 31%, false-block 0.6%

  Receipts: .sentinel/backtest/2026-07-03/  (per-PR: diff, findings, label evidence)
```

Every number links to a receipt — the actual historical diff, the actual finding, the actual revert
commit. That artifact *is* the wow demo, and it regenerates on any repo.

---

## The benchmark nobody has

Public code benchmarks measure **writing** (SWE-bench and descendants) because the repo's test
suite grades for free. **Judging** — "was this change safe, complete, wise?" — has no public
benchmark, because the answer key always had to be hand-built. Backtest mining builds it from
outcomes instead.

The endgame asset: a public corpus of a few hundred replayable judgment cases mined (with
permission) from real OSS repos — each one `(diff, repo-at-parent, outcome label, receipt)` —
plus the harness to run any model against it. Call it what it is: a benchmark for models as
*reviewers*, not authors. Publish the leaderboard: frontier vs open, diff-only vs agentic loop,
with tokens and latency per verdict.

This is the move that changes what sentinel *is*. Tools compete on features and lose to funded
teams; **the project that defines the measurement becomes the reference point** — SWE-bench did not
win by being a better coding agent. Every AI-review vendor today asserts quality with marketing
case studies; none can be compared, because there is nothing to compare them *on*. The project that
ships the yardstick doesn't have to win the review-tool market to matter.

Honest bound on the claim: SZZ-style mining exists in academia, and defect-prediction datasets
exist. What does not exist anywhere, commercial or academic: (1) self-serve backtesting of an AI
reviewer against your own repo's outcome labels, (2) gate certification with a stated, measured
operating point, (3) a public replayable benchmark of code *judgment*. Shipping all three from one
mechanism is the "never done" part — and it's the part a fleet of autonomous coding agents will
need, because when no human reviews the code, the reviewer's measured miss rate is the only safety
number that exists.

---

## The fleet angle

Sentinel is the Reviewer inside a multi-agent loop (see Non-goals in `PLAN.md` — it stays one
component). Backtest generalizes across the fleet exactly the way [`skill-design.md`](skill-design.md)'s
template does: every agent's history is a labeled dataset for that agent.

| Agent | Backtest against | Label |
|---|---|---|
| Reviewer (sentinel) | Merged PRs | Reverted / hotfixed / clean |
| Implementer | Past task→PR traces | Passed review+tests first try, or not |
| Planner | Past goal→plan traces | Plan survived contact with execution, or was reworked |
| Operator | Past incidents | Response resolved symptom, or escalated |

The fleet primitive is: **no agent gets write authority until it is backtested against the history
of the decisions it will make.** Sentinel builds that primitive first because review has the
cleanest labels — but the certification pattern, not the review tool, is the durable contribution.
An autonomous engineering org runs on certified agents the way finance runs on backtested
strategies; nobody currently ships the certifier.

---

## Deriving new skills from the misses

Backtest measures the skills that exist. Its byproduct is more valuable: a set of judgment-class
failures **no current skill caught** — the missed reverts, the missed hotfixes, the things only a
human reviewer flagged. That set is the highest-grade ore for skill discovery, better than reviewer
comments alone (v0.8's plan), because every case comes with an outcome receipt.

The loop, with the property that makes it rigorous:

1. **Cluster the misses.** Group uncaught positives by failure shape (LLM-assisted): "config
   changed, consumer env not updated", "new service, no alert rule", "retry added, no idempotency
   check".
2. **Draft a raw-skill candidate per cluster.** An LLM writes the `.sentinel/skills/*.md` prompt
   from the cluster's cases — each case's diff, fix, and receipt are the few-shot examples.
3. **Validate on held-out history.** Split the mined corpus by time: derive candidates only from
   the older slice, evaluate on the newer slice the candidate never saw. A candidate ships only if
   it (a) catches held-out misses in its class and (b) does not raise the false-block rate on the
   held-out clean set. Train/test discipline on your own git log.
4. **Human approves; the skill enters the normal lifecycle** ([`skill-design.md`](skill-design.md)):
   raw skill → accumulates evidence → clusters into mid-level → retires into fixtures.

Step 3 is the difference between this and every "AI learns from your review feedback" feature on
the market: those adjust prompts and assert improvement; this synthesizes a named check and proves
it empirically against outcomes before it ever runs on a live PR. The skill's backtest report is
its birth certificate — recall and false-block rate on data it wasn't fit to, attached to the PR
that adds it.

This also resequences v0.8: auto-discovery no longer waits for months of production telemetry.
History is the telemetry. A repo with a year of merged PRs can bootstrap a validated,
repo-specific skill set on day one — which is a stronger adoption story than any built-in skill,
because the skills it proposes are *derived from that team's own incidents* and arrive pre-measured.

---

## What's honestly hard

Stated up front so the first run doesn't get oversold:

1. **Base rate.** Most reverts are product decisions, flaky-test noise, or logic bugs no
   judgment-reviewer should catch. Expect a minority of positives to be judgment-class. So the
   pipeline includes a **triage pass** (LLM-assisted, human-confirmed) that classifies each positive
   as catchable / not-catchable *before* scoring, and reports recall on the catchable set with the
   triage receipts published. Recall on all reverts would be a dishonest denominator in both
   directions.
2. **Label noise.** Hotfix detection has false positives; reverts get re-landed. Weight classes
   separately, never mix them in one headline number.
3. **Training-data contamination.** Public repos' histories may be in the model's weights — the
   model may "remember" the fix. Mitigations: prefer post-knowledge-cutoff PRs for public-repo
   benchmark cases; note that the *adoption* use case (private repos) is naturally uncontaminated,
   which is exactly where the wow demo runs.
4. **Cost.** 200 PRs × routed skills × agentic loop is real tokens. Two-pass design: pass 1
   diff-only (`max_turns: 0`) across everything, pass 2 full agentic budget only on positives and a
   sampled negative subset. Publish the token count in the report — the cost transparency *is* part
   of the bake-off story.
5. **Grading fuzz.** "Did the finding point at the problem" needs the same discipline as the v0.4
   scorer: location + severity matching against the fix's touched paths, not title text. Ambiguous
   matches go to the LLM judge tier (v0.4 Layer 2) — which finally gives Layer 2 a reason to exist
   on real data instead of curated data.

---

## Build order

Small, and mostly composition of things that exist:

- **B1 — miner.** `sentinel backtest mine`: labels from git log + GitHub API → `backtest/cases.jsonl`.
  Pure git/API code, unit-testable on this repo's own history, no LLM. (~2–3 days)
- **B2 — replayer.** Worktree-at-parent + existing runner + existing scorer's matching, two-pass
  budget. The report with receipts. (~3–4 days; the runner and scorer already exist)
- **B3 — self-run + first receipt.** Backtest sentinel's own repo and the inference-service repo.
  Whatever the numbers are, publish them — a 40% recall honestly triaged is more credible than any
  claim, and *the blog post is the receipt* ("I backtested my AI reviewer against a year of my own
  mistakes"). This is post 2 of the series the judgment-gap post promised: "how do you know a
  judgment check is actually right?"
- **B4 — fixture promotion.** One command to promote a backtest case to `evals/fixtures/` —
  closes the v0.5 loop without waiting for users.
- **B5 — gate certification.** `sentinel backtest certify --gate 'fail_on: [critical,high]'` →
  the operating-point table. This is the v0.7.5 prerequisite, landed early.
- **B6 — the public corpus.** Only after B1–B5 prove out privately. Mine consenting OSS repos,
  post-cutoff cases only, publish corpus + harness + leaderboard. Full spec:
  [`judgment-corpus.md`](judgment-corpus.md) — same engine pointed at many repos, with the model
  (not the skills) as the variable under test.
- **B7 — skill derivation from misses.** The *Deriving new skills* loop above: cluster → draft →
  held-out validation → human approval. Depends on B1–B4 (needs the miss set and the fixture
  promotion path). This is v0.8's auto-discovery, landed early and with empirical validation
  instead of human vibes — arguably a bigger deal than B6.

B1–B3 fit in roughly two weeks and produce the wow demo, the fixture engine, and the blog post.
Nothing in the existing skill contract changes — this is the trigger-decoupling design cashing its
check: backtest is just one more trigger, where the diff comes from history and the verdict comes
with a receipt.
