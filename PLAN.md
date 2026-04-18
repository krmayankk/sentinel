# Sentinel — Build Plan

## Vision

Sentinel is a framework for AI agents that reason about software changes with judgment — the class of analysis that requires understanding relationships, context, and consequences, not just rules.

The first agents are **reviewers**: passive, read-only, they analyze diffs and produce findings. The architecture supports **actors**: agents that fix what they find, opening draft PRs for human review. The same judgment framework that reviews PRs can eventually manage infrastructure — detect drift, correlate incidents with recent changes, enforce deployment gates — because both require the same capability: reasoning about relationships across a system.

**The progression:**

| Phase | What sentinel does | Trust level |
|---|---|---|
| Review (v0.1–v0.5) | Reads diffs, reasons about them, produces findings | Read-only. Human decides. |
| Fix (v0.8) | Creates a branch and opens a draft PR for confirmed findings | Human reviews and merges. Sentinel does not self-merge. |
| Operate (v1.0+) | Watches for drift, correlates incidents, enforces gates | Human sets policy. Sentinel acts within it. Git is always the interface. |

Each phase builds on the one before it. You cannot fix what you cannot judge. You cannot operate what you cannot fix. The milestones below build the judgment layer first, then the action layer.

---

## The problem

Rule-based tools catch known violations. What they cannot do is reason about your specific codebase, your team's conventions, the blast radius of a change across files or repos, or whether a PR is actually complete. These are the things that cause incidents — not missing semicolons.

## What existing tools already handle (don't duplicate)

| Tool | Already does |
|---|---|
| Gitleaks / GitHub secret scanning | Hardcoded secrets and credentials |
| Dependabot / Snyk | Dependency CVEs and version pinning |
| Checkov / tfsec | Known IaC misconfigurations |
| Semgrep / CodeQL | Static analysis, known bug patterns |
| ESLint / language linters | Style, syntax, type errors |
| Polaris / kube-linter | K8s operational hygiene (probes, limits, PDB) |
| Compilers (Go, Rust, Java, C#) | Interface breaks within a single compiled language |

Sentinel does none of these. It does what requires judgment: reasoning about relationships that cross the boundaries these tools cannot see.

---

## How it works

```
Event (PR, commit, schedule, incident)
    |
    v
Context Assembly
  |-- git diff (structured per file)
  |-- CLAUDE.md (your team's rules, plain English)
  |-- sentinel.yml (which skills, which thresholds)
  |-- .sentinel/skills/ (team-defined custom skills)
  |-- external repos (cross-repo caller search)
  |-- past PR history + incidents (semantic retrieval)
    |
    v
Skill Execution (parallel, per sentinel.yml routing)
  |-- ChangeCompletenessSkill      <- v0.1: did you update all the dependents?
  |-- ContractDriftSkill           <- v0.3: cross-boundary interface contracts
  |-- WorkflowSecuritySkill        <- v0.4: GHA privilege escalation paths
  |-- [.sentinel/skills/*.md]      <- v0.2+: team-defined, no fork needed
    |
    v
Verification (LLM+grep two-step)
  |-- For each finding: grep the repo (and external repos) for the search term
  |-- Callers found -> finding confirmed, severity elevated, exact locations reported
  |-- No callers found -> finding dismissed (no speculation)
    |
    v
Output -> GitHub
  |-- Per-skill annotations: "[ChangeCompleteness] HIGH: missing caller update"
  |-- Summary comment with severity breakdown, per skill
  |-- Check run: pass / warn / block (configurable per skill via sentinel.yml)
```

---

## Warnings vs. CI blockers

Every finding has a severity: `critical`, `high`, `medium`, `low`.

```yaml
fail_on: []                # day one: everything is a warning, nothing blocks
fail_on: [critical]        # month one: only block on critical findings
fail_on: [critical, high]  # when you trust it: block on high severity too
```

Start with zero friction. Move findings to blocking as you validate they are real and actionable. The progression is explicit and team-controlled.

---

## Customization surface

Four layers. Each solves a different problem. Each works independently. The org layer cannot be bypassed — everything else is repo-controlled.

### Layer 0: Org config (`my-org/.sentinel`) — governance that repos cannot bypass

A central config repo owned by the security or platform team. Defines mandatory skills, mandatory rules, and minimum severity thresholds that apply to every repo in the org. Individual repos cannot remove, weaken, or override these — they can only add to them or make them stricter.

```yaml
# my-org/.sentinel/org-sentinel.yml

mandatory_skills:
  - workflow_security:
      fail_on: [critical]           # repo cannot relax this
  - change_completeness:
      fail_on: [high, critical]     # repo can escalate to [medium, high, critical] but not to []

mandatory_rules: |
  - All services must have a health check endpoint
  - All Terraform must use the shared S3 backend module
  - No service may store PII without encryption at rest
  - All IAM roles must have a permission boundary
```

```markdown
# my-org/.sentinel/skills/compliance_check.md
Check that new data stores (S3, RDS, DynamoDB, Redis) have encryption
at rest enabled and that access logging is configured. Unencrypted data
stores in any environment are critical. This is a compliance requirement
that cannot be waived at the repo level.
```

**Who uses it:** Security team, platform team, compliance. This is the policy floor for the entire org.

**What it controls:** The minimum set of judgment checks and blocking thresholds. The Kubernetes admission controller equivalent for code review — org sets the floor, teams build on top.

**How it merges with repo config:**
1. Org mandatory skills are always included — repo `sentinel.yml` cannot remove them
2. Org mandatory rules are prepended to the repo's `CLAUDE.md` context — always present
3. Org custom skills run alongside repo custom skills — both produce findings
4. `fail_on` uses the strictest value: if org says `[critical]` and repo says `[critical, high]`, the result is `[critical, high]` (repo made it stricter, which is allowed)
5. If repo tries to set `fail_on: []` for a mandatory skill, org `fail_on` wins

### Layer 1: `CLAUDE.md` — teach existing skills your conventions

Every repo has conventions no generic tool knows. Write them in plain English. Sentinel injects them into every skill's prompt as high-priority context.

```markdown
# CLAUDE.md
## Completeness rules
- When a Terraform module variable changes, all callers under terraform/envs/ must be updated
- All Lambda functions must have a dead-letter queue configured
- New IAM roles must have a permission boundary attached

## Architecture rules
- Services must not import directly from other services' internal packages
- Database access must go through the repository layer, never raw SQL in handlers
```

**Who uses it:** Any engineer on the team. No code, no DSL, no redeployment. Push to `CLAUDE.md` and the next PR picks it up.

**What it controls:** What the built-in skills look for. The same `ChangeCompletenessSkill` checks different things in different repos based on what `CLAUDE.md` teaches it.

### Layer 2: `sentinel.yml` — control what runs and how

Structured configuration for the runner: which skills, which file patterns, which severity levels block merge, which external repos to search.

```yaml
fail_on: [critical, high]

skills:
  - change_completeness
  - contract_drift
  - cost_attribution    # custom skill from .sentinel/skills/

routing:
  - pattern: "terraform/**"
    skills: [change_completeness, contract_drift]
    fail_on: [critical, high, medium]   # stricter for IaC
  - pattern: ".github/workflows/**"
    skills: [workflow_security]

context:
  external_repos:
    - repo: my-org/shared-modules
      path: modules/
```

**Who uses it:** Platform team, tech leads. Controls the operational behavior — what runs, what blocks, what searches where.

**What it controls:** The runner. Not what skills look for (that's CLAUDE.md), but which skills run on which files and what happens when they find something.

### Layer 3: `.sentinel/skills/` — define entirely new judgment checks

Custom skill prompts in the target repo. Each markdown file defines a new judgment check that runs as a first-class skill alongside built-in ones.

```markdown
# .sentinel/skills/cost_attribution.md
Check that every new AWS resource (S3, RDS, Lambda, ECS, etc.) has a
`cost_center` tag. Missing tags on production resources have caused
unattributed spend incidents. Severity: high for production resources
(anything under terraform/envs/prod/), medium for staging/dev.
```

```markdown
# .sentinel/skills/api_versioning.md
When a public API endpoint changes its request or response schema, check
that the API version has been bumped and a migration guide entry exists
in docs/api/migrations/. Breaking changes to unversioned endpoints are
critical — they break all existing clients silently.
```

**Who uses it:** Senior engineers, architects. Define domain-specific judgment that is unique to your system — not generic enough for a built-in skill, too important to leave to memory.

**What it controls:** What sentinel checks for. New skills, not new rules for existing skills (that's CLAUDE.md). Each file is a self-contained judgment check that the framework loads, runs, and reports independently. Custom skills use the same execution pipeline as built-in skills (prompt → LLM → parse findings → grep verify) — the only difference is where the prompt lives.

### How the layers compose

| Layer | What it controls | Who writes it | Example |
|---|---|---|---|
| Org config (`my-org/.sentinel`) | Mandatory skills and policy floor | Security / platform team | "All repos must run workflow_security at fail_on: [critical]" |
| `CLAUDE.md` | What existing skills look for | Any engineer | "Lambda functions need a DLQ" |
| `sentinel.yml` | Which skills run, what blocks merge | Tech lead | Route IaC skills to `terraform/**` only |
| `.sentinel/skills/` | New judgment checks | Architects | Cost attribution, API versioning |

A team starts with just `CLAUDE.md` on day one. Adds `sentinel.yml` when they want routing and blocking. Adds `.sentinel/skills/` when they need judgment checks no built-in skill covers. The org layer is set once by the platform team — repos inherit it automatically. Each layer is a separate commit, a separate decision. Repos can only make things stricter, never weaker than what the org mandates.

### Where things come from at review time

Skills, config, and conventions each have multiple sources. The runner merges them with clear precedence.

**Skills** — three sources, all run:

| Source | Location | Who controls | Can repo remove? |
|---|---|---|---|
| Built-in | `sentinel/skills/*.py` (sentinel package) | Sentinel maintainers | Can choose not to enable via `sentinel.yml`, but can't delete |
| Org mandatory | `my-org/.sentinel/skills/*.md` (org config repo) | Security / platform team | No — always runs |
| Repo custom | `.sentinel/skills/*.md` (target repo) | Repo team | Yes |

**Config** — two sources, org is the floor:

| Source | Location | Precedence |
|---|---|---|
| Org config | `my-org/.sentinel/org-sentinel.yml` | Sets mandatory skills and minimum `fail_on` — cannot be weakened |
| Repo config | `sentinel.yml` (target repo) | Additive: can enable more skills, make `fail_on` stricter, add routing |

**Conventions** — two sources, concatenated:

| Source | Location | Scope |
|---|---|---|
| Org mandatory rules | `mandatory_rules` in org config | Prepended to every repo's prompt context |
| Repo CLAUDE.md | `CLAUDE.md` (target repo) | This repo only, appended after org rules |

The runner resolves all three dimensions before executing: built-in + org + repo skills, org floor + repo config, org rules + repo CLAUDE.md. A single review may run five skills from three different sources — the output groups findings by skill so the team can see exactly which judgment check flagged what.

---

## Milestones

Each milestone is additive and independently useful. A team running v0.1 gets value immediately. Each subsequent version widens the judgment surface or deepens the framework capability.

---

### v0.1 — Change completeness (shipped)

**The problem.** A PR removes `var.enable_logging` from a shared Terraform module. Three environment configs still pass `enable_logging = true`. The PR is merged. The next `terraform apply` in production fails with `An argument named "enable_logging" is not expected here`. The outage was preventable.

Sentinel reasons across files. It understands that a change to a module interface has consumers, that a changed gRPC proto has generated clients, that a renamed database column has references in application code. It flags the gap before merge.

**What shipped:**
- `ChangeCompletenessSkill`: cross-file impact reasoning — changed A, did you update B?
- Two-step LLM+grep verification: LLM identifies the search term; grep confirms real callers. Findings dismissed when no callers found — no speculation.
- `CLAUDE.md` reader: injected into the skill's prompt as high-priority context. Teams write their rules in plain English; sentinel enforces them on every PR.
- GitHub Action (BYOK), posts severity-grouped comment with confirmed caller locations
- Self-review: sentinel runs on its own PRs. The review history is part of the demo.
- `fail_on` env var — empty by default (warning-only); set to `high,critical` to block merge

**Works on:** any repo, any language. The reasoning is about relationships between files, not syntax.

**What this proved:** The LLM+grep two-step eliminates speculation. Judgment-level review is possible with a single API call plus codebase verification. CLAUDE.md as a customization surface works — freeform English beats a DSL.

---

### v0.2 — The framework (multi-skill runner)

**The problem.** v0.1 hardcodes one skill: `ChangeCompletenessSkill(model=model).run(diff, context)`. There is no skill registry, no way to run multiple skills, no per-skill GHA output, no way for a team to add their own skill without editing sentinel's source. The Skill ABC exists but nothing uses it as a framework.

**What ships:**
- **Skill runner**: reads `sentinel.yml`, discovers built-in + custom skills, runs them in parallel, aggregates findings tagged by skill name
- **Per-skill GHA output**: annotations say `[ChangeCompleteness] HIGH: ...` not just `sentinel: ...`. PR comment groups findings by skill. Teams can see which judgment checks passed and which failed.
- **`sentinel.yml` support**: `skills` list, `fail_on` (global and per-skill), `routing` (file pattern -> skill mapping)
- **`.sentinel/skills/` loader**: custom skill prompt files in the target repo are loaded and executed as first-class skills. A team adds a file, the next PR runs it — no fork, no redeployment.
- This repo ships its own `sentinel.yml` — the self-referential demo shows the framework in action.

**Example: a team adds their own skill without touching sentinel:**
```
.sentinel/skills/cost_attribution.md   <- custom skill prompt
sentinel.yml                           <- registers it
CLAUDE.md                              <- teaches it team conventions
```

GHA output:
```
[ChangeCompleteness] PASS — no findings
[CostAttribution] HIGH — S3 bucket missing cost_center tag
```

**What this proves:** The framework is real. Skills are composable and extensible. Adding a new judgment check is a markdown file, not a code change.

---

### v0.3 — Contract drift across boundaries

**The problem.** A compiler catches broken interfaces within a single language. It cannot see across boundaries: a Protobuf schema changes but the generated client in a downstream service is not regenerated; a Kafka event schema drops a required field but three consumers still expect it; a shared Terraform module removes a variable but callers in two other repos still pass it; a database migration drops a column that application code in a separate repo still queries.

These are the changes that cause distributed system incidents. They pass every linter, every type checker, and every unit test. They fail in production.

**What ships:**
- `ContractDriftSkill`: reasoning about cross-boundary interface contracts — generated code (proto/OpenAPI/Avro), event schemas, shared module interfaces, database schema vs. application layer consistency
- **Cross-repo search**: `sentinel.yml` accepts `context.external_repos` — paths from other repos are checked out and included in codebase verification. Same LLM+grep two-step, wider search scope.
- `fail_on: [critical]` becomes meaningful here — a confirmed event schema break across three consumers is critical
- New eval fixtures: proto change with stale generated client, Avro schema field removal with live consumer, cross-repo Terraform module caller

**Cross-repo configuration:**
```yaml
# sentinel.yml in my-org/platform
context:
  external_repos:
    - repo: my-org/consumer-service
      path: src/
    - repo: my-org/data-pipeline
      path: jobs/
```
Sentinel checks out those paths during review. A proto change in `platform` is verified against callers in `consumer-service` and `data-pipeline`. The same two-step, across repo boundaries.

**What this proves:** The LLM+grep pattern extends across repositories without architectural changes. Cross-repo judgment — what no other tool provides — is a configuration change, not a code change.

---

### v0.4 — GHA workflow security

**The problem.** A workflow is added that triggers on `pull_request_target`, checks out `${{ github.event.pull_request.head.sha }}`, and runs `npm install && npm test`. A malicious PR from a fork can modify `package.json` postinstall scripts to run arbitrary commands with the repository's `GITHUB_TOKEN` — which has write access. This is not a hypothetical. It is a documented class of attack that has hit major open-source projects.

Pattern matchers flag unpinned actions. They do not reason about the interaction between trigger types, checkout behavior, and token permissions.

**What ships:**
- `WorkflowSecuritySkill`: dangerous trigger + checkout combinations, over-broad OIDC trust policies (wildcard branch matching), missing `permissions: {}` blocks, secrets passed via env instead of `--arg`, excessive token scopes
- Severity `critical` by default for privilege escalation paths — blocks merge if `fail_on: [critical]` is set

**What this proves:** AI reasoning about multi-step attack paths, not just pattern matching. A new built-in skill plugs into the framework (v0.2) with zero runner changes — the extension point works.

---

### v0.5 — Measuring whether it works (evals)

**The problem.** You have been running sentinel for a month. Is it catching real things or generating noise? You changed a prompt and now it flags every `count = 0` resource as a misconfiguration — 40% false positive rate, up from 8%. You do not know this yet.

Almost no AI tooling in the wild ships with evals. Sentinel does, and it runs them on every change to its own prompts.

**What ships:**
- Eval harness: `sentinel eval run` against a fixture suite
- LLM-as-judge with 5-dimension rubric: precision, recall, actionability, context use, tone
- 15+ curated fixtures covering each skill — realistic scenarios with documented expected verdicts
- Evals run in CI on every PR to sentinel itself. A prompt change that regresses below threshold fails the check.
- Prompts are versioned `.md` files. `PROMPT_MANIFEST` tracks which version is active per skill.
- Eval report published as a GitHub Actions artifact

**What this proves:** AI systems can be measured, not just shipped. The LLM-as-judge pattern works. Prompt changes need regression tests. This is the chapter most AI projects skip.

---

### v0.6 — Context from history

**The problem.** A PR touches `eks/node-groups/main.tf`. Four months ago, PR #891 made a structurally similar change. After merge, nodes entered `NotReady` state due to a missing taint toleration. The incident lasted 47 minutes. The author of today's PR doesn't know this. Their reviewer joined the team last month.

Sentinel does.

**What ships:**
- GitHub API integration: fetches merged PRs, stores diff summaries and reviewer comments, embeds for semantic retrieval
- Incident linking: GitHub issues labeled `postmortem` or `incident` are stored and retrievable
- RAG retrieval: top-k semantically similar past PRs and incidents injected as context at review time
- Human feedback loop: when a developer dismisses a finding, it is stored. Consistently dismissed findings are down-weighted.

**What this proves:** RAG in a real application. How to build AI systems that learn from team history without retraining.

---

### v0.7 — Sentinel fixes what it finds

**The problem.** Sentinel flags that three callers still pass a removed Terraform variable. A reviewer leaves a comment. The author makes the fix in each file. This is mechanical work that should not require a human round-trip.

Sentinel can fix it. It creates a branch, applies the change, opens a draft PR. The human reviews and merges. Sentinel does not self-merge.

**What ships:**
- `AutoFixMode`: for well-defined, low-risk fixes, sentinel creates a branch and opens a draft PR
- Every auto-fix PR body documents: which finding triggered it, what was changed, why the fix is safe
- Fixes are traceable back to the sentinel review that produced them

**What this proves:** The agent pattern — observe, reason, act, hand off. This is the bridge from review agent to operational agent. The same judgment that found the problem generates the fix.

---

### v0.8 — Operational agent preview

**The problem.** Sentinel currently reacts to PRs. But drift happens between PRs too: a shared module is updated in one repo, consumers in other repos are now stale. An infrastructure config is manually changed in the console but not reflected in the Terraform state. A deployment config references a secret that was rotated but the deployment manifest was not updated.

**What ships:**
- Scheduled mode: sentinel runs on a cron, diffs current state against expected state, opens PRs for detected drift
- Incident correlation: when a GitHub issue is labeled `incident`, sentinel identifies the most likely causal PR and surfaces it
- Deployment gate: sentinel as a required check before deploy, not just before merge — reviews the full set of changes since last deploy

**What this proves:** The review agent framework generalizes to operational use. Same skills, same judgment, different trigger. Git remains the interface — the output is always a PR or a finding, never a direct mutation.

---

### v1.0 — A framework, not just a tool

**What ships:**
- `sentinel` Python package on PyPI — usable as a library
- `Skill`, `EvalHarness`, `ContextAssembler` as stable public APIs
- `sentinel init` CLI: scaffolds sentinel config in any repo
- A second repository built on sentinel demonstrating a different domain
- Full eval history: quality metrics from v0.1 through v1.0, visible in the repo

The architecture — skill-based analysis, eval harness, prompt versioning, cross-repo context — applies to any AI automation task in the SDLC. Sentinel is both the tool and the reference implementation of the pattern.

---

## Adoption journey

| When | What you do | What changes |
|---|---|---|
| Day 1 | Add the GitHub Action, `fail_on: []` | Non-blocking AI review comments appear on PRs |
| Day 1 | Write `CLAUDE.md` with your team's rules | Reviews enforce your conventions, not generic ones |
| Week 2 | Enable `fail_on: [critical]` | Genuinely dangerous changes blocked before merge |
| Week 3 | Add `.sentinel/skills/` custom prompts | Domain-specific judgment checks, no fork needed |
| Month 2 | Run evals, review the report | You know if sentinel is helping or generating noise |
| Month 3 | Add cross-repo references in `sentinel.yml` | Changes verified against consumers in other repos |
| Month 4 | Enable auto-fix for confirmed findings | Mechanical fixes stop requiring human round-trips |
| Month 6 | Enable scheduled drift detection | Sentinel watches for problems between PRs |

---

## This repository

Sentinel reviews its own pull requests from v0.1 onward. The PR history is part of the demo — you can read the git log and see sentinel's reviews improving milestone by milestone. The eval harness runs in CI. Prompt regressions fail the build. The quality metrics are tracked and visible.

The goal is not just to ship a useful tool. It is to show, concretely and step by step, how any engineering team can introduce AI judgment into their development process — measurably, incrementally, without replacing what already works. And to show how that same judgment extends from reviewing code to managing the systems it runs on.
