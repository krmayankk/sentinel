"""Tests for the grep verification pipeline in sentinel.skills.base."""
import os
import tempfile

from sentinel.core import Finding, Severity
from sentinel.skills.base import _verify, _changed_files, _grep


def test_changed_files_extraction():
    diff = """diff --git a/terraform/modules/rds/variables.tf b/terraform/modules/rds/variables.tf
index abc..def 100644
--- a/terraform/modules/rds/variables.tf
+++ b/terraform/modules/rds/variables.tf
@@ -1,5 +1,3 @@
-variable "enable_performance_insights" {
-  type = bool
-}
 variable "instance_class" {
   type = string
 }
diff --git a/sentinel/core.py b/sentinel/core.py
index 123..456 100644
"""
    changed = _changed_files(diff)
    assert "terraform/modules/rds/variables.tf" in changed
    assert "sentinel/core.py" in changed
    assert len(changed) == 2


def test_grep_finds_term():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "main.tf"), "w") as f:
            f.write('enable_performance_insights = true\n')
        matches = _grep("enable_performance_insights", d)
        assert len(matches) == 1
        assert "main.tf" in matches[0]


def test_grep_excludes_changed_files():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "variables.tf"), "w") as f:
            f.write('variable "enable_performance_insights" {}\n')
        matches = _grep("enable_performance_insights", d, exclude_files={"variables.tf"})
        assert len(matches) == 0


def test_grep_no_matches():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "main.tf"), "w") as f:
            f.write('instance_class = "db.t3.medium"\n')
        matches = _grep("enable_performance_insights", d)
        assert len(matches) == 0


def test_verify_confirms_finding():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "caller.tf"), "w") as f:
            f.write('enable_perf = true\n')

        finding = Finding(
            skill="test",
            severity=Severity.MEDIUM,
            title="Missing caller update",
            message="Variable removed but callers not updated",
            suggestion="Update callers",
            search_for="enable_perf",
        )
        verified = _verify([finding], "test", d)
        assert len(verified) == 1
        assert "Confirmed" in verified[0].message
        assert verified[0].severity == Severity.HIGH  # elevated


def test_verify_dismisses_when_no_callers():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "clean.tf"), "w") as f:
            f.write('instance_class = "db.t3.medium"\n')

        finding = Finding(
            skill="test",
            severity=Severity.HIGH,
            title="Suspected missing caller",
            message="Variable might have callers",
            suggestion="Check callers",
            search_for="enable_perf",
        )
        verified = _verify([finding], "test", d)
        assert len(verified) == 1  # kept — finding may be about absence
        assert "Confirmed" not in verified[0].message  # but not elevated


def test_verify_passes_through_no_search_term():
    finding = Finding(
        skill="test",
        severity=Severity.LOW,
        title="Style issue",
        message="Minor inconsistency",
        suggestion="Fix it",
        search_for="",  # no search term
    )
    with tempfile.TemporaryDirectory() as d:
        verified = _verify([finding], "test", d)
        assert len(verified) == 1
        assert verified[0].severity == Severity.LOW  # unchanged


def test_verify_with_extra_search_paths():
    """Cross-repo search: finding confirmed via extra search paths."""
    with tempfile.TemporaryDirectory() as main_repo:
        with tempfile.TemporaryDirectory() as extra_repo:
            # Main repo has no matches
            with open(os.path.join(main_repo, "main.tf"), "w") as f:
                f.write('instance_class = "db.t3.medium"\n')
            # Extra repo has the caller
            with open(os.path.join(extra_repo, "consumer.tf"), "w") as f:
                f.write('enable_perf = true\n')

            finding = Finding(
                skill="test",
                severity=Severity.MEDIUM,
                title="Cross-repo caller",
                message="Variable removed but callers in other repos not updated",
                suggestion="Update callers",
                search_for="enable_perf",
            )
            verified = _verify(
                [finding], "test", main_repo,
                extra_search_paths=[extra_repo],
            )
            assert len(verified) == 1
            assert "Confirmed" in verified[0].message
            assert verified[0].severity == Severity.HIGH  # elevated


def test_verify_kept_without_elevation_when_no_matches_with_extra_paths():
    """If neither main nor extra repos have callers, finding is kept but not elevated."""
    with tempfile.TemporaryDirectory() as main_repo:
        with tempfile.TemporaryDirectory() as extra_repo:
            with open(os.path.join(main_repo, "clean.tf"), "w") as f:
                f.write('instance_class = "db.t3.medium"\n')
            with open(os.path.join(extra_repo, "also_clean.tf"), "w") as f:
                f.write('instance_class = "db.t3.large"\n')

            finding = Finding(
                skill="test",
                severity=Severity.MEDIUM,
                title="Suspected cross-repo issue",
                message="Might have callers somewhere",
                suggestion="Check callers",
                search_for="enable_perf",
            )
            verified = _verify(
                [finding], "test", main_repo,
                extra_search_paths=[extra_repo],
            )
            assert len(verified) == 1  # kept
            assert "Confirmed" not in verified[0].message
            assert verified[0].severity == Severity.MEDIUM  # not elevated
