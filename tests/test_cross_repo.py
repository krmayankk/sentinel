"""Tests for cross-repo checkout and tool integration."""
import os
import subprocess
import tempfile

from unittest.mock import patch

from sentinel.cross_repo import checkout_repos, cleanup_repos
from sentinel.skills.base import _tool_grep, _tool_read_file, _tool_list_files


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
        assert all(os.path.isdir(p) for p in paths)


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
        assert paths[0] == repo_dir


def test_checkout_repos_uses_token_in_url():
    """When token is provided, it's embedded in the clone URL."""
    clone_urls = []

    def capture_clone(args, **kwargs):
        clone_urls.append(args[-2])  # the URL argument (second to last, before repo_dir)
        repo_dir = args[-1]
        os.makedirs(repo_dir, exist_ok=True)
        return subprocess.CompletedProcess(args, 0, "", "")

    with tempfile.TemporaryDirectory() as workspace:
        with patch("sentinel.cross_repo.subprocess.run", side_effect=capture_clone):
            checkout_repos(["org/repo-a"], token="ghp_test123", workspace=workspace)

    assert len(clone_urls) == 1
    assert "x-access-token:ghp_test123@" in clone_urls[0]


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

            result = _tool_grep("process_order", ".", [local, remote])
            assert "service.py" in result
            assert "shared.py" in result


def test_read_file_falls_through_to_cross_repo():
    """read_file finds a file in the cross-repo path when it's not in the local repo."""
    with tempfile.TemporaryDirectory() as local:
        with tempfile.TemporaryDirectory() as remote:
            os.makedirs(os.path.join(remote, "proto"), exist_ok=True)
            with open(os.path.join(remote, "proto/order.proto"), "w") as f:
                f.write("message Order { string id = 1; }\n")

            result = _tool_read_file("proto/order.proto", [local, remote])
            assert "message Order" in result


def test_list_files_merges_across_repos():
    """list_files shows entries from both local and cross-repo."""
    with tempfile.TemporaryDirectory() as local:
        with tempfile.TemporaryDirectory() as remote:
            with open(os.path.join(local, "local.py"), "w") as f:
                f.write("")
            with open(os.path.join(remote, "remote.py"), "w") as f:
                f.write("")

            result = _tool_list_files(".", [local, remote])
            assert "local.py" in result
            assert "remote.py" in result
