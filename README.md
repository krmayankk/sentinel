# sentinel

Deploy AI agents across your software lifecycle: review PRs, auto-fix issues, generate tests, enforce team standards — measurably, at scale.

Sentinel is a framework for building and governing AI agents in your software delivery pipeline. Git is the interface. PRs, diffs, commits, and issues are inputs. Agents review, fix, generate, and enforce — triggered by the events your team already produces.

It is not a linter. It does not replace Semgrep, Checkov, Dependabot, or Gitleaks. Those tools catch known rule violations. Sentinel catches what requires judgment: the Terraform change that looks like one line but destroys a NAT gateway; the GitHub Actions workflow that is a privilege escalation path; the PR that changes a shared module interface without updating its three consumers; the service that ships with no health check, no alerts, and no runbook.

Designed to be introduced incrementally — non-blocking on day one, as autonomous as the team decides over time. See [PLAN.md](./PLAN.md) for the full architecture, milestone breakdown, and how a team adopts it from zero to full automation.

> This repo uses sentinel to review its own pull requests. The review history is part of the demo.

## Quickstart

Add sentinel to any repo in five lines. Create `.github/workflows/sentinel.yml`:

```yaml
on: [pull_request]
jobs:
  sentinel:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: krmayankk/sentinel/.github/actions/sentinel@main
        with:
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
          fail-on: "high,critical"   # omit to run in warning-only mode
```

Add `ANTHROPIC_API_KEY` as a [repository secret](https://docs.github.com/en/actions/security-guides/encrypted-secrets). That's it — sentinel reviews every PR and posts findings as inline annotations and a comment.

**Teach sentinel your conventions.** Add a `CLAUDE.md` to your repo with a `## Completeness rules` section:

```markdown
## Completeness rules
- When a Terraform module variable changes, all callers under terraform/envs/ must be updated
- When a new GHA action input is added, it must be forwarded in runs.steps.env and read in the entrypoint
- When a new required env var is added, k8s/configmaps/ and .env.example must reference it
```

Sentinel injects this on every review. No redeployment — push to `CLAUDE.md` and the next PR picks it up.

**Run locally** against any diff:

```bash
pip install sentinel-ai
sentinel review --diff my.patch --repo-path . --env .env
```
