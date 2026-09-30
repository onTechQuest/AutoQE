# M3 Execution Providers

## ProjectAdapter and local security

`RwaProjectAdapter` accepts only the M1 `cypress-rwa` profile pinned to `9dfcb9869533ce8a8963c556facc0d80457f9d39`, with `LOCAL_ONLY`, the qualified seed adapter, and HTTP loopback URLs. It verifies the checked-out revision and clean tracked worktree, probes the frontend/API roots, invokes the existing `POST /testData/seed`, and reads seeded users through `GET /testData/users`. It may create one named history fixture using the existing authenticated transaction endpoint. No RWA files or data utilities are modified.

The RWA backend source calls `app.listen(port)` without an explicit host; M1 observed a wildcard IPv6 listener. M3 uses the process-scoped `scripts/force_loopback_bind.cjs` preload for RWA's Node processes. It narrows hostless/wildcard Node binds to `127.0.0.1` and rejects other explicit hosts. The profile URLs retain `localhost` to preserve RWA's configured CORS origin. Actual listeners are inspected while the server runs; no firewall, tunnel, remote debug, or LAN access is configured.

The seeded password is read from `RWA_TEST_PASSWORD` at runtime only. It is never written to records or evidence. AutoQE/report/evidence artifacts are under gitignored `reports/`.

## Semantic actions and providers

`RwaSemanticActionResolver` maps a small explicit set of M2 semantic actions and target names to typed RWA operations. Unknown targets or mismatched action arguments fail explicitly. No `eval`, `exec`, arbitrary shell, or model-generated selectors/code are used.

`PlaywrightExecutionProvider` supports selected UI/BOTH TestSpecs using accessible labels/roles and the inspected stable RWA test hooks. Browser requests are restricted to loopback; screenshots capture only relevant visible elements. No trace archive is stored because it could include authentication traffic.

`ApiExecutionProvider` uses httpx with `trust_env=False` against loopback only. It authenticates using the RWA session flow and exercises only the selected transaction/history routes. Persisted API evidence includes status/count/hash metadata, never raw bodies, headers, or cookies.

## Evidence and BOTH decision

UI/API TestSpecs produce one frozen M0 `ExecutionRecord`. A BOTH TestSpec runs the two providers sequentially, resetting and setting up the seed before each half, then produces one composite ExecutionRecord. Provider names and per-step observations identify which evidence came from Playwright or httpx; assertion results merge by the contract's stable outcome ID. Any error dominates failure; failure dominates pass. This preserves the M0 schema without creating a distributed execution contract.

Records preserve PASSED, FAILED, ERROR, SKIPPED, and INCOMPLETE statuses. M3 reports execution evidence only; it does not perform root-cause triage.

## Determinism and M4 boundary

Before every provider run, the adapter verifies checkout/readiness, resets through RWA's existing deterministic seed endpoint, and resolves the seeded actors. Reset verification checks the pinned SHA-256 of `database-seed.json` and compares parsed `database.json` state to that seed; lowdb reserialization may change trailing whitespace without changing data.

Healthy-baseline qualification at the pinned revision passed three consecutive runs per layer:

| Scenario | Result | Durations |
|---|---|---|
| UI transaction history | 3/3 PASSED | 6419.87 ms, 5952.95 ms, 6278.12 ms |
| API invalid-payment rejection | 3/3 PASSED | 2893.61 ms, 2867.68 ms, 2847.73 ms |
| BOTH payment | 3/3 PASSED | 7369.33 ms, 6963.02 ms, 7052.74 ms |

Observed listeners during qualification were frontend `::1:3000` and API `127.0.0.1:3001`; both are loopback. Durations are recorded without thresholds. Final cleanup restored the tracked RWA database file to its pre-start HEAD state and stopped both listeners.

M4 owns controlled defects and triage intelligence. M3 injects no defects, does not classify root cause, and does not modify AgentGuard. Cypress remains independent benchmark evidence.