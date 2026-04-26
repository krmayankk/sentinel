When a new built-in skill is added under sentinel/skills/ (a new Python file
that defines a class extending LLMSkill), check that:

1. The skill is registered in sentinel/runner.py in the _BUILTIN_SKILLS dict
2. A corresponding test file exists under tests/ (e.g. test_<skill_name>.py)
3. An eval fixture exists under evals/fixtures/ with diff.patch, expected.json, and context.json

A new skill file without all three is incomplete and will cause confusion
for contributors.

Severity: high if registration in _BUILTIN_SKILLS is missing (skill won't run).
Severity: medium if tests or eval fixtures are missing.
