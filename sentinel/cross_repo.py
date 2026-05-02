"""Cross-repo checkout utility.

Clones external repos (shallow) so skills can grep across repo boundaries.
This is an opt-in capability configured per-skill in sentinel.yml.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile


def _write_askpass_script(workspace: str) -> str:
    """Write a GIT_ASKPASS script that reads the token from an env var.

    The script echoes $SENTINEL_GIT_TOKEN so the token is never written
    to disk — only passed via the subprocess environment.
    """
    script_path = os.path.join(workspace, ".git-askpass.sh")
    with open(script_path, "w") as f:
        f.write('#!/bin/sh\nprintf \'%s\' "$SENTINEL_GIT_TOKEN"\n')
    os.chmod(script_path, stat.S_IRWXU)
    return script_path


def checkout_repos(repos: list[str], token: str = "", workspace: str = "") -> list[tuple[str, str]]:
    """Clone repos (shallow, depth=1) and return (local_path, repo_name) pairs.

    Uses GIT_ASKPASS to pass credentials so tokens don't leak into
    process arguments, git config, or logs.

    Args:
        repos: list of "owner/repo" strings
        token: GitHub token for private repos (PAT or GitHub App token)
        workspace: parent directory for clones; uses a temp dir if empty

    Returns:
        list of (local_path, repo_name) tuples
    """
    if not workspace:
        workspace = tempfile.mkdtemp(prefix="sentinel-xrepo-")

    askpass_script = ""
    if token:
        askpass_script = _write_askpass_script(workspace)

    results: list[tuple[str, str]] = []
    try:
        for repo in repos:
            repo_dir = os.path.join(workspace, repo.replace("/", "_"))
            if os.path.isdir(repo_dir):
                results.append((repo_dir, repo))
                continue

            url = f"https://x-access-token@github.com/{repo}.git"

            env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
            if askpass_script:
                env["GIT_ASKPASS"] = askpass_script
                env["SENTINEL_GIT_TOKEN"] = token

            result = subprocess.run(
                ["git", "clone", "--depth", "1", "--single-branch", url, repo_dir],
                capture_output=True, text=True, env=env,
            )
            if result.returncode == 0:
                results.append((repo_dir, repo))
            else:
                print(f"sentinel: warning: failed to clone {repo}: {result.stderr.strip()}")
    finally:
        if askpass_script and os.path.exists(askpass_script):
            os.remove(askpass_script)

    return results


def cleanup_repos(paths: list[str]) -> None:
    """Remove cloned repo directories."""
    for path in paths:
        shutil.rmtree(path, ignore_errors=True)
