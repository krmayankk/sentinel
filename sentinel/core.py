from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Finding:
    skill: str
    severity: Severity
    title: str
    message: str
    suggestion: str
    file: str = ""
    line: int = 0
    search_for: str = ""   # term to grep for in the repo; empty means no verification needed


@dataclass
class Context:
    repo: str        # "owner/repo"
    pr_number: int
    claude_md: str = ""                         # contents of CLAUDE.md if present
    config: dict = field(default_factory=dict)  # sentinel.yml contents
    repo_path: str = ""                         # local path to repo root; enables codebase search


class Skill(abc.ABC):
    """Base class for all sentinel skills.

    A skill takes a diff and context, reasons via LLM, and returns findings.
    It has no side effects — posting findings is the caller's responsibility.
    """

    name: str

    @abc.abstractmethod
    def run(self, diff: str, context: Context) -> list[Finding]:
        ...
