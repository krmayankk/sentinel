# CLAUDE.md — guidance for working on sentinel

## Working style
- Always test on real PRs. Theory without validation is useless.
- Don't flip-flop. Think through the architecture before implementing.
- No trailing summaries after every response — the user can read diffs.
- No Co-Authored-By lines in commits.
- Be concise. Lead with the answer.

## Decision principles
- The moat is encoded judgments, not the LLM. Every skill is a vertical slice of expertise.
- Cross-repo is a capability of skills, not a separate skill.
- Framework value scales with the number of useful skills.
- Each version must be testable on a real repo with real PRs.

## Testing
- Unit tests: every PR, no API key needed, no LLM calls.
- Integration tests: merge to main only (saves API tokens).
- Eval fixtures in evals/fixtures/ — each fixture has diff.patch, context.json, expected.json, repo/.
- Always add fixtures when adding new skills.

## Architecture
- Every skill is an agentic loop. Diff is the first input. The LLM can explore the repo with tools (grep, read_file, list_files). max_turns controls the budget (0 = diff-only, 3 = light, 10 = deep).
- New skills subclass LLMSkill and implement _build_prompt().
- sentinel.yml controls what runs. CLAUDE.md teaches skills what to look for.
- Four customization layers: org config → CLAUDE.md → sentinel.yml → .sentinel/skills/

## Repository structure
- sentinel/skills/*.py — built-in skills
- sentinel/runner.py — multi-skill runner
- sentinel/config.py — sentinel.yml parsing
- entrypoint.py — CLI and GHA entrypoint
- evals/fixtures/ — eval fixtures for integration tests
- tests/ — unit tests
