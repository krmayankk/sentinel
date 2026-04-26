"""Tests for MigrationSafetySkill — prompt construction and parsing (no LLM calls)."""
from sentinel.core import Context, Severity
from sentinel.skills.migration_safety import MigrationSafetySkill


def _make_skill():
    """Create a MigrationSafetySkill without hitting the API."""
    skill = object.__new__(MigrationSafetySkill)
    skill.name = "migration_safety"
    skill._model = "claude-sonnet-4-6"
    skill._max_tokens = 1024
    return skill


def _context(instructions=""):
    return Context(repo="test/repo", pr_number=1, instructions=instructions)


_SAMPLE_DIFF = """\
diff --git a/migrations/0042_add_email_index.sql b/migrations/0042_add_email_index.sql
--- /dev/null
+++ b/migrations/0042_add_email_index.sql
@@ -0,0 +1,3 @@
+-- Add index on users.email
+ALTER TABLE users ADD COLUMN verified BOOLEAN NOT NULL DEFAULT false;
+CREATE INDEX idx_users_email ON users(email);
"""


def test_skill_name():
    skill = _make_skill()
    assert skill.name == "migration_safety"


def test_build_prompt_includes_diff():
    skill = _make_skill()
    prompt = skill._build_prompt(_SAMPLE_DIFF, _context())
    assert "ALTER TABLE" in prompt
    assert "CREATE INDEX" in prompt
    assert "locking" in prompt.lower()


def test_build_prompt_includes_migration_concerns():
    skill = _make_skill()
    prompt = skill._build_prompt(_SAMPLE_DIFF, _context())
    assert "backward" in prompt.lower()
    assert "rollback" in prompt.lower()
    assert "CONCURRENTLY" in prompt


def test_build_prompt_includes_custom_rules():
    skill = _make_skill()
    prompt = skill._build_prompt(_SAMPLE_DIFF, _context("Always use pt-online-schema-change for MySQL"))
    assert "pt-online-schema-change" in prompt
    assert "Custom migration rules" in prompt


def test_build_prompt_no_custom_rules():
    skill = _make_skill()
    prompt = skill._build_prompt(_SAMPLE_DIFF, _context(""))
    assert "Custom migration rules" not in prompt


def test_parse_critical_finding():
    skill = _make_skill()
    raw = '''{
      "findings": [
        {
          "severity": "critical",
          "title": "DROP TABLE without backup strategy",
          "message": "Migration drops the orders table with no rollback path",
          "suggestion": "Add a backup step or soft-delete strategy before dropping",
          "file": "migrations/0042_drop_orders.sql",
          "line": 1,
          "search_for": "orders"
        }
      ],
      "summary": "Critical data loss risk"
    }'''
    findings = skill._parse(raw)
    assert len(findings) == 1
    assert findings[0].severity == Severity.CRITICAL


def test_parse_mixed_severities():
    skill = _make_skill()
    raw = '''{
      "findings": [
        {
          "severity": "high",
          "title": "Index creation without CONCURRENTLY",
          "message": "CREATE INDEX on users table will lock writes",
          "suggestion": "Use CREATE INDEX CONCURRENTLY",
          "search_for": "idx_users_email"
        },
        {
          "severity": "medium",
          "title": "NOT NULL without default",
          "message": "Adding NOT NULL column to existing table requires backfill",
          "suggestion": "Add column as nullable first, backfill, then add constraint",
          "search_for": "verified"
        }
      ],
      "summary": "Two migration safety issues found"
    }'''
    findings = skill._parse(raw)
    assert len(findings) == 2
    assert findings[0].severity == Severity.HIGH
    assert findings[1].severity == Severity.MEDIUM


def test_parse_no_findings():
    skill = _make_skill()
    raw = '{"findings": [], "summary": "Migration looks safe"}'
    findings = skill._parse(raw)
    assert len(findings) == 0
