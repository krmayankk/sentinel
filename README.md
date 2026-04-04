# sentinel

Deploy AI agents across your software lifecycle: review PRs, auto-fix issues, generate tests, enforce team standards — measurably, at scale.

Sentinel is a framework for building and governing AI agents in your software delivery pipeline. Git is the interface. PRs, diffs, commits, and issues are inputs. Agents review, fix, generate, and enforce — triggered by the events your team already produces.

It is not a linter. It does not replace Semgrep, Checkov, Dependabot, or Gitleaks. Those tools catch known rule violations. Sentinel catches what requires judgment: the Terraform change that looks like one line but destroys a NAT gateway; the GitHub Actions workflow that is a privilege escalation path; the PR that changes a shared module interface without updating its three consumers; the service that ships with no health check, no alerts, and no runbook.

Designed to be introduced incrementally — non-blocking on day one, as autonomous as the team decides over time. See [PLAN.md](./PLAN.md) for the full architecture, milestone breakdown, and how a team adopts it from zero to full automation.

> This repo uses sentinel to review its own pull requests. The review history is part of the demo.
