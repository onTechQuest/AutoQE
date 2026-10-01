# AutoQE Project Handoff

## Purpose

AutoQE is a vendor-neutral autonomous Quality Engineering orchestration framework.

It converts product intent and project context into grounded behavioral contracts and risk-based, vendor-neutral TestSpecs, delegates deterministic execution to existing test frameworks, normalizes execution evidence, and can later be independently evaluated by AgentGuard.

AutoQE is not intended to replace Playwright, API frameworks, CI/CD systems, test management products, observability platforms, or other enterprise engineering systems.

## Repositories

### AutoQE

Path:

C:\Projects\AutoQE

Current completed implementation through:

M3 - Deterministic Execution Providers

Current M3 commit:

683e997

### Reference Application

Cypress Real World App (RWA)

Path:

C:\Projects\autoqe-reference-rwa

Qualified and pinned revision:

9dfcb9869533ce8a8963c556facc0d80457f9d39

RWA is an external system under test and is not part of AutoQE core.

Its existing Cypress tests are an independent human-authored benchmark and must not be used as generation/planning context.

### Independent Evaluator

AgentGuard

Path:

C:\Projects\AgentGuard

AgentGuard remains a separate project.

AutoQE must not absorb or directly couple itself to AgentGuard internals. Future integration should use an external artifact adapter.

## Core Architecture

Current contract chain:

ProjectProfile
    |
    v
BehavioralContract
    |
    v
TestSpec
    |
    v
ExecutionRecord
    |
    v
TriageRecord

Current implemented flow:

Requirements / project context
    |
    v
ProjectProfile
    |
    v
Context and Behavioral Contract Extraction
    |
    v
BehavioralContract
    |
    v
Risk-Based Planning
    |
    v
Vendor-Neutral TestSpec
    |
    v
RwaProjectAdapter
    |
    +--> PlaywrightExecutionProvider
    |
    +--> ApiExecutionProvider
    |
    v
ExecutionRecord

Triage is defined in the M0 contract but is not yet implemented as runtime intelligence.

## Architectural Principles

1. AutoQE core must remain project-agnostic.
2. Project-specific behavior belongs behind ProjectProfile / ProjectAdapter.
3. AI may produce structured intent and evidence but must not generate arbitrary executable Python, JavaScript, shell, or other code in v1.
4. Execution occurs through typed, deterministic providers.
5. TestSpec is the vendor-neutral handoff between planning and execution.
6. Existing testing frameworks remain authoritative for execution.
7. UNKNOWN and UNAVAILABLE must never be fabricated into known behavior.
8. RWA Cypress tests must remain excluded from AutoQE generation/planning context.
9. AutoQE must remain independently usable without AgentGuard.
10. Replay/offline behavior is preferred for deterministic CI and demonstrations.
11. For every defect or requested change, evaluate the correct architectural layer before applying a tactical patch.

For defects and changes consider:

- root cause
- correct architectural layer
- generic versus case-specific solution
- false-positive risk
- false-negative risk
- determinism
- observability/evidence
- regression strategy
- enterprise maintainability

## Security Constraints

Reference/demo execution must remain local-only.

Allowed listener targets:

- localhost
- 127.0.0.1
- ::1

Do not:

- create Windows Firewall exceptions
- bind application services to 0.0.0.0
- bind application services to ::
- intentionally expose services to LAN/public interfaces
- configure port forwarding
- create tunnels such as ngrok/cloudflared
- enable remote debugging
- persist credentials
- store raw authentication traffic in execution evidence

RWA_TEST_PASSWORD is supplied only at runtime.

M3 uses:

scripts/force_loopback_bind.cjs

as a process-scoped local reference-environment containment mechanism. It is not AutoQE production security infrastructure.

## Completed Milestones

### M-1 - Feasibility and Reference Qualification

Status: COMPLETE

Qualified RWA as the v1 reference target.

Verified:

- deterministic seeded/resettable state
- independent Playwright smoke execution
- independent API smoke execution
- selected RWA Cypress UI tests: 18/18 passed
- RWA Cypress API tests: 21/21 passed
- controlled browser-only UI defect was detectable
- RWA returned clean after qualification
- no live LLM usage

### M0 - Architecture and Contract Freeze

Status: COMPLETE

Defined frozen v1 contracts:

- ProjectProfile
- BehavioralContract
- TestSpec
- ExecutionRecord
- TriageRecord

Defined interfaces:

- ModelProvider
- ExecutionProvider
- ProjectAdapter

Added:

- provenance
- availability semantics
- risk semantics
- evidence references
- schema versioning
- credential/body sentinels
- local-only project profile validation

Persistent contract schema version:

1.0

M0 contracts must not be changed merely for implementation convenience.

M0 offline tests:

15 passed

### M1 - Context and Behavioral Contract Extraction

Status: COMPLETE

Implemented:

MarkdownRequirementProvider
    |
    v
bounded ContextBundle
    |
    v
ReplayModelProvider
    |
    v
BehavioralContract validation
    |
    v
deterministic grounding

Synthetic RWA requirements include:

- REQ-AUTH-001
- REQ-ACCT-001
- REQ-PAY-001
- REQ-HIST-001
- REQ-AUTHZ-001

Key properties:

- bounded source ingestion
- explicit allowlisting
- no repository browsing
- no Cypress test ingestion
- no hidden defect metadata
- deterministic fingerprints
- exact provenance grounding
- explicit assumptions and unknowns
- replay-only provider for v1 demonstrations

Live provider remains disabled/fail-closed.

M1 full offline result:

32 passed

Known limitation:

Exact-source grounding may reject semantically valid paraphrases. This is accepted for v1.

### M2 - Risk-Based Planning and TestSpec Generation

Status: COMPLETE

Implemented:

BehavioralContract
    |
    v
RiskPlanner
    |
    v
CoveragePlanner
    |
    v
LayerSelector
    |
    v
Replay-supported semantic planning
    |
    v
TestSpec

Planning supports bounded coverage categories including:

- positive
- negative
- authorization
- state transition
- explicit behavior

Risk priorities:

- CRITICAL = 1
- HIGH = 2
- MEDIUM = 3
- LOW = 4
- UNKNOWN = 5

Layer selection is capability-aware.

TestSpec remains semantic and vendor-neutral.

No executable provider code is embedded in TestSpec.

UNKNOWN values remain limitations rather than invented expected behavior.

M2 full offline result:

61 passed

### M3 - Deterministic Execution Providers

Status: COMPLETE

Commit:

683e997

Implemented:

- RwaProjectAdapter
- deterministic execution service
- allowlisted semantic actions
- PlaywrightExecutionProvider
- ApiExecutionProvider
- BOTH-layer execution
- frozen ExecutionRecord normalization
- execution CLI
- loopback-only RWA preload
- sanitized evidence handling

Execution flow:

TestSpec
    |
    v
RwaProjectAdapter reset/setup
    |
    v
Allowlisted semantic action resolution
    |
    +--> Playwright
    |
    +--> httpx
    |
    v
ExecutionRecord

No:

- eval
- exec
- arbitrary generated shell
- generated executable code
- self-healing
- runtime triage
- live model calls

Qualified M3 executions:

UI / transaction history:
3/3 passed

API / invalid payment rejection:
3/3 passed

BOTH / payment:
3/3 passed

Focused M3 tests:

17 passed

Full AutoQE suite:

78 passed

Verified runtime listeners:

Frontend:
::1:3000

API:
127.0.0.1:3001

RWA was stopped after qualification.

AgentGuard remained unchanged.

RWA remained pinned and clean.

M0 contracts remained unchanged.

## Current Clean Checkpoint

Completed:

M-1  Reference Qualification
M0    Architecture and Contracts
M1    Behavioral Contract Extraction
M2    Risk-Based Test Planning
M3    Deterministic UI/API Execution

Current full-suite result:

78 passed

Current repository state at M3 completion:

clean

## Next Milestone

M4 - Controlled Faults, Evidence, and Triage

Intent:

Prove that AutoQE can execute the same TestSpecs against healthy and deliberately faulty versions of the reference application, detect meaningful behavioral failures, preserve evidence, and classify failures without knowing which fault was injected.

Planned failure classifications already defined by the M0 contract:

- PRODUCT_DEFECT
- TEST_DEFECT
- ENVIRONMENT_FAILURE
- DATA_FAILURE
- UNSUPPORTED_BEHAVIOR
- UNKNOWN

M4 should use a small bounded set of deterministic hidden fault profiles.

Potential fault domains include:

- payment validation
- authorization / ownership
- transaction amount or state
- input validation

The active fault identity must not be exposed to AutoQE planning or triage logic.

M4 must not begin until explicitly authorized.

## Deferred / V2 Capabilities

Do not implement during current v1 milestones unless explicitly authorized:

- RAG / KnowledgeProvider
- MCP / ToolProvider
- multi-agent orchestration
- self-healing
- visual AI testing
- accessibility testing
- security scanning
- performance testing
- enterprise Jira integration
- TestRail/Xray integration
- BrowserStack/Sauce integration
- production dashboards
- Kubernetes/cloud deployment
- broad enterprise governance
- second reference application

These may be documented as future architecture but must not silently enter v1 implementation.

## Portfolio Relationship

The intended portfolio story is:

Product under test: Cypress RWA
        ^
        | tested by
      AutoQE
        ^
        | evaluated by
     AgentGuard

AgentGuard answers:

How do we know AI systems are reliable?

AutoQE answers:

How can AI perform Quality Engineering work reliably?

A future Enterprise AgentOps project will address:

How do we operate many enterprise agents safely at scale?
