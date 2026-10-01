# M4 Controlled Faults, Evidence, and Triage

M4 adds deterministic triage using the frozen `TriageRecord` and a separate,
bounded reference qualification controller. No live model, evaluator integration,
mutation platform, score, or release gate is introduced.

## Runtime boundary

`scripts/triage_execution.py` accepts only ProjectProfile, TestSpec, ExecutionRecord,
and an output path. The project-agnostic `autoqe.triage` package reads no controller
metadata, target source, environment configuration, or external evidence files.
It reasons from normalized assertions, setup evidence, and evidence references.
The provider hashes retained API evidence and includes bounded transaction
measurements: amounts, states, counts, identity hashes, and participant-match
booleans. It retains no raw authentication traffic or unrestricted payloads.

The execution adapter reports explicit reference, readiness, reset, and fixture
stages. Transport failures are environment evidence; seed/fixture verification
failures after readiness are data evidence. Original exception messages and
private payloads are not propagated into records.

Source identity and runtime data location are separate adapter concerns.
`--reference-root` verifies the clean pinned source checkout; `--rwa-root` locates
the deployed seed/runtime data. Neither is a fault selector. When the paths
differ, reference verification attests the baseline source, not the deployed
source contents. Deployment provenance is owned by the external controller.
Ordinary M3 execution defaults both paths to the same checkout.

## Deterministic triage rules

1. Concrete artifact identity, assertion-definition, duplicate-ID, or contradictory
   pass-status evidence establishes TEST_DEFECT. This rule identifies a test or
   reporting inconsistency, not arbitrary locator failures.
2. Explicit environment-stage failure evidence establishes ENVIRONMENT_FAILURE.
3. Explicit reset/fixture failure with readiness evidence establishes DATA_FAILURE.
4. Explicit capability rejection establishes UNSUPPORTED_BEHAVIOR.
5. PRODUCT_DEFECT requires FAILED/ASSERTION_FAILURE, supported semantics, verified
   setup for every required provider, a successful submit reaching the target,
   and an observed failed assertion matching the TestSpec with hashed evidence.
   Provider/result errors prevent this inference.
6. Insufficient, ambiguous, and opaque provider evidence remains UNKNOWN. Healthy
   executions also use UNKNOWN with an explicit no-observed-failure rationale;
   the frozen classification enum intentionally has no healthy category.

Triage preserves references and expected/observed assertion IDs. It does not
invent component-level root causes or confidence scores. These rules trust the
normalized provider evidence; they are not cryptographic attestations of runtime
truth, and the triage service does not independently interpret screenshots.

## External controlled experiments

`qualification/m4/profiles.json` defines exactly three bounded product regressions:

| Profile | Patch point | Existing semantic test |
|---|---|---|
| Missing recipient default | Transaction route defaults an absent recipient to the requester before validation | Invalid-payment rejection |
| Payment unit conversion | Transaction storage multiplies the submitted amount by 10 instead of 100 | BOTH payment |
| Payment completion state | Completion update leaves the transaction pending | BOTH payment |

Expected behavior comes from approved requirements/contracts, never the RWA
Cypress suite. Repository TestSpec fixtures are derived from approved planning
replays and validated against the unchanged TestSpec model.

The controller creates a new detached Git worktree at the pinned revision for
each healthy and faulty execution. Paths use random identifiers. Dependencies
are reused through a temporary node_modules junction; the junction is removed
before the worktree is discarded. The canonical source/data checkout is never
the running target. Each patch requires a unique exact match and the controller
rejects activating a second patch on the same target.

Each target starts under the existing process-scoped loopback preload. The
controller inspects IPv4 and IPv6 listeners, invokes a fresh execution subprocess,
then a separate triage subprocess. Worker arguments are normal artifact paths;
worker environments are allowlisted and contain no profile identity or expected
classification. Credentials exist only in the execution worker environment.
The triage worker receives no credential. Source patches, labels, and expected
classifications stay in the controller; only ordinary target behavior reaches
AutoQE. Runtime artifact paths contain no active profile identity.

The external report joins healthy/faulty results only after runtime triage and
compares TestSpec hashes. It records factual counts and expected/actual categories.
It is separate from all artifacts consumed by triage.

Additional qualification covers stopped-service readiness, a seed fingerprint
mismatch in a disposable target, valid unsupported semantics, insufficient
synthetic evidence, and a synthetic test-side assertion-definition mismatch.
Synthetic evidence cases are explicitly labeled and are not presented as live
product failures.

## Commands

Triage an existing execution without starting the target:

```powershell
.venv/Scripts/python.exe scripts/triage_execution.py `
  --project-profile examples/rwa/project-profile.json `
  --test-spec examples/rwa/execution/payment.json `
  --execution-record <execution.json> `
  --output reports/triage/<record>.json
```

Run the bounded Windows qualification controller with an unused output directory:

```powershell
.venv/Scripts/python.exe scripts/qualify_m4.py `
  --rwa-root C:/Projects/autoqe-reference-rwa `
  --output reports/<new-run-directory>
```

The controller uses the existing Node/Yarn dependencies and seeded runtime
credential setting. It does not install packages, modify firewall rules, expose
public listeners, or call a model. The final handoff records observed results;
unit tests alone do not establish M4 completion.
