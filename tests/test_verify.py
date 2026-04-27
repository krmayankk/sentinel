"""Tests for the agentic tool functions used by LLMSkill."""
import os
import subprocess
import tempfile
from unittest.mock import patch

from sentinel.skills.base import tool_grep, tool_read_file, tool_list_files, execute_tool


def test_tool_grep_finds_term():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "main.tf"), "w") as f:
            f.write('enable_performance_insights = true\n')
        result = tool_grep("enable_performance_insights", ".", [d])
        assert "enable_performance_insights" in result
        assert "main.tf" in result


def test_tool_grep_no_matches():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "main.tf"), "w") as f:
            f.write('instance_class = "db.t3.medium"\n')
        result = tool_grep("enable_performance_insights", ".", [d])
        assert "No matches found" in result


def test_tool_grep_multiple_search_paths():
    with tempfile.TemporaryDirectory() as d1:
        with tempfile.TemporaryDirectory() as d2:
            with open(os.path.join(d1, "a.py"), "w") as f:
                f.write("import foo\n")
            with open(os.path.join(d2, "b.py"), "w") as f:
                f.write("import foo\n")
            result = tool_grep("import foo", ".", [d1, d2])
            assert "a.py" in result
            assert "b.py" in result


def test_tool_read_file():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "config.py"), "w") as f:
            f.write("SKILLS = {'completeness': True}\n")
        result = tool_read_file("config.py", [d])
        assert "SKILLS" in result


def test_tool_read_file_not_found():
    with tempfile.TemporaryDirectory() as d:
        result = tool_read_file("nonexistent.py", [d])
        assert "not found" in result.lower()


def test_tool_read_file_across_search_paths():
    with tempfile.TemporaryDirectory() as d1:
        with tempfile.TemporaryDirectory() as d2:
            with open(os.path.join(d2, "remote.py"), "w") as f:
                f.write("REMOTE = True\n")
            # File only exists in d2, not d1
            result = tool_read_file("remote.py", [d1, d2])
            assert "REMOTE" in result


def test_tool_list_files():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "foo.py"), "w") as f:
            f.write("")
        os.makedirs(os.path.join(d, "tests"))
        result = tool_list_files(".", [d])
        assert "foo.py" in result
        assert "tests/" in result


def test_tool_list_files_empty_dir():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "empty"))
        result = tool_list_files("empty", [d])
        # Empty dir has no entries
        assert "empty" in result.lower() or result.strip() == ""


def test_execute_tool_dispatch():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "hello.py"), "w") as f:
            f.write("print('hello')\n")
        result = execute_tool("grep", {"pattern": "hello", "path": "."}, [d])
        assert "hello" in result
        result = execute_tool("read_file", {"path": "hello.py"}, [d])
        assert "print" in result
        result = execute_tool("list_files", {"path": "."}, [d])
        assert "hello.py" in result


def test_execute_tool_unknown():
    result = execute_tool("delete_file", {"path": "x"}, ["/tmp"])
    assert "Unknown tool" in result


# -- Path traversal sandboxing tests --

def test_read_file_rejects_path_traversal():
    with tempfile.TemporaryDirectory() as d:
        # Create a file inside the sandbox
        with open(os.path.join(d, "safe.py"), "w") as f:
            f.write("SAFE = True\n")
        # Attempt to escape via ../
        result = tool_read_file("../../../etc/passwd", [d])
        assert "not found" in result.lower()


def test_grep_rejects_path_traversal():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "safe.py"), "w") as f:
            f.write("hello\n")
        # Attempt to grep outside the sandbox
        result = tool_grep("hello", "../../../etc", [d])
        assert "No matches found" in result


def test_list_files_rejects_path_traversal():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "subdir"))
        result = tool_list_files("../../../etc", [d])
        assert "not found" in result.lower() or "empty" in result.lower()


def test_grep_timeout_returns_message():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "file.py"), "w") as f:
            f.write("hello\n")
        with patch("sentinel.skills.base.subprocess.run",
                    side_effect=subprocess.TimeoutExpired(cmd="grep", timeout=10)):
            result = tool_grep("hello", ".", [d])
        assert "timed out" in result
