# Public-sharing review

The M8 audit covered source files, proposed documentation/demo artifacts and the
11 commits reachable at checkpoint `55d24f754c5ee9359d3ecc252e9b95fcb398ffe8`.
It was a bounded content review; it did not rewrite repository history.

## Findings

- No real API key, access token, private key/certificate, credential file or
  persisted runtime password was identified in the reviewed source/history.
- No tracked environment file, runtime reports, screenshots, IDE-private
  configuration, wheel/install output or virtual environment was found.
- Credential-assignment searches matched an intentional privacy-test sentinel
  in `tests/test_metrics.py`, not a credential. User-directory searches matched
  rejection patterns in demo artifact tests, not an actual local account path.
- No confidential document, proprietary dataset, private discussion link or
  identifying account information was identified in project file contents.
  Git author metadata remains normal repository attribution, separate from
  runtime evidence and fixture identities.
- Public documentation uses repository-relative links and configurable external
  checkout paths rather than machine-specific absolute directories.
- Ignore rules cover environment files, virtual environments, reports, build,
  dist, bytecode/cache and IDE configuration. The tracked-file inventory was
  reviewed separately because ignore rules do not remove already tracked files.

## Public demo provenance

The walkthrough copies approved inputs and selected qualified outputs.
Execution/triage projections remove screenshot references and relocate content-preserving, LF-normalized
API metadata with separate public and original-source hashes. Metric source labels are anonymized consistently while
numerators/denominators remain unchanged. The external result retains its
original request/source hashes. No fault identity, absolute local path, raw
authentication traffic or unrestricted request/response body is included.
`examples/demo/provenance.json` records transformations and byte hashes; tests
validate models, linkage, hashes and prohibited data/path categories.

Published projections are not byte-identical to the original records and were
not newly evaluated by AgentGuard during M8. Historical producer versions retain
their original meaning. Static examples do not represent new live execution.

## Scope and limits

Manual/pattern-based audits cannot guarantee detection of every secret format
or intellectual-property issue. Ignored reports are not public source; only
selected evidence was reviewed for export. Archives that include ignored files
are outside this audit's scope.

AutoQE is licensed under the [Apache License 2.0](../LICENSE). RWA and AgentGuard
remain separate repositories; their source and dependencies are not redistributed
in the AutoQE wheel. Licensing and attribution requirements for external projects
remain independent. The content audit does not constitute production security
assurance or release certification.
