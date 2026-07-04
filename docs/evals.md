# How the eval harness works

The eval harness is how we know sentinel is doing its job. It runs the configured skills against frozen-on-disk fixtures and grades the output. Re-run it after every prompt change, every model upgrade, every runner refactor. If the score drops, you regressed something. If the score holds, you're free to ship.

This doc explains *how* the grading works, why it can be called "deterministic," and what that actually buys you. The schema for `expected.json` lives in [`evals/README.md`](../evals/README.md); the strategic rationale (why we ship evals at all, where the LLM judge layer fits) lives in [`PLAN.md`](../PLAN.md#v04--measuring-whether-it-works-evals).

---

## The two-layer architecture

The full pipeline has one non-deterministic part and one deterministic part. The non-deterministic part is the LLM doing the judging. The deterministic part is the scorer grading what the LLM produced. You can re-run the scorer a million times on the same LLM output and get the exact same grade every time — that's what "deterministic" means here.

```
[ LLM judgment loop ]                          [ Scorer ]
─────────────────────                          ──────────
LLM reads diff
LLM greps the repo (Grep #1) ──────────┐
LLM reads files                        │
LLM judges: "change incomplete"        │
LLM returns Finding ───────────────────┘ ───► scorer.matches(expected, finding)
                                                  │
                                                  ├─ skill name == expected?
                                                  ├─ severity ≥ expected?
                                                  ├─ any "match_any" substring
                                                  │  in title+message+suggestion+file?  (Grep #2)
                                                  ├─ any "file_contains" substring
                                                  │  in file?  (Grep #2)
                                                  └─ derived verdict == expected?

                                              PASS / FAIL
```

The important part — where judgment lives — is everything left of the arrow. The LLM looks at code, reasons, decides whether a change is complete, writes the finding. That's the work no one else can do.

The measurement — everything right of the arrow — is dumb substring matching. **That's intentionally dumb.** Because it's dumb, it's reproducible. Because it's reproducible, it can detect when the left side regresses. A dumb ruler measures a smart system. That's the whole trick.

---

## Two different "greps," at different layers

A common point of confusion: there are two grep-like operations in the pipeline. They happen at different times and serve different purposes.

### Grep #1 — inside the LLM step (non-deterministic)

While the LLM is judging change completeness, it uses `grep`, `read_file`, and `list_files` as *tools* in an agentic loop. The LLM picks what to grep for ("look for `enable_performance_insights` in `terraform/`") and interprets the results with judgment. This grep is part of how the LLM *forms* the finding — it runs *during* skill execution. Sonnet drives it; the runner just executes whatever Sonnet asks for. The output is non-deterministic because Sonnet's choices are non-deterministic.

### Grep #2 — inside the scorer (deterministic)

After the LLM produces a `Finding` (with `title`, `message`, `severity`, `file`, ...), the scorer runs *substring matching* over those text fields. This isn't `grep` the shell tool — it's Python `"caller".lower() in finding.message.lower()`. But functionally, yes: it's "grep against the finding's text." No LLM is involved. The inputs are fixed by `expected.json`, which is a static file in version control. Same finding + same expected.json → same grade, always.

The old v0.3 pipeline used something like Grep #2 *during* the skill run, as a "mechanical verify step" that *dismissed findings* when grep returned no matches. That destroyed information — absence of a match doesn't prove absence of the bug. The new design only uses Grep #2 for *scoring*, never for dismissing findings. The LLM's own grep usage (Grep #1, with judgment wrapped around it) is what determines whether a finding exists in the first place.

---

## A worked example, end-to-end

Take the `terraform_variable_removed` fixture. Here's exactly what happens.

### The fixture (static, frozen on disk)

`evals/fixtures/terraform_variable_removed/`:

**`diff.patch`** — removes a variable from a Terraform module:

```diff
- variable "enable_performance_insights" {
-   type    = bool
-   default = false
- }
```

**`repo/`** — the surrounding code the LLM can `grep` and `read` during judgment. Crucially, it contains:

```
terraform/envs/prod/main.tf      → still has: enable_performance_insights = true
terraform/envs/staging/main.tf   → still has: enable_performance_insights = false
terraform/envs/dev/main.tf       → still has: enable_performance_insights = false
```

These are the *callers* — the files that didn't change in the diff but will break on the next `terraform apply` because the module no longer accepts the argument.

**`expected.json`** — the rubric:

```json
{
  "must_find": [{
    "skill": "change_completeness",
    "severity_min": "high",
    "match_any": ["caller", "consumer", "module", "variable", "enable_performance_insights"]
  }],
  "verdict": "incomplete"
}
```

This says: "to pass, the change_completeness skill must produce at least one finding at severity ≥ high whose text mentions any of these concepts. And the overall verdict must be `incomplete`."

### Step 1 — the LLM step (non-deterministic)

The runner calls `ChangeCompletenessSkill.run(diff, context)`. Inside that call:

1. Sonnet receives the diff plus the `grep`, `read_file`, `list_files` tools.
2. Sonnet decides: "this removed a Terraform variable; I should look for callers."
3. Sonnet calls `grep("enable_performance_insights", "terraform/")` — **this is Grep #1**.
4. The runner executes the grep against the fixture's `repo/`. It returns 3 hits across `envs/prod`, `envs/staging`, `envs/dev`.
5. Sonnet reads at least one of the files for context.
6. Sonnet decides it has enough evidence and returns a `Finding`:

```python
Finding(
    skill="change_completeness",
    severity=Severity.HIGH,
    title="Removed Terraform variable still referenced by 3 environments",
    message=(
        "The variable 'enable_performance_insights' was removed from the module, "
        "but terraform/envs/{prod,staging,dev}/main.tf still pass this argument. "
        "Next terraform apply will fail."
    ),
    suggestion="Remove the enable_performance_insights argument from the three caller files.",
    file="terraform/envs/prod/main.tf",
    line=12,
)
```

**The exact wording can change run to run.** Sonnet might write "callers" one day and "downstream environments" the next. The set of files cited might differ slightly. That variance is *in the system under test* — it's part of what we're measuring.

### Step 2 — the scorer (deterministic)

The scorer now takes that `Finding` and the `expected.json` and applies pure pattern matching. No LLM, no randomness, no clock, no network — just substring matching and integer comparisons.

```
must_find check (only one entry in this fixture):
  skill match?     "change_completeness" == "change_completeness"   ✓
  severity ≥ high? HIGH(2) >= HIGH(2)                                ✓
  match_any?       any of [caller, consumer, module, variable,
                           enable_performance_insights] present in
                           title + message + suggestion + file?
                   → "variable" is in the title                       ✓
                   → "enable_performance_insights" is in the message  ✓
                   → "caller" is in the suggestion                    ✓
                   (only one hit is required; we got three)

verdict check:
  derived verdict from findings: HIGH severity present → "incomplete"
  expected verdict:                                       "incomplete"  ✓

→ FixtureScore.passed = True
```

### What "deterministic" actually buys you

If I copy that exact `Finding` object and run the scorer one million times, I get PASS one million times. **The scorer has no state.** That property is what makes it a regression net.

Two concrete things this catches:

**Catch #1 — silent skill failure.**
Tomorrow I "improve" the change_completeness prompt and accidentally make it not produce a finding for Terraform changes. The next eval run gets `findings = []`. The scorer sees the `must_find` is unsatisfied → FAIL. Loud. Reproducible. Always. No human had to notice.

**Catch #2 — wording drift doesn't trip the scorer.**
The old `title_contains` design would have failed if Sonnet phrased the title as "downstream consumers broken" instead of "callers broken" — the title text changed, the keyword wasn't there anymore. Wrong signal: the finding was still correct, but the test went red.

The new `match_any` design widens the haystack to `title + message + suggestion + file`. A correct finding worded differently still passes because the concept ("caller" or "consumer" or "module" or "variable" or the exact variable name) appears *somewhere* in those fields. The scorer is grading the **concept**, not the **style**.

Style is what the LLM-judge layer (v0.4 Layer 2) will grade later — actionability, calibration, grounding. That's a separate concern, behind its own gate.

### Why this matters when the LLM is non-deterministic

Same prompt + same model still varies across runs. Sonnet might phrase the title differently each time. The deterministic scorer is the **stable ruler** against which we measure that variance.

- If 10 runs out of 10 PASS → the skill is working reliably.
- If 9 runs out of 10 PASS → the skill is mostly working but flakes near the rubric boundary; tighten either the prompt or the fixture.
- If 0 out of 10 PASS → real regression. Bisect.

You can re-run the eval N times and look at the distribution. The ruler doesn't move.

---

## Yes, fixtures are static — by design

The fixtures (`diff.patch`, `context.json`, `expected.json`, `repo/`) are frozen on disk and that's the point. They're the immutable reference baseline. Drift in the score = drift in the LLM (or its prompt, or the model, or the runner). The fixtures themselves are version controlled — when we want to change what "correct" means, we change them in a reviewable commit.

Production telemetry (v0.5) will *propose* new fixtures from real PR feedback, but a human still approves each one before it joins the static corpus. The static-ness of the corpus is what makes the score interpretable.

---

## Making the scorer more precise — the typed-claim direction

The deterministic scorer today grades four things well — skill (stamped by the runner, zero brittleness),
severity (floor, not equality), file/location, and the derived verdict — and leans on `match_any`
substring matching for the rest. Substring-on-prose is the *loosest* rung: it works, but it's only as good
as the anchors a human picks. The direction that makes Layer 1 sharper *without* sacrificing determinism is
to **push each finding from prose toward a typed claim, and grade the type, not the text**:

- **First-class `symbol` field** — the skill emits the exact entity it's flagging
  (`enable_performance_insights`) as structured data, not buried in the message. Expected matches it
  exactly/normalized. A correct finding is forced to name its subject, and a discrete field is airtight.
- **`category` per skill from a controlled vocabulary** — e.g. `workflow_security` emits
  `privilege_escalation | missing_permissions | secret_exposure`. Grades "the right *kind* of problem" as
  an enum. Needs an `other` escape and periodic vocabulary review.
- **Location as a set with precision/recall** — compare the set of flagged files against the expected set
  and score the overlap (3 of 4 callers = 0.75 recall, not a binary fail).
- **Diff-derived anchors** — the patch is machine-parseable; extract the changed files/identifiers and
  check the finding references actually-changed code, auto-generating anchors instead of hand-authoring
  `match_any`.

Two ceilings kept honest: every structured field is a new thing the model must populate correctly (trades
prose-brittleness for output-format reliability — mitigate with tool-use / constrained decoding); and
structure makes *where / what-kind* airtight but cannot make *why / is-the-reasoning-sound* deterministic —
that ceiling is exactly where the LLM judge (Layer 2) and humans take over.

*(Design direction — not yet implemented. `match_any` remains the shipped fallback rung.)*

---

## Why not just an LLM judge?

An LLM judge can grade subjectively — actionability, calibration, tone. But it has three problems as the *primary* signal:

1. **Same-family blind spots.** A Sonnet-generated finding graded by Sonnet shares the generator's blind spots. The judge passes things a human wouldn't.
2. **Non-reproducibility.** Re-running the judge gives slightly different scores. Can't tell drift from noise.
3. **Cost.** Every fixture × every skill × every PR = N extra LLM calls. Multiplied across CI, it's expensive.

The deterministic checker has none of those problems. It's the cheap regression net that runs on every PR. The LLM judge (v0.4 Layer 2) sits *behind* the deterministic check, used for the nuance the deterministic layer can't measure, and is itself measured against a small human-graded gold set so the judge can't quietly regress either.

---

## Pointers

- Schema for `expected.json`: [`evals/README.md`](../evals/README.md)
- Strategic context (why v0.4 exists, what v0.5 layers on top): [`PLAN.md`](../PLAN.md#v04--measuring-whether-it-works-evals)
- Code: [`sentinel/evals/scorer.py`](../sentinel/evals/scorer.py), [`sentinel/evals/runner.py`](../sentinel/evals/runner.py), [`sentinel/evals/report.py`](../sentinel/evals/report.py)
- Tests: [`tests/test_evals_scorer.py`](../tests/test_evals_scorer.py) (deterministic, no API key), [`tests/test_integration.py`](../tests/test_integration.py) (gated on `ANTHROPIC_API_KEY`)
