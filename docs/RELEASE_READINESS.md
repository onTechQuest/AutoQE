# v1.0.0 release readiness

**Prepared, not released.** Proposed tag: `v1.0.0`. Distribution metadata and
`autoqe.__version__` are `1.0.0`. No commit, tag, push, release, remote repository
or GitHub setting is created by M8.

## Release decisions and limits

| Item | State |
|---|---|
| Package version | 1.0.0 prepared; existing schema version 1.0 unchanged |
| Historical provenance | Original producer versions and source hashes retained |
| LICENSE | Absent; owner must choose licensing before release |
| Git remote | None configured at M8 preflight |
| Hosted CI | No GitHub Actions run occurred; local validation is not hosted proof |
| Changes | Intended M8 changes remain uncommitted for review |
| Public sharing | Bounded audit documented in PUBLIC_SHARING_REVIEW.md |
| External repositories | RWA and AgentGuard remain separate, clean and pinned |
| New capabilities | None; cleanup is opt-in operational housekeeping |

Release blockers are the owner licensing decision and the publication/hosted-CI
steps that are intentionally not authorized here. Before tagging, review and
commit the prepared changes, choose/configure the repository destination, and
obtain an actual passing hosted CI run. Those are future owner actions, not work
performed or implied by an M8 local pass.

The demo explicitly uses the approved M2 planning checkpoint. Fresh M1 extraction
has one different historical limitation string, which causes exact planning replay
matching to reject it. This existing fixture mismatch is documented, not silently
patched or presented as a continuous fresh-artifact pipeline. It is a known v1
demo limitation; resolving it would require a separately reviewed fixture change.

No live model production qualification, broad target coverage, statistical
effectiveness claim, production security assurance or comprehensive reasoning
evaluation accompanies this release.

## Suggested repository presentation

Final local M8 checks passed: 45 focused tests (23 cleanup, four demo/provenance/
version, 18 wheel checks); one complete suite of 399 tests in a fresh full local
checkout without historical reports; 39 local Markdown links; PowerShell demo
syntax; seven CLI help commands; offline extraction, approved-checkpoint planning,
static-evidence triage and synthetic metrics commands. The 1.0.0 wheel built and
validated with 48 core, eight integration and four metadata files, then passed
isolated installed-wheel imports/version checks. No generated artifacts are staged.

The bounded public-sharing/history audit and `git diff --check` passed. M0 is
unchanged. RWA remains clean at `9dfcb9869533ce8a8963c556facc0d80457f9d39` and
AgentGuard at `ee104f90fe9c0c23f320ab110fdd2c9adf20d37c`. Ports 3000/3001 have no
listeners. Live model calls: zero. No live external qualification or hosted CI
run occurred. Intended M8 changes are ready for review/commit; release remains
subject to the decisions above.

Description: **Vendor-neutral QE orchestration with grounded contracts, risk-based
TestSpecs, UI/API evidence, deterministic triage and independent evaluation.**

Topics: `quality-engineering`, `agentic-ai`, `ai-testing`, `test-automation`,
`playwright`, `llm-evaluation`, `software-testing`, `ai-quality`, `ci-cd`.
The README qualifies the AI/evaluation scope; these topics do not imply live-model
or comprehensive reasoning qualification.

Suggested release summary: “AutoQE v1 establishes a governed requirement-to-evidence
QE pipeline, qualified on a bounded pinned reference target with deterministic
replay, UI/API execution, evidence-based triage, metrics and external classification
evaluation. Includes self-contained CI and a provenance-labeled portfolio demo.”

See [changelog](../CHANGELOG.md), [architecture](ARCHITECTURE.md),
[demo](DEMO_GUIDE.md), [public-sharing review](PUBLIC_SHARING_REVIEW.md) and
[handoff](PROJECT_HANDOFF.md) for evidence and exact limits.
