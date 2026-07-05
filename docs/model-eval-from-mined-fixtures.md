# Seed: a repeatable model-eval from mined PR fixtures

**Status: seed / idea. Superseded by the full spec in [`judgment-corpus.md`](judgment-corpus.md)
(multi-repo corpus, review-thread labels, contamination controls, multi-model evaluator). This
doc is kept as the original rationale; build from the new spec.**

A repeatable way to measure new open-source / open-weight models against a corpus mined from a team's
own git history (commits, PRs, review comments, reverts, incidents) — using the sentinel
`(diff, context) → findings` harness as the scoring substrate.

This is the **office use case**: not a public leaderboard, a repeatable internal instrument that answers
"is model X good enough for *our* code-review/judgment workload, at what cost, vs. Sonnet/Opus."

Related existing design (this is not net-new to the repo, just aimed at model-eval):
- `docs/bake-off.md` — open + harness vs. frontier methodology (already names Kimi K2 / DeepSeek / Qwen vs Sonnet/Opus).
- `PLAN.md` v0.5 **fixture-proposal pipeline** — telemetry → candidate fixtures for human approval.
- `docs/skill-design.md` — `signal → skill → fixture` lifecycle (evidence never thrown away).
- `PLAN.md` v0.6 **LLMProvider** — the swappable provider seam (NOT built; required to run open-weight backends).

---

## Why this fits the harness (the underserved angle, plainly)

Two task classes: **writing** code (SWE-bench etc. — graded free by the repo's test suite) vs. **judging**
code (risky? complete? safe to merge? — *no* automatic oracle, a human must have decided the answer).
Almost all public benchmarks test writing because grading is free. Judging benchmarks barely exist
because the answer key is hand-built. Sentinel's `expected.json` **is** that hand-built answer key.
So the harness is already shaped to measure the judging task that public evals skip.

The Step-5 property makes it a clean *model-comparison* instrument: navigation is externalized to the
model, everything else (the `(diff, context)` interface, the 3 tools, the deterministic scorer) is fixed
and model-agnostic → an eval delta isolates *model capability* with less scaffolding confound than a
generation benchmark.

---

## The pipeline (mechanical part = easy)

A merged PR is a `(diff, context)` pair sitting in git:
1. `diff.patch` = the PR diff — `git diff <parent>...<head>`.
2. `context` = the repo **at the parent commit** — `git checkout <parent-sha>` so the model sees what
   the reviewer saw, not the fixed version. (The whole-repo `repo_path` + tools model already fits this.)
3. `expected.json` = derived from history signals:
   - review comment that caught a real issue → `must_find` (skill/severity/location).
   - revert, or a follow-up "fix" commit referencing the PR → strong "this was wrong."
   - linked incident / postmortem → gold-standard "this change was bad."
   - merged clean, never reverted, no incident → *candidate* negative (`must_not_find`) — see caveat.

Then: run each backend (Sonnet / Opus / GPT / open-weight) over the corpus via the same skills, score
with the deterministic scorer (Layer 1), N=5 runs to bound variance, emit the per-backend table
(quality / tokens / latency / derived cost) — exactly the `bake-off.md` protocol.

---

## The hard 90% (label quality — this is the actual project)

1. **Noisy labels.** Review comments mix real catches with nitpicks/questions/style. Auto-labeling from
   them measures "does the model agree with whatever the reviewer typed" = model quality **×** reviewer
   quality, confounded. Needs a human-validation pass on a sample (inter-annotator agreement on labels).
2. **Negatives are the trap.** "No review comment" ≠ "nothing was wrong" — reviewers miss things.
   Absence of a flag is not proof of cleanliness (same epistemics as the removed mechanical-verify step).
   Trustworthy negatives are the hardest to mine and the most important for a review eval (don't-cry-wolf).
3. **Context reconstruction** — fiddly but doable: checkout parent SHA; strip anything time-travelled.
4. **Contamination — and here internal repos WIN.** Frontier models may have trained on public GitHub PRs,
   inflating their scores vs. open models. Mining **internal/private** repos avoids that AND measures the
   actual domain. For a fair open-vs-Sonnet comparison, internal is the *right* source, not a compromise.

**Honest verdict:** extraction is a weekend; trustworthy labeling is the real work. This is exactly why
the repo's corpus is 4 fixtures, not 400 — the bottleneck is labels, not diffs.

---

## Blockers before this runs (for a work presentation, don't overclaim)

- **LLMProvider seam not built** (`base.py:284` hardcodes `anthropic.Anthropic()`). Needed to point the
  same harness at GPT / a vLLM/TGI open-weight endpoint. This is the first build task.
- **Corpus scale + label validity** — need low-hundreds of validated fixtures with inter-annotator
  agreement before rankings are trustworthy; 4 is a smoke test.
- **Negative-mining strategy** — unresolved; the make-or-break for review-eval credibility.

---

## Next-session TODO (build order)

1. Prototype the miner: `(parent-sha, head-sha) → {diff.patch, context checkout, raw signals}` over one internal repo.
2. Weak-label deriver: review-comment / revert / incident → draft `expected.json`. Flag confidence.
3. Human-validation harness: review a sample, measure agreement, keep only validated fixtures.
4. Build the LLMProvider seam (v0.6) so open-weight endpoints run through the identical path.
5. Run the `bake-off.md` protocol on the validated corpus; emit the per-backend table.
6. Tackle negatives explicitly — the hardest and most valuable slice.
