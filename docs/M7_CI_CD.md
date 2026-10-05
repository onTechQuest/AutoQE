# M7: shift-left / CI/CD

M7 adds deterministic installation, test, distribution and architecture checks.
It adds no runtime testing intelligence. **CI PASS is not full real-world RWA or
AgentGuard qualification.** M8, deployment, release automation and publishing
are outside this milestone.

## Workflow

`.github/workflows/ci.yml` runs on pull requests, pushes to the current `master`
branch, and `workflow_dispatch`. One `ubuntu-24.04` job uses Python 3.13 and a
15-minute timeout. Concurrency cancels superseded runs for the same PR/branch.
If the default branch is renamed, update the push branch filter.

Checkout fetches full history because the existing frozen-M0 test compares
contracts/interfaces/schemas to `29eadfa`. Node 22 is installed solely for the
existing process-scoped loopback-preload unit test, which opens an ephemeral
loopback listener and closes it. No npm dependencies or RWA are installed.

The job:

1. Installs pip and AutoQE with `python -m pip install ".[test]"`. Setuptools
   comes from the declared build requirements in an isolated build environment.
2. Compiles Python sources and imports the installed metrics and integration
   packages in Python isolated mode (`-I`), excluding checkout/PYTHONPATH fallback.
3. Runs the complete deterministic pytest suite, including existing boundary tests.
4. Builds a wheel using `pip wheel --no-deps`, validates it with
   `scripts/verify_wheel.py`, then reinstalls that wheel without dependencies and
   repeats the isolated import checks.

The wheel validator requires exactly one wheel in its output directory. It
allows only `autoqe/`, `autoqe_integration/`, and the project's versioned
distribution metadata. Every package file must match a current Python source
file, normalizing only CRLF/LF. Required metadata and all package sources must
be present. Duplicate members, unsafe paths, bytecode, caches, unexpected files,
old `integration/`, qualification/tests/reports/examples and external AgentGuard
source are rejected. AutoQE's own AgentGuard provider remains intentionally
inside `autoqe_integration/providers/agentguard/`.

## Architecture and security

Existing tests remain the boundary authority:

- `test_contracts.py`: no AgentGuard dependency or core imports.
- `test_external_evaluation.py`: generic contracts/schema semantics, provider
  isolation, and runtime independence from metrics/integration providers.
- `test_metrics.py`: metrics remain observational; frozen M0 tree hash.
- `test_triage.py`: no runtime qualification dependency; frozen M0 Git comparison.
- `test_execution.py`: execution boundaries and loopback preload behavior.

Permissions are only `contents: read`; checkout disables credential persistence.
There are no repository secrets, PR write permissions, `pull_request_target`,
PR-controlled shell expressions, remote-script execution, firewall changes,
tunnels or external repository clones. Only official actions are used, pinned
to stable major versions. See upstream documentation for
[checkout](https://github.com/actions/checkout),
[setup-python](https://github.com/actions/setup-python) and
[setup-node](https://github.com/actions/setup-node).

The normal ephemeral GitHub checkout token is used by checkout; no application
credentials are configured. Dependency/runtime downloads use normal Python and
GitHub infrastructure. setup-python caches pip downloads keyed by pyproject;
correctness never depends on caches or historical reports. No artifacts are
uploaded, and nothing is published to PyPI or released.

## Standard CI versus external qualification

Standard CI needs only the AutoQE checkout, its Git history, Python dependencies
and Node. It uses committed synthetic fixtures and mocked external providers.
It requires no local Windows paths, RWA checkout, AgentGuard checkout,
`RWA_TEST_PASSWORD`, model credentials or paid API. Playwright's Python package
is installed through project metadata; browser binaries are not installed.
No live model calls, real evaluator invocations or product fault injection run.

M4 external qualification may execute against an explicitly available isolated,
pinned RWA with loopback-only execution and runtime-only credentials. M6 external
qualification requires the separate pinned AgentGuard repository/interpreter.
Their prerequisites and procedures remain in
[M4](M4_CONTROLLED_FAULTS_AND_TRIAGE.md) and
[M6](M6_EXTERNAL_EVALUATION.md). Neither is represented by a placeholder CI job.
A manual dispatch runs standard CI only; it does not enable external evaluation.

## Local reproduction

Use a fresh full Git checkout with Python 3.13 and Node 22 on PATH. Create and
activate a virtual environment (`python -m venv .venv`; activation is platform
specific). From the repository root, run the same commands as CI:

```text
python -m pip install --upgrade pip
python -m pip install ".[test]"
python -m compileall -q src/autoqe autoqe_integration scripts
python -I -c "import autoqe.metrics; import autoqe_integration.contracts; import autoqe_integration.providers.agentguard"
python -B -m pytest -q -p no:cacheprovider
python -m pip wheel --no-deps --wheel-dir dist .
python scripts/verify_wheel.py dist
```

Then install the single wheel using its actual filename:
`python -m pip install --no-deps --force-reinstall dist/autoqe-1.0.0-py3-none-any.whl`
and repeat the isolated import command. Keep the version in that filename aligned
with pyproject. Use a fresh output directory after version changes; stale wheels
cause validation to fail. `build/`, `dist/` and bytecode are ignored. No generated
artifacts belong in commits. No separate local test runner duplicates pytest.

## Limitations

Local M7 verification started from clean commit
`fa1a16164ad42cd70b398dc75d617256e3df7392` (354 baseline tests). The 18 new
wheel-validator tests passed. A fresh full local clone with the M7 changes and
a newly installed Python 3.13 environment passed all 372 tests. Compilation,
isolated installed-package imports, wheel build, validation and wheel reinstall
imports passed. The wheel contained 48 `autoqe` files, eight
`autoqe_integration` files and four distribution metadata files.

The initial verification clone was under `reports/`; an existing test rejects
any ancestor named `reports`, so that attempt had one false positive. Moving the
verification checkout under ignored `build/` resolved it without a test/runtime
change. Verification used Windows locally; the Ubuntu workflow has not run on
GitHub, and no remote was configured. RWA and AgentGuard stayed clean at their
pinned revisions, ports 3000/3001 had no listeners, and live model calls were zero.

The test suite is deterministic with respect to its committed inputs, but
dependency ranges and action major tags are not a fully locked, byte-reproducible
supply chain. Network access is needed for initial dependency/runtime downloads.
Only one hosted OS/Python combination is configured. Full history is required;
a source archive without Git history cannot run the existing Git boundary test.
The validator currently permits only Python source within package roots; adding
legitimate package data requires an explicit validator update and tests.
Unit tests are not a network sandbox. CI does not establish real browser/API
qualification, external evaluator correctness, production readiness or release
approval. Local verification does not prove a GitHub-hosted run succeeded.
