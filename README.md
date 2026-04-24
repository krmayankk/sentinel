# sentinel

A framework for running AI agents in your software delivery pipeline. Git is the interface — PRs, diffs, and commits are inputs. Agents review, enforce, fix, and generate — triggered by the events your team already produces.

Sentinel is not a linter. It does not replace Semgrep, Checkov, Dependabot, or Gitleaks. Those tools catch known rule violations. Sentinel catches what requires judgment: the Terraform change that looks like one line but destroys a NAT gateway; the GitHub Actions workflow that is a privilege escalation path; the PR that renames a shared interface without updating its callers; the service that ships with no health check and no runbook.

**The building blocks:**

- **Skills** — composable analysis units. Each skill takes a diff and context, reasons via LLM, and returns typed findings. Skills are independent: run one or all, add your own.
- **CLAUDE.md** — teach sentinel your team's conventions in plain English. Injected into every review as high-priority context. No DSL, no redeployment.
- **Evals** — fixtures with expected verdicts. Quality is measured, not assumed. A prompt change that regresses below threshold fails the build.
- **Judgment levels** — every finding has a severity. Start non-blocking on day one. Move findings to blocking (`fail_on: [critical]`, then `[critical, high]`) as you validate they are real.

See [PLAN.md](./PLAN.md) for the full architecture and milestone breakdown.

> This repo uses sentinel to review its own pull requests. The review history is part of the demo.

---

## Quickstart

Add sentinel to any repo. Create `.github/workflows/sentinel.yml`:

```yaml
on: [pull_request]
jobs:
  sentinel:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: krmayankk/sentinel@main
        with:
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
          fail-on: ""   # empty = warning-only; use "high,critical" to block merge
```

Add `ANTHROPIC_API_KEY` as a [repository secret](https://docs.github.com/en/actions/security-guides/encrypted-secrets). Sentinel reviews every PR and posts findings as inline annotations and a PR comment.

**Start non-blocking.** Review the findings for a week. When you trust a severity level, add it to `fail-on`. The progression is explicit and team-controlled — no surprise CI failures on day one.

---

## Teaching sentinel your conventions

Sentinel's built-in prompts cover universal patterns. Your team's specific conventions go in `CLAUDE.md`. Add a section:

```markdown
## Completeness rules
- When a Terraform module variable changes, all callers under terraform/envs/ must be updated
- All Lambda functions must have a dead-letter queue configured
- New services require a runbook at docs/runbooks/<service>.md before merge
- When a new required env var is added, k8s/configmaps/ and .env.example must reference it
```

Push to `CLAUDE.md` and the next PR picks it up. No redeployment, no DSL to learn. Any engineer on the team can add or update rules.

---

## Built-in skills

Sentinel ships with skills that catch real incident classes no existing tool prevents:

| Skill | What it catches | Severity |
|---|---|---|
| `change_completeness` | Renamed function but callers not updated. Removed Terraform variable but three envs still pass it. | high |
| `workflow_security` | GHA `pull_request_target` + head checkout = privilege escalation. Missing `permissions:` block. Secrets exposed to untrusted code. | critical |
| `migration_safety` | `CREATE INDEX` without `CONCURRENTLY` locks writes for minutes. `DROP COLUMN` on a table the app still queries. | high/critical |

Each skill is a prompt that teaches the LLM what to reason about, plugged into the same pipeline: prompt → LLM → parse findings → grep verify.

---

## Configuring with sentinel.yml

Control which skills run, what blocks merge, and which skills apply to which files:

```yaml
# sentinel.yml
skills:
  - change_completeness
  - workflow_security
  - migration_safety

fail_on: [critical, high]

routing:
  - pattern: ".github/workflows/**"
    skills: [workflow_security]
  - pattern: "migrations/**"
    skills: [migration_safety]
```

**Routing** maps file patterns to skills. When a PR only changes workflow files, only `workflow_security` runs — saves API tokens and eliminates noise. Files that don't match any route fall back to the full skills list. Routing works the same for built-in and custom skills.

---

## Custom skills

Define new judgment checks as markdown files in `.sentinel/skills/`. Each file becomes a skill that runs alongside built-in ones through the same pipeline.

```markdown
# .sentinel/skills/cost_attribution.md
Check that every new AWS resource (S3, RDS, Lambda, ECS) has a
`cost_center` tag. Missing tags on production resources have caused
unattributed spend incidents. Severity: high for production resources
(anything under terraform/envs/prod/), medium for staging/dev.
```

Add the file, push, and the next PR runs it. No fork, no code change, no redeployment.

---

## Run locally

```bash
git clone https://github.com/krmayankk/sentinel && cd sentinel
pip install -e .
sentinel review --diff my.patch --repo-path . --env .env
```

---

## How the verification works

Sentinel uses a two-step approach to eliminate speculation:

1. **LLM analysis** — the diff is sent to Claude. The model identifies what changed, reasons about what depends on it, and returns candidate findings with a `search_for` term for each gap it suspects.

2. **Codebase verification** — for each candidate, sentinel greps the actual repository for the search term. Findings confirmed by real matches are reported with exact file paths and line numbers. Findings with no matches are dismissed — the LLM suspected a problem, but the codebase confirms it is clean.

A finding is only reported when broken callers are confirmed to exist. No noise.
