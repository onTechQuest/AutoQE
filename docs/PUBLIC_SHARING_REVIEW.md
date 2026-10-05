# M8 public-sharing review

Scope: current tracked files, proposed M8 files, and the 11 commits reachable
from local refs at preflight `55d24f754c5ee9359d3ecc252e9b95fcb398ffe8`.
No history was rewritten and no remote operation was performed.

## Findings

- No real API key, access token, private key/certificate, credential file or
  persisted runtime password was identified in the reviewed source/history.
- No tracked `.env`, runtime reports, screenshots, IDE-private configuration,
  wheel/install output or virtual environment was found.
- Credential-assignment search matched an intentional negative privacy-test
  sentinel in `tests/test_metrics.py`; it is not a credential. Personal-path
  search matched rejection patterns in the new demo artifact test, not a person's
  path. Credential variable names and privacy documentation are intentional.
- No private chat/conversation link, company-confidential document, proprietary
  dataset or personal identifier was identified in project file contents.
  Git author metadata is normal repository attribution and remains unchanged;
  the owner should review their author identity before publishing history.
- Recruiter-facing docs use repository-relative links. Existing historical
  milestone documents may describe generic local project paths; they are not
  private user-profile links.
- `.gitignore` covers `.env` variants, `.venv`/`venv`/`env`, reports, build, dist,
  Python bytecode/cache and `.vscode`. Ignore rules do not remove previously
  tracked files; the file inventory was checked separately.

## Public demo provenance

The walkthrough copies approved inputs and selected real qualified outputs.
Execution/triage projections remove screenshot references and relocate an exact
hashed API metadata file. Metrics source labels are anonymized consistently;
numerators/denominators remain unchanged. The normalized external result is
unchanged and retains original request/source hashes. No fault identity, local
absolute path, raw authentication traffic or unrestricted request/response body
is included. `examples/demo/provenance.json` labels transformations and byte hashes;
tests validate models, linkage, hashes and forbidden data/path categories.

These artifacts do not pretend that a live system ran during M8. Published
projections are not byte-identical to original records and are not newly evaluated
by AgentGuard. Historical producer versions are intentionally retained.

## Limits and owner decisions

This is a bounded manual/pattern-based source/history audit, not a guarantee that
all possible secret formats or intellectual-property concerns can be detected.
No scanner framework or v2 security capability was added. Ignored local reports
were not swept into public source; only selected evidence was reviewed for export.
Do not publish the working directory or zip ignored files indiscriminately.

No LICENSE exists. M8 does not choose a license or grant third-party rights.
The owner must choose a license and review attribution/distribution rights before
public release. RWA and AgentGuard remain separate repositories; no external
source or dependencies are redistributed in the AutoQE wheel. The public-sharing
content review passes within this scope; release authorization remains separate.
