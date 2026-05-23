"""Eval harness for sentinel skills.

Two layers:
- scorer: deterministic, pattern-matching, no LLM in the scoring path
- runner: loads fixtures, drives skill execution, hands findings to scorer

The LLM judge (Layer 2 from PLAN.md v0.4) is a follow-up, not in this slice.
"""
