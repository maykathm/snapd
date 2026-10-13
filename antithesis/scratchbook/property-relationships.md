---
sut_path: /home/katie.may@canonical.com/source/snapd
commit: e88ec08852fbc8af019dc39e22097e5720aa6dfd
updated: 2026-10-13
external_references: []
---

# Property Relationships

Scope answer (verbatim): "just this directory".

## Persistence Cluster

`dirty-unlock-checkpointed`, `checkpoint-readback-matches`,
`checkpoint-crash-generations`, `checkpoint-restores-task-graph`.
Control-flow success does not imply correct bytes; correct bytes do not prove
durability after crash; durable bytes do not prove correct graph restoration.
These are complementary checks, not dominance proofs.

## Installed Resource Cluster

`snap-current-in-sequence`, `active-links-match-current`,
`retained-revisions-have-resources`, `sequence-write-matches-input`,
`accepted-blob-digest`, `settled-app-launches`. Links can agree while content is wrong or older retained
revisions are missing. Writer-local sequence equality does not imply perpetual
state equality. No member subsumes the full cluster.

## Ownership and Recovery Cluster

`rollback-preserves-unrelated-snaps`, `removal-is-scoped`,
`replay-preserves-semantic-effects`, `recovery-cohort-completes`.
All depend on independent admission/ownership expectations. Stable second
recovery does not prove the first result was correct; rollback and removal checks
supply specific projections. Recovery-cohort completion adds progress rather
than replacing safety. Replay do/undo Reachable sub-properties expose coverage.

## Dispatch and Cancellation Cluster

`ensure-pass-visits-managers`, `ensure-requests-progress`,
`task-scheduling-is-safe`, `abort-wins-completion-race`,
`cleanup-follows-readiness`. A completed Ensure pass can visit everyone while
tasks remain blocked; progress needs its own cohort oracle. Cancellation and
cleanup protect undo obligations across runner completion and persistence.

## Assumptions

Connections are hypotheses about shared mechanisms, not proven implications.
Only canonical active catalog slugs appear in these clusters.

## Open Questions

No property-specific relationship uncertainty blocks the initial campaign.