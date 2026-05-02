"""Tests for cross-repo checkout and tool integration."""
import os
import subprocess
import tempfile

from unittest.mock import patch

from sentinel.cross_repo import checkout_repos, cleanup_repos
from sentinel.skills.base import tool_grep, tool_read_file, tool_list_files


# -- checkout_repos unit tests (no real clones) --

def test_checkout_repos_clones_to_workspace():
    """checkout_repos calls git clone and returns paths for successful clones."""
    with tempfile.TemporaryDirectory() as workspace:
        # Mock git clone to just create the directory with a file
        def fake_clone(args, **kwargs):
            repo_dir = args[-1]
            os.makedirs(repo_dir, exist_ok=True)
            with open(os.path.join(repo_dir, "main.py"), "w") as f:
                f.write("print('hello')\n")
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch("sentinel.cross_repo.subprocess.run", side_effect=fake_clone):
            paths = checkout_repos(["org/repo-a", "org/repo-b"], workspace=workspace)

        assert len(paths) == 2
        assert all(os.path.isdir(p) for p, _ in paths)
        assert paths[0][1] == "org/repo-a"
        assert paths[1][1] == "org/repo-b"


def test_checkout_repos_skips_failed_clone():
    """Failed clones are skipped with a warning, not a crash."""
    with tempfile.TemporaryDirectory() as workspace:
        def fake_fail(args, **kwargs):
            return subprocess.CompletedProcess(args, 128, "", "fatal: repo not found")

        with patch("sentinel.cross_repo.subprocess.run", side_effect=fake_fail):
            paths = checkout_repos(["org/nonexistent"], workspace=workspace)

        assert paths == []


def test_checkout_repos_reuses_existing_dir():
    """If the repo dir already exists, it's reused without cloning."""
    with tempfile.TemporaryDirectory() as workspace:
        repo_dir = os.path.join(workspace, "org_repo-a")
        os.makedirs(repo_dir)
        with open(os.path.join(repo_dir, "existing.py"), "w") as f:
            f.write("EXISTING = True\n")

        with patch("sentinel.cross_repo.subprocess.run") as mock_run:
            paths = checkout_repos(["org/repo-a"], workspace=workspace)
            mock_run.assert_not_called()

        assert len(paths) == 1
        assert paths[0] == (repo_dir, "org/repo-a")


def test_checkout_repos_uses_askpass_for_token():
    """When token is provided, GIT_ASKPASS + env var is used instead of embedding in URL."""
    captured_env = {}
    captured_urls = []

    def capture_clone(args, **kwargs):
        captured_env.update(kwargs.get("env", {}))
        captured_urls.append(args[-2])
        repo_dir = args[-1]
        os.makedirs(repo_dir, exist_ok=True)
        return subprocess.CompletedProcess(args, 0, "", "")

    with tempfile.TemporaryDirectory() as workspace:
        with patch("sentinel.cross_repo.subprocess.run", side_effect=capture_clone):
            checkout_repos(["org/repo-a"], token="ghp_test123", workspace=workspace)

    # Token must NOT be in the clone URL
    assert "ghp_test123" not in captured_urls[0]
    # GIT_ASKPASS script must be set
    assert "GIT_ASKPASS" in captured_env
    assert captured_env["GIT_TERMINAL_PROMPT"] == "0"
    # Token passed via env var, not embedded in script
    assert captured_env["SENTINEL_GIT_TOKEN"] == "ghp_test123"


def test_cleanup_repos_removes_dirs():
    with tempfile.TemporaryDirectory() as workspace:
        d1 = os.path.join(workspace, "repo1")
        d2 = os.path.join(workspace, "repo2")
        os.makedirs(d1)
        os.makedirs(d2)
        cleanup_repos([d1, d2])
        assert not os.path.exists(d1)
        assert not os.path.exists(d2)


# -- Tool functions work across search paths (simulates cross-repo) --

def test_grep_across_local_and_cross_repo():
    """grep finds matches in both the local repo and a cross-repo checkout."""
    with tempfile.TemporaryDirectory() as local:
        with tempfile.TemporaryDirectory() as remote:
            with open(os.path.join(local, "service.py"), "w") as f:
                f.write("from shared import process_order\n")
            with open(os.path.join(remote, "shared.py"), "w") as f:
                f.write("def process_order(order_id): ...\n")

            result = tool_grep("process_order", ".", [local, remote])
            assert "service.py" in result
            assert "shared.py" in result


def test_grep_labels_cross_repo_results():
    """grep prefixes cross-repo matches with [owner/repo]."""
    with tempfile.TemporaryDirectory() as local:
        with tempfile.TemporaryDirectory() as remote:
            with open(os.path.join(local, "local.py"), "w") as f:
                f.write("compute_total(price, qty)\n")
            with open(os.path.join(remote, "consumer.py"), "w") as f:
                f.write("compute_total(price, qty, tax_rate)\n")

            labels = {remote: "org/consumer"}
            result = tool_grep("compute_total", ".", [local, remote], labels)
            # Local results have no prefix
            assert "local.py:" in result
            assert "[org/consumer] consumer.py:" in result


def test_read_file_falls_through_to_cross_repo():
    """read_file finds a file in the cross-repo path when it's not in the local repo."""
    with tempfile.TemporaryDirectory() as local:
        with tempfile.TemporaryDirectory() as remote:
            os.makedirs(os.path.join(remote, "proto"), exist_ok=True)
            with open(os.path.join(remote, "proto/order.proto"), "w") as f:
                f.write("message Order { string id = 1; }\n")

            result = tool_read_file("proto/order.proto", [local, remote])
            assert "message Order" in result


def test_read_file_labels_cross_repo_source():
    """read_file includes [from owner/repo] header for cross-repo files."""
    with tempfile.TemporaryDirectory() as local:
        with tempfile.TemporaryDirectory() as remote:
            with open(os.path.join(remote, "billing.py"), "w") as f:
                f.write("def bill(): pass\n")

            labels = {remote: "org/consumer"}
            result = tool_read_file("billing.py", [local, remote], labels)
            assert "[from org/consumer]" in result
            assert "def bill(): pass" in result


def test_list_files_merges_across_repos():
    """list_files shows entries from both local and cross-repo."""
    with tempfile.TemporaryDirectory() as local:
        with tempfile.TemporaryDirectory() as remote:
            with open(os.path.join(local, "local.py"), "w") as f:
                f.write("")
            with open(os.path.join(remote, "remote.py"), "w") as f:
                f.write("")

            result = tool_list_files(".", [local, remote])
            assert "local.py" in result
            assert "remote.py" in result


def test_list_files_labels_cross_repo_section():
    """list_files groups cross-repo entries under [owner/repo] header."""
    with tempfile.TemporaryDirectory() as local:
        with tempfile.TemporaryDirectory() as remote:
            with open(os.path.join(local, "local.py"), "w") as f:
                f.write("")
            with open(os.path.join(remote, "remote.py"), "w") as f:
                f.write("")

            labels = {remote: "org/consumer"}
            result = tool_list_files(".", [local, remote], labels)
            assert "local.py" in result
            assert "[org/consumer]" in result
            assert "remote.py" in result
