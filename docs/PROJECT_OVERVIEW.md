# AutoQE project overview

## Purpose and problem

AutoQE connects product intent to risk-based tests, structured evidence and
failure triage. Test generation alone cannot establish requirement grounding,
meaningful coverage or trustworthy diagnosis. Each QE handoff needs an inspectable
contract and conclusions need independent evaluation.

## Solution and architecture

Approved requirements become a grounded BehavioralContract, a vendor-neutral
TestSpec, an ExecutionRecord and an evidence-based TriageRecord. ProjectAdapter
contains target-specific behavior; Playwright and httpx execute bounded semantic
actions. AutoQE orchestrates these technologies without generating arbitrary
executable test code.

## Key design decisions

- Frozen typed artifacts separate planning from execution governance.
- Replay reproduces approved AI-stage outputs without live model variability.
- Explicit UNKNOWN and unavailable states preserve uncertainty and missing evidence.
- Metrics observe outcomes without feeding back into execution.
- Independent labels and external evaluation remain separate from runtime decisions.

Changes belong in the appropriate architectural layer. Evaluation considers false
positives and negatives, determinism, evidence, regression risk and maintainability.

## Technologies

Python 3.13, Pydantic, pytest, Playwright, httpx, JSON artifacts and GitHub Actions.
Node/Yarn support the isolated reference application. AgentGuard uses a separate
pinned repository and interpreter, not an AutoQE package dependency.

## Demonstrated qualification

Healthy UI/API/BOTH scenarios each passed three consecutive runs. Three isolated
product faults were detected with no faulty passes. M5 reported 0/3 healthy false
positives, 8/8 labeled triage agreement and 11/11 artifact completion; two cases
were synthetic triage-only inputs. M6 reported eight classification passes, no
failures/errors/incomplete results, a passing positive control and a failing
negative control. Its population also includes synthetic evidence cases.

Qualification used zero live model calls. Local fresh-checkout validation passed
372 tests at M7 and 399 at M8. These bounded populations do not establish
production-scale effectiveness or comprehensive reasoning quality. GitHub-hosted
CI has separately passed its standard deterministic checks on the latest master
checkpoint; it does not execute real RWA or AgentGuard qualification.

## AgentGuard relationship

AutoQE evaluates whether AI-enabled orchestration can perform useful QE work.
AgentGuard independently evaluates system behavior against expected outcomes.
The implemented joint dimension is triage-classification agreement only, not all
planning, reasoning or rationale quality. AgentGuard is the first provider behind
a provider-neutral external-evaluation contract.

## Scope and limitations

V1 qualifies one reference application and a bounded semantic vocabulary using
replay outputs. Exact replay matching requires approved inputs; the demo documents
the metadata difference between fresh extraction and the approved planning
checkpoint. Triage trusts normalized evidence and does not infer component root
cause. Historical qualification is distinct from new runtime execution.

## Future directions

Live-model production qualification, richer semantic evaluation, RAG/MCP and
multi-agent systems, visual/accessibility/performance/security adapters and
enterprise integrations remain deferred. None is implied by the v1 results.

[Guided demonstration](DEMO_GUIDE.md) | [architecture](ARCHITECTURE.md) |
[static artifacts](../examples/demo/README.md) | [release readiness](RELEASE_READINESS.md)
