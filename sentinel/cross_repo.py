"""Cross-repo checkout utility.

Clones external repos (shallow) so skills can grep across repo boundaries.
This is an opt-in capability configured per-skill in sentinel.yml.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile


def checkout_repos(repos: list[str], token: str = "", workspace: str = "") -> list[str]:
    """Clone repos (shallow, depth=1) and return local paths.

    Args:
        repos: list of "owner/repo" strings
        token: GitHub token for private repos (PAT or GitHub App token)
        workspace: parent directory for clones; uses a temp dir if empty

    Returns:
        list of local paths to cloned repos
    """
    if not workspace:
        workspace = tempfile.mkdtemp(prefix="sentinel-xrepo-")

    paths = []
    for repo in repos:
        repo_dir = os.path.join(workspace, repo.replace("/", "_"))
        if os.path.isdir(repo_dir):
            paths.append(repo_dir)
            continue

        if token:
            url = f"https://x-access-token:{token}@github.com/{repo}.git"
        else:
            url = f"https://github.com/{repo}.git"

        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--single-branch", url, repo_dir],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            paths.append(repo_dir)
        else:
            print(f"sentinel: warning: failed to clone {repo}: {result.stderr.strip()}")

    return paths


def cleanup_repos(paths: list[str]) -> None:
    """Remove cloned repo directories."""
    for path in paths:
        shutil.rmtree(path, ignore_errors=True)
