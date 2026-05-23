"""Deterministic scoring for sentinel evals.

Scores actual findings against an expected.json. No LLM is invoked here —
same findings + same expected always produce the same score.

Schema for expected.json:

    {
      "must_find": [
        {
          "skill": "change_completeness",      # required: skill that must produce this
          "severity_min": "high",              # required: minimum severity (low|medium|high|critical)
          "match_any": ["caller", "module"],   # optional: at least one substring must appear in
                                               #   title + message + suggestion + file (case-insensitive)
          "file_contains": ["envs/prod"],      # optional: at least one substring must appear in
                                               #   the `file` field specifically (location grading)
          "title_contains": [...],             # alias for match_any (back-compat)
          "rationale": "free text"             # ignored by scorer; documentation for humans
        }
      ],
      "must_not_find": [ ... same shape ... ],
      "verdict": "incomplete" | "complete"
    }

A must_find passes when ALL its constraints pass for at least one actual finding.
A must_not_find FAILS the fixture if any actual finding satisfies all its constraints
(it's a false positive that should not appear).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sentinel.core import Finding, Severity

# Ordered severity for threshold comparison.
SEVERITY_ORDER: dict[str, int] = {
    Severity.LOW.value: 0,
    Severity.MEDIUM.value: 1,
    Severity.HIGH.value: 2,
    Severity.CRITICAL.value: 3,
}

# Severities at or above this threshold cause the derived verdict to be "incomplete".
# Matches the conventional fail_on default of [critical, high].
VERDICT_BLOCKING_THRESHOLD = SEVERITY_ORDER[Severity.HIGH.value]


@dataclass
class MustFindResult:
    """Result of checking one must_find entry against the produced findings."""
    expected: dict
    matched: Optional[Finding]  # the first finding that satisfied this must_find, if any

    @property
    def passed(self) -> bool:
        return self.matched is not None


@dataclass
class MustNotFindResult:
    """Result of checking one must_not_find entry."""
    expected: dict
    violating: Optional[Finding]  # a finding that improperly matched (a false positive)

    @property
    def passed(self) -> bool:
        return self.violating is None


@dataclass
class FixtureScore:
    """Aggregate score for one fixture."""
    fixture: str
    findings: list[Finding]
    must_find: list[MustFindResult] = field(default_factory=list)
    must_not_find: list[MustNotFindResult] = field(default_factory=list)
    expected_verdict: str = ""
    actual_verdict: str = ""

    @property
    def verdict_match(self) -> bool:
        return self.expected_verdict == self.actual_verdict

    @property
    def passed(self) -> bool:
        if any(not r.passed for r in self.must_find):
            return False
        if any(not r.passed for r in self.must_not_find):
            return False
        if not self.verdict_match:
            return False
        return True


def matches(expectation: dict, finding: Finding) -> bool:
    """Check whether a single finding satisfies an expected entry.

    Used for both must_find (a passing match) and must_not_find (a violating match).
    All constraints are AND'd. Substring checks are case-insensitive and use any-of semantics.
    """
    expected_skill = expectation.get("skill")
    if expected_skill and finding.skill != expected_skill:
        return False

    severity_min = expectation.get("severity_min")
    if severity_min:
        if severity_min not in SEVERITY_ORDER:
            raise ValueError(f"unknown severity_min: {severity_min!r}")
        if SEVERITY_ORDER[finding.severity.value] < SEVERITY_ORDER[severity_min]:
            return False

    # match_any (canonical) | title_contains (back-compat alias):
    # at least one substring must appear in the combined text of the finding.
    needles = expectation.get("match_any") or expectation.get("title_contains") or []
    if needles:
        haystack = " ".join([
            finding.title,
            finding.message,
            finding.suggestion,
            finding.file,
        ]).lower()
        if not any(needle.lower() in haystack for needle in needles):
            return False

    # file_contains: at least one substring must appear in the file path specifically.
    file_needles = expectation.get("file_contains") or []
    if file_needles:
        file_lower = finding.file.lower()
        if not any(needle.lower() in file_lower for needle in file_needles):
            return False

    return True


def derive_verdict(findings: list[Finding]) -> str:
    """A fixture is 'incomplete' if any finding is HIGH or CRITICAL, else 'complete'."""
    for f in findings:
        if SEVERITY_ORDER[f.severity.value] >= VERDICT_BLOCKING_THRESHOLD:
            return "incomplete"
    return "complete"


def score_fixture(name: str, expected: dict, findings: list[Finding]) -> FixtureScore:
    """Score a fixture by comparing produced findings to expected.json."""
    must_find_results: list[MustFindResult] = []
    for mf in expected.get("must_find", []):
        match = next((f for f in findings if matches(mf, f)), None)
        must_find_results.append(MustFindResult(expected=mf, matched=match))

    must_not_find_results: list[MustNotFindResult] = []
    for mnf in expected.get("must_not_find", []):
        violator = next((f for f in findings if matches(mnf, f)), None)
        must_not_find_results.append(MustNotFindResult(expected=mnf, violating=violator))

    expected_verdict = expected.get("verdict", "complete")
    actual_verdict = derive_verdict(findings)

    return FixtureScore(
        fixture=name,
        findings=list(findings),
        must_find=must_find_results,
        must_not_find=must_not_find_results,
        expected_verdict=expected_verdict,
        actual_verdict=actual_verdict,
    )


@dataclass
class Aggregate:
    """Aggregate metrics across all fixtures."""
    total: int
    passed: int
    must_find_total: int
    must_find_hit: int
    must_not_find_total: int
    must_not_find_clean: int
    verdict_match: int

    @property
    def recall(self) -> float:
        return self.must_find_hit / self.must_find_total if self.must_find_total else 1.0

    @property
    def precision(self) -> float:
        # In this layer, "precision" approximates: of the cases where we could
        # produce a false positive, how often did we stay clean?
        return (
            self.must_not_find_clean / self.must_not_find_total
            if self.must_not_find_total
            else 1.0
        )


def aggregate(scores: list[FixtureScore]) -> Aggregate:
    mf_total = sum(len(s.must_find) for s in scores)
    mf_hit = sum(sum(1 for r in s.must_find if r.passed) for s in scores)
    mnf_total = sum(len(s.must_not_find) for s in scores)
    mnf_clean = sum(sum(1 for r in s.must_not_find if r.passed) for s in scores)
    return Aggregate(
        total=len(scores),
        passed=sum(1 for s in scores if s.passed),
        must_find_total=mf_total,
        must_find_hit=mf_hit,
        must_not_find_total=mnf_total,
        must_not_find_clean=mnf_clean,
        verdict_match=sum(1 for s in scores if s.verdict_match),
    )
