# AutoQE: portfolio overview

**Problem.** Test generation cannot by itself establish requirement grounding,
meaningful coverage or trustworthy failure diagnosis. QE needs traceability from
intent to evidence and independent evaluation of conclusions.

**Solution and architecture.** AutoQE converts approved intent into a grounded
BehavioralContract, risk-based TestSpec, ExecutionRecord and evidence-based
TriageRecord. A ProjectAdapter contains target behavior; Playwright and httpx
execute bounded semantics. No arbitrary executable test code is generated.

**Differentiators.** Frozen typed handoffs; replay-reproducible AI-stage outputs;
explicit unknown/unavailable states; observational metrics; external expected
labels separated from runtime decisions.

**Technologies.** Python 3.13, Pydantic, pytest, Playwright, httpx, GitHub Actions,
JSON artifacts and Node/Yarn for the reference application. AgentGuard uses a
separate pinned repository/interpreter, not an AutoQE dependency.

**Demonstrated results.** Healthy UI/API/BOTH: three consecutive passes each.
Three isolated product faults detected, no faulty passes. M5: 0/3 healthy false
positives, 8/8 labeled triage agreement, 11/11 artifact completion, including two
synthetic triage-only cases. M6: eight independent classification passes, zero
failures/errors/incomplete results; positive control passes, negative fails.
Qualification used zero live model calls. M7's local fresh-checkout suite passed
372 tests. These small populations do not establish production-scale effectiveness.

**AgentGuard relationship.** AutoQE asks whether AI-enabled orchestration can do
useful QE work. AgentGuard asks whether an AI/agent system behaves correctly and
reliably. Their implemented joint evaluation measures triage-classification
agreement only—not all planning, reasoning or rationale quality.

**Engineering principles.** Put changes in the correct architectural layer;
prefer general contracts over case patches. Evaluate false positives/negatives,
determinism, evidence, regression risk and maintainability. Preserve independent
labels and runtime-only credentials.

**Limits/v2.** One reference app and bounded vocabulary; replay-qualified AI stages.
Live-model production qualification, richer semantics, RAG/MCP/multi-agent systems,
visual/accessibility/performance/security adapters and enterprise integrations
remain deferred.

**30-second recruiter description.** “I built AutoQE to connect requirements to
risk-based tests, structured execution evidence and explainable failure triage.
It orchestrates existing UI/API tools through typed contracts instead of generating
arbitrary code. I qualified it against a pinned reference app with controlled
defects, added independent classification evaluation through AgentGuard, and made
the deterministic pipeline reproducible in CI.”

**Two-minute hiring-manager description.** “The interesting problem was preserving
intent and evidence across the QE lifecycle. I used a frozen artifact chain and
vendor-neutral TestSpec so planning cannot bypass execution governance.
ProjectAdapter owns target setup, reset and capabilities; providers normalize
UI/API observations. Triage classifies only what evidence supports, while metrics
distinguish missing data from real zeroes. I evaluated healthy runs and isolated
regressions without leaking fault identities into runtime decisions. AgentGuard
independently checked classification agreement in a separate pinned environment.
The results are intentionally narrow: three product faults, eight labeled
evaluations, no live-model qualification. That boundary is part of the engineering
story—reproducible evidence before broader autonomy. The demo makes every handoff
inspectable, including unresolved observations and limitations. CI protects the
contracts and package boundaries. Expanding targets or autonomy should preserve
those controls and be supported by new evidence, rather than inferred from the
success of a small reference population.”

[Demo](DEMO_GUIDE.md) · [architecture](ARCHITECTURE.md) ·
[artifacts](../examples/demo/README.md) · [release readiness](RELEASE_READINESS.md)
