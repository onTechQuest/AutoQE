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

M4 - Controlled Faults, Evidence, and Triage (working tree; not committed)

Current M3 commit:

683e997

Pre-M4 hardening checkpoint: `29eadfa`.

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

M4 adds deterministic runtime triage from TestSpec and ExecutionRecord evidence,
using the frozen TriageRecord. The external qualification controller is outside
the implemented decision path and never supplies fault identity to AutoQE.

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

## M3 Clean Checkpoint

Completed:

M-1  Reference Qualification
M0    Architecture and Contracts
M1    Behavioral Contract Extraction
M2    Risk-Based Test Planning
M3    Deterministic UI/API Execution

Full-suite result at M3 completion:

78 passed

Current repository state at M3 completion:

clean

## Pre-M4 Execution Hardening Checkpoint

Status: COMPLETE, committed as `29eadfa`. This checkpoint preceded M4.

The core execution service now uses internal `ExecutionSetupAdapter` and
`CheckedExecutionProvider` protocols. The frozen M0 contracts, interfaces, and
schemas are unchanged. RWA fixture setup is inferred from resolved semantic
operations inside the adapter, not from a contract ID in the core service.

Providers preflight semantic targets, arguments, ordering, and exact supported
outcome IDs/descriptions before setup. Unsupported semantics produce SKIPPED
records with UNSUPPORTED_BEHAVIOR and explicit UNKNOWN assertions. Completeness
validation prevents PASSED when outcomes or steps are missing, unresolved,
ambiguous, skipped, or mismatched. It preserves provider evidence and never
upgrades an existing non-pass.

BOTH status precedence is ERROR, then FAILED, then INCOMPLETE. All PASSED is
PASSED; all SKIPPED is SKIPPED; mixed PASSED/SKIPPED is INCOMPLETE. Each provider
must independently account for every expected outcome. Provider-specific setup,
steps, assertions, and evidence are retained in the composite record.

Qualified payment semantics now check the submitted amount and transaction
identity. API checks also require correct sender/recipient identities and the
complete payment state in both participant histories. UI checks require exactly
one matching payment with the submitted amount, and the same transaction in both
histories for the reflected-state outcome. These implement existing payment
requirements; fees, limits, insufficient-funds rules, and balance formulas are
not inferred. Stored completion status is not exposed by the current UI checks,
so the UI state-transition outcome is explicitly unsupported. Authorization and
account-setup execution remain unsupported. The resolver is intentionally bounded
to approved outcome semantics rather than accepting unfamiliar IDs or paraphrases.

IPv6 loopback URLs retain the required brackets around `::1`. Local-only
validation and runtime-only credential handling remain in force.

Execution test fixtures are generated in memory from committed M1 contracts and
approved planning replays, then validated against the frozen TestSpec model.
Tests no longer require ignored runtime plans. No runtime reports were committed
and `.gitignore` is unchanged.

Verification:

- Focused execution/hardening tests: 122 passed.
- One complete AutoQE suite: 183 passed.
- Isolated source copy without `reports/`: 122 focused tests passed; no reports
  directory was created. The existing Python environment supplied dependencies.
- `git diff --check`: passed.
- AgentGuard: clean and unchanged at `ee104f9`.
- RWA: clean at `9dfcb9869533ce8a8963c556facc0d80457f9d39`.
- Ports 3000/3001: no listeners.
- Live model calls: zero. No real credential was persisted; synthetic transport
  tests verify credentials are absent from normalized records and API evidence.

The initial hardening checkpoint used offline transport/browser doubles. A
subsequent real runtime requalification passed 3/3 UI history, 3/3 API invalid
payment, and 3/3 BOTH payment runs, including the strengthened assertions.
No fault injection or runtime triage was performed during that checkpoint.

## M4 - Controlled Faults, Evidence, and Triage

Status: COMPLETE in the working tree; not committed.

Architecture and commands: [M4 controlled faults and triage](M4_CONTROLLED_FAULTS_AND_TRIAGE.md).

Runtime triage is a project-agnostic deterministic service under `autoqe.triage`.
`scripts/triage_execution.py` accepts only normal project, test, and execution
artifacts. It uses the unchanged M0 TriageRecord, retains evidence references,
and explains decisions without model calls or confidence scores.

Explicit setup evidence distinguishes readiness/transport failures from reset or
fixture failures. Product classification requires supported semantics, successful
setup, target submission, and concrete failed assertions with hashed evidence.
Opaque provider/locator failures remain UNKNOWN. TEST_DEFECT is limited to an
established test/reporting artifact inconsistency. Healthy records receive UNKNOWN
with a no-observed-failure rationale, because M0 has no healthy classification.

The controller in `qualification/m4/` creates detached disposable worktrees at the
same pinned RWA revision, applies at most one registered exact patch per target,
and removes each worktree after execution. A temporary dependency junction is
unlinked before cleanup. The canonical checkout is never the running target.
The adapter verifies canonical source identity separately from deployed seed/data.

Fault identity is external to AutoQE. Execution and triage run in separate fresh
processes with ordinary artifact arguments, opaque directory identifiers, and
allowlisted environments. Neither runtime service imports the controller or reads
fault definitions. Only the external qualification report joins expected fault
labels with actual results after triage. No Cypress test source was used.

Real healthy-versus-faulty qualification at the pinned revision:

| Controlled product regression | Healthy | Same TestSpec, faulty | Triage |
|---|---|---|---|
| Missing recipient incorrectly defaults to requesting user | PASSED | FAILED: invalid payment persisted | PRODUCT_DEFECT |
| Payment amount uses incorrect unit conversion | PASSED | FAILED: 350 observed versus 3500 expected minor units | PRODUCT_DEFECT |
| Payment completion update leaves pending state | PASSED | FAILED: pending observed versus complete expected | PRODUCT_DEFECT |

Healthy/faulty TestSpec SHA-256 values matched within every pair. Product faults
attempted: 3; detected: 3; healthy baselines passed: 3; faulty runs incorrectly
passed: 0. These are bounded factual counts, not an AI score or release gate.

Non-product qualification:

- Stopped local service: ERROR / ENVIRONMENT_FAILURE.
- Disposable target seed fingerprint mismatch: ERROR / DATA_FAILURE.
- Valid unsupported semantics: SKIPPED / UNSUPPORTED_BEHAVIOR.
- Explicitly synthetic insufficient evidence: UNKNOWN.
- Explicitly synthetic assertion-definition inconsistency: TEST_DEFECT.

All expected classifications matched. The latter two are evidence fixtures,
not claims of observed application defects.

Verification:

- Focused M4 plus execution/hardening tests: 160 passed.
- One final complete AutoQE suite: 221 passed.
- Real qualification: PASS; ignored report at
  `reports/m4-qualification-20260930/qualification.json`.
- Runtime evidence: 29 JSON artifacts and 13 screenshots; 19 unique evidence
  references resolved, with all supplied hashes verified. Credential, private-key,
  raw-payload-key, and fault-identity audits passed for runtime artifacts.
- Observed listeners: frontend `[::1]:3000`, API `127.0.0.1:3001` only.
- Final listeners: none on ports 3000/3001.
- All temporary worktrees removed; only the canonical RWA worktree remains.
- Canonical RWA clean at `9dfcb9869533ce8a8963c556facc0d80457f9d39`.
- AgentGuard clean and unchanged; no integration added.
- Live model calls: zero. Runtime credentials were not persisted or printed.
- Frozen M0 contracts/interfaces/schemas unchanged; `git diff --check` passed.

Remaining limitations: the controller currently targets Windows with existing
Node/Yarn dependencies. Process/input separation is an architectural information
boundary, not an OS sandbox against malicious worker code. Triage trusts normalized
provider evidence and does not infer component-level root cause or interpret
screenshots. UI-interrupted outcomes can remain unresolved; the controlled product
classifications are supported by concrete API assertions. TEST_DEFECT qualification
covers artifact inconsistency only. The three faults do not establish broad defect
coverage, authorization correctness, or production readiness.

## Next Milestone Boundary

M5 is not started. AgentGuard integration and M5 metrics infrastructure remain
outside this checkpoint and require a separate authorized scope.

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
