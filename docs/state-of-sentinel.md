# State of Sentinel (2026-05-30)

A snapshot of where this project stands relative to the state of the art in AI eval and autonomous code review, and an honest read on what it would take to make this Distinguished-Engineer-level work people would want to adopt.

Audience: anyone evaluating sentinel as a framework, contributing to it, or considering the same design choices in their own AI system.

---

## What sentinel is, in one paragraph

Sentinel is an AI agent framework whose unit of work is a **skill** — a vertical slice of judgment over a code change. Skills are agentic loops: they receive a diff, explore the surrounding code with read-only tools (grep, read_file, list_files), and return typed findings. The framework ships with skills for change completeness, GitHub Actions security, and migration safety, plus a CLAUDE.md mechanism for teaching skills your team's conventions in plain English. Triggers (pull_request, push, merge_group, schedule, agent_commit) are decoupled from skills — the same judgment runs whether a human opened the PR or an agent did. Every prompt change is gated by a deterministic eval harness (`sentinel eval run`) that grades skill output against frozen fixtures, so prompt regressions break the build.

---

## How the eval approach compares to state of the art

**The pattern is industry-standard, not novel.** Two-layer evals — a cheap deterministic regression net plus an LLM judge graded against humans — is what Braintrust, Langfuse, Humanloop, OpenAI evals, and Promptfoo all converge on. The "different model family for the judge" rule is also standard practice. Sentinel implements Layer 1 well; Layer 2 is not yet built.

**Where the design is differentiated:**

- **Telemetry → fixture proposal pipeline (v0.5, planned).** Most teams say they want this loop; few publish one. If sentinel ships it, it'll be ahead of most public examples.
- **Skill as the unit of customization.** Most code-review bots are monolithic prompts. Sentinel's four-layer customization surface — org config → CLAUDE.md → sentinel.yml → custom skills — is genuinely uncommon thinking.
- **Trigger decoupling as an architectural commitment.** Everyone says "agents not just PRs"; sentinel actually has the table that says the same skill code runs across all five triggers.

**Where it's at risk of feeling obsolete:**

- The PR-review space is crowded: Greptile, CodeRabbit, Bito, Korbit, Cursor's review, Graphite Diamond, GitHub's own Copilot review. Most have funded teams and polished UI.
- As models improve, "just give the diff to the model and ask 'safe to merge?'" competes with the skill abstraction. The defense is that skills encode *team-specific* judgment no general model can know (CLAUDE.md is the moat), but that defense has to be earned by adoption, not asserted.
- The fixture corpus is 4 today. The "ships with evals" credibility holds only if it grows to where regressions actually surface.

---

## Distinguished-Engineer read

The **thinking** is DE-level. The **implementation** is strong senior+.

What a reviewer who knows this space would note:

| | |
|---|---|
| ✅ Architectural reasoning | Skills, layered customization, trigger decoupling, two-layer evals — these are the kinds of design decompositions a DE produces, not just clean code. |
| ✅ Honest documentation | `docs/evals.md` arguing *why* deterministic, *why* `match_any` not `title_contains` — that's senior-staff judgment legible to a reviewer. |
| ✅ Dogfooding | The repo reviews itself. Sentinel's own self-review caught the security gap that PR #15 then fixed. Hard to fake. |
| ⚠️ Adoption | Zero outside users yet. DE-level is partly "did anyone other than the author find it useful?" |
| ⚠️ Production reliability data | Absent until v0.5 telemetry ships. |

**As an interview artifact: yes.** The design choices — skill abstraction, two-layer evals, BYO telemetry storage for trust, the deliberate decision not to grade on title keywords — are exactly what hiring committees probe for, and each one is defensible with a *why*.

---

## What it will take to survive 1–2 years of autonomous agentic work

The architecture has the right bones for the autonomous era:

- **Skills are portable across model generations.** Better models make skills more valuable, not less, because the value is the encoded judgment, not the model call.
- **Git is the interface.** No proprietary state, no lock-in. Every output is a finding, a comment, or a PR.
- **BYO telemetry storage.** Teams own their data. This is the trust posture that lets outsiders adopt without giving up control.
- **Trigger decoupling.** Adding `agent_commit` as a first-class trigger does not require re-architecting skills.

The gaps to close before "fully autonomous repo" works:

1. **Explicit autonomous-merge milestone.** The trigger table acknowledges `agent_commit`, but there is no milestone that says "tests pass + sentinel passes → auto-merge, sentinel blocks → file a bug or open an autofix branch." This is a decision the framework has to take, not leave to the operator.
2. **What happens when sentinel blocks an autonomous commit.** Three options exist: page a human, file a tracking issue with the finding attached, or hand the finding to the auto-fix loop (v0.6). The framework needs an explicit policy, not an ambiguous one.
3. **Eval corpus growth.** Autonomous gating only works if the regression net is wide enough. 15+ fixtures by end of v0.4, then production-fed growth in v0.5.

---

## Will sentinel succeed as an OSS project

Technically: yes. The architecture will hold for years.

Commercially / as an adopted framework: depends on three things sentinel does not have yet:

1. **A "wow" demo PR.** One real bug a real human missed, sentinel caught, with the receipt. One viral case study moves more adoption than any architectural argument.
2. **5-minute onboarding.** The README quickstart is good; needs to survive an actual stranger trying it in front of you.
3. **One outside adopter.** Your other repos are credibility; someone *else's* repo is legitimacy. v0.5 BYO telemetry is the trust-unlock for that.

The v0.4 → v0.5 ordering is correct: measure first, then learn from production. Resist jumping to v0.6 (auto-fix) before v0.5 produces real data. That ordering is what separates a DE-level execution from "interesting prototype."

---

## Pivot (2026-06): sentinel evolves through a real autonomous workload

Sentinel's PR-review surface is feature-complete enough. Further investment in skills, fixtures, and the LLM judge layer has diminishing returns *without a real downstream consumer*. The pivot:

- **Sentinel is now driven by a separate project** — a fully autonomous inference service (agents commit code, sentinel gates, the cluster manages itself). That repo lives elsewhere; this one stays focused.
- **Primary milestones shift** to v0.5 (telemetry from real usage), v0.6 (auto-fix), v0.7 (operational agent for drift / incidents), and v0.7.5 (autonomous merge gate). The PR-review polish is in maintenance mode.
- **v0.8 (skill authoring CLI) and v1.0 (general framework) wait.** They serve OSS adopters that don't exist yet. Adoption follows a real case study, not the other way around.
- **Sentinel does not become the orchestrator.** It stays the *Reviewer* (and eventually the *Operator*) inside a fleet — see Non-goals in `PLAN.md`.

This is what makes sentinel **earn** its relevance instead of just claim it. The framework was good enough to support a real use case six months in; the discipline now is to let that use case shape what ships next.
