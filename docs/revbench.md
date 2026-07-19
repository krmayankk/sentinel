# revbench — moved to its own repo

**The spec and implementation live in the standalone `revbench` repository**
(`~/src/revbench` locally; publication TBD). This stub keeps sentinel's cross-references
working.

One sentence: a deterministic benchmark for AI code reviewers, mined from git history —
review comments that provably changed code (ceiling: what your best reviewers caught)
and merged PRs that later blew up (floor: what they missed) become frozen, replayable
exam cases; models are graded by deterministic scorers and an executable test oracle,
certified by a published proxy-fidelity audit. History authors the answer keys; no
model ever grades another model in the headline.

Relationship to sentinel:

- **Sentinel consumes revbench.** Onboard Phase 4 (mining) should use revbench cases
  instead of reimplementing backtest B1 — revbench's labels are stricter
  (comment-region causal check + fix-survival filter) and its case format is
  fixture-compatible with `evals/fixtures/`.
- The judgment-corpus spec ([`judgment-corpus.md`](judgment-corpus.md)) remains the
  design for the *public, multi-repo* variant (contamination controls, skills arms);
  revbench is the internal-first, model-comparison core of it, shipped standalone.
