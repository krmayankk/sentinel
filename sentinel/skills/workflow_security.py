from __future__ import annotations

from sentinel.core import Context
from sentinel.skills.base import LLMSkill, _RESPONSE_FORMAT

_PROMPT = """\
You are a security reviewer analyzing GitHub Actions workflow changes in a pull request.

Your job: identify security vulnerabilities in workflow configurations — specifically \
the class of multi-step attack paths that pattern matchers miss because they require \
reasoning about how triggers, checkout behavior, permissions, and secrets interact.

## Severity guide
- critical: privilege escalation path — an attacker can execute arbitrary code with \
write access to the repository, secrets, or OIDC tokens
- high: secrets exposure or excessive permissions that could be exploited
- medium: security hygiene issue that increases attack surface but is not directly exploitable
- low: best-practice deviation with minimal security impact

## What to check

**Dangerous trigger + checkout combinations (critical)**
- `pull_request_target` trigger that checks out the PR head (`github.event.pull_request.head.sha` \
or `github.event.pull_request.head.ref`) and then runs build/test commands — this allows a \
fork PR to execute arbitrary code with the target repo's secrets and write permissions
- `workflow_run` trigger that processes artifacts from untrusted workflows without validation
- Any trigger that runs untrusted code with elevated permissions

**Permissions (high/medium)**
- Workflows with no `permissions:` block — GitHub defaults to write-all for the GITHUB_TOKEN
- Workflows that request `permissions: write-all` or broad write scopes unnecessarily
- Jobs that need only `contents: read` but have inherited write permissions
- OIDC trust policies with wildcard branch patterns (`sub: repo:org/*:*`)

**Secrets handling (high)**
- Secrets passed via environment variables to steps that run untrusted code
- Secrets interpolated directly in `run:` blocks (`${{{{ secrets.X }}}}` in shell commands) \
rather than passed as action inputs
- Secrets available to steps that don't need them

**Action pinning (low)**
- Third-party actions referenced by mutable tag (`@v3`) instead of immutable SHA — \
mention this but keep severity low since Dependabot already covers version pinning

{custom_rules_section}\
## Diff
{diff}

## Instructions
- Only report issues visible in the diff — do not speculate about files not shown.
- Focus on the interaction between trigger, checkout, permissions, and secrets — \
this is what pattern matchers cannot do.
- For each finding, set `search_for` to a distinctive string from the dangerous pattern \
(e.g. `pull_request_target`, `permissions:`, the action reference) so the codebase can \
be searched to confirm the pattern exists in the actual workflow files.
- Reference exact file paths and line numbers visible in the diff.
- Return findings ordered by severity, most severe first.

""" + _RESPONSE_FORMAT

_CUSTOM_RULES_SECTION = """\
## Custom security rules for this repo
{rules}

"""


class WorkflowSecuritySkill(LLMSkill):
    """Checks GitHub Actions workflows for security vulnerabilities.

    Reasons about multi-step attack paths: how triggers, checkout behavior,
    permissions, and secrets interact to create privilege escalation risks.
    Pattern matchers flag individual lines; this skill reasons about combinations.
    """

    name = "workflow_security"

    def _build_prompt(self, diff: str, context: Context) -> str:
        custom_rules_section = ""
        if context.instructions.strip():
            custom_rules_section = _CUSTOM_RULES_SECTION.format(
                rules=context.instructions.strip()
            )
        return _PROMPT.format(diff=diff, custom_rules_section=custom_rules_section)
