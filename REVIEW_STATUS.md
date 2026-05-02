# Sentinel Review Status

Date: 2026-04-26
Updated after merge review: 2026-04-26
Reviewed merged branch: `main` through PR #12 and PR #13

## Executive verdict

Sentinel has a credible AI-native thesis and a real framework skeleton. After the latest fixes, it is materially stronger than the first review: several implementation/documentation mismatches are closed, tool safety is better, and tests expanded.

It is still not yet "Distinguished Engineer quality" as a public framework. That judgment is not based on small cleanup issues alone. DE-level work means the architecture can scale, the product solves a painful real-world problem better than existing approaches, people can adopt it without the author hand-holding them, and the system can survive years of use, extension, operational failures, and changing model/provider behavior.

Sentinel is a strong senior/principal-level prototype with a good architecture and a real AI-native use case. The remaining gap is product proof and durability: clear config semantics, stronger failure behavior, broader evals, production reliability data, evidence of adoption, and a path from clever prototype to ecosystem-quality framework.

The project does show senior-level product and AI systems thinking: skills, custom markdown checks, agentic context gathering, routing, cross-repo search, eval fixtures, and GitHub Action integration are all present. The gap is that the implementation and evidence do not yet support the strongest claims in `README.md` and `PLAN.md`.

## What is already strong

- The core thesis is sound: use LLMs for judgment-heavy review classes such as change completeness, workflow security interactions, migration safety, repo conventions, and cross-file impact.
- The skill architecture exists: built-in skills, custom markdown skills, a shared LLM skill pipeline, typed findings, and a multi-skill runner.
- The repo dogfoods Sentinel through a GitHub Action.
- Unit coverage exists for config, runner behavior, custom skills, cross-repo utilities, tool execution, GitHub formatting, and skill prompt parsing.
- The current non-LLM test suite passes on merged `main`: `88 passed in 1.73s`.

## DE-level criteria

For this project, "Distinguished Engineer quality" should mean more than clean code and passing tests. The bar should be:

- Real pain point: It catches review failures teams actually miss and care enough to install a new CI component for.
- Durable architecture: Skills, context assembly, evals, provider boundaries, and GitHub integration can evolve without rewrites.
- Scalable adoption: A new repo can onboard with clear docs, predictable config, useful defaults, and low false-positive risk.
- Measurable quality: Claims are backed by evals, true/false-positive tracking, regression tests, and real review history.
- Operational resilience: Tool failures, LLM parse failures, provider outages, rate limits, and repo scale are handled explicitly.
- Extensibility: Custom skills are easy to write, test, version, debug, and share without modifying Sentinel internals.
- Ecosystem fit: It complements CodeQL, Semgrep, Dependabot, Gitleaks, and normal CI instead of making vague claims about replacing them.
- Time durability: It avoids tight coupling to one model, one prompt style, one repo shape, or one author's workflow.

Sentinel has the beginnings of this shape, especially around skills and agentic codebase exploration. It does not yet have enough adoption evidence, eval depth, operational hardening, or ecosystem maturity to claim that level.

## Original review findings

The earlier review found these major gaps:

1. `sentinel.yml fail_on` was parsed but not applied to blocking behavior. Blocking was driven only by `SENTINEL_FAIL_ON`.
2. Per-skill `max_turns` in `sentinel.yml` is documented in the plan but not implemented in config parsing or skill construction.
3. README and implementation disagree about verification. README still describes mechanical grep verification, while the current architecture uses an agentic tool loop.
4. README says routing works the same for built-in and custom skills, but custom skills currently bypass routing.
5. Eval quality is early-stage: a few fixtures exist, but there is no full eval CLI, LLM-as-judge rubric, prompt manifest, precision/recall tracking, or CI artifact trend.
6. Tooling needs hardening: path confinement, tool timeouts, better search behavior, failure isolation, and stronger cross-repo operational behavior.
7. A single skill exception can still kill the whole review.
8. Cross-repo checkout is useful but basic: no cache, no ref selection, no dependency discovery, and limited token/security hardening.

## What Claude fixed in the merged PR

Claude's completed work was merged in PR #12 (`a1a1ce7`) and then the MIT license was merged in PR #13 (`79ecc62`).

The merged fixes addressed most of the concrete issues from the first review:

- `sentinel.yml fail_on` is now wired into blocking logic when the action input/env var is empty.
- Per-skill `max_turns` is implemented through `sentinel.yml` config and passed into built-in skill construction.
- README no longer claims mechanical grep verification; it now describes the agentic tool loop.
- README now clearly says routing applies to built-in skills and custom skills always run.
- Tool access is safer: path sandboxing was added for `grep`, `read_file`, and `list_files`.
- `grep` now has a timeout to avoid hanging indefinitely.
- Per-skill exception isolation was added so one failed skill does not stop the full review.
- Tests expanded from 79 to 88 passing non-LLM tests.
- A standard MIT `LICENSE` file was added.

## Remaining review findings after merge

These do not look like emergency blockers, but they still matter before claiming production-grade or DE-level quality.

1. `fail-on: ""` semantics are now ambiguous. The GitHub Action and README say an empty `fail-on` means warning-only, but the code now falls back to `sentinel.yml fail_on` when the env/action input is empty. That means a user may set `fail-on: ""` expecting no blocking while `sentinel.yml` still blocks.
2. Skill crashes are isolated but reported as `low` findings. With normal `fail_on: [critical, high]`, a configured skill can crash and the check can still pass. For a merge gate, infrastructure failures should probably fail separately or be configurable.
3. `PLAN.md` still says per-skill `max_turns` through `sentinel.yml` is planned/not implemented, but the merged code implements it. The plan needs one more doc cleanup.
4. `max_turns` is parsed without validation. Invalid YAML values like strings or negative values can flow into runtime numeric comparisons.
5. The eval story is still early. There are useful fixtures, but not yet enough negative cases, precision/recall measurement, prompt regression tracking, or public quality trend data.
6. Cross-repo support remains basic: no cache, no ref selection, no dependency discovery, and limited operational hardening.
7. There is not yet adoption proof beyond self-dogfooding. DE-quality public frameworks usually need external users, issue feedback, case studies, or usage data showing the idea survives outside its creator's repo.
8. Provider/model abstraction is still thin. The architecture is currently Anthropic-shaped, which is acceptable for a prototype but not ideal for long-lived framework credibility.

## Current technical status

- Merged main has the implementation fixes from PR #12 and the license from PR #13.
- Non-LLM tests pass: `88 passed in 1.73s`.
- The framework is substantially more honest and robust than before the fixes.
- The biggest remaining correctness concern is config semantics around explicit warning-only mode.

## Recommended next steps

1. Decide and document exact precedence for `fail-on`:
   - Option A: empty action input means warning-only and overrides `sentinel.yml`.
   - Option B: empty action input means "use sentinel.yml"; add a separate explicit `warning-only` input.
2. Treat skill execution failures as gate failures when Sentinel is used as a required check, or add a config knob for that behavior.
3. Fix the stale `PLAN.md` statements around per-skill `max_turns`.
4. Validate `max_turns` during config parsing.
5. Expand eval fixtures with both true-positive and false-positive cases.
6. Add public quality metrics before advertising production readiness.
7. Add a small adoption path: `sentinel init`, sample repos, a "first week in warning-only mode" guide, and examples of useful custom skills.
8. Add an explicit model/provider boundary so the framework is not structurally tied to one LLM API forever.

## Public positioning recommendation

Do not advertise Sentinel yet as production-grade or Distinguished Engineer-level infrastructure.

A defensible public description would be:

> Sentinel is an experimental AI code-review framework for judgment-based checks that traditional CI and static analysis do not cover well.

That positioning is honest and still strong. The repo can showcase AI coding workflow knowledge and senior engineering judgment if the docs clearly separate implemented capability from roadmap.

After the merged fixes, a stronger public description is also defensible:

> Sentinel is an AI-native code-review framework for judgment-based checks that traditional CI and static analysis do not cover well. It is experimental but already dogfooded on its own repository.
