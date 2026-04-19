"""Tests for WorkflowSecuritySkill — prompt construction and parsing (no LLM calls)."""
from sentinel.core import Context, Severity
from sentinel.skills.workflow_security import WorkflowSecuritySkill


def _make_skill():
    """Create a WorkflowSecuritySkill without hitting the API."""
    skill = object.__new__(WorkflowSecuritySkill)
    skill.name = "workflow_security"
    skill._model = "claude-sonnet-4-6"
    skill._max_tokens = 1024
    return skill


def _context(instructions=""):
    return Context(repo="test/repo", pr_number=1, instructions=instructions)


_SAMPLE_DIFF = """\
diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -1,5 +1,10 @@
+on:
+  pull_request_target:
+jobs:
+  test:
+    steps:
+      - uses: actions/checkout@v4
+        with:
+          ref: ${{ github.event.pull_request.head.sha }}
+      - run: npm test
"""


def test_skill_name():
    skill = _make_skill()
    assert skill.name == "workflow_security"


def test_build_prompt_includes_diff():
    skill = _make_skill()
    prompt = skill._build_prompt(_SAMPLE_DIFF, _context())
    assert "pull_request_target" in prompt
    assert "npm test" in prompt
    assert "severity" in prompt.lower()


def test_build_prompt_includes_custom_rules():
    skill = _make_skill()
    prompt = skill._build_prompt(_SAMPLE_DIFF, _context("No third-party actions allowed"))
    assert "No third-party actions allowed" in prompt
    assert "Custom security rules" in prompt


def test_build_prompt_no_custom_rules():
    skill = _make_skill()
    prompt = skill._build_prompt(_SAMPLE_DIFF, _context(""))
    assert "Custom security rules" not in prompt


def test_parse_valid_response():
    skill = _make_skill()
    raw = '''{
      "findings": [
        {
          "severity": "critical",
          "title": "Privilege escalation via pull_request_target",
          "message": "Workflow checks out PR head and runs npm test with write permissions",
          "suggestion": "Use pull_request trigger instead, or add permissions: read-all",
          "file": ".github/workflows/ci.yml",
          "line": 2,
          "search_for": "pull_request_target"
        }
      ],
      "summary": "Critical privilege escalation path found"
    }'''
    findings = skill._parse(raw)
    assert len(findings) == 1
    assert findings[0].severity == Severity.CRITICAL
    assert findings[0].title == "Privilege escalation via pull_request_target"
    assert findings[0].search_for == "pull_request_target"


def test_parse_no_findings():
    skill = _make_skill()
    raw = '{"findings": [], "summary": "No security issues found"}'
    findings = skill._parse(raw)
    assert len(findings) == 0


def test_parse_multiple_severities():
    skill = _make_skill()
    raw = '''{
      "findings": [
        {
          "severity": "critical",
          "title": "Dangerous trigger",
          "message": "pull_request_target with head checkout",
          "suggestion": "Fix it",
          "search_for": "pull_request_target"
        },
        {
          "severity": "medium",
          "title": "Missing permissions block",
          "message": "No permissions: {} in workflow",
          "suggestion": "Add permissions: read-all",
          "search_for": "permissions:"
        }
      ],
      "summary": "Found issues"
    }'''
    findings = skill._parse(raw)
    assert len(findings) == 2
    assert findings[0].severity == Severity.CRITICAL
    assert findings[1].severity == Severity.MEDIUM
