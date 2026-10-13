# rollback-preserves-unrelated-snaps

Scope answer (verbatim): "just this directory"; external_references: [].
Focus: lifecycle/integrity/idempotency. Confidence: high in scoped contract;
unrelated-instance fault coverage is proposed, not established by existing tests.

## Property

**P0 | Safety | AlwaysOrUnreachable**: whenever an eligible ordinary-app refresh
has completed rollback, both (1) its old Current, activation, configuration,
links and controlled old data are restored, and (2) unrelated snap/instance
semantic state and resources equal their independent admitted expectations.
Message: `completed app rollback restores old revision and preserves unrelated instances`.
Rollback is an optional error path, hence AlwaysOrUnreachable rather than
requiring every run to roll back. A separate Reachable rollback-outcome anchor
can drive coverage; it is not the safety check.

## Verified Evidence

- [handlers.go](../../../overlord/snapstate/handlers.go#L2068): doLinkSnap saves
  old-current and candidate-placement undo metadata on the owning task.
- [handlers.go](../../../overlord/snapstate/handlers.go#L2439): undoLinkSnap
  reads that metadata; it removes a new candidate or adjusts the prior index
  for already-discarded revisions. It restores old Current and configuration,
  then marks ordinary apps inactive. Relinking belongs to
  [handlers.go](../../../overlord/snapstate/handlers.go#L1236),
  undoUnlinkCurrentSnap, not the intermediate undoLinkSnap snapshot.
- [handlers.go](../../../overlord/snapstate/handlers.go#L2660): undo commits
  instance-specific Set together with UndoneStatus before releasing the lock.
  [snapstate.go](../../../overlord/snapstate/snapstate.go#L4038) replaces only
  the named entry in the current snaps map, rather than restoring an old map.
- [handlers_link_test.go](../../../overlord/snapstate/handlers_link_test.go#L2065)
  and [handlers_link_test.go](../../../overlord/snapstate/handlers_link_test.go#L2109)
  check old Current and sequence restoration for new/existing candidates.
- [snapstate_update_test.go](../../../overlord/snapstate/snapstate_update_test.go#L2637):
  TestUpdateUndoRunThrough expects old-revision relinking and active state after
  rollback. Configuration restoration is tested at
  [snapstate_update_test.go](../../../overlord/snapstate/snapstate_update_test.go#L2844).
- [link_test.go](../../../overlord/snapstate/backend/link_test.go#L309): backend
  instance link/unlink preserves the shared directory. This is supporting path
  evidence, not an end-to-end unrelated-instance rollback test.

## Oracle, Faults And Boundary

Before admission, retain target A's old fixture revision, Active, config and
controlled revision/common-data sentinels in an independent ledger. Install
unrelated B with distinct tokens; freeze B or admit its independent update and
record that successful outcome. After A's full rollback, check A against its
old ledger and B against its latest ledger, not a stale whole-state snapshot.
Require A's restored old links, mounted identity and sentinels as well as
state. An unchanged B alone cannot certify a broken A rollback. Never compute
expected old revision from task undo metadata, which is itself under test.

Use a two-revision fixture/retention policy that does not intentionally prune
preexisting revisions. Crash during link or undo after external effects and
before checkpoint; interleave B's separate change commit with A's unlocked
work. A later instance-aware fixture should use A/B sharing a snap name but
different instance keys and verify both private and shared-resource ownership.
Loss here leaves the old app unusable or destroys a different app's data.

Observe only after full rollback and a barrier draining/preventing affecting
handlers/background cleanup, not after undoLinkSnap alone or Settle nil. Do
not require restoration of intentionally discarded historical revisions.
Initially start with an active ordinary app; disabled snapshots remain inactive
unless an independent admitted operation enables them, and need no active links.
Exclude destructive removal rollback (data may already be lost), user hooks
with uncontrolled effects, try-mode, components, seeded resources, snapd
self-refresh, reboot/boot participants and remodel. Snaps in the failed
transaction's dependency/lane domain are not automatically "unrelated".

## Instrumentation And Questions

**Missing**, per [existing-assertions.md](../existing-assertions.md). Proposed
undo completion search anchors and independent stable safety checks are absent;
the existing Hold assertion is neither an isolation nor restoration oracle.
Fixture policy, parallel-instance extension and stable barrier remain
catalog-wide implementation plans in
[deployment-topology.md](../deployment-topology.md), not existing APIs.

**Open Questions:** None within this initial scope.

### Investigation Log

#### Does undoLinkSnap alone restore activation or every prior revision?

Examined saved undo fields, candidate removal/reordering, final Set/status and
the full refresh/config undo tests above. Found ordinary apps are temporarily
inactive, relinking is another undo task, and discarded revisions affect index
restoration. Conclusion: check full rollback, use non-pruning fixtures and
independent ownership/ledger expectations; exclude destructive removal and
special lifecycle paths. No per-property semantic question remains.