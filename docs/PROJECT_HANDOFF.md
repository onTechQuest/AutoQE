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

M6 - Provider-neutral External Evaluation (qualified in the working tree; not committed).
The preceding M5 checkpoint is committed as `073507c`; M4 is `d7ce21b`.

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

Status: COMPLETE, committed as `d7ce21b`.

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

## M5 - Quality Metrics

Status: COMPLETE, committed as `073507c`. Qualified 2026-10-01.

Architecture: explicit versioned `MetricsManifest` -> validated
`MetricsEvidenceBundle` -> nine independent calculators -> deterministic
`QualityMetricsReport` JSON and concise CLI. All new reporting models live under
`src/autoqe/metrics`, outside frozen M0 contracts. There are no reverse imports
from extraction, planning, execution, adapters or triage. External fault labels
are consumed after execution only. No aggregate score, release gate, thresholds,
dashboard, live model dependency or AgentGuard integration was added.

Design, input rules and commands: [M5 quality metrics](M5_QUALITY_METRICS.md).

Exact definitions and real saved M4 window results:

| Metric | Definition | Result |
|---|---|---|
| Requirement traceability | Unique requirement IDs explicitly referenced by valid evaluated TestSpecs / unique IDs in selected contracts | 1/1; REQ-PAY-001, no uncovered IDs |
| TestSpec schema validity | Valid selected TestSpec inputs / all selected inputs, including malformed JSON | 3/3; positive, negative, unsupported variant |
| Executability | Runtime attempts with supported capability, successful setup, meaningful execution, valid completed PASSED/assertion-FAILED records and all final expected outcomes resolved / runtime attempts | 6/9; environment, data setup and unsupported cases excluded from numerator |
| Healthy false-positive rate | Incorrect assertion/product/test failure signals / externally healthy cases with successful setup and supported semantics | 0/3 |
| Controlled-defect detection | Fault attempts with observed, referenced assertion mismatch after successful setup and meaningful execution / controlled fault attempts | 3/3; zero missed; zero faulty runs passed |
| Triage accuracy | Actual classification matching external expected label / externally labeled cases, including missing triage as incorrect | 8/8 |
| Task completion | Cases producing all explicitly required valid artifacts/terminal results / evaluation cases attempted | 11/11; no incomplete stages |
| AI usage | Actual live token count, or explicit corroborated no-live/replay-or-deterministic-only attestation | 0 live calls, 0 live tokens for this runtime window |
| AgentGuard pass rate | Independent evaluation passes / evaluations | UNAVAILABLE: M6 integration and evaluation dataset/results do not exist |

Counting distinctions: the schema denominator is three input artifacts, not nine
runtime attempts. Accuracy covers three product faults and one each environment,
data, unsupported, unknown and test-defect label. UNKNOWN and TEST_DEFECT are
synthetic triage-only cases, excluded from runtime executability. Healthy baseline
triage records have no external expected label and are excluded from accuracy.
Task completion covers nine runtime pipelines plus two explicitly triage-only
synthetic tasks. A product FAILED result and valid terminal ERROR/SKIPPED result
may complete an artifact pipeline; INCOMPLETE does not complete an execution
stage. Completion does not imply correctness.

Availability distinguishes AVAILABLE (including observed zero), NOT_APPLICABLE
(empty eligible ratio denominator, null value and explicit reason), and
UNAVAILABLE (missing telemetry or capability, null value). Malformed TestSpecs
remain in the schema denominator with safe diagnostic categories and hashes;
other malformed artifacts, missing referenced files, duplicate case identities,
inconsistent evidence and mixed projects fail clearly. Optional missing stage
references are incomplete tasks, not missing-file errors. Generic artifact sets
without usage evidence remain UNAVAILABLE; no token estimates are made.

Qualification and verification:

- Deterministic committed synthetic fixture: `examples/metrics/manifest.json`;
  report at ignored `reports/m5-fixture/quality-metrics.json`. Traceability 1/2
  explicitly leaves REQ-DELETE uncovered; empty healthy sample is NOT_APPLICABLE.
- Actual saved M4 integration: ignored `reports/m5-integration/manifest.json`
  and `reports/m5-integration/result/quality-metrics.json`. No RWA restart or
  additional fault injection was needed. Values above came from saved artifacts,
  not constants. Paired TestSpec hashes and summary counts were corroborated.
- All 19 referenced M4 evidence files existed and matched their supplied hashes.
  Report serialization was byte-stable across independent loads; privacy checks
  passed and no credentials were read, printed or persisted by M5.
- Focused metrics tests: 58 passed. Metrics plus corrected dependency-boundary
  tests: 73 passed.
- Fresh-checkout-style copy, without `.git` or pre-existing reports: 58 metrics
  tests and the fixture reporting CLI passed using only copied committed/new
  source and fixtures plus the existing interpreter/dependencies.
- Final full suite: 279 passed. The first milestone-close full run found one
  legacy test that banned the word AgentGuard anywhere in source (278 passed,
  one failed). It was corrected to enforce static/dynamic import and packaging
  dependency boundaries while allowing M5's required unavailable metric text.
  Focused verification and the final complete rerun then passed. No runtime or
  frozen M0 contract changes were made for this correction.
- RWA remained clean at `9dfcb9869533ce8a8963c556facc0d80457f9d39`.
  AgentGuard remained clean and unchanged at
  `ee104f90fe9c0c23f320ab110fdd2c9adf20d37c`.
- Ports 3000/3001 had no listeners before or after M5; live model calls: zero.
  Reports and fresh-checkout output are ignored. Frozen M0 contracts/interfaces/
  schemas are unchanged; `git diff --check` passed. No commit was made.

Limitations: one payment requirement and three controlled faults cannot establish
broad behavioral coverage or statistical significance. External labels and usage
attestations are trusted qualification evidence; hashes identify bytes rather
than prove independent truth. Calculators use normalized observations and do not
interpret screenshots or implicitly read referenced evidence files. Composite
final outcomes may be resolved by another provider after one provider stops.
Concrete fault detection and complete executability are deliberately separate:
a supported observed mismatch may detect a fault while other outcomes remain
unresolved. AgentGuard pass rate remains unavailable until M6. Historical runtime
reports are intentionally not fresh-checkout dependencies.

## M6 - Provider-neutral External Evaluation

Status: COMPLETE in the working tree; not committed. Qualified 2026-10-01.

Architecture and commands: [M6 external evaluation](M6_EXTERNAL_EVALUATION.md).

Top-level `autoqe_integration/contracts` owns versioned ExternalEvaluationRequest,
ExternalEvaluationResult, planned-window identity and the EvaluationProvider
protocol. These models are outside frozen M0. `autoqe_integration/transport` owns a
bounded local subprocess transport. `autoqe_integration/providers/agentguard` owns the
first real provider and fixed worker. Generic contracts have no evaluator-specific
fields or imports, and provider revisions need not be Git hashes for future
providers. No placeholder providers were added.

The worker uses the separate AgentGuard environment and pinned revision
`ee104f90fe9c0c23f320ab110fdd2c9adf20d37c`. It calls only the existing deterministic
`evaluate_record` over a minimal captured classification view. It does not execute
the support agent, semantic judges, quality gates, safety aggregates or full native
run-lineage builder. Actual and expected values must each be one exact frozen
classification enum, without surrounding prose or whitespace. Expected labels
come from separate external qualification evidence, never actual triage output.

AgentGuard's native ScenarioScore is retained unchanged inside the provider-neutral
result. Empty tool expectations/calls represent inapplicable tool evaluation;
those native flags are not presented as AutoQE tool-quality evidence. No latency,
model/prompt identity, tool results or usage telemetry is fabricated. The result
preserves sanitized request identity, original source IDs/hashes, provenance,
applicability, provider identity, completion status and bounded error codes.

The export is field-allowlisted. Full M4/M5 reports, runtime records, fault IDs,
patches, worktree paths, credentials, cookies, headers and authentication/body
payloads are not forwarded. Opaque case/label IDs replace controller case names.
Worker environment inheritance is restricted, bytecode writes disabled, and
live/reference execution imports plus network connection/binding/DNS paths are
blocked. No AgentGuard installation or checkout mutation is performed.

M5 imports only the generic integration contracts. Its optional external window
binds planned case IDs, request hashes, provider/revision and control flags.
COMPLETED_PASS contributes to numerator; COMPLETED_PASS and COMPLETED_FAIL to
denominator. Any missing real result, ERROR or INCOMPLETE makes the headline
UNAVAILABLE. Planned/attempted/completed/passed/failed/error/incomplete/missing
and excluded-control counts remain visible. Controls never enter the real metric.
Metrics without external evidence retain their previous unavailable behavior.

Final real qualification at `reports/m6-qualification/qualification.json`:

| Population | Planned | Completed PASS | Completed FAIL | ERROR | INCOMPLETE/missing |
|---|---:|---:|---:|---:|---:|
| Previously qualified, externally labeled AutoQE cases | 8 | 8 | 0 | 0 | 0 |
| Positive provider control | 1 | 1 | 0 | 0 | 0 |
| Negative provider control | 1 | 0 | 1 | 0 | 0 |

The population is derived from explicit sanitized evidence, not hardcoded. It
includes three product-defect cases and one each environment, data, unsupported,
unknown and test-defect label. The last two are historical synthetic triage cases,
not new runtime defects, and differ from the two new qualification-only controls.
Positive control: expected PRODUCT_DEFECT / actual PRODUCT_DEFECT. Negative
control: expected PRODUCT_DEFECT / actual DATA_FAILURE. Both controls behaved as
required. Ten real evaluator subprocess invocations produced ten native scores
in the final window. M5 reports AVAILABLE, 8/8 (100%), excluding both controls.

Verification:

- Focused M6 tests: 75 passed; combined M6/metrics/contracts: 148 passed.
- Fresh-checkout-style copy without `.git` or historical reports: all 148 focused
  tests passed. Unit tests require neither AgentGuard nor RWA.
- AutoQE wheel built successfully from that copy and imported from an isolated
  target directory. The environment initially lacked setuptools; a temporary
  isolated build dependency download was approved after sandbox network denial.
  Neither existing project environment nor AgentGuard was installed/modified by
  that packaging check.
- One final complete AutoQE suite: 354 passed.
- Actual interpreter separation: AutoQE Python 3.13.7; AgentGuard Python 3.11.5
  in its existing separate virtual environment.
- Original artifact byte hashes and independent expectation source hash were
  corroborated against explicitly referenced M4/M5 evidence. All normalized
  results preserved their request identity and native score; repeated report
  serialization was deterministic. Exported results contained no fault-profile
  IDs, patch filenames, private payloads or reference credentials.
- Final reports: `reports/m6-qualification/metrics-manifest.json`, normalized
  per-case result files and `reports/m6-metrics/quality-metrics.json` (ignored).
  The standalone M6 report selects only external evaluations; it does not infer
  unrelated M1-M5 metric populations or token telemetry.
- Live model calls: zero. No RWA startup or fault injection. Ports 3000/3001
  remained stopped. RWA is clean at
  `9dfcb9869533ce8a8963c556facc0d80457f9d39`. AgentGuard remains clean at its
  qualified revision; no source or environment modification was needed.
- AutoQE extraction/planning/execution/triage and frozen M0 contracts/interfaces/
  schemas are unchanged. No AgentGuard imports/dependencies in AutoQE core.
  Runtime reports/build verification outputs are ignored. `git diff --check`
  passed. No commit was made.

Only triage-classification agreement was independently evaluated. Contract
grounding, planning quality, execution integrity, rationale quality, screenshots,
comprehensive privacy, operational SLOs, model/prompt regression and release
readiness remain outside M6. External oracle truth is trusted; hashes are not
signatures. The pinned internal scorer interface is not a general stable SDK.
The worker guards are not an OS sandbox, and captured process output is size-checked
after completion rather than streamed under a hard resource cap.

The same generic contracts can later use REST/events/queues/object storage/MCP.
Documentation specifies a future TLS gateway with OAuth2/OIDC/service identities,
short-lived credentials/mTLS, least-privilege scopes, schema/payload/rate controls,
audit/correlation, replay protection, projection and provider routing. None of
these services or transports is implemented in M6.

## M7: Shift-left / CI/CD

M7 adds `.github/workflows/ci.yml` for PRs, pushes to `master`, and manual
dispatch. One Ubuntu/Python 3.13 job installs `.[test]`, compiles/imports packages,
runs the deterministic suite with existing architecture guards, builds and
validates the wheel, and verifies isolated imports of the installed wheel.
Node 22 supports only the existing loopback-preload test; full Git history
supports the frozen-M0 checkpoint test. No runtime architecture changed.

Permissions are `contents: read`; checkout credentials are not persisted.
Standard CI uses no application secrets, external checkouts, live models,
Playwright browsers, historical reports or real RWA/AgentGuard execution.
The wheel validator admits only current `autoqe` and `autoqe_integration` sources
and distribution metadata. Build output is ignored and not uploaded/published.

Preflight: clean `master` at `fa1a16164ad42cd70b398dc75d617256e3df7392`,
354 baseline tests passed, and no Git remote configured. Local validation details
and reproduction are in [M7 CI/CD](M7_CI_CD.md). A local pass is not evidence of
a GitHub-hosted workflow run. **CI PASS is not full real-world RWA/AgentGuard
qualification**; M4 and M6 remain separately provisioned external procedures.

M7 local verification: 18 focused validator tests and 372 full-suite tests passed
in a fresh local clone/environment. Wheel build/content checks and isolated
installed-wheel imports passed (48 core files, eight integration files, four
metadata files). No live model calls or external qualification ran. RWA and
AgentGuard remained clean/pinned, ports 3000/3001 stopped, and M0/runtime code
unchanged. No commit or push was made; no GitHub-hosted run occurred.

## Next Milestone Boundary

M7 is limited to deterministic CI and packaging checks. M8 is not started.
Release automation, new evaluation dimensions, deployment and enterprise
transports require separate authorization.

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
