# AutoQE

AutoQE is a vendor-neutral autonomous Quality Engineering orchestration framework that converts product intent and change context into risk-based executable test specifications, delegates execution to existing testing ecosystems, analyzes evidence, and can be independently evaluated by AgentGuard.

**AutoQE v1 is an MVP under construction.** This milestone freezes contracts only; it does not implement planning, execution, agents, or runtime integrations.

The primary reference target is the [Cypress Real World App](https://github.com/cypress-io/cypress-realworld-app), pinned for qualification at `9dfcb9869533ce8a8963c556facc0d80457f9d39`. Its existing Cypress tests remain independent benchmark/oracle evidence and are not inputs to AutoQE generation.

AutoQE artifacts may later be evaluated by AgentGuard through an external adapter. AutoQE does not import or depend on AgentGuard at runtime.

The initial implementation uses Python 3.13, Pydantic v2, and offline pytest contract checks:

```powershell
py -3.13 -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[test]"
.venv/Scripts/python.exe -m pytest tests -q
```

M1 adds bounded Markdown requirement extraction with an offline replay provider:

```powershell
.venv/Scripts/python.exe -m autoqe.cli.extract_contract `
	--project-profile examples/rwa/project-profile.json `
	--requirements examples/rwa/requirements/payments.md `
	--provider replay `
	--output reports/contracts
```

See [M0 architecture and contracts](docs/M0_ARCHITECTURE_CONTRACTS.md), [M1 context and contracts](docs/M1_CONTEXT_AND_CONTRACTS.md), and [M1 reference qualification](docs/M1_REFERENCE_QUALIFICATION.md).

M2 adds bounded, offline risk-based TestSpec planning from a validated BehavioralContract:

```powershell
.venv/Scripts/python.exe scripts/plan_tests.py `
	--project-profile examples/rwa/project-profile.json `
	--contract examples/rwa/plans/contracts/payment.json `
	--provider replay
```

See [M2 risk-based planning](docs/M2_RISK_BASED_PLANNING.md). Planning does not execute tests.

M3 adds deterministic, loopback-only Playwright/httpx execution against the pinned RWA. See [M3 execution providers](docs/M3_EXECUTION_PROVIDERS.md). Execution requires the seeded test password through `RWA_TEST_PASSWORD` and the process-scoped loopback preload described there.

The M3 CLI executes exactly one TestSpec and writes normalized evidence under `reports/executions/`:

```powershell
.venv/Scripts/python.exe scripts/execute_testspec.py `
	--project-profile examples/rwa/project-profile.json `
	--test-spec reports/plans/contract-payment-valid-001/testspec-02-contract-payment-valid-001-negative.json `
	--provider api
```