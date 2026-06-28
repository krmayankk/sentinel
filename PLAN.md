# Sentinel — Build Plan

## Vision

Sentinel is a framework for AI agents that reason about software changes with judgment — the class of analysis that requires understanding relationships, context, and consequences, not just rules.

The first agents are **reviewers**: passive, read-only, they analyze diffs and produce findings. The architecture supports **actors**: agents that fix what they find, opening draft PRs for human review. The same judgment framework that reviews PRs can eventually manage infrastructure — detect drift, correlate incidents with recent changes, enforce deployment gates — because both require the same capability: reasoning about relationships across a system.

### Scope of this document

This is the plan for **sentinel** — one layer (the reviewer agent, the eval harness, the telemetry, the operator agent in time) within a broader agentic-AI architecture. The wider picture — a model-portable platform, a multi-agent fleet (planner, implementer, operator, postmortem), drop-in adoption for any team — is deliberately outside the scope of this document. It will get its own home when the work warrants it, most likely a separate orchestrator repo with its own plan.

For sentinel's role inside that fleet, see § Current direction and § Non-goals. The rest of this document is the sentinel plan in increasing depth: why the triggering model is changing, the milestone progression, why open-source adoption is first-class, where we are today, and what the bake-off measures.

### The triggering model is decoupling from the PR

Most code review today happens at PR-open. That model is not going away in the next year — but it is fraying at the edges. Merge queues (GitHub native, Graphite, Cursor's pending Graphite integration) move review from before-merge to queue-time. Autonomous coding agents land commits no human authored. Trunk-based teams already gate on tests, not human review. The endpoint of the trajectory is **no PR at all** — code is generated, tests run, gates pass, it lands; if something is wrong, a bug is auto-filed or an autofix branch is opened.

Sentinel's design intentionally separates *the skill* (judgment about a diff) from *the trigger* (when judgment runs). A skill that works on a PR works on a push, on a queue entry, on a scheduled drift check, on an autonomous-agent commit. The judgment is reusable across the trigger evolution. This is why the same framework can ship as a PR reviewer today and a pre-merge gate for autonomous agents tomorrow — without rewriting the skills.

### The progression

| Phase | What sentinel does | Trust level | Primary trigger |
|---|---|---|---|
| Review (v0.1–v0.3) | Reads diffs, reasons about them, produces findings | Read-only. Human decides. | PR-open |
| Measure (v0.4) | Quantifies whether the reviewer works | Same | Prompt / model change |
| Learn (v0.5) | Telemetry + history feed skill context and grow the eval corpus | Same | PR-open + production data |
| Fix (v0.6) | Opens a draft PR for confirmed findings | Human reviews and merges. Sentinel does not self-merge. | PR-open |
| Operate (v0.7) | Watches for drift, correlates incidents, gates deploys | Human sets policy. Git is the interface. | Schedule, push, deploy |
| General (v1.0) | Public library and CLI, second-domain reference, full eval history | Same | All of the above |
| Autonomous (v1.0+) | Gates code no human wrote and no human reviewed; auto-files bugs or opens autofix branches | Human sets policy and watches metrics. | Merge queue, agent commit |

Each phase builds on the one before it. You cannot fix what you cannot judge. You cannot operate what you cannot fix. You cannot gate autonomous agents until your gate is itself measured. The milestones build the judgment layer first, then measurement, then the action layer, then the operational surface.

### Open-source adoption is a first-class goal

This repo is the reference implementation. The four customization layers (org config, `CLAUDE.md`, `sentinel.yml`, `.sentinel/skills/`) are designed so a team can adopt sentinel without forking it. The eval harness is designed so a team can trust the system without trusting us. The framework is designed so adding a new judgment check is a markdown file, not a code change. If a team outside this org can run sentinel on their repo, get useful findings on day one, and write their own skill on day three — the framework works.

### Current direction (2026-06): drive sentinel from a real autonomous workload

Sentinel's PR-review surface is feature-complete enough. Further investment in skills, fixtures, and the LLM judge layer has diminishing returns *without a real downstream consumer*. The framework now evolves in service of one — a fully autonomous inference service (separate repo) where coding agents push, sentinel gates, and the cluster manages itself.

This shifts emphasis on the milestone map:

- **v0.5 (in progress)** stays primary because the inference service is where real telemetry comes from.
- **v0.6 (auto-fix)** and **v0.7 (operational agent)** become load-bearing — drift detection and auto-PRs are what make the inference service self-maintaining.
- **v0.7.5 (autonomous merge gate)** is the unlock — once an agent commit can land without a human reviewer, the whole loop closes.
- **v0.8 (skill authoring)** and **v1.0 (general framework)** wait. They serve OSS adopters that don't exist yet. Adoption follows a real case study, not the other way around.

Sentinel doesn't become the orchestrator (see Non-goals). It stays one component — the *Reviewer* and eventually the *Operator* — inside a fleet driven by the inference repo.

### The bake-off

Concurrent with the autonomous workload, sentinel is also the *measurement layer* for a multi-backend comparison: open model + full sentinel harness vs. frontier model + the same harness, on quality / tokens / latency / cost. See [`docs/bake-off.md`](docs/bake-off.md) for the methodology. The bake-off is what turns sentinel's sovereignty thesis from architectural claim into evidence — and is the load-bearing reason `v0.6 LLMProvider` is now early in the queue.

### Skills compound — they don't just accumulate

A skill system that only *grows* eventually drowns in its own output. A skill system that *compounds* is what makes the framework worth adopting. Sentinel's skills sit at three tiers — **raw** (narrow checks), **mid-level** (today's built-ins, vertical-slice expertise), and **meta** (skills about skills). The lifecycle is *signal → raw skill → retired-as-fixture → mid-level skill grows*, so accumulated evidence carries forward when a skill is subsumed. The same architecture generalises to every learning agent in the broader fleet — Planner, Implementer, Operator, Reviewer all implement the same template of *skills + eval + telemetry + meta-loop*. This is the **anti-blurriness model**: re-read [`docs/skill-design.md`](docs/skill-design.md) when the architectural picture goes hazy. It promotes the auto-discovery thinking out of v0.8 (where it was buried as one bullet) into a top-level concept — because *the loop that generates judgment* is itself the framework's defining feature.

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

## Non-goals

The following are deliberately outside the scope of sentinel. Drawing the boundary keeps the framework focused and lets it slot into larger systems cleanly.

- **Sentinel is not an agent orchestrator.** A multi-agent loop (plan → implement → test → review → merge) is a separate concern with a different shape. Sentinel is the *review* agent in that quartet — one specialized agent with deep judgment, not the conductor. Frameworks like Claude Code, Cursor agents, or a bespoke planner-implementer-critic loop are the right home for orchestration. Sentinel is invoked *by* such a system, or directly by CI.
- **Sentinel is not an LLM observability platform.** See the v0.5 telemetry layering note — call-level tracing belongs to Phoenix / Langfuse / Helicone / Braintrust, and sentinel emits OTLP spans so those tools work out of the box.
- **Sentinel is not a linter or static analyzer replacement.** The table above covers the tools sentinel does not duplicate.

## Model portability (architectural commitment)

Skills are model-agnostic by design — the skill prompt is the IP, the model is the runtime. Today the runner is hard-coded to the Anthropic SDK; making that a swappable `LLMProvider` adapter (Anthropic, OpenAI, Bedrock) is a v0.6 commitment, forced by the v0.4 LLM-judge layer (which already requires a *different* model family from the generator). The encoded judgment in each skill is portable across model and provider shifts; only the call site changes. This is what makes the framework durable across the next 1–2 years of model churn.

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
Skill Execution (per sentinel.yml routing)
  |-- Every skill is an agentic loop. The diff is the first input.
  |-- The LLM can explore the codebase with tools: grep, read_file, list_files.
  |-- max_turns is the only control — it sets the tool-use budget per skill.
  |
  |-- max_turns: 0  → diff-only, single LLM call, no tools, zero extra cost
  |-- max_turns: 3  → light exploration (grep for callers, read a file or two)
  |-- max_turns: 10 → deep analysis (follow dependency chains across files)
  |
  |-- The LLM decides whether to use tools based on what it sees in the diff.
  |     If confident from the diff alone, it returns findings immediately.
  |     If uncertain, it greps, reads files, then returns findings backed by evidence.
  |
  |-- ChangeCompletenessSkill      <- max_turns: 5 (explores callers)
  |-- WorkflowSecuritySkill        <- max_turns: 0 (YAML is self-contained)
  |-- MigrationSafetySkill         <- max_turns: 0 (SQL is self-contained)
  |-- [.sentinel/skills/*.md]      <- max_turns: 3 default, configurable via frontmatter
  |
  |-- Language-agnostic: the LLM knows what to grep for in any language.
  |     No regex, no parser, no per-language patterns to maintain.
  |-- Cross-repo: when enabled, tools search cloned repos too — same loop.
  |
  |-- No mechanical verify step. The LLM is the verifier — it greps, reads,
  |     and reports with evidence. No findings are silently dismissed.
    |
    v
Output -> GitHub
  |-- Per-skill annotations: "[ChangeCompleteness] HIGH: missing caller update"
  |-- Summary comment with severity breakdown, per skill
  |-- Check run: pass / warn / block (configurable per skill via sentinel.yml)
```

---

## Triggers — the skill is one, the trigger is many

A skill doesn't know which event fired it. The runner extracts a diff and a context; the skill judges. This is the architectural reason the framework extends from PR review today to autonomous-agent gating tomorrow: the trigger evolves, the judgment stays put.

| Trigger | When it fires | What sentinel sees | Status |
|---|---|---|---|
| `pull_request` | PR opened or updated | base..head diff | Shipped (v0.1) |
| `push` | Commit pushed to a branch | previous..HEAD diff | Wired in entrypoint; GHA template pending |
| `merge_group` | GitHub merge queue evaluates a queued PR | queued diff | Same code path as `pull_request`; just a different GHA event |
| `schedule` | Cron — diff between last-known-good main and current main | drift diff | Planned (v0.7) |
| `audit` | Manual or scheduled compliance scan | whole tree (files matched by routing globs) | Planned (v0.5.5) — output is a baseline, not a per-change finding |
| `agent_commit` | A coding agent pushes; gate before merge | agent's diff | Future (v1.0+) — same skill code, new output path (auto-file bug or open autofix branch) |

The two trigger-time controls already in `sentinel.yml`:

```yaml
mode:
  on_push: [workflow_security, change_completeness]   # cheap, every push
  on_merge: [migration_safety]                        # expensive, final gate only
```

`on_push` is the cheap-and-frequent lane. `on_merge` is the expensive-and-final lane (merge queue, deploy gate, or autonomous-commit gate). Same skills, different budget and stakes. A team adopting sentinel can start with `on_push` only, prove value, then enable the heavier `on_merge` skills when they trust the gate.

---

## Warnings vs. CI blockers

Every finding has a severity: `critical`, `high`, `medium`, `low`.

```yaml
fail_on: []                # day one: everything is a warning, nothing blocks
fail_on: [critical]        # month one: only block on critical findings
fail_on: [critical, high]  # when you trust it: block on high severity too
```

Start with zero friction. Move findings to blocking as you validate they are real and actionable. The progression is explicit and team-controlled.

From v0.5.5, blocking is keyed on *new* findings, not all findings: a finding blocks only when its fingerprint isn't already in the committed baseline. Pre-existing debt is reported but never blocks an unrelated PR — the cardinal rule that a contributor is never blocked for code they didn't write. `fail_on` also becomes per-skill at that point, so a trusted skill can block on new violations while a freshly-added skill stays observe-only until its baseline is seeded.

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
  - change_completeness:
      cross_repo:                          # opt-in: expensive, off by default
        - repo: my-org/shared-modules
        - repo: my-org/consumer-service
  - workflow_security
  - migration_safety
  - cost_attribution    # custom skill from .sentinel/skills/

routing:
  - pattern: "terraform/**"
    skills: [change_completeness]
    # fail_on: [critical, high, medium]   # per-route fail_on — planned, not yet implemented
  - pattern: ".github/workflows/**"
    skills: [workflow_security]
  - pattern: "migrations/**"
    skills: [migration_safety]

mode:
  on_push: [workflow_security, change_completeness]   # cheap, every push
  on_merge: [migration_safety]                        # expensive, final gate only
```

**Who uses it:** Platform team, tech leads. Controls the operational behavior — what runs, what blocks, what searches where.

**What it controls:** The runner. Not what skills look for (that's CLAUDE.md), but which skills run on which files and what happens when they find something.

**Cross-repo search is a skill property, not a separate skill.** Any skill can opt into cross-repo search via `cross_repo` in its config. When enabled, the runner checks out the specified repos and adds them to the tool search paths. This is expensive (clone time, API tokens) so it's off by default and explicitly enabled per-skill by the repo owner. Long-term, the LLM can deduce which repos to check from imports and dependencies — no manual config needed.

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

**What it controls:** What sentinel checks for. New skills, not new rules for existing skills (that's CLAUDE.md). Each file is a self-contained judgment check that the framework loads, runs, and reports independently. Custom skills use the same agentic pipeline as built-in skills — the only difference is where the prompt lives. Custom skills default to `max_turns: 3` (light exploration) and support YAML frontmatter to configure the budget.

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
- `CLAUDE.md` reader: injected into the skill's prompt as high-priority context. Teams write their rules in plain English; sentinel enforces them on every PR.
- GitHub Action (BYOK), posts severity-grouped comment with caller locations
- Self-review: sentinel runs on its own PRs. The review history is part of the demo.
- `fail_on` env var — empty by default (warning-only); set to `high,critical` to block merge

**Works on:** any repo, any language. The reasoning is about relationships between files, not syntax.

**What this proved:** Judgment-level review is possible with a single LLM call. CLAUDE.md as a customization surface works — freeform English beats a DSL. Later upgraded to agentic context gathering (v0.3) — skills that need it can explore the repo with tools before judging.

---

### v0.2 — The framework (multi-skill runner)

**The problem.** v0.1 hardcodes one skill: `ChangeCompletenessSkill(model=model).run(diff, context)`. There is no skill registry, no way to run multiple skills, no per-skill GHA output, no way for a team to add their own skill without editing sentinel's source. The Skill ABC exists but nothing uses it as a framework.

**What ships:**
- **Skill runner**: reads `sentinel.yml`, discovers built-in + custom skills, runs them in parallel, aggregates findings tagged by skill name
- **Per-skill GHA output**: annotations say `[ChangeCompleteness] HIGH: ...` not just `sentinel: ...`. PR comment groups findings by skill. Teams can see which judgment checks passed and which failed.
- **`sentinel.yml` support**: `skills` list, `fail_on` (global), `routing` (file pattern -> built-in skill mapping). Per-skill and per-route `fail_on` are planned but not yet implemented.
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

### v0.3 — High-value judgment skills + cross-repo as a skill property (shipped)

**The thesis.** Everyone has an LLM. The vertical value is in how many useful judgments you encode. v0.3 ships the first batch of built-in skills that catch real incidents — each one represents a class of production failure that no existing tool prevents. It also introduces cross-repo search as an opt-in property of any skill, not a separate skill.

**What shipped:**
- WorkflowSecuritySkill, MigrationSafetySkill (built-in skills)
- Agentic tool-use loop (grep, read_file, list_files) with per-skill max_turns budget
- Cross-repo checkout and search as a skill property
- Mode filtering (on_push vs on_merge)
- Path sandboxing, tool timeouts, per-skill exception isolation
- Custom skill frontmatter for max_turns

**Not yet implemented (planned):**
- Per-skill max_turns override via sentinel.yml config
- Per-route fail_on thresholds
- Per-skill fail_on thresholds
- Org-level config layer (mandatory skills, policy floor)

**Skills:**

#### WorkflowSecuritySkill

**The burn.** A workflow triggers on `pull_request_target`, checks out `${{ github.event.pull_request.head.sha }}`, and runs `npm install && npm test`. A malicious PR from a fork modifies `package.json` postinstall scripts to run arbitrary commands with the repository's `GITHUB_TOKEN` — which has write access. This is not a hypothetical. It is a documented class of attack that has hit major open-source projects.

Pattern matchers flag unpinned actions. They do not reason about the interaction between trigger types, checkout behavior, and token permissions.

What it checks:
- Dangerous trigger + checkout combinations (`pull_request_target` + head checkout)
- Over-broad OIDC trust policies (wildcard branch matching)
- Missing `permissions: {}` blocks (defaults to write-all)
- Secrets passed via env instead of `--arg`
- Excessive token scopes
- Severity `critical` for privilege escalation paths

#### MigrationSafetySkill

**The burn.** A migration adds a column with a `NOT NULL DEFAULT` on a 200M-row table. In MySQL < 8.0 and older Postgres, this locks the table for minutes. The migration passes in CI against an empty test database. It takes production down for 12 minutes during deploy.

Migration linters check syntax. They do not reason about table size, lock duration, backward compatibility with running application code, or whether a migration is safe to roll back.

What it checks:
- Locking operations on potentially large tables (add column with default, add index without CONCURRENTLY)
- Migrations that aren't backward-compatible with the current running application code
- Missing rollback path (destructive operations like column drops without a reversible strategy)
- Data migrations mixed with schema migrations (should be separate deploys)
- Severity `high` for locking operations, `critical` for irreversible data loss

**Framework capabilities that ship:**

#### Agentic context gathering (tool-use loop)

The diff alone is not enough for skills that reason about dependencies. If you rename a function in `foo.py`, the breakage is in `bar.py` — but `bar.py` isn't in the diff. The LLM guesses blind, then grep confirms after. Better: let the LLM explore the repo *before* it judges.

**Alternatives we rejected:**
- Regex symbol extraction — brittle, language-specific, patterns to maintain per language forever.
- Haiku scout call — slightly smarter grep, but still one-shot guessing. Doesn't follow dependency chains.
- Send all files — drowns signal in noise, blows token budget.
- Send only changed files — misses the point. Impact is in files that *didn't* change.

**The design: tool-use loop with budget.** Skills that need codebase context use Anthropic's tool-use API. The LLM gets three read-only tools (`grep`, `read_file`, `list_files`) and explores the repo in a bounded loop, deciding what to look at based on what it finds. This is the same pattern Claude Code uses — but scoped to three tools, read-only, with a hard turn limit.

```
1. Sonnet receives: diff + tools (grep, read_file, list_files)
2. Sonnet calls: grep("process_order", ".")
3. Runner executes, returns results
4. Sonnet calls: read_file("billing/charge.py")
5. Runner executes, returns file content
6. Sonnet: "I've seen enough" → returns findings JSON
   Or: max_turns hit → forced to return findings with what it has
```

**Per-skill config (planned — not yet wired through sentinel.yml):**

Each built-in skill has a hardcoded default `max_turns` (e.g. change_completeness=5, workflow_security=0). Custom skills set it via frontmatter. Overriding via sentinel.yml is planned:
```yaml
# planned — not yet implemented
skills:
  - change_completeness:
      max_turns: 5
  - workflow_security             # max_turns: 0 (diff-only, zero extra cost)
  - migration_safety
```

**`max_turns` is the only cost knob.** Same skill, same code, different budget:
- `max_turns: 0` = diff-only (today's behavior)
- `max_turns: 2` = quick exploration (one grep, read top files)
- `max_turns: 10` = thorough merge-gate analysis (follow dependency chains)

**Custom skills opt in via frontmatter:**
```markdown
---
max_turns: 5
---
Check that every new AWS resource has a cost_center tag...
```

Without frontmatter, custom skills default to `max_turns: 3` (light exploration).

**Language-agnostic.** The LLM understands Go imports, Python modules, Terraform variables, YAML references, proto schemas — any language. No per-language patterns to maintain. The tools are file operations; the intelligence is in the model.

**Works with cross-repo.** When `cross_repo` is enabled, the tools search cloned repos too. The LLM doesn't need to know they're separate repos — grep returns results from all search paths. Same loop, wider scope.

**Mechanical grep verify goes away.** The current post-judgment grep step (no matches = dismiss finding) is fundamentally flawed. It can only confirm *presence* of broken callers — it cannot confirm *absence* of a required entry. A skill that correctly flags "this registration is missing" gets dismissed because grep finds nothing. This isn't theoretical — it silently killed a correct finding from `skill_hygiene` in PR #7 while `change_completeness` caught the same issue only because it used a different search strategy (searching for `_BUILTIN_SKILLS` instead of `APIBreakingChangeSkill`).

In the agentic loop, the LLM uses `grep` as a tool and interprets results with judgment. "No matches for X in runner.py" means "X is missing — that's the bug." The mechanical verify step is replaced by the LLM's own evidence gathering. For `max_turns: 0` skills, findings are reported as-is — they're judgment calls from the diff alone.

#### Cross-repo search as a skill property

Cross-repo is not a skill — it's an optional capability any skill can use. When a skill has `cross_repo` configured in `sentinel.yml`, the runner checks out those repos and includes them in the tool search paths. Same agentic loop, wider scope — `grep` and `read_file` see files across all repos.

```yaml
# sentinel.yml
skills:
  - change_completeness:
      cross_repo:
        - repo: my-org/consumer-service
        - repo: my-org/data-pipeline
```

A proto change in `platform` is verified against callers in `consumer-service` and `data-pipeline`. ChangeCompleteness doesn't need new code — the runner widens its grep scope.

This is expensive (repo checkout, longer CI runs) so it's off by default. The repo owner opts in for specific skills where cross-boundary verification matters. Long-term (with agentic verification), the LLM can deduce dependencies from imports — no manual config needed.

#### Merge-gate mode

Some skills are cheap (single diff, fast) and should run on every push. Others are expensive (cross-repo, holistic analysis) and should only run as a final merge gate. The runner supports both:

```yaml
mode:
  on_push: [workflow_security, change_completeness]
  on_merge: [migration_safety]
```

**What this proves:** The framework's value scales with the number of encoded judgments. Each skill is a vertical slice of expertise — GHA security, migration safety, change completeness — that would otherwise live only in a senior engineer's head. Cross-repo search is a capability dimension, not a skill. The runner supports both cheap-and-frequent and expensive-and-final execution modes.

---

### v0.4 — Measuring whether it works (evals)

> For a worked end-to-end example of how the harness grades a fixture — the LLM step, the deterministic scorer step, and why "deterministic" matters when the LLM is non-deterministic — see [`docs/evals.md`](docs/evals.md). The section below is the strategic rationale; that doc is the concrete walkthrough.

**Status (2026-05-30):** Layer 1 shipped and gating CI. Layer 2 and the production-feedback loop are open.

| Item | Status |
|---|---|
| `sentinel eval run` CLI subcommand | shipped (#14) |
| Deterministic checker (Layer 1) | shipped (#14) |
| CI gate on skill/eval/runner changes | shipped (#15) |
| Curated fixtures | 4 / ~15 (one per built-in skill) |
| LLM judge (Layer 2) | not started |
| Judge-meta-eval gold set | not started |
| `PROMPT_MANIFEST` (prompt versioning) | not started |
| Quality × tokens × latency report | not started (today: pass/fail only) |
| Delta-vs-main in report | not started |

**The problem.** You ran sentinel for a month. Did it catch real things, or generate noise? You changed a prompt and now it flags every `count = 0` resource — false-positive rate went from 8% to 40%. You don't know yet. The model upgraded from Sonnet 4.6 to Sonnet 4.7; behavior shifted; nobody measured it. Most AI tooling in the wild ships without measurement. Sentinel ships with it — and the measurement story is itself the differentiator that makes the framework adoptable outside our own projects.

#### The measurement is two layers

**Layer 1 — deterministic check (no LLM in the scoring path).**

For each fixture, the harness runs the configured skills against `diff.patch` and `repo/`, then scores the produced findings against `expected.json` using pure pattern matching:

- For each entry in `must_find`: did sentinel produce a finding from the right *skill*, at or above the expected *severity*, that points at the expected *location* (file path or symbol)? Title text is not graded — only what the finding points at.
- For each entry in `must_not_find`: did sentinel produce that specific false positive?
- Did the overall *verdict* (complete / incomplete) match?
- Report per-fixture pass/fail and aggregate precision and recall.

"Deterministic" means **reproducible without an LLM**: same fixtures + same skill outputs always yield the same scores. There is no judgment in the scoring path. This is the cheap regression net — if a prompt change makes a skill stop firing or fire on the wrong file, the deterministic check turns red. No tokens spent on grading. No randomness. This layer alone catches the gross failure modes (skill silent, skill misfiring, skill verdict flipped) that account for most prompt regressions.

> **Why not grade on title keywords?** The v0.4 sketch originally scored on `title_contains`. That's brittle — a correct finding worded differently fails the test, producing noise on the measurement itself. A finding's value is whether it points the engineer at the actual problem: that's location + severity + skill. Title text is style and gets graded by the LLM judge below, not the deterministic checker.

**Layer 2 — LLM judge (graded by another model, on dimensions the deterministic layer can't measure).**

A separate LLM call grades each finding on:

- **Actionability** — could a reader fix the issue from this finding alone?
- **Grounding** — is the rationale supported by code that exists in the diff or repo?
- **Calibration** — is the severity appropriate to the actual blast radius?

The judge gets the diff, the finding, and the expected.json, and returns a score per dimension. **The judge uses a different model family from the generator** — if Sonnet generates the findings, a GPT or Gemini model grades them. Same-family judging is a known anti-pattern: the judge and the generator share blind spots, so the judge passes findings a human would reject.

**The judge is itself measured.** A small human-graded gold set (~20 findings, scored by us) is the ground truth. Each release of the judge prompt is checked against the gold set: if the judge disagrees with the human grader more than X% of the time, the judge prompt is rejected. The judge is part of the system under test, not above it.

#### Output: a quality × cost frontier, not a single pass/fail

The eval report has three measurement axes:

- **Quality** — precision, recall, judge scores per dimension
- **Tokens** — input + output, per skill, per fixture
- **Latency** — wall-clock per skill

A prompt change that improves recall by 3% but doubles tokens is not strictly better. The report surfaces the trade. **Cost is not a measured axis** — it's a derived view (tokens × current model price). The underlying measurement is tokens, which doesn't shift when Anthropic re-prices.

#### Fixtures are seeded curated, grown from production (v0.5 closes the loop)

v0.4 ships with ~15 hand-built fixtures derived from the incident classes each skill is meant to catch. The long-term corpus is grown from production telemetry (v0.5): every real sentinel run records its diff, findings, and any user feedback (dismissed / acted on). A pipeline samples *disagreements* — sentinel said critical and a user dismissed it; or a user flagged something sentinel missed — and proposes each as a candidate fixture for human approval. The eval corpus stays representative of what teams actually ship, not just what we thought of when we wrote v0.4.

This is what makes the harness durable rather than a museum of yesterday's bugs. The curated fixtures are the seed; production is the engine.

#### When evals run (not just on prompt change)

- **On skill / prompt change** — required pre-merge gate on this repo
- **On model upgrade** — full eval before flipping the default model (Sonnet 4.6 → 4.7 must pass)
- **On runner / context change** — same as prompt change; non-skill code can still move skill behavior
- **Scheduled drift** — weekly run on a stable corpus and prompt set; if scores wander, something upstream changed silently
- **On corpus growth** — every new fixture re-scores every skill against it

#### What ships in v0.4

- `sentinel eval run` CLI subcommand — load fixtures, run skills, score, emit report
- Deterministic checker (Layer 1) — location + severity + verdict grading, no LLM
- LLM judge (Layer 2) — rubric scoring with a different model family from the generator
- Judge-meta-eval — gold set of ~20 human-graded findings; the judge prompt is gated against it
- ~15 curated fixtures covering each built-in skill (current count: 4)
- Eval report — quality × tokens × latency, per skill, per fixture, with delta-vs-main
- `PROMPT_MANIFEST` — versioned prompt files; each report binds to a manifest hash
- CI workflow — runs eval on every PR to sentinel; fails on quality regression
- Eval report published as a GitHub Actions artifact

#### What this proves

AI systems are measurable. The two-layer approach — cheap deterministic regression net + nuanced LLM judge graded against humans — is a reproducible pattern any team can adopt. Shipping a tool with evals is the credibility move that lets outside teams trust the framework. The harness is part of the product, not internal scaffolding.

---

### v0.5 — Learning from production: telemetry + history

**Two problems, one feedback loop.**

**Telemetry problem.** v0.4 measures sentinel against fixtures *we* curated. The fixtures may not match what teams actually ship. Without production data we don't know if the eval corpus is representative, which findings users act on, which they dismiss, which PRs got merged despite a sentinel block. The eval is rigorous against itself but unmoored from reality.

**History problem.** A PR touches `eks/node-groups/main.tf`. Four months ago, PR #891 made a structurally similar change. After merge, nodes entered `NotReady` state from a missing taint toleration — 47-minute outage. Today's reviewer joined last month and doesn't know. Sentinel can.

Both problems share the same shape: *make sentinel learn from what already happened in this team's repo.* Telemetry is sentinel's own history (findings produced, dismissed, acted on). History is the team's (merged PRs, incidents). Both feed skill context at review time. Telemetry additionally feeds the v0.4 eval corpus — closing the loop between measurement and reality.

#### What ships

**Telemetry**
- Every sentinel run emits a structured event: trigger, repo, PR/commit, skills run, findings produced, tokens, latency
- Findings get a stable ID and a feedback URL (one-click dismiss; one-click "this was useful")
- Storage backend is BYO — default is a GitHub repo dedicated to telemetry; HTTP endpoint also supported. No Anthropic-side data store; teams own their data.
- Weekly aggregation: per-skill precision (acted-on / total findings), per-team noise rate, latency distribution
- **Fixture-proposal pipeline**: samples agreement cases (sentinel critical → user acted) and disagreement cases (sentinel critical → user dismissed; or human flagged something sentinel missed). Each becomes a candidate fixture queued for human review. Approved candidates land in `evals/fixtures/`.

**Telemetry layering — Sentinel is not an observability platform.**
LLM observability (Arize Phoenix, Langfuse, Helicone, Braintrust) traces individual LLM calls — prompts, responses, tokens, latency. Sentinel telemetry sits one layer above: the unit is a *finding* and what the user did with it, not the LLM call. The two are complementary, not competing. Sentinel emits OpenTelemetry-compatible spans so any team already running Phoenix or Langfuse picks up sentinel traces for free — wire the OTLP endpoint and it works. Sentinel does not ship its own trace UI.

**History (RAG)**
- GitHub API integration: fetches merged PRs from the last N months; stores diff summaries and reviewer comments
- Incident linking: GitHub issues labeled `postmortem` or `incident` are stored and retrievable
- RAG retrieval: top-k semantically similar past PRs and incidents injected as context when a skill runs
- Consistently-dismissed finding patterns (via telemetry) are down-weighted in future similar contexts — the system gets quieter without retraining

#### Privacy and trust

For sentinel to be adopted outside our own projects, telemetry must be opt-in and self-hosted by default. The reference setup stores events in a private GitHub repo the team controls. No diff or finding text leaves the team's GitHub org unless they explicitly point telemetry at a remote endpoint. This is the same trust posture as the API key model — BYO, locally controlled, no central data plane.

#### What this proves

AI systems learn from their environment without retraining weights. The eval corpus stays current because production feeds it. Skills get sharper because they see what reviewers actually flag and dismiss. The pattern — telemetry → eval growth → prompt refinement — is the loop every serious AI deployment needs and almost none publish openly. Sentinel ships it as part of the framework.

---

### v0.5.5 — Baseline & compliance (stock measurement + ratchet)

**The gap.** v0.4 and v0.5 measure the *flow* — findings per PR, dismissed vs. acted on. Neither answers the *stock* question: how compliant is the whole repo, right now, against a given skill? PR review is structurally blind to it — a diff that introduces no violations passes while the untouched code may hold hundreds. And the moment you add a new skill — a new compliance dimension: i18n, a security standard, a rollout — *all* existing code is unmeasured: the skill has reviewed zero PRs and cannot know the repo's state without scanning it. This is the capability an autonomous workload needs most: without a baseline, a fleet of agent commits either drowns in legacy-debt findings or grandfathers everything silently.

**The model — flow + stock, one judgment.**

```
level(today) = baseline (from an audit) + Σ(PR deltas since)
```

Same skills, same encoded judgment. The `audit` trigger feeds the skill the *tree* (files selected by routing globs) instead of a *diff*, and the output contract flips from "is this change compliant" to "enumerate the violations." The result is a **baseline** — `.sentinel/baseline.json`, committed to the repo: the set of known pre-existing violations per skill. PR review then *ratchets* against it. Audit does not run per-PR — the PR delta already captures change. Audit runs to seed the baseline, to onboard a new skill, and on a schedule to correct drift.

**What ships:**
- **`audit` trigger** — runs routed skills over matching files, emits a finding per violation, writes/updates the baseline. Reuses the v0.7 schedule mechanism.
- **Stable fingerprints** — each finding gets a line-insensitive identity (skill + file + anchor) so line drift doesn't manufacture false "new" findings. Skills may emit an explicit anchor; the default is (file + normalized title).
- **The ratchet, on every PR:**
  1. Run routed skills on the diff (today's path).
  2. Load the committed baseline.
  3. Classify each finding — **NEW** (not in baseline) / **KNOWN** (standing debt) / **FIXED** (a baselined violation this PR removed).
  4. **Block only on NEW** at the skill's `fail_on` severity. KNOWN is reported, never blocks. FIXED decrements the baseline — burndown credit.
  5. Emit a per-skill telemetry event carrying `{new, known, fixed, baseline_total}`.
- **New-skill onboarding** — a skill with no baseline runs **observe-only** (non-blocking) until `sentinel audit --skill X` scans existing code once and seeds its baseline with the starting debt. That one-time scan is the only audit a new skill triggers; from then on it ratchets.
- **Re-baseline escape hatch** — `sentinel audit --update-baseline` accepts the current state. Because the baseline is a committed file, the change appears in the PR diff and is itself code-reviewed — no silent waiver.
- **Per-skill / per-route `fail_on`** — finally wired (planned since v0.3). This is the blocking/non-blocking tier: new skills observe, trusted skills block on NEW.
- **Surfacing** — the job summary and PR comment gain two panels: **This PR** (new / fixed) and **Repo debt** (baseline totals for the touched skills, read straight from the committed baseline — no re-audit). `sentinel telemetry summarize` gains the stock view: baseline trajectory per skill = the burndown curve, alongside the flow view it already has.

**Scheduled audit keeps the number live.** The `audit` trigger also runs on a cron against *every* skill, not only newly-added ones — re-measuring the whole tree so the compliance number reflects reality (direct-to-main commits, anything PRs missed, drift). Re-latching onto *existing* skills is the point: a cron that only scans for new-skill issues silently lets established skills rot. Each scheduled run **always emits a fresh measurement**, but it does **not** silently rewrite the accepted baseline — it opens a PR proposing the delta (consistent with v0.7: git is the interface, output is a PR or a finding, never a silent mutation). That keeps the ratchet honest — new debt cannot launder itself into the baseline — while keeping the headline number current.

**The PR is the surface.** The most valuable view is the one a reviewer already looks at. Every PR shows, per skill: what *this* PR added vs. fixed (flow), the repo's *current* compliance level (stock), and how that level moved over recent PRs (trend) — e.g. "this repo carries 12 known migration risks, down from 18 a month ago; this PR moves it to 13." Debt and new issues are never conflated: new is actionable-now and may block; debt is context and never blocks an unrelated change.

**Compliance telemetry as a standard emission.** Every skill run already emits a per-skill, per-PR event; the framework promotes this to a documented *compliance event* — `{repo, pr, skill, severity, new, known, fixed, baseline_total, ts}` — a first-class contract independent of where it's stored (BYO sink today; OTLP spans for Phoenix/Langfuse, same posture as v0.5). Three signals fall out of that one stream for free:
- **Current compliance** per skill (latest `baseline_total`).
- **Trend** per skill over time (`baseline_total` trajectory = burndown).
- **Attribution** — *which PRs deteriorated which skills most* (rank PRs by `new` per skill). A deterioration leaderboard points straight at the changes that introduced the most debt — exactly where to aim a fix or a new skill.

Standardising the *emission* rather than the storage is the leverage: a dashboard, the eval corpus, or an alert all read one stable schema. We don't have to know today where it's consumed — only that every trigger emits it the same way.

**Skill effectiveness — the other trend line.** The trend above is about the *repo* (is it getting cleaner). The orthogonal trend is about the *skill itself* (is it any good, and does it stay good across production PRs) — and "a skill not catching enough" is the hardest, most important half. Three sources combine into one per-skill effectiveness time series:
- **Precision (noise) trend** — `dismissed / (dismissed + acted_on)` from the v0.5 feedback signal. A rising dismiss rate means the skill is going noisy. Fold `dismissed` / `acted_on` into the compliance event so precision and volume live in one stream.
- **Recall (under-catching) trend** — the signal the flow/stock split uniquely unlocks. When a *scheduled audit* surfaces a violation in code that a PR introduced *after* the skill was active, and that PR was reviewed clean for that skill, the skill **missed** it. With per-baseline-entry provenance (`first_seen` + blame to the introducing PR), recall ≈ caught-at-introduction / (caught + later-found-by-audit). This is *production* recall — the thing v0.4 evals structurally cannot measure, because fixtures only test what we thought to curate.
- **Firing health** — a skill whose `new` rate falls to ≈0 across many PRs with no prompt or model change is silently broken (regression, bad route, model drift). A simple anomaly check on the existing event stream catches "the skill went quiet" before anyone notices the misses.

Together these answer *which skill is decaying and in which direction* — losing precision (noisy) or losing recall (blind) — per skill, over time, attributable to PRs. v0.4 fixtures stay the controlled, point-in-time, pre-merge gate; this is the uncontrolled, over-time, production trend. Complementary: a fixture regression is caught before merge, a production drift is caught over weeks.

**Eval alignment.** Audit mode gets first-class fixtures: alongside `diff.patch` / `expected.json` (flow), a fixture may carry an `expected_baseline.json` (stock), scored by the same deterministic checker — did the audit enumerate the right violations across `repo/`? The audit path stays measurable by the v0.4 harness rather than a side channel, and the attribution logic is regression-tested like any skill.

**Compatibility — this does not break v0.3 as it stands.** Every part is additive. No baseline file → exactly today's behavior (all findings are "new," `fail_on` is global). New event fields are optional. The `Skill.run(diff, context)` signature is untouched — audit is a new *traversal + entrypoint* that composes the skill's judgment over files, not a change to the skill contract. Implementation lands later; the plan commits to the shape, not a rewrite.

**Deferred — touched-file evaluation.** Pure diff review can miss issues where a small change interacts with untouched code. Evaluating the *full content* of files the PR touches (not just the hunk) catches those interactions and makes fix-detection exact. It is bounded (touched files only, not the tree) and rides the same machinery as FIXED-detection, so it lands as a refinement here rather than a separate effort.

**What this proves.** The flow/stock split completes the measurement story: v0.5 tracks whether new code degrades; this tracks the absolute level and its trend. Compliance becomes a managed number with a burndown, not a vibe — and a new standard can be rolled out across a repo (or, with cross-repo, a fleet) with a known starting debt and a ratchet that prevents regression. This is the missing piece between "we review PRs" and "we run a compliance program" — and it's the distinction between sentinel and the company proposal that started this: they specified the compliance/tracking layer; this is how it bolts onto a judgment engine that already exists.

---

### v0.6 — Sentinel fixes what it finds

**The problem.** Sentinel flags that three callers still pass a removed Terraform variable. A reviewer leaves a comment. The author makes the fix in each file. This is mechanical work that should not require a human round-trip.

Sentinel can fix it. It creates a branch, applies the change, opens a draft PR. The human reviews and merges. Sentinel does not self-merge.

**What ships:**
- `AutoFixMode`: for well-defined, low-risk fixes, sentinel creates a branch and opens a draft PR
- Every auto-fix PR body documents: which finding triggered it, what was changed, why the fix is safe
- Fixes are traceable back to the sentinel review that produced them

**What this proves:** The agent pattern — observe, reason, act, hand off. This is the bridge from review agent to operational agent. The same judgment that found the problem generates the fix.

---

### v0.7 — Operational agent

**The problem.** Drift happens between PRs. A shared module updates; consumers stale. Console-edited infra diverges from Terraform state. Rotated secrets unreferenced in manifests. The PR loop catches none of this.

**What ships:**
- **Scheduled drift detection** — cron runs sentinel against live state vs declared state; opens a PR per detected drift.
- **Incident correlation** — GitHub issues labelled `incident` get a sentinel comment naming the most likely causal commit.
- **Deployment gate** — sentinel as a required check on the changes since last deploy, not just since last merge.

**What this proves:** Same skills, different trigger. Git stays the interface — output is always a PR or a finding, never a direct mutation. This is the milestone that turns the inference service from "agents commit code" to "cluster manages itself."

---

### v0.7.5 — Autonomous merge gate

**The problem.** A coding agent pushes a commit. *Something* decides whether to merge. Today that "something" is implicit — a human still reviews, or there is no gate. Sentinel has the judgment; what's missing is an explicit policy for autonomous gating and an explicit answer for what happens when sentinel blocks (because no human is on the other side of the comment).

**Three viable commit shapes** the gate must support:

| Shape | When to use |
|---|---|
| Auto-merge PR | Default. Agent opens PR, gates pass → auto-merge. Free GitHub audit trail. |
| Pre-receive gate (no PR) | High commit rate, audit handled elsewhere. |
| Merge queue (`merge_group`) | Only when conflict rate from concurrent agent commits warrants serialization. |

**What ships:**
- **Gate policy in `sentinel.yml`** — one block declaring "green" (tests + sentinel verdict + optional judge confidence floor) and what happens on red.
- **Block-mode choices** — `file-issue`, `page-human` (webhook / on-call), or `handoff-to-autofix` (chain into v0.6).
- **`agent_commit` trigger wired** — same skill code, new output path. Stops being aspirational.
- **Agent-loop telemetry** — per-decision event (what blocked, what passed, gate latency). No human to compensate for noise; signal quality matters more.
- **Reference deployment** — `docs/autonomous-gate.md` with the inference repo wired in end-to-end. Pattern proven on a real workload before being recommended to anyone else.

**What this proves:** Sentinel survives the trigger model collapsing. The framework takes the gate decision as a first-class concern rather than leaving every operator to invent it. This is what makes the design durable across the 1–2 year arc to autonomous workflows.

---

### v0.8 — Skill authoring CLI and auto-discovery

**The problem.** A team wants to add a custom skill but doesn't know what makes a good one. They write a vague prompt, get noisy findings, and turn it off. The gap between "I know what reviewers keep catching" and "I have a working sentinel skill" is too wide.

**What ships:**
- `sentinel init-skill` CLI: interactive scaffolding that produces a well-structured `.sentinel/skills/*.md` file. Encodes the anatomy of a good skill: what to check, severity criteria, positive/negative examples, tool-use examples.
- Skill template with inline guidance — the generated file teaches the author what each section does
- `sentinel validate-skill`: dry-run a custom skill against a sample diff, shows what findings it would produce before committing
- **Auto-suggested skills from PR history**: sentinel analyzes merged PRs and reviewer comments (from v0.5 feedback data), identifies recurring patterns ("reviewers flagged missing changelog entries 12 times in 60 days"), and proposes a draft skill. The human reviews, edits, and commits — sentinel doesn't self-create skills.

**The arc:** Skills start as tribal knowledge in reviewers' heads. `init-skill` helps teams encode what they already know. Auto-suggestion surfaces patterns they haven't noticed yet. The system gets smarter without anyone retraining a model — the intelligence lives in the skill library, not the weights.

**What this proves:** AI tooling can lower its own adoption barrier. The CLI that runs skills also helps you write them. The feedback loop from v0.5 (history) feeds forward into new skills — review comments become codified judgment automatically.

---

### v1.0 — A framework, not just a tool

**What ships:**
- `sentinel` Python package on PyPI — usable as a library
- `Skill`, `EvalHarness`, `ContextAssembler` as stable public APIs
- `sentinel init` CLI: scaffolds sentinel config in any repo
- `sentinel init-skill` CLI: scaffolds custom skills with best-practice structure (from v0.8)
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
| Week 3 | `sentinel init-skill` to create custom prompts | Guided skill authoring, domain-specific judgment, no fork needed |
| Month 2 | Run evals, review the report | You know if sentinel is helping or generating noise |
| Month 3 | Add cross-repo references in `sentinel.yml` | Changes verified against consumers in other repos |
| Month 4 | Enable auto-fix for confirmed findings | Mechanical fixes stop requiring human round-trips |
| Month 6 | Enable scheduled drift detection | Sentinel watches for problems between PRs |
| Year 1+ | Wire sentinel as the pre-merge gate for an autonomous coding agent | Same skills, new trigger — judgment continues to apply when no human writes the PR |

---

## This repository

Sentinel reviews its own pull requests from v0.1 onward. The PR history is part of the demo — you can read the git log and see sentinel's reviews improving milestone by milestone. The eval harness runs in CI. Prompt regressions fail the build. The quality metrics are tracked and visible.

The goal is not just to ship a useful tool. It is to show, concretely and step by step, how any engineering team can introduce AI judgment into their development process — measurably, incrementally, without replacing what already works. And to show how that same judgment extends from reviewing PRs today to gating autonomous coding agents tomorrow: the trigger evolves, the skills don't have to.
