# sentinel

An AI-powered pull request reviewer for engineering teams — works on any repo, any language, any stack.

Sentinel is not a linter. It does not replace Semgrep, Checkov, Dependabot, or Gitleaks. Those tools catch known rule violations. Sentinel catches the things that slip through anyway: the Terraform change that looks like one line but destroys a NAT gateway and causes a network outage; the GitHub Actions workflow that is a privilege escalation path; the PR that changes a shared module interface without updating its consumers; the service that ships to production with no health check, no alerts, and no runbook.

It is also designed to be introduced incrementally — non-blocking on day one, as strict as you want over time. See [PLAN.md](./PLAN.md) for the full architecture, milestone breakdown, and the story of how a team adopts it from zero to full automation.

> This repo uses sentinel to review its own pull requests. The review history is part of the demo.
