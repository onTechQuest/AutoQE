# AutoQE Project Handoff

## Purpose

AutoQE is a vendor-neutral Quality Engineering orchestration framework. It turns
product intent into grounded behavioral contracts and risk-based TestSpecs,
delegates execution to existing UI/API technologies, retains structured evidence,
classifies observed failures and supports independent external evaluation.

The core is project-agnostic. RWA is the qualified reference target, not the
framework's identity. AutoQE does not replace execution frameworks or generate
arbitrary executable test code.

## Current release state

- Package version: **1.0.0**; proposed release tag: **v1.0.0**.
- Branch: **master**.
- License: [Apache License 2.0](../LICENSE).
- Public repository: `https://github.com/onTechQuest/AutoQE`.
- GitHub-hosted CI: **passed** on the latest master checkpoint.
- Recorded final deterministic fresh-checkout suite: **399 passed**.
- Public demo provenance: corrected and validated against canonical LF bytes.
- The v1.0.0 tag/release has not been created.

Hosted CI validates the standard deterministic pipeline. It does not execute
real RWA or the separately installed AgentGuard evaluator. The 399-test result
is the recorded final fresh-checkout qualification; focused regression checks
are separate and do not redefine that historical population.

## Repositories and dependencies

AutoQE uses Python 3.13, Pydantic, Playwright, httpx and pytest. Node 22 supports
the deterministic loopback-preload test in CI. Standard installation and tests
need no external application checkout, model credentials or browser binaries.

Cypress Real World App is separately provisioned and pinned to
`9dfcb9869533ce8a8963c556facc0d80457f9d39`. Its Cypress tests remain independent
benchmark evidence and are excluded from extraction/planning context.

AgentGuard is separately provisioned and qualified at
`ee104f90fe9c0c23f320ab110fdd2c9adf20d37c`. Its existing interpreter and repository
remain independent; AutoQE neither installs it as a dependency nor imports it
from core runtime modules. Standard CI mocks external provider responses.

The wheel contains only `autoqe` and `autoqe_integration` package roots plus
metadata. Tests, examples, qualification controllers and reports are excluded.

## Current architecture

```text
Requirements / project context
    -> ProjectProfile + bounded context
    -> BehavioralContract
    -> Risk-Based Planning
    -> TestSpec
    -> ProjectAdapter + UI/API Execution Providers
    -> ExecutionRecord
    -> TriageRecord
    -> Observational Metrics

Selected artifacts + independent expected labels
    -> ExternalEvaluationRequest
    -> EvaluationProvider
    -> AgentGuardEvaluationProvider
    -> Separate AgentGuard environment
    -> ExternalEvaluationResult -> Metrics
```

ProjectProfile declares environment and capability boundaries. BehavioralContract
retains source grounding and unknowns. TestSpec is the governed execution handoff.
The adapter owns target-specific setup/reset/authentication and semantic mapping;
providers normalize observations into ExecutionRecord. Triage consumes governed
artifacts rather than controller labels or target source.

Metrics observe artifacts without controlling execution. External evaluation
uses explicit selected inputs and independent expectations, not a metric-derived
oracle. See [Architecture](ARCHITECTURE.md) for component responsibilities.

## Architectural principles

- Keep the core project-agnostic and target behavior behind adapters.
- Preserve frozen typed contracts, interfaces and schemas.
- Produce structured intent, not arbitrary executable AI-generated test code.
- Use TestSpec as the governance boundary between planning and execution.
- Resolve supported actions and execute deterministically through providers.
- Preserve UNKNOWN, UNAVAILABLE and NOT_APPLICABLE explicitly.
- Reject missing/unresolved assertions rather than manufacture a passing result.
- Keep AutoQE independently usable without AgentGuard.
- Exclude benchmark tests, fault identities and expected labels from generation
  and runtime classification inputs.
- Diagnose defects in the correct architectural layer before applying a patch.
  Evaluate false positives/negatives, determinism, evidence, regression risk and
  maintainability; prefer general architectural solutions to case-specific fixes.

## Security boundaries

Reference execution is restricted to localhost, 127.0.0.1 and ::1. The
process-scoped Node preload and actual-listener inspection enforce this boundary.
No LAN/public binds, port forwarding, tunnels, remote debugging or firewall
changes are part of reference execution.

`RWA_TEST_PASSWORD` is supplied at runtime only. Evidence excludes raw
authentication traffic, cookies, headers and unrestricted request/response bodies.
API evidence retains bounded measurements and hashes. Public demo projections
omit screenshots and explicitly describe sanitization.

Public `sha256` values identify canonical LF artifact bytes. `source_sha256`
values identify original pre-projection bytes and remain separate. External
request hashes and lineage retain original qualification identities. Hashes prove
byte identity, not independent oracle truth or runtime authenticity.

Qualification labels and fault activation belong to the external controller.
Ignored reports contain local runtime output and are not automatically safe for
publication. See [Public release review](PUBLIC_RELEASE_REVIEW.md).

## Implemented v1 capabilities

- Approved Markdown/context extraction with grounding and source fingerprints.
- Replay ModelProvider for reproducible structured AI-stage outputs.
- Risk/coverage planning with explicit unknowns and layer selection.
- Vendor-neutral UI/API/BOTH TestSpecs and capability validation.
- Deterministic reference reset, execution and assertion-completeness checks.
- Structured execution evidence and evidence-based triage.
- Separate controlled-fault qualification with independent expected labels.
- Denominator-explicit observational quality metrics.
- Provider-neutral external requests/results and isolated AgentGuard provider.
- Self-contained deterministic CI, wheel validation and installed-package checks.
- Guided demonstration, provenance-labeled public artifacts and opt-in cleanup.

The [Demo guide](DEMO_GUIDE.md) provides actual offline and optional live commands.
Report cleanup defaults to dry run and requires an explicit confirmed selection;
it rejects traversal, links/reparse points and protected nested source trees.

## Qualification summary

| Bounded population | Observed result |
|---|---|
| Healthy UI/API/BOTH scenarios | Three consecutive passes per scenario |
| Controlled product faults | 3/3 detected; zero faulty runs passed |
| Healthy false-positive population | 0/3 |
| Externally labeled triage agreement | 8/8 |
| Artifact completion | 11/11 |
| External classification agreement | 8/8; no FAIL/ERROR/INCOMPLETE results |
| External controls | Positive passed; negative failed as expected |
| Final fresh-checkout suite | 399 passed |
| GitHub-hosted standard CI | Passed |
| Live model calls required for deterministic qualification | Zero |

The triage population includes two synthetic triage-only cases. External
evaluation also includes synthetic evidence cases; its two controls are excluded
from the eight-case metric. Completion is not correctness. Different metrics
have different denominators and must not be combined into an aggregate score.
These small populations do not establish production-scale effectiveness or
statistical significance. Standard CI does not replace external qualification.

## AgentGuard relationship

```text
Cypress RWA
    ^ tested by
  AutoQE
    ^ evaluated by
 AgentGuard
```

AutoQE performs governed QE orchestration. AgentGuard independently compares
selected behavior with expected outcomes through EvaluationProvider. The current
dimension is triage-classification agreement only; it does not comprehensively
evaluate planning, rationale, screenshots, tool selection or all AI reasoning.

## Known limitations

One reference application and a bounded semantic vocabulary are qualified.
AI stages use approved replay, not production-qualified live models. Exact replay
fingerprinting detects a limitation-string difference between fresh extraction
and the approved planning checkpoint; the demo makes this discontinuity explicit.

Payment checks cover bounded transaction amount/identity/participants/state, not
bank-ledger reconciliation. Triage trusts normalized evidence and does not infer
component root cause. The evaluator worker is not an OS sandbox. Dependency
ranges are not a fully locked supply chain. No statistical production claims or
comprehensive security certification follow from these qualification results.

## V1 / future boundary

The following are **NOT IMPLEMENTED**: live-model production qualification,
richer autonomous exploration, RAG, MCP/tool ecosystems, multi-agent QE,
self-healing, visual AI, accessibility/performance/security testing adapters,
Jira/TestRail/observability integrations, BrowserStack/Sauce integrations,
production dashboards/analytics, enterprise gateways/APIs, broad enterprise
governance, Kubernetes/cloud deployment and a second reference application.
Richer semantic planning/rationale evaluation remains deferred as well.

These are potential extensions, not implied v1 capabilities. Extension work must
preserve contract governance, target isolation, explicit uncertainty and evidence
boundaries. See [Project overview](PROJECT_OVERVIEW.md) for the public scope.

## Detailed qualification history

[Qualification history](QUALIFICATION_HISTORY.md) preserves milestone chronology,
checkpoint commits, intermediate test counts, observations and limitations.
[Release readiness](RELEASE_READINESS.md) records release checks and remaining
publication steps without repeating that history.
