# `sentinel onboard` — spec

**Status: design. Not built.** This is the complete spec for the onboarding flow. The measurement
engine underneath it is [`backtest.md`](backtest.md); this doc is the delivery vehicle — the thing
a stranger actually runs. PLAN.md tracks it as v0.5.6.

**The promise, one sentence:** point sentinel at any repo — yours or any open-source repo — and in
one budget-capped run it profiles the repo, picks and installs the right skills, backtests them
against the repo's own history, seeds a compliance baseline, derives repo-specific skills from the
misses, writes the fixtures that keep everything measured, and hands you a single PR containing
your configured, certified review system.

Onboarding is the adoption product. Every competitor's day one is "install the app, wait for PRs,
form a vibe over weeks." Sentinel's day one is a receipt: *here is what I would have caught in
your last year, here is my false-block rate, here is your starting debt, here are three skills I
derived from your own incidents — validated on history they weren't fit to. Merge this PR to turn
it on.*

---

## The product moment

What the user sees (terraform + GHA repo, ~14 months of history):

```
$ sentinel onboard --since 12mo

  Profile      python (61%), hcl (24%), yaml • surfaces: terraform, github-actions, sql-migrations
               squash-merge repo, 214 PRs in range, default branch: main

  Skills       built-in:  change_completeness, workflow_security, migration_safety
               registry:  terraform-ops v3 (cost tagging, state backend, provider pinning)
               → 4 skills selected, routing generated from detected layout      [approve? y/N]

  Mine         214 merged PRs → 6 reverted, 11 hotfixed, 23 reviewer-caught, 158 clean, 16 excluded
  Triage       32 of 40 positives are judgment-class (receipts in report)
  Replay       pass 1 (diff-only): 190 cases • pass 2 (agentic): 47 cases
               recall on judgment-class: 19/32 (59%) • false-block on clean set: 5/158 (3.2%)
               token spend: 4.1M in / 0.4M out (budget: 6M)

  Derive       3 skill candidates from 13 uncaught misses:
                 tf_env_parity        held-out: 3/4 caught, +0 false-blocks   → proposed
                 alert_rule_required  held-out: 2/2 caught, +1 false-block    → proposed
                 dag_backfill_guard   held-out: 0/2 caught                    → rejected (report only)

  Baseline     seeded for 4 skills over routed files: 27 pre-existing violations (ratchet-ready)
  Fixtures     11 backtest cases promoted to .sentinel/fixtures/

  → branch sentinel/onboard opened as PR #341:
      sentinel.yml, .sentinel/skills/proposed/, .sentinel/baseline.json,
      .sentinel/fixtures/, .sentinel/backtest/report.md, CLAUDE-suggestions.md
    Nothing is active until this PR is reviewed and merged. fail_on starts empty.
```

The onboarding PR **is** the wow artifact: self-generated on the adopter's own repo, every number
linked to a receipt, nothing activated without human review.

---

## Principles

1. **Git is the interface.** The entire output is one branch + one PR. No dashboard signup, no
   silent state. Rejecting onboarding = closing the PR.
2. **Nothing activates without approval.** Derived skills land in `.sentinel/skills/proposed/`
   (the loader ignores that subdirectory); `fail_on` is generated empty; the baseline blocks
   nothing until v0.5.5 ratchet logic ships. Onboard configures and proves — the human enables.
3. **Budget-capped, tokens first.** The run takes `--max-tokens` (cost is derived, per the
   PLAN.md measurement rule) and degrades gracefully: mining and profiling are free (no LLM),
   replay samples down before it truncates, and a partial run still emits a partial report that
   says exactly what was skipped.
4. **Receipts everywhere.** Every number in the report links to the diff, finding, and label
   evidence that produced it. Every derived skill carries its held-out validation as a birth
   certificate. Every registry pack ships with fixtures and a backtest receipt or it isn't listed.
5. **Reuse the runner.** Onboard adds *traversals and composition*, never a second skill pipeline.
   `Skill.run(diff, context)` is untouched throughout.

---

## Pipeline

Ten phases. Each names its contract and what it reuses. Phases 0–2 and 4 are LLM-free.

### Phase 0 — Preflight (no LLM)

Checks: git repo present; history depth ≥ `--since` (warn and shrink if shallow); `ANTHROPIC_API_KEY`;
GitHub token if the remote is GitHub (mining degrades to git-log-only without it — see *Honest
limits*); estimated token budget vs. `--max-tokens`, printed and confirmed unless `--yes`.

### Phase 1 — Profile (no LLM)

A file census over the tree plus git metadata. Pure deterministic code, unit-testable offline.

Output — `RepoProfile`:

```python
@dataclass
class RepoProfile:
    languages: dict[str, float]        # extension census, fraction of files
    surfaces: list[str]                # "terraform", "github-actions", "sql-migrations",
                                       # "kubernetes", "protobuf", "helm", "dockerfile", ...
    surface_globs: dict[str, list[str]]  # surface → the globs that detected it (feeds routing)
    merge_style: str                   # "squash" | "merge" | "rebase" (sampled from history)
    default_branch: str
    pr_count_in_range: int
    tree_files: int
```

Surface detection is a static table of glob heuristics (`**/*.tf` → terraform;
`.github/workflows/*.yml` → github-actions; `**/migrations/**`, `alembic/`, `db/migrate/` →
sql-migrations; `**/*.proto` → protobuf; k8s via `apiVersion:` sniff in yaml; etc.). No LLM —
this must be free, instant, and deterministic.

### Phase 2 — Skill selection (no LLM)

Map surfaces → skills via a static table:

| Surface | Built-in | Registry pack (when registry exists) |
|---|---|---|
| (always) | `change_completeness` | — |
| github-actions | `workflow_security` | — |
| sql-migrations | `migration_safety` | — |
| terraform | — | `terraform-ops` (cost tagging, backend, provider pinning) |
| kubernetes | — | `k8s-operations` (probes/runbook/alert judgment) |
| protobuf | — | `api-compat` (wire-compat, consumer bump) |

Print the selection with reasons ("terraform-ops because 24% of tree is .tf"); require approval
unless `--yes`. Registry packs are fetched per *Registry* below; before the registry exists,
this phase selects built-ins only and the table is the registry roadmap.

### Phase 3 — Config synthesis (one small LLM call, optional)

Writes:

- **`sentinel.yml`** — selected skills, `routing` generated from `surface_globs`, `fail_on: []`,
  `telemetry.enabled: true`. Deterministic template fill; no LLM. If a `sentinel.yml` already
  exists, onboard **stops and diffs** instead of overwriting — onboarding an already-onboarded
  repo is an update flow, proposed as edits in the same PR.
- **`CLAUDE-suggestions.md`** — an LLM drafts candidate convention rules from README/docs/CI
  config (e.g. "envs under terraform/envs/ must stay in parity"). Explicitly suggestions: the file
  lands in the PR for the team to curate into their real `CLAUDE.md`. Onboard **never edits an
  existing CLAUDE.md** — it may contain instructions for other tools.

### Phase 4 — Mine (backtest B1; no LLM)

Per [`backtest.md`](backtest.md) § Mining. Walk `git log --first-parent <default-branch>` over
`--since`; map commits to PRs via GitHub API (`merge_commit_sha` — required for squash-merge
repos, which is most repos); label four positive classes (reverted, hotfixed, reviewer-caught,
incident-linked) and the clean negative class.

Output — `.sentinel/backtest/cases.jsonl`, one line per case:

```json
{"pr": 212, "merge_sha": "…", "base_sha": "…", "merged_at": "…",
 "label": "reverted", "label_evidence": {"revert_pr": 230, "revert_sha": "…"},
 "fix_touched_paths": ["terraform/envs/prod/main.tf"],
 "files_changed": 4, "diff_bytes": 9182, "routed_skills": ["change_completeness", "terraform-ops"]}
```

`routed_skills` is computed here (cheaply, from changed paths × the routing just generated) so
replay cost is predictable before any LLM call.

### Phase 5 — Replay (backtest B2)

Two-pass, per backtest.md § Replay mechanics:

- Worktree per case: `git worktree add <tmp> <base_sha>` — repo-at-merge-base is `Context.repo_path`.
- Diff: `git diff base_sha...merge_sha`, through the existing `filter_noise` + `truncate_diff`.
- Pass 1: all cases, routed skills forced to `max_turns=0` (the constructor already accepts the
  override). Pass 2: full agentic budget on all positives + a random sample of negatives
  (`--clean-sample`, default 25%; the false-block rate is reported with its sample size).
- Each case = one `run_skills(diff, context, config, telemetry=sink)` call with
  `event_type="backtest"` — events flow through the existing `JSONLSink` unchanged (`Event.trigger`
  is a free string), so token/latency accounting lands in the same stream live runs use.

**Grading reuses the deterministic scorer, not new matching code:** each positive case is compiled
into a synthetic `expected.json` — `must_find: [{severity_min: "high", file_contains:
[<fix_touched_paths>]}]` — and scored by the existing `score_fixture`. A backtest case *is* a
machine-generated fixture; that identity is what makes Phase 8's promotion a file-copy.

### Phase 6 — Triage (LLM, cheap)

Classify each positive as judgment-class / not-catchable (flaky-test revert, product rollback,
pure logic bug) with a one-call-per-case rubric prompt; a human can override via
`.sentinel/backtest/triage-overrides.yml`. Recall is reported **only over judgment-class**, with
the triage receipts published — the honest denominator, both directions.

### Phase 7 — Baseline seed (optional; the v0.5.5 bridge)

Seeds `.sentinel/baseline.json` so the v0.5.5 ratchet has a starting point the day it ships. A
minimal audit traversal: for each route, batch matching files into chunks (~40k chars), run each
routed skill with an audit prompt wrapper ("enumerate existing violations in these files" — flips
the output contract exactly as v0.5.5 specifies; `Skill.run` unchanged, the wrapper composes the
prompt). Fingerprints are **line-insensitive** — `sha256(skill|file|normalized_title)[:12]` — a
new `anchor_fingerprint()` beside the existing line-sensitive `finding_id()` in
`telemetry/events.py` (which stays, for feedback identity). Skippable via `--skip-baseline`; on
big trees this is the most expensive phase and the budget governor samples top-level dirs first.

### Phase 8 — Derive + fixtures (backtest B7 + B4)

Per backtest.md § Deriving new skills: cluster uncaught judgment-class misses, LLM-draft one
`.sentinel/skills/proposed/<name>.md` per cluster (standard custom-skill format with frontmatter —
they run through `CustomSkill` with zero new machinery when approved), then **validate on a time
split**: derive from the older ~70% of cases, evaluate on the newest ~30% the candidate never saw.
Ship only candidates that catch held-out misses without raising held-out false-blocks; print
rejected candidates in the report anyway (a rejected hypothesis is still a finding about the repo).
Each proposed skill's frontmatter embeds its birth certificate:

```markdown
---
max_turns: 3
derived_from: backtest 2026-07-03
held_out: {caught: 3, of: 4, false_blocks: 0}
---
When a variable changes in terraform/modules/, verify every env under
terraform/envs/ is updated in the same PR. Derived from PRs #212, #187, #94 …
```

Fixture promotion: the top backtest cases (all incident-linked ones, the strongest revert cases,
one representative false-block) are written to `.sentinel/fixtures/<name>/` in the **target repo**
— `diff.patch` + `context.json` + the synthetic `expected.json` from Phase 5 + a worktree snapshot
of only the files the skills touched (full `repo/` copies would bloat the PR; the manifest records
provenance). `sentinel eval run --fixtures-dir .sentinel/fixtures` already works — the flag exists.
The team now has a regression net for *their* config from day zero.

### Phase 9 — Report + PR

`.sentinel/backtest/report.md` (human, receipts inline) + `report.json` (machine). Branch
`sentinel/onboard`, one commit per phase (reviewable piecewise), PR body = the report summary.
`--no-pr` leaves the branch local. The report's final section is *next steps*, generated from the
actual results: "watch findings for a week → set `fail_on: [critical]` → move proposed skills out
of proposed/ → wire the GHA workflow" — the README's adoption journey, personalized.

---

## CLI surface

```
sentinel onboard [--since 12mo] [--max-tokens 6000000] [--clean-sample 0.25]
                 [--skip-baseline] [--skip-derive] [--no-pr] [--yes]
                 [--repo-path .] [--env .env]

# The engine remains independently runnable (backtest.md B1–B5, B7):
sentinel backtest mine|run|certify|derive [...]
sentinel skills install <pack>[@<sha>] | list | search
```

`onboard` is composition: profile → select → configure → mine → replay → triage → baseline →
derive → report. Each `backtest` subcommand stays usable standalone — an already-onboarded repo
re-runs `sentinel backtest run` quarterly to re-certify, without re-onboarding.

---

## Registry ("marketplace"), minimal honest version

A git repo (`sentinel-registry`), not a service. A pack is a directory:

```
packs/terraform-ops/
  pack.yml          # name, version, surfaces: [terraform], skills list, min sentinel version
  skills/*.md       # standard custom-skill markdown — prompts, not code
  fixtures/         # standard fixture dirs proving each skill
  RECEIPT.md        # backtest results on ≥1 real repo (which repo, date, recall, false-block)
```

`sentinel skills install terraform-ops@<sha>` fetches at a pinned commit and copies `skills/` into
`.sentinel/skills/` and `fixtures/` into `.sentinel/fixtures/`. Uninstall = delete files. No
executable code — packs are prompts and fixtures, so the supply-chain surface is prompt content,
not arbitrary execution; installs are pinned by SHA and land in the PR for review like everything
else.

**The listing bar is the differentiator:** no pack is listed without fixtures and a backtest
receipt. A marketplace of measured judgment vs. everyone else's marketplace of vibes. (This bar is
also why the registry comes *after* onboard ships — receipts require the backtest engine.)

---

## Fit with the existing code

Verified against the source as of 2026-07. Onboard composes through existing seams:

| Existing seam | Used by |
|---|---|
| `run_skills(diff, context, config, model, event_type, telemetry)` — pure per-diff engine | Phase 5 replay, Phase 7 audit chunks, held-out validation |
| `Context.repo_path` (+ `extra_search_paths`) | worktree-at-merge-base per case |
| `CustomSkill` / `load_custom_skills` — skills are markdown + frontmatter | derived skills, registry packs; zero new execution machinery |
| `evals.scorer.score_fixture` + `expected.json` schema (`file_contains`, `severity_min`) | backtest grading — cases compile to synthetic expecteds |
| `evals.runner` + `--fixtures-dir` flag | promoted fixtures run in the target repo unchanged |
| `telemetry.Event` (`trigger` is a free string) + `JSONLSink` | `"backtest"` / `"onboard"` / `"audit"` events, same stream |
| `preprocess.filter_noise` / `truncate_diff` | historical diffs |
| `config.load_config` / `Route` / `SkillConfig` | generated `sentinel.yml` round-trips through the existing parser (generator emits, parser validates — a unit test) |

New modules (all under `sentinel/`): `onboard/profile.py`, `onboard/select.py`,
`onboard/configgen.py`, `backtest/mine.py`, `backtest/replay.py`, `backtest/triage.py`,
`backtest/derive.py`, `backtest/report.py`, `audit.py`, `registry.py`, plus entrypoint
subcommands. GitHub read-side API (PR listing, `merge_commit_sha`, review threads) is new;
`github.py` today only posts comments.

**Preconditions — real bugs in the current code that would corrupt published numbers:**

1. `runner.py:165` — `parts[-1].lstrip("b/")` is a char-set strip, not a prefix strip: any changed
   path starting with `b` is mangled, which corrupts routing and therefore `routed_skills` in
   mining and recall in replay. Fix to `removeprefix("b/")` (and reuse `preprocess._DIFF_FILE_HEADER`
   instead of splitting on spaces, which breaks on filenames with spaces).
2. `base.py:417` — `Severity(item["severity"])` silently drops findings on case mismatch
   (`"HIGH"` → `continue`). Silent finding loss is fatal in a measurement run; normalize case.
3. `base.py:317` — `response.content[0].text` assumes the first block is text; breaks under any
   non-text leading block. Use the existing `_extract_text`.
4. `finding_id` is line-sensitive; the baseline needs the line-insensitive `anchor_fingerprint`
   (Phase 7) — additive, both coexist.

Known quirk, acceptable for v1: routing uses `fnmatch`, where `*` crosses `/`, so `terraform/**`
works by accident. Document it; don't change matching semantics mid-flight.

---

## Cost model

Budget is tokens (measured); dollars are derived. Ballpark for the 214-PR example, Sonnet-class:

| Phase | Est. tokens (in/out) | Notes |
|---|---|---|
| Profile, select, mine | 0 | deterministic |
| Config synthesis | ~20k / 2k | one call |
| Replay pass 1 (190 × diff-only) | ~1.2M / 100k | prompt ~2k + filtered diff ~4k avg |
| Replay pass 2 (47 × agentic) | ~2.0M / 150k | ~6–8 turns × routed skills |
| Triage (40 cases) | ~150k / 20k | rubric call each |
| Baseline (routed files, chunked) | ~0.5–2M / 80k | most variable; sampled under budget pressure |
| Derive + held-out validation | ~400k / 60k | clusters + re-replay of held-out slice |
| **Total** | **~4–6M in** | roughly $15–25 at current Sonnet pricing |

Governor: a shared token meter (from the replay telemetry events) checked between phases and
between cases; on `--max-tokens` exhaustion the run downsamples (negatives first, then baseline
dirs), never silently truncates a number — every reported metric carries its actual N. The spend
itself goes in the report: cost transparency is part of the bake-off story, and onboard is
incidentally the first real bake-off workload (rerun with `--model` to fill the comparison table).

---

## Honest limits

- **Non-GitHub remotes / no token:** mining degrades to git-log-only — reverts still work
  (`--grep` + `--first-parent`), reviewer-caught and PR linkage don't. The report says which
  classes were unavailable.
- **Shallow or young repos:** under ~50 PRs the recall number is anecdote, not statistics; the
  report labels it as such and leans on baseline + config as the deliverable.
- **Training-data contamination** on public repos, **label noise**, **base rate**: per
  backtest.md § What's honestly hard. Onboard's report repeats the mitigations inline so the
  numbers are never quoted without their caveats.
- **Monorepos:** worktree-per-case on a huge repo is disk-heavy; v1 uses one worktree reused
  serially (checkout per case), parallelism deferred.
- **The derive phase can produce zero shippable skills.** Likely on well-reviewed repos. The
  report says so plainly — "your humans catch what sentinel's built-ins catch" is itself a finding,
  and the false-block rate + baseline still justify the PR.

## Non-goals

- No hosted service, no signup, no central data plane — the trust posture is unchanged (BYOK, PR
  as the only output).
- No auto-enable: onboard never sets `fail_on`, never activates proposed skills, never edits
  CLAUDE.md.
- No pack payments/ratings in the registry v1 — the listing bar (fixtures + receipt) is the
  quality mechanism.
- Not a replacement for the v0.5 production loop: onboard bootstraps from history; live telemetry
  keeps it current. History is the cold start, production is the engine.

## Build order

Revises backtest.md's B-list into delivery slices; the B-numbers are the engine work inside them.

- **O1 — engine on this repo** (B1–B3 + the four precondition fixes): mine + replay + triage +
  report, run against sentinel itself and the inference-service repo. First receipt, blog post 2.
- **O2 — onboard v1** (Phases 0–5, 9): profile, select (built-ins only), configgen, backtest,
  report-as-PR. This alone is the adoption demo.
- **O3 — baseline + fixtures** (Phase 7 + B4): audit traversal, `anchor_fingerprint`, fixture
  promotion. Feeds v0.5.5 directly.
- **O4 — derive** (Phase 8 / B7): clustering, drafting, held-out validation.
- **O5 — registry** (+ B5 certify, B6 public corpus): first two packs (terraform-ops,
  k8s-operations), authored with O1's tooling so they ship with receipts by construction.

## Open questions

1. Fixture `repo/` snapshots in the target repo: touched-files-only keeps the PR small but weakens
   replays that need to grep beyond them — measure how often pass-2 findings cite un-snapshotted
   files before deciding.
2. Where does the triage rubric's judgment-class boundary live — global, or per-surface (an infra
   revert and an app revert have different catchability priors)?
3. Registry governance once outside contributions arrive: who verifies receipts? (Deferred until
   the problem exists.)
4. `onboard` on a repo that already runs a competitor bot: mine that bot's PR comments as a fifth
   label class ("competitor-caught")? Tempting for the bake-off; possibly hostile. Decide later.
