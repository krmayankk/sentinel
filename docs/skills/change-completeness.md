# ChangeCompletenessSkill

Catches changes that are internally consistent but break dependents elsewhere — the class of problem that compilers miss, linters miss, and code review misses when the reviewer is unfamiliar with every consumer of what changed.

## What it catches

### Config and infrastructure drift
Terraform, Helm, Kubernetes, and similar tools have no compiler. A variable removed from a module, a key renamed in a ConfigMap, a required value dropped from a Helm chart — none of these produce a build failure. They fail silently at apply time, often in production.

```
# PR changes this:
variable "enable_performance_insights" { ... }   # removed

# These callers are not in the diff. They will break on next terraform apply:
module "rds" {
  enable_performance_insights = true   # 'An argument named ... is not expected here'
}
```

### Runtime errors in interpreted languages
Python, JavaScript, Ruby, and similar languages have no compile step. A renamed dataclass field, a removed function argument, a changed return type — these only surface at runtime. By then they are in production.

```
# PR renames this field in models.py:
- db_url: str = ""
+ database_url: str = ""

# These callers are not in the diff. They will raise AttributeError at runtime:
config = AppConfig(db_url=load_config())   # TypeError on construction
config.db_url                              # AttributeError on access
```

### Schema and contract changes
Proto/Thrift/Avro schema changes, OpenAPI spec changes, database column renames — all require updating generated code and consumers. Forgetting one breaks the contract silently.

### Operational gaps
New services and deployments added without the supporting artifacts they require: runbooks, alert rules, dashboard configs, secret store references.

## What it does not catch

**Compiled language breakage** — Go, Java, Rust, C#, Swift. The compiler already catches these. Sentinel adds no value here and will not waste tokens on it.

**Semantic correctness** — whether the logic of a change is right. That requires understanding intent, which is the domain of human review.

**Things already covered by existing tools** — secret scanning (Gitleaks), dependency CVEs (Dependabot), known misconfigurations (Checkov, tfsec). Sentinel does not duplicate these.

## How it works

Two steps:

1. **LLM analysis** — the diff is sent to Claude with a structured prompt. The model identifies what changed, reasons about what typically depends on it, and returns candidate findings with a `search_for` term for each.

2. **Codebase verification** — for each candidate finding, sentinel greps the actual repository for the search term. Findings confirmed by real matches are reported. Findings with no matches are dismissed — the LLM suspected a problem but the codebase search confirms it is clean.

This eliminates speculation. A finding is only reported when broken callers are confirmed to exist, with their exact file paths and line numbers.

## Extending coverage with CLAUDE.md

The skill's built-in prompt covers universal patterns. Team-specific conventions require `CLAUDE.md`. Add a section to your repo's `CLAUDE.md`:

```markdown
## Completeness rules
- When a Terraform module variable changes, all callers under terraform/envs/ must be updated
- When a new GHA action input is added, it must be forwarded in runs.steps.env and read in the entrypoint
- When a proto file changes, the generated code in gen/ must be regenerated and included
- When a new required env var is added, k8s/configmaps/ and .env.example must reference it
```

Sentinel reads this and applies your rules on every PR — enforcing team conventions that no generic tool knows about.

## Cross-repo completeness (future)

The current implementation searches within a single repository. Many real-world completeness gaps span repositories: a shared library changes its interface and consumers in downstream repos break.

Configure cross-repo context in `sentinel.yml`:

```yaml
context:
  external_repos:
    - repo: my-org/platform-standards
      path: docs/api-contracts/
    - repo: my-org/shared-terraform-modules
      path: modules/
```

Sentinel will check out the referenced paths and include them in the codebase search. A change to a shared Terraform module in one repo can be verified against its consumers in another.

This is the same two-step approach — LLM identifies the search term, grep confirms callers — extended across repository boundaries.

## Fixture

`evals/fixtures/terraform_variable_removed/` — a Terraform module variable is removed. Three environment callers (`prod`, `staging`, `dev`) still pass the removed argument. Sentinel must identify the callers and report a HIGH finding.

To run:
```bash
sentinel review \
  --diff evals/fixtures/terraform_variable_removed/diff.patch \
  --repo-path evals/fixtures/terraform_variable_removed/repo
```
