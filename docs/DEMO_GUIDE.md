# Guided demo: REQ-PAY-001

Use the **offline artifact tour** for a self-contained demonstration: skip live steps 1–2,
9 and 11, inspect their committed alternatives, and run extraction, planning,
triage and synthetic metrics locally. Nothing in that route needs credentials,
RWA, AgentGuard or a live model. The static failure and external result are
historical qualification, never presented as generated during this demo.

The **optional live route** needs Windows, Python 3.13, Node 22, Yarn Classic
1.22.22, the clean pinned RWA with existing node_modules, and installed Playwright
Chromium (`.venv/Scripts/python.exe -m playwright install chromium`). AgentGuard
needs its separate existing interpreter only if rerunning step 16. Do not install
AgentGuard into AutoQE. Dependency provisioning is separate from the demonstration.

Run commands from the AutoQE repository root in PowerShell. After the README
installation, initialize a fresh output folder in the main terminal:

```powershell
$AutoQERoot = (Get-Location).Path
$Python = Join-Path $AutoQERoot '.venv/Scripts/python.exe'
$Demo = Join-Path $AutoQERoot ('reports/demo-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Demo | Out-Null
$Profile = 'examples/rwa/project-profile.json'
$PaymentSpec = 'examples/rwa/execution/payment.json'
$ApiSpec = 'examples/rwa/execution/invalid-payment.json'
```

Do not run against valuable data: each provider reseeds the disposable target.
Each step identifies its output artifact and the engineering boundary it demonstrates.

## 1. Start RWA safely — optional live route

In a **second PowerShell terminal**, also at the AutoQE root, use the existing
healthy-target context manager from M4. It creates a disposable pinned worktree,
reuses dependencies through a junction, starts Node with the loopback preload,
checks actual listeners, and removes the isolated target on normal exit. No fault
is applied. The canonical RWA tracked source/data stays untouched; worktree
metadata is temporarily registered by the existing harness.

```powershell
$Python = (Resolve-Path '.venv/Scripts/python.exe').Path
$RwaRoot = (Resolve-Path '../autoqe-reference-rwa').Path
$YarnJs = Join-Path $env:APPDATA 'npm/node_modules/yarn/bin/yarn.js'
if (-not (Test-Path -LiteralPath $YarnJs)) { throw 'Set YarnJs to the installed Yarn Classic CLI file' }
$TargetParent = Join-Path (Get-Location).Path ('reports/demo-target-' + [guid]::NewGuid().ToString('N'))
$TargetSession = @'
import sys
from pathlib import Path
from qualification.m4.harness import IsolatedTarget
with IsolatedTarget(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])) as target:
    target.start()
    print('Runtime path:', target.path, flush=True)
    print('Actual listeners:', target.observed_listeners, flush=True)
    input('Keep this terminal open. Press Enter only after the demo to stop RWA: ')
'@
& $Python -B -c $TargetSession $RwaRoot $TargetParent $YarnJs
```

Artifact: a printed disposable runtime path and actual listeners. Accept only
`127.0.0.1:3001` and loopback port 3000 (`[::1]` or `127.0.0.1`). Existing occupied
ports, a dirty/unpinned reference, or a non-loopback bind fail closed. Do not bypass
the guard or change firewall rules. Keep the controller terminal open; do not
close it forcibly. These are PowerShell/Python equivalents, not Unix seed scripts.

Source identity and runtime data location are separate. Repeatable setup and
actual-listener verification establish the environment boundary; a localhost URL
alone does not establish it.

## 2. Show RWA manually — optional live route

In the main terminal:

```powershell
$RwaRoot = (Resolve-Path '../autoqe-reference-rwa').Path
$RuntimeRoot = Read-Host 'Paste the disposable runtime path from the controller'
Start-Process 'http://localhost:3000'
```

Artifact: the local RWA browser page. Sign in manually only with the public seeded
demo account if appropriate; never screen-share or record credential entry.
The payment UI is the target of the execution providers. This is the product under test. AutoQE orchestrates tests
of it; AutoQE is not a replacement UI framework. Offline alternative:
`Get-Content examples/demo/README.md`—no screenshot or live-page claim.

## 3. Inspect the requirement

```powershell
Get-Content examples/rwa/requirements/payments.md
```

Artifact: REQ-PAY-001 Markdown. The requirement retains explicit unknowns around fees, limits
and insufficient funds. Expected behavior comes from product intent. Missing
policy is retained as uncertainty, not invented by a generator.

## 4. Inspect ProjectProfile

```powershell
Get-Content $Profile
```

Artifact: pinned revision, local URLs, capabilities, reset and adapter identities.
The Cypress-test reference is qualification provenance, not model input.
Project-specific environment knowledge is declarative and adapter-owned. It does
not leak into a target-specific core planner.

## 5. Generate a BehavioralContract

```powershell
& $Python -m autoqe.cli.extract_contract --project-profile $Profile `
  --requirements examples/rwa/requirements/payments.md --provider replay `
  --output (Join-Path $Demo 'contract.json')
if ($LASTEXITCODE -ne 0) { throw 'Extraction failed' }
```

Artifact: `$Demo/contract.json`; CLI reports grounding validation and one unknown.
Replay supplies an approved structured output without a live LLM. Grounding and
schema validation still run, so the demonstration is repeatable.

## 6. Inspect the contract and approved planning checkpoint

```powershell
Get-Content (Join-Path $Demo 'contract.json')
Get-Content examples/rwa/plans/contracts/payment.json
```

Artifact: generated contract alongside the approved M2 input. **Existing fixture
limitation:** the fresh extraction says `Approved offline replay; no model was
called.` while M2's checkpoint says `Approved offline M1 replay; no model was
called.` All other parsed fields match. Planning fingerprints the complete input,
so the fresh file does not match its approved replay key. Step 7 explicitly uses
the M2 checkpoint; this is not an uninterrupted fresh-artifact chain.
Fail-closed replay matching makes even metadata drift visible. This demo uses
the approved checkpoint rather than weakening the boundary.

## 7. Plan TestSpecs

```powershell
& $Python scripts/plan_tests.py --project-profile $Profile `
  --contract examples/rwa/plans/contracts/payment.json --provider replay `
  --output (Join-Path $Demo 'plans')
if ($LASTEXITCODE -ne 0) { throw 'Planning failed' }
$PlanDir = Join-Path $Demo 'plans/contract-payment-valid-001'
```

Artifact: three TestSpecs and `planning-summary.json`: positive BOTH, negative API
and state-transition BOTH. Risk and coverage policy determine the scenarios;
the governed output is a TestSpec, not arbitrary generated test code.

## 8. Inspect risk, layer and expected behavior

```powershell
Get-Content (Join-Path $PlanDir 'planning-summary.json')
Get-Content (Join-Path $PlanDir 'testspec-01-contract-payment-valid-001-positive.json')
Get-Content (Join-Path $PlanDir 'testspec-02-contract-payment-valid-001-negative.json')
```

Artifact: HIGH risk, layer rationales, expected outcomes and unknowns. Execution
below uses the unchanged qualified copies in `examples/rwa/execution/`; their
positive/negative semantics match these planned cases. The state-transition case
is planned, not claimed to be a separately qualified executable scenario.
Coverage, layer selection and executable capability are separate decisions.

## 9. Execute the API case — optional live route

Enter the seeded test password into a secure prompt; never put it in a command,
file or transcript. The short conversion exists only to supply the process
environment and is removed in `finally`:

```powershell
$Credential = Read-Host 'Seeded RWA demo password' -AsSecureString
try {
  $env:RWA_TEST_PASSWORD = [System.Net.NetworkCredential]::new('', $Credential).Password
  & $Python scripts/execute_testspec.py --project-profile $Profile --test-spec $ApiSpec `
    --provider api --rwa-root $RuntimeRoot --reference-root $RwaRoot `
    --output (Join-Path $Demo 'api') --evidence-output (Join-Path $Demo 'api-evidence')
  if ($LASTEXITCODE -ne 0) { throw 'API execution did not pass; inspect normalized record' }
} finally {
  Remove-Item Env:RWA_TEST_PASSWORD -ErrorAction SilentlyContinue
  $Credential.Dispose()
}
```

Artifact: an `execution-*.json` under `$Demo/api/<test-id>/` plus sanitized evidence.
A healthy target is expected to reject the invalid payment without creating a
transaction. The assertion checks business outcomes after deterministic setup,
not merely whether an HTTP request completed. Offline: inspect the historical execution in step 10.

## 10. Inspect ExecutionRecord and evidence

```powershell
# Live route:
Get-ChildItem (Join-Path $Demo 'api') -Recurse -Filter 'execution-*.json' | Get-Content
# Self-contained static route: this is a real historical controlled failure:
Get-Content examples/demo/05-execution-record.json
Get-Content examples/demo/evidence/api-result-metadata.json
```

Artifact: normalized statuses, assertion IDs, reset identity and hashed evidence.
The static example expected 3500 minor units but observed 350; status remains FAILED.
A failure signal requires an explicit expectation, an observation and evidence
that the environment/setup was trustworthy.

## 11. Execute the Playwright-supported payment — optional live route

```powershell
$Credential = Read-Host 'Seeded RWA demo password' -AsSecureString
try {
  $env:RWA_TEST_PASSWORD = [System.Net.NetworkCredential]::new('', $Credential).Password
  & $Python scripts/execute_testspec.py --project-profile $Profile --test-spec $PaymentSpec `
    --provider playwright --rwa-root $RuntimeRoot --reference-root $RwaRoot `
    --output (Join-Path $Demo 'both') --evidence-output (Join-Path $Demo 'both-evidence')
  if ($LASTEXITCODE -ne 0) { throw 'Payment execution did not pass; inspect normalized record' }
} finally {
  Remove-Item Env:RWA_TEST_PASSWORD -ErrorAction SilentlyContinue
  $Credential.Dispose()
}
```

Artifact: one composite ExecutionRecord and UI/API evidence. **The positive spec
is BOTH**, so the existing CLI runs Playwright and API sequentially regardless of
the provider flag; it resets before each half. The provider is **headless** and has
no headed/slow-motion CLI flag. Complementary UI and API observations share a
stable artifact contract; the CLI exposes no additional UI demonstration controls.

## 12. Inspect browser behavior and evidence

```powershell
Start-Process 'http://localhost:3000'
Get-ChildItem (Join-Path $Demo 'both-evidence') -Recurse -Filter '*.png'
Get-ChildItem (Join-Path $Demo 'both') -Recurse -Filter 'execution-*.json' | Get-Content
```

Artifact: manual browser view, local evidence filenames and composite record.
Refresh/re-login after reseeding if necessary. Inspect local screenshots only after
checking them; they are not automatically safe to publish. A manual browser is not
the headless automation session and final API reset affects visible data.
Evidence illustrates observed behavior; the normalized assertions determine the
recorded result. Offline: `Get-Content examples/demo/05-execution-record.json`.

## 13. Triage an execution

The offline command classifies the published historical failure, without RWA:

```powershell
& $Python scripts/triage_execution.py --project-profile $Profile --test-spec $PaymentSpec `
  --execution-record examples/demo/05-execution-record.json --output (Join-Path $Demo 'triage.json')
```

Artifact: `$Demo/triage.json`, PRODUCT_DEFECT. For a live run, use the actual
execution path and its matching TestSpec; healthy runs yield UNKNOWN with a
no-observed-failure rationale. Triage receives only governed artifacts, never the
controller's fault label. It does not invent component-level root cause.

## 14. Inspect TriageRecord

```powershell
Get-Content (Join-Path $Demo 'triage.json')
Get-Content examples/demo/06-triage-record.json
```

Artifact: regenerated triage and original static projection. IDs/timestamps can
differ; compare category and expected/observed references. A category must be
supported by evidence. UNKNOWN is a valid honest result, not a hidden pass.

## 15. Produce and view quality metrics

```powershell
& $Python scripts/report_quality_metrics.py --evidence-manifest examples/metrics/manifest.json `
  --output (Join-Path $Demo 'synthetic-metrics')
Get-Content (Join-Path $Demo 'synthetic-metrics/quality-metrics.json')
Get-Content examples/demo/07-quality-metrics.json
```

Artifacts: a newly calculated **synthetic fixture** report and a static real M5
window projection. They are different populations, not metrics for this live demo.
The synthetic traceability is 1/2; M5's historical window has its own denominators.
Metrics expose population and missing evidence. Fixture results and real
qualification use distinct populations and must be interpreted separately.

## 16. View or optionally rerun external evaluation

The default command needs no evaluator:

```powershell
Get-Content examples/demo/08-external-evaluation.json
```

Artifact: the real historical M6 result for the original M4 case; source hashes
refer to original records, not regenerated M8 triage. If the separate qualified
AgentGuard environment is explicitly available, optionally run:

```powershell
$AgentGuardRoot = (Resolve-Path '../AgentGuard').Path
$AgentGuardPython = Join-Path $AgentGuardRoot '.venv/Scripts/python.exe'
& $Python scripts/qualify_m6.py --evidence qualification/m6/fixtures/evidence.json `
  --expectations qualification/m6/fixtures/expectations.json `
  --evaluator-root $AgentGuardRoot --evaluator-python $AgentGuardPython `
  --output (Join-Path $Demo 'external-evaluation')
```

Expected artifacts: per-case results, metrics manifest/report and qualification
summary. The output directory must not already exist. This reruns the fixed M6
population, not the new live demo records: eight classification passes, positive
control passes, negative control fails. Independent evaluation is a provider
boundary. This dimension measures label agreement, not all AI reasoning.

## 17. Explain healthy versus controlled-defect qualification

```powershell
Get-Content docs/M4_CONTROLLED_FAULTS_AND_TRIAGE.md
Get-Content examples/demo/README.md
```

Artifact: qualification method and truthful projection notes. Historical M4 used
paired healthy/faulty targets with identical TestSpec hashes, three product faults,
separate labels and no controller identity in runtime triage. No fault injection
is needed for this demonstration. Healthy false positives and controlled missed
defects are distinct risks. A small experiment demonstrates a method, not broad
production effectiveness.

## 18. Stop RWA and verify ports — live route only

Press Enter in the controller terminal from step 1. Its context manager stops the
owned process tree, checks listeners, unlinks the dependency junction and discards
the disposable worktree. Then in the main terminal:

```powershell
$Listeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop |
  Where-Object { $_.LocalPort -in 3000,3001 })
if ($Listeners.Count) { throw 'RWA ports still listening; inspect the owned controller before continuing' }
git -C $RwaRoot status --short
git -C $RwaRoot rev-parse HEAD
Remove-Item Env:RWA_TEST_PASSWORD -ErrorAction SilentlyContinue
```

Expected artifact: no listeners, clean canonical RWA and pinned SHA. Windows may
require an elevated read-only listener check. Do not terminate unrelated processes.
Cleanup and isolation are part of repeatability; a demonstration must leave its
reference environment trustworthy.

## Opt-in report housekeeping

Stop writers and preserve required evidence first. Preview, then explicitly confirm:

```powershell
& $Python scripts/cleanup_reports.py
& $Python scripts/cleanup_reports.py --older-than-days 30
& $Python scripts/cleanup_reports.py --older-than-days 30 --confirm
& $Python scripts/cleanup_reports.py --all
# Only after reviewing the all-preview:
# & $Python scripts/cleanup_reports.py --all --confirm
```

Only this checkout's reports tree is eligible; its root remains. Files are selected
by modification age; directories are removed only when old enough and all children
are selected. Links/junctions/reparse points and nested source/examples/docs/
qualification/.git/venvs cause refusal before deletion. Embedded old verification
checkouts may therefore block cleanup; move/archive them deliberately outside this
utility's scope. Exit 0 means successful preview/cleanup (including absent reports);
exit 2 means invalid options or safety/I/O refusal. An I/O failure after deletion
starts may leave partial progress; rerun a preview. This is not protection against
a hostile concurrent filesystem writer and no automatic execution cleanup is added.

## Verification scope

M8 runs CLI help, offline extraction, approved-checkpoint planning, static-evidence
triage, synthetic metrics and artifact tests. Live startup/execution commands are
checked against the existing harness/provider code, but are not rerun in M8.
No new live UI/API or AgentGuard qualification, GitHub-hosted CI or release is claimed.
