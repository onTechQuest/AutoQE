# AUTOQE M-1: Reference Target & Integration Qualification

Date: 2026-09-30  
Decision: **CONDITIONAL GO**

## Scope

This is a feasibility result only. No AutoQE framework, agent, RAG, MCP, v2 feature, or live LLM call was added. AgentGuard and the Cypress RWA product source were not modified.

## Reference target and environment

- Upstream: `https://github.com/cypress-io/cypress-realworld-app`
- Local target: `C:\Projects\autoqe-reference-rwa`
- Pinned commit: `9dfcb9869533ce8a8963c556facc0d80457f9d39` (detached HEAD; commit dated 2026-09-29)
- OS: Windows 11 Home, build 26200
- Git: 2.42.0.windows.2
- Node: **22.23.3**, while `.nvmrc` and `.node-version` pin 22.20.0
- npm: 10.9.9; Yarn Classic: 1.22.22
- Python: 3.13.7 selected; Python 3.11 is also installed
- `venv` creation works. Python Playwright was initially absent and was installed with Chromium in a local RWA virtual environment, not globally.
- Ports 3000 and 3001 were free before startup.

Node 22.23.3 is recorded as an environment variance, not a blocker: `package.json` allows `^22.0.0 || ^24.0.0`; dependency installation, type validation, app startup, and all selected Cypress specs succeeded on 22.23.3.

## Qualification evidence

| Check | Result |
|---|---|
| Locked dependency install | `yarn install --frozen-lockfile` completed with Yarn 1.22.22 |
| Static type validation | `yarn types` passed |
| Startup | `yarn dev` started frontend and API; frontend and API roots returned HTTP 200; ports 3000 and 3001 listened |
| Deterministic reset | Two `yarn db:seed:dev` runs each matched `data/database-seed.json` SHA-256 `C2449435BBF44BCEF412A178FB51B8561D3C2D7BA9FC55B10D0B8A09EA66C3A1` |
| Independent Python UI smoke | Playwright 1.63.0 / Chromium loaded the sign-in page with HTTP 200, rendered React content, and found three visible inputs |
| Independent Python API smoke | Python standard-library HTTP client received HTTP 200 from `/testData/users`; response had a `results` list with five user records |
| Existing UI workflows | Cypress `auth.spec.ts` and `new-transaction.spec.ts`: 18/18 passed |
| Existing API contracts | Cypress `api-testdata.spec.ts` and `api-users.spec.ts`: 21/21 passed |
| Controlled defect probe | A transient browser-only CSS injection hid the sign-in submit control; the visibility assertion detected it. No source was changed. |

The RWA working tree was clean after qualification and its database was restored to the canonical seed. The local dev server was stopped.

## Selected workflows

1. **Authentication:** seeded-user sign-in, redirect/session behavior, and invalid-input/error behavior. The existing auth suite also exercises sign-up and logout with per-test database seeding.
2. **Transaction:** seeded-user payment/request creation and verification of the resulting transaction/balance state.
3. **API:** seeded `/testData/:entity` fixtures and `/users` REST behavior, including status codes, validation, and response fields.

These workflows are locally executable, resettable, and observable through DOM state, HTTP responses, and seeded JSON state. The selected Cypress baseline passed in full.

## API contract feasibility

The app exposes Express JSON routes and Cypress contract assertions; the development-only `/testData/:entity` route provides a deterministic fixture surface and `/testData/seed` resets it. The test-data and user API specs passed (21 checks). The inspected contract is represented by route implementations and tests; no separate versioned OpenAPI document was identified. AutoQE can initially consume HTTP status/body assertions and retain endpoint, request, and response evidence without requiring a live model.

## Controlled defect feasibility

A browser-only style injection hid `[data-test=signin-submit]`, and the visibility check changed from passing to detecting the defect. This demonstrates a reversible UI fault-injection path without changing the reference source. It does not qualify backend fault injection or mutation-score completeness.

## v2 extension feasibility

The reference target can be represented by a versioned profile with optional capability declarations, leaving future runners/reporters behind explicit extension points. Feasibility is architectural only: no plugin system or v2 behavior was implemented. Unknown capabilities should remain rejected or explicitly unavailable rather than silently treated as supported.

## AgentGuard artifact-level assessment

AgentGuard remains unchanged. Its v1 evaluation result and run-manifest schemas describe agent scenarios, model/evaluator identities, lineage, and evaluation evidence; Cypress UI/API results are not valid substitutes for an AgentGuard `EvaluationRecord` or evaluation-result envelope. AgentGuard documents Reporter and ArtifactStore adapters as future contracts, not implemented interfaces. Therefore, direct native ingestion is not available today, but artifact-level association is feasible: AutoQE should retain its own versioned run summary and raw test evidence, and reference those artifacts from any future integration without claiming they are AgentGuard evaluation results. No live AgentGuard evaluation was run.

## ProjectProfile recommendation

Use a versioned, declarative ProjectProfile for this reference target. Keep it limited to target identity/commit, runtime and package-manager constraints, install/start/stop commands, readiness URLs, reset command and expected seed fingerprint, selected workflow/spec identifiers, API base URL and contract checks, and artifact locations. Record pinned and permitted runtime versions separately so an upstream pin deviation such as Node 22.23.3 remains visible without being mislabeled as incompatibility. Store credentials as environment-variable references only; this target's selected checks require none.

## Decision

**CONDITIONAL GO.** Cypress RWA is qualified as a deterministic AutoQE v1 reference target at the pinned commit. Node 22.23.3 caused no observed incompatibility. Startup, reset, independent Python UI/API smoke, and selected native UI/API suites passed. The condition is that the AutoQE-to-AgentGuard artifact boundary and ProjectProfile schema must be defined in AutoQE before claiming direct integration: the current workspace contains no such contract, and AgentGuard intentionally has no native Cypress adapter. This is a known, bounded adapter/schema decision, not a blocker to using RWA as the reference application. No work beyond M-1 qualification is authorized by this result.

Non-blocking upstream notices during qualification: a Vite plugin peer-range warning, stale Browserslist data, deprecated Cypress Electron browser, and the removed `experimentalStudio` option.