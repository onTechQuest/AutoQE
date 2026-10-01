# M5 quality metrics

M5 observes artifacts after execution. `autoqe.metrics` imports frozen models,
but extraction, planning, execution, adapters and triage never import metrics.
It does not start an application, invoke a model, rerun triage, apply faults,
integrate AgentGuard, or make release decisions.

## Evidence and report

`MetricsManifest` version 1.0 names local files relative to the manifest, with
stable artifact identifiers and kinds: contract, spec, execution, triage,
qualification, usage. No directories are scanned. `load_evidence` validates
frozen artifact models, identities and case links, then returns a
`MetricsEvidenceBundle`. Missing referenced files are errors. An intentionally
unproduced stage has a null/omitted case reference; this counts as incomplete.

Each case names its required stages, whether runtime execution was attempted,
and optionally external target-state/expected-classification labels and their
qualification source. Synthetic triage evidence must declare `kind=SYNTHETIC`
and `execution_attempted=false`. Its required stages can be triage only.
Duplicate case IDs, repeated runtime executions, duplicate artifact paths,
ambiguous contract identities, mixed projects, contradictory artifact links,
invalid non-TestSpec schemas and unsupported manifest versions fail closed.

Malformed JSON and schema-invalid TestSpecs are retained as identified invalid
inputs with file hashes and sanitized diagnostic categories. Raw invalid values
and Pydantic validation inputs are never copied into reports or CLI errors.
Valid TestSpecs must explicitly reference selected contracts and their requirement
IDs. Different input variants of the same test ID may be evaluated separately.

Qualification sources are externally authored JSON metadata, not runtime inputs.
Their factual truth is trusted, not independently reconstructed. Optional `checks`
corroborate exact values using explicit source identifiers and JSON pointers.
The M4 integration manifest checks saved statuses/classifications against the
actual records, and its creation verified paired TestSpec byte hashes. Fault
controller logic is neither imported nor duplicated.

Usage is a separate bounded-window artifact. TELEMETRY requires actual call and
token counts matching its qualification source. NO_LIVE_PROCESSING requires zero
calls corroborated by its source and an explicit replay/deterministic-only
attestation. Only then are live tokens zero. No usage artifact means unavailable,
even if supplied TestSpecs mention replay. Usage cannot span multiple windows.

`QualityMetricsReport` is a non-M0 model, version 1.0, with project/window IDs,
nine independent metrics, artifact-ID-to-SHA-256 sources and limitations. Metric
records include definition, numerator/denominator where applicable, value, unit,
sample size, availability, source references and supporting/excluded case IDs.
Ratios range from 0 to 1. Usage is a token count with live call count as sample
size. Reports omit timestamps and sort JSON keys. No aggregate score, weights,
confidence estimates, thresholds or release gates exist.

Availability:

- AVAILABLE: observed numerical result, including genuine zero.
- NOT_APPLICABLE: ratio has no eligible denominator in the selected window;
  value is null, counts remain zero, and the reason is explicit.
- UNAVAILABLE: telemetry or an evaluation capability has no evidence; value and
  unavailable numerator/denominator are null. AgentGuard is always unavailable
  until separately authorized M6 integration.

## Exact metric definitions

| Metric | Numerator / denominator or count |
|---|---|
| Requirement traceability | Unique requirement IDs referenced by valid evaluated TestSpecs / unique requirement IDs in selected BehavioralContracts. Includes uncovered IDs; no inferred semantic coverage. |
| TestSpec schema validity | Inputs validating against frozen TestSpec / all selected TestSpec inputs, including malformed JSON. Counting unit is explicit input artifact, not executions. |
| Test executability | Runtime case attempts meeting the conditions below / runtime case attempts. Synthetic triage-only fixtures excluded. |
| Healthy false-positive rate | Eligible healthy cases signaling assertion failure or PRODUCT_DEFECT/TEST_DEFECT triage / externally HEALTHY cases with successful readiness/setup and supported semantics. Environment, data and unsupported failures excluded. |
| Controlled-defect detection | Fault attempts producing a concrete observed, hashed-reference-backed assertion mismatch after successful setup and meaningful execution / externally labeled controlled fault attempts. Missing results, passed faults and setup failures are missed, not detections. |
| Triage accuracy | Actual classification equal to external expected classification / externally labeled cases, including missing triage as incorrect. Includes per-class support, confusion counts and individual expected/actual values. |
| Task completion | Cases producing all explicitly required valid artifacts and terminal execution results / attempted evaluation cases. Required stages are declared individually, not inferred from status. |
| AI token usage | Actual observed live tokens; zero only with the explicit no-live attestation above. Actual calls are reported separately. No text-length estimates. |
| AgentGuard pass rate | UNAVAILABLE: integration planned for M6; no evaluation dataset/result exists for this window. Never reported as 0%. |

Executable means a valid linked TestSpec and ExecutionRecord, explicit PASSED
capability/readiness/setup evidence for every provider setup group, no
contradictory failed setup stage, completed PASSED or assertion-FAILED terminal
status, and meaningful SUBMIT/ASSERT/WAIT_FOR_STATE execution. An observed failed
ASSERT can establish execution. Required outcome IDs must appear exactly once,
match expected descriptions and resolve PASSED/FAILED consistently with terminal
status. Unknown, skipped, erroneous, absent or mismatched outcomes are excluded.
Provider errors, unsupported semantics and incomplete execution are excluded with
reasons. Passed records must also account for all steps as passed. Legitimate
assertion failure can stop subsequent steps.

For composite records, final normalized assertion results are the counting unit:
one provider may resolve an outcome left unresolved by another. This does not
claim every provider independently completed its assertions. Concrete fault
detection can still be established when other outcomes are unresolved; the
executability metric separately exposes that incompleteness. Evidence reference
hashes are required for detection, but calculators do not interpret screenshots
or read implicitly referenced evidence files. M4 integration separately checked
their existence and hashes.

Task completion is artifact production, not correctness. Execution stages require
completed timestamps and PASSED/FAILED/ERROR/SKIPPED results; INCOMPLETE is not
terminal for this metric. Synthetic triage-only tasks can finish with a valid
triage of an incomplete input record.

## Reproduction

From a fresh checkout with AutoQE's normal dependencies:

```powershell
.venv/Scripts/python.exe -B scripts/report_quality_metrics.py --evidence-manifest examples/metrics/manifest.json --output reports/metrics
.venv/Scripts/python.exe -B -m pytest tests/test_metrics.py -q -p no:cacheprovider
```

The small `examples/metrics` fixture uses a different project identity and is
entirely synthetic. It requires no RWA, AgentGuard, ignored historical reports,
browser, credentials or model access. Output is `quality-metrics.json` in the
requested directory. Exit 2 indicates invalid evidence/report or an output error;
exit 0 means a report was generated, not a quality gate was passed.

For actual qualification, explicitly map saved artifacts into the same manifest.
The M5 integration used `reports/m5-integration/manifest.json`, referencing the
saved `reports/m4-qualification-20260930/qualification.json` and its records.
The two synthetic triage artifact paths absent from the original M4 summary were
explicitly curated into this manifest. No runtime folder scanning is part of the
metrics engine. Historical runtime reports and the integration manifest remain
ignored and are not fresh-checkout dependencies.

## Scope and interpretation

The integration window covers one payment requirement, three TestSpec inputs
(positive, negative and unsupported variant), nine real runtime attempts and two
synthetic triage-only cases. Three controlled faults are not a representative
defect population. Triage class supports are three PRODUCT_DEFECT and one each
ENVIRONMENT_FAILURE, DATA_FAILURE, UNSUPPORTED_BEHAVIOR, UNKNOWN and TEST_DEFECT.
Healthy cases have no external expected triage label and are excluded from triage
accuracy. No statistical confidence or broad product coverage is implied.
