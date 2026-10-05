# Payment evidence walkthrough

These are **static historical examples**, assembled during M8. No RWA execution,
fault injection or AgentGuard invocation happened during M8. Start with
`01-requirement.md`, then compare the two assertions in `04-testspecs.json` with
the measurements in `05-execution-record.json`.

Business intent → structured contract → TestSpec → execution evidence → triage
→ observational metrics → independent classification evaluation.

| File | Label and origin | What to notice |
|---|---|---|
| `01-requirement.md` | Illustrative input; existing public synthetic REQ-PAY-001 | Positive amount, recipient eligibility, explicit unknowns |
| `02-project-profile.json` | Qualified example; existing M1 profile | Loopback endpoints, pinned target, adapter/reset identity |
| `03-behavioral-contract.json` | Qualified example; approved payment replay | Requirement grounding, source fingerprint, unknowns |
| `04-testspecs.json` | Qualified examples; unchanged positive BOTH and negative API objects in one JSON array | Governed actions/outcomes, no generated code; CLI takes one object, not this array |
| `05-execution-record.json` | Sanitized projection of real M4 controlled payment failure | Expected 3500 minor units, observed 350; amount, identity, participants and state checks; FAILED remains FAILED |
| `06-triage-record.json` | Sanitized projection of that execution's original M4 triage | PRODUCT_DEFECT, referenced mismatch, no invented component root cause |
| `07-quality-metrics.json` | Sanitized projection of the full historical M5 window | Different denominators; not metrics over this one selected case; AgentGuard was unavailable at M5 |
| `08-external-evaluation.json` | Qualified example; unchanged real M6 result for this original M4 case | Classification agreement only, with original source hashes and external oracle provenance |
| `evidence/api-result-metadata.json` | Qualified example; unchanged hashed, bounded API evidence | Measurements only; no raw bodies, credentials, cookies or screenshots |

`provenance.json` records original source hashes, exported byte hashes and exact
transformations. Source labels in the metrics report were anonymized; screenshot
references in execution/triage were removed and an explicit limitation added.
API evidence URIs point to the committed copy, with its original hash intact.
IDs, timestamps, statuses, observations and producer versions retain their
historical meaning. Original source reports are private, ignored and not required
to inspect or validate this directory. Git preserves these files' exact bytes.

The external result's request hash covers the **original** records, not these
edited projections. It must not be presented as independent evaluation of an
M8-regenerated triage. The M5 report covers nine runtime attempts plus two
synthetic triage-only tasks; the M6 population covers eight labeled evaluations,
including synthetic cases, with two separate controls excluded. Neither is a
production-scale sample. Other original source hashes in these reports are
provenance references, not promises that every original artifact is published.

The payment's UI half stopped at a mismatch; the API half supplied concrete failed
outcomes. Retained unresolved-UI limitations are intentional, not edited away to
make the report look better. The profile's reference to Cypress API tests is
qualification provenance; those tests are never extraction/planning context.

From the repository root, inspect safely:

```powershell
Get-Content examples/demo/01-requirement.md
Get-Content examples/demo/05-execution-record.json
Get-Content examples/demo/08-external-evaluation.json
.venv/Scripts/python.exe -B -m pytest tests/test_demo_artifacts.py -q -p no:cacheprovider
```

For offline regeneration and optional live demonstration, follow the
[demo guide](../../docs/DEMO_GUIDE.md). These examples cannot establish broad
coverage, bank-ledger correctness, semantic reasoning quality or release safety.
