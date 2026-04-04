# Sentinel — Build Plan

## The problem

Rule-based tools catch known violations. What they cannot do is reason about your specific codebase, your team's conventions, the blast radius of a change across files, or whether a PR is actually complete. These are the things that cause incidents — not missing semicolons.

Sentinel fills that gap. It reviews pull requests the way a senior engineer would: by understanding intent, cross-referencing related files, applying team-specific standards, and flagging things that look technically valid but are operationally wrong.

## What existing tools already handle (don't duplicate)

| Tool | Already does |
|---|---|
| Gitleaks / GitHub secret scanning | Hardcoded secrets and credentials |
| Dependabot / Snyk | Dependency CVEs and version pinning |
| Checkov / tfsec | Known IaC misconfigurations |
| Semgrep / CodeQL | Static analysis, known bug patterns |
| ESLint / language linters | Style, syntax, type errors |

Sentinel does none of these. It does what requires judgment.

---

## How it works

```
Pull Request
    │
    ▼
Context Assembly
  ├── git diff (structured per file)
  ├── CLAUDE.md (your team's rules, plain English)
  ├── sentinel.yml (which skills, which thresholds)
  ├── past PR history (semantic retrieval via GitHub API)
  └── incident data (postmortem issues, linked PRs)
    │
    ▼
Skill Execution (parallel)
  ├── ChangeCompletenessSkill
  ├── IaCImpactSkill
  ├── WorkflowSecuritySkill
  ├── OperationalReadinessSkill
  └── ArchitecturalConsistencySkill
    │
    ▼
Synthesis → GitHub Review
  ├── Inline line comments on specific findings
  ├── Summary comment with severity breakdown
  └── Check run: pass / warn / block (configurable)
    │
    ▼
Eval Recording (async)
  └── LLM-as-judge scores the review → metrics → prompt improvement
```

---

## Warnings vs. CI blockers

Every finding has a severity: `critical`, `high`, `medium`, `low`.

In `sentinel.yml`:

```yaml
fail_on: []          # day one: everything is a warning, nothing blocks
```

```yaml
fail_on: [critical]  # month one: only block on critical findings
```

```yaml
fail_on: [critical, high]  # when you trust it: block on high severity too
```

Start with zero friction. Move findings to blocking as you validate they are real and actionable. The progression is explicit and team-controlled.

---

## Milestones

Each milestone solves one real pain. Each is immediately usable as a standalone GitHub Action.

---

### v0.1 — Change completeness

**The problem.** A PR removes `var.enable_logging` from a shared Terraform module. Three environment configs still pass `enable_logging = true`. The PR is merged. The next `terraform apply` in production fails with `An argument named "enable_logging" is not expected here`. The outage was preventable.

Sentinel reasons across files. It understands that a change to a module interface has consumers, that a changed gRPC proto has generated clients, that a renamed database column has references in application code. It flags the gap before merge.

**What ships:**
- `ChangeCompletenessSkill`: cross-file impact reasoning — changed A, did you update B?
- GitHub Action (BYOK), posts a summary comment, non-blocking by default
- `sentinel.yml` with `fail_on: []` — safe to add to any repo immediately

**Works on:** any repo, any language. The reasoning is about relationships between files, not syntax.

**Lesson:** How to parse a git diff and structure it for an LLM. How to build a GitHub Action that calls the Claude API. The simplest possible useful AI review.

---

### v0.2 — Your rules, not generic rules

**The problem.** Your team has established standards that no generic tool enforces: all Lambda functions must have a dead-letter queue; all new services need a runbook before merging; all EKS deployments use IRSA, never instance profiles. These rules exist in a wiki no one reads. They get caught inconsistently in review — if at all. Messages silently disappear into dead Lambdas. Services ship to production with no runbook.

Sentinel reads `CLAUDE.md` from the target repo and uses it as high-priority context in every review. You write your rules in plain English, once. Sentinel enforces them on every PR.

**What ships:**
- `CLAUDE.md` reader — injected into every skill's system prompt
- `sentinel.yml` structured rule overrides (severity, file patterns, exceptions)
- Sentinel begins reviewing its own PRs. The self-referential demo starts here.

**Example `CLAUDE.md` section:**
```markdown
## For code reviewers
- All Lambda functions must have a dead-letter queue configured
- New services require a runbook at docs/runbooks/<service>.md before merge
- EKS deployments must use IRSA — never instance profiles or hardcoded keys
- Terraform state must always use S3 backend — never local
```

**Lesson:** The difference between rule-based enforcement and reasoning-based enforcement. Why freeform English instructions produce better results than a DSL. How to design a customization surface that non-engineers can use.

---

### v0.3 — Infrastructure change impact

**The problem.** A one-line PR changes a `subnet_id` on a NAT gateway in a shared VPC module. Terraform will destroy and recreate it. That is 2-3 minutes of internet connectivity loss for every private subnet in the VPC. The author did not know. The reviewer did not catch it. It merged on a Friday afternoon.

Separately: a new Kubernetes Deployment is added with no `readinessProbe`, no resource limits, and the container runs as root. It passes all existing checks. During the first rollout, the pod receives traffic before the app is ready. Users see 502s for 90 seconds.

Sentinel understands what infrastructure changes mean operationally, not just syntactically.

**What ships:**
- `IaCImpactSkill`: destroy/recreate detection on stateful resources, blast radius across module consumers, missing lifecycle guards
- `OperationalReadinessSkill`: new k8s workloads checked for readiness/liveness probes, resource limits, non-root user, PodDisruptionBudget, HPA
- Inline GitHub line comments pointing at specific lines
- `fail_on: [critical]` is now meaningful — NAT gateway destroy is critical

**Lesson:** Domain-specific skills. How to combine a fast static pre-screening pass (regex/AST) with a slower LLM reasoning pass to reduce cost and latency. How to make findings actionable: specific line, specific consequence, specific fix.

---

### v0.4 — GitHub Actions security

**The problem.** A workflow is added that triggers on `pull_request_target`, checks out `${{ github.event.pull_request.head.sha }}`, and runs `npm install && npm test`. A malicious PR from a fork can modify `package.json` postinstall scripts to run arbitrary commands with the repository's `GITHUB_TOKEN` — which has write access. This is not a hypothetical. It is a documented class of attack that has hit major open-source projects.

Pattern matchers flag unpinned actions. They do not reason about the interaction between trigger types, checkout behavior, and token permissions.

**What ships:**
- `WorkflowSecuritySkill`: dangerous trigger + checkout combinations, over-broad OIDC trust policies (wildcard branch matching), missing `permissions: {}` blocks, secrets passed via env instead of `--arg`, excessive token scopes
- Severity `critical` by default for privilege escalation paths — blocks merge if `fail_on: [critical]` is set

**Lesson:** AI reasoning about multi-step attack paths, not just pattern matching. How to write prompts that reason about interaction effects. When AI review adds value that static analysis genuinely cannot.

---

### v0.5 — Measuring whether it works

**The problem.** You have been running sentinel for a month. Is it catching real things or generating noise? You have no idea. You changed the IaC prompt to improve blast radius detection and now it flags every `count = 0` resource as a misconfiguration — 40% false positive rate, up from 8%. You do not know this yet. Neither does anyone else.

Almost no AI tooling in the wild ships with evals. Sentinel does, and it runs them on every change to its own prompts.

**What ships:**
- Eval harness: `sentinel eval run` against a fixture suite
- LLM-as-judge with 5-dimension rubric: precision, recall, actionability, context use, tone
- 15 curated fixtures covering each skill — realistic scenarios, not toy examples, with documented expected verdicts
- Evals run in CI on every PR to sentinel itself. A prompt change that regresses below threshold fails the check.
- Prompts are versioned `.md` files — never edited in place, only added. `PROMPT_MANIFEST` tracks which version is active per skill.
- Eval report published as a GitHub Actions artifact

**Lesson:** How to write evals for AI systems. The LLM-as-judge pattern. Why prompt changes need regression tests. How to measure signal-to-noise ratio. This is the chapter most AI projects skip — the repo exists partly to demonstrate it shouldn't be.

---

### v0.6 — Context from history

**The problem.** A PR touches `eks/node-groups/main.tf`. Four months ago, PR #891 made a structurally similar change. After merge, nodes entered `NotReady` state due to a missing taint toleration on the system pods. The incident lasted 47 minutes. The author of today's PR doesn't know this. Their reviewer joined the team last month.

Sentinel does.

**What ships:**
- GitHub API integration: fetches merged PRs, stores diff summaries and reviewer comments, embeds for semantic retrieval
- Incident linking: GitHub issues labeled `postmortem` or `incident` that reference a PR number are stored and retrievable
- RAG retrieval: top-k semantically similar past PRs and incidents injected as context at review time
- Human feedback loop: when a developer dismisses a finding, it is stored. Consistently dismissed findings are down-weighted in future reviews.
- `sentinel.yml` cross-repo context: pull standards from a shared `platform-standards` repo, incident history from a dedicated `postmortems` repo

**Lesson:** RAG in a real application. SQLite as a zero-dependency vector store. The difference between retrieval-augmented generation and fine-tuning. How to build AI systems that improve from team feedback without retraining.

---

### v0.7 — Full infra team workflow

**The problem.** The team wants to run sentinel on the actual infrastructure monorepo — Terraform for three cloud providers, EKS cluster configs, deployment pipelines, a database migration pipeline. Each area has different risk profiles, different conventions, different reviewers.

**What ships:**
- `DeploymentRiskSkill`: migration safety (column dropped while app code still references it?), rollout strategy, missing feature flag coverage for risky changes
- Per-directory skill routing in `sentinel.yml`: different skills and thresholds for `terraform/`, `k8s/`, `.github/workflows/`, `migrations/`
- `.sentinel/skills/`: team-defined custom skill prompts in the target repo — extend sentinel without forking it
- Multi-environment Terraform impact: which environments does this change affect? Is there a staging-first deployment gate?
- Docker image for self-hosted runners

**Lesson:** Composing multiple skills into a coherent, non-redundant review. Designing extension points that teams can use without understanding the internals. The full adoption arc: built in public, configured and deployed privately.

---

### v0.8 — Sentinel fixes what it finds

**The problem.** Sentinel flags that three Kubernetes Deployments use `image: myapp:latest` instead of a pinned digest. A reviewer leaves a comment. The author makes the fix. This is mechanical work that should not require a human round-trip.

Sentinel can fix it. It creates a branch, applies the change, opens a draft PR. The human reviews and merges. Sentinel does not self-merge.

**What ships:**
- `AutoFixMode`: for well-defined, low-risk fixes, sentinel creates a branch and opens a draft PR
- Initial scope: IaC fixes (image pinning, missing labels, missing resource limits, missing lifecycle blocks)
- Every auto-fix PR body documents: which finding triggered it, what was changed, why the fix is safe, what to verify before merging
- Fixes are traceable back to the sentinel review that produced them

**Lesson:** The agent pattern — observe, reason, act, hand off. How to make automated code changes auditable. Where to draw the line between automation and human judgment (draft PR, not direct push, not auto-merge).

---

### v0.9 — Sentinel writes the tests

**The problem.** A new function `CalculateRetryDelay(attempt int, baseDelay time.Duration) time.Duration` is added with no tests. Sentinel flags the coverage gap. An engineer writes `TestCalculateRetryDelay_basic` that passes one happy path. The function has an integer overflow bug on high attempt values that ships to production.

Sentinel generates the tests. It opens a PR with table-driven tests covering boundary conditions, edge cases, and the specific behaviors the function is documented to provide.

**What ships:**
- `TestGenerationMode`: identifies uncovered functions in the diff, generates tests in the repo's existing test style and framework
- Tests are opened as a draft PR, not committed to the branch under review
- Eval harness extended: generated tests are evaluated for coverage of documented behaviors, not just "does it compile"
- Works across languages — test style is detected from existing test files in the repo

**Lesson:** Generating code with AI vs reviewing it. How to evaluate AI-generated tests beyond syntax correctness. The feedback loop between sentinel-as-reviewer and sentinel-as-contributor.

---

### v1.0 — A framework, not just a tool

**What ships:**
- `sentinel` Python package on PyPI — usable as a library
- `Skill`, `EvalHarness`, `ContextAssembler`, `Memory` as stable public APIs
- `sentinel init` CLI: scaffolds sentinel config in any repo in under a minute
- A second repository, built on sentinel, demonstrating a different domain (incident triage, or automated runbook generation)
- Full eval history for sentinel itself: quality metrics from v0.1 through v1.0, visible in the repo

The architecture — skill-based analysis, eval harness, prompt versioning, memory — applies to any AI automation task in the SDLC. Sentinel is both the tool and the reference implementation of the pattern.

---

## Adoption journey

| When | What you do | What changes |
|---|---|---|
| Day 1 | Add the GitHub Action, `fail_on: []` | Non-blocking AI comments appear on PRs |
| Week 2 | Write `CLAUDE.md` with your team's rules | Reviews enforce your conventions, not generic ones |
| Week 3 | Enable `fail_on: [critical]` | Genuinely dangerous changes are blocked before merge |
| Month 2 | Run evals, review the report | You know if sentinel is helping or generating noise |
| Month 2 | Add fixtures from real incidents | Weak spots improve, quality is tracked |
| Month 3 | Enable memory, seed with past PRs | Sentinel references your actual history |
| Month 4 | Add `.sentinel/skills/` custom prompts | Domain-specific checks unique to your platform |
| Month 6 | Enable auto-fix for IaC findings | Mechanical fixes stop requiring human round-trips |

---

## Customization surface

Three layers, each independently useful:

**`sentinel.yml`** — structured configuration: which skills run, severity thresholds, which file patterns route to which skills, `fail_on` list, model selection, external context sources.

**`CLAUDE.md`** — freeform English instructions injected into every review as high-priority context. Write it like you are briefing a senior engineer who is new to your team. No DSL to learn. Any team member can update it.

**`.sentinel/skills/`** — custom skill prompt files in the target repo. Define entirely new review behaviors without forking sentinel. Each file is a versioned prompt with structured output instructions.

---

## This repository

Sentinel reviews its own pull requests from v0.2 onward. The PR history is part of the demo — you can read the git log and see sentinel's reviews improving milestone by milestone. The eval harness runs in CI. Prompt regressions fail the build. The quality metrics are tracked and visible.

The goal is not just to ship a useful tool. It is to show, concretely and step by step, how any engineering team can introduce AI into their development process — measurably, incrementally, without replacing what already works.
