from __future__ import annotations

import re

# Files that add tokens without adding signal: generated, locked, vendored.
_NOISE_PATTERNS = [
    r"package-lock\.json",
    r"yarn\.lock",
    r"poetry\.lock",
    r"Pipfile\.lock",
    r"go\.sum",
    r"Cargo\.lock",
    r"\.terraform\.lock\.hcl",
    r"^dist/",
    r"^vendor/",
    r"^generated/",
    r"\.pb\.go$",
    r"\.pb\.py$",
    r"_pb2\.py$",
    r"_generated\.",
]

_NOISE_RE = re.compile("|".join(_NOISE_PATTERNS))
_DIFF_FILE_HEADER = re.compile(r"^diff --git a/.+ b/(.+)$", re.MULTILINE)


def filter_noise(diff: str) -> str:
    """Remove generated and lock files — they add tokens, not signal."""
    blocks = _split_file_blocks(diff)
    return "\n".join(b for b in blocks if not _is_noise(_filename(b)))


def truncate_diff(diff: str, max_chars: int = 80_000) -> str:
    """Hard truncate with a clear marker so the LLM knows the diff is partial."""
    if len(diff) <= max_chars:
        return diff
    return diff[:max_chars] + "\n\n[diff truncated — showing first 80,000 characters]"


def _split_file_blocks(diff: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for line in diff.splitlines(keepends=True):
        if line.startswith("diff --git") and current:
            blocks.append("".join(current))
            current = []
        current.append(line)
    if current:
        blocks.append("".join(current))
    return blocks


def _filename(block: str) -> str:
    m = _DIFF_FILE_HEADER.search(block)
    return m.group(1) if m else ""


def _is_noise(filename: str) -> bool:
    return bool(_NOISE_RE.search(filename))
