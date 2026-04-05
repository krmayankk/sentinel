# Evals

Fixtures for measuring sentinel's review quality. Each fixture is a realistic scenario derived from the class of change that causes real incidents.

The eval harness (v0.5) will run these automatically in CI. Adding fixtures here from day one means when the harness ships, it has a corpus to run against.

## Adding a fixture

```
evals/fixtures/<scenario-name>/
    diff.patch      — the git diff sentinel will review
    context.json    — repo, pr_number, claude_md, and a description of the scenario
    expected.json   — what sentinel must find, must not find, and the expected verdict
```

`expected.json` schema:

```json
{
  "must_find": [
    {
      "skill": "change_completeness",
      "severity_min": "high",
      "title_contains": ["keyword1", "keyword2"],
      "rationale": "why this finding must be present"
    }
  ],
  "must_not_find": [
    {
      "rationale": "why a specific false positive must not appear"
    }
  ],
  "verdict": "incomplete | complete"
}
```

## Current fixtures

| Fixture | Scenario | Skills |
|---|---|---|
| `terraform_variable_removed` | Terraform module variable removed; callers not updated | change_completeness |
