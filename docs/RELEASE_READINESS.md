# v1.0.0 release readiness

Distribution metadata and `autoqe.__version__` are `1.0.0`; the proposed release
tag is `v1.0.0`. The repository is public, Apache-2.0 is present, and GitHub-hosted
CI has passed on the latest master checkpoint. The v1.0.0 tag/release has not
been created.

## Repository and release state

| Item | State |
|---|---|
| Package version | 1.0.0; frozen schema version 1.0 unchanged |
| Historical provenance | Original producer versions and source hashes retained |
| License | [Apache License 2.0](../LICENSE) |
| Repository | Public: `https://github.com/onTechQuest/AutoQE.git`, configured as origin |
| Hosted CI | Passed on the latest master checkpoint; standard deterministic checks only |
| Public sharing | Bounded audit documented in [public release review](PUBLIC_RELEASE_REVIEW.md) |
| External repositories | Separate pinned RWA and AgentGuard environments |
| Operational tooling | Cleanup is opt-in housekeeping, not new QE functionality |

Release publication remains a separate step. The release revision must retain
reviewed changes and passing CI; hosted CI does not perform real RWA or AgentGuard
qualification and does not itself create a tag or release.

## Demo provenance integrity

The documentation review identified stale public hashes after LF normalization.
All nine published artifact hashes now cover canonical LF bytes; files 01-03 also
have a final newline that was absent from the original sources. Public API evidence
references in execution/triage now hash the LF copy they actually reference.
Original source hashes remain separate and unchanged. The external evaluation's
original request hash and source/evidence lineage are unchanged.

The previously failing strict provenance test passes, and all six focused demo/
documentation checks pass, including canonical-byte, nested-reference and original
lineage regression checks. No qualified result values or runtime code changed.

## Demonstration limitations

The demo uses the approved M2 planning checkpoint. Fresh M1 extraction has one
different historical limitation string, causing exact planning replay matching
to reject it. This documented fixture mismatch means the demo is not a continuous
fresh-artifact pipeline. Aligning the fixtures requires explicit review without
weakening replay matching.

No live-model production qualification, broad target coverage, statistical
effectiveness claim, production security assurance or comprehensive reasoning
evaluation accompanies the bounded v1 qualification.

## Recorded local validation

Final M8 checks passed: 45 focused tests (23 cleanup, four demo/provenance/version,
18 wheel checks); 399 tests in a fresh full local checkout without historical
reports; 39 local Markdown links; PowerShell demo syntax; seven CLI help commands;
offline extraction, approved-checkpoint planning, static-evidence triage and
synthetic metrics. The 1.0.0 wheel contained 48 core, eight integration and four
metadata files, and passed isolated installed-wheel imports/version checks.

The bounded source/history audit and diff checks passed. M0 was unchanged.
RWA was clean at `9dfcb9869533ce8a8963c556facc0d80457f9d39`, AgentGuard at
`ee104f90fe9c0c23f320ab110fdd2c9adf20d37c`, and ports 3000/3001 had no listeners.
Live model calls: zero. No live external qualification or hosted CI was part of
those local checks. These observations describe the recorded validation window.

## Release scope

AutoQE v1 provides a governed requirement-to-evidence QE pipeline, qualified on
a bounded pinned reference target with deterministic replay, UI/API execution,
evidence-based triage, metrics and external classification evaluation. It includes
self-contained CI and a provenance-labeled guided demonstration.

See [changelog](../CHANGELOG.md), [architecture](ARCHITECTURE.md),
[demonstration](DEMO_GUIDE.md), [public release review](PUBLIC_RELEASE_REVIEW.md)
and [project handoff](PROJECT_HANDOFF.md) for evidence and limitations.
