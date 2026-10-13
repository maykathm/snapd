# active-links-match-current

Scope answer (verbatim): "just this directory"; external_references: [].
Focus: integrity/lifecycle. Confidence: high for ordinary apps at stability.

## Property

**P0 | Safety | Always**: at an admitted stable ordinary-app observation, an
Active instance's mount and data current links both resolve to that instance's
committed Current revision, with the fixture's mounted identity. Message:
`settled active app links select committed current`. Every eligible observation
must agree; Sometimes would allow broken observations beside one good result.
A separate fixed-message Always check for an explicitly disabled fixture
requires both links absent, while Current and retained resources remain.

## Verified Evidence

- [link.go](../../../overlord/snapstate/backend/link.go#L98):
  updateCurrentSymlinks updates data then mount using separate AtomicSymlink
  calls. It creates the data directory; snapd gets special old-link restoration.
- [link.go](../../../overlord/snapstate/backend/link.go#L170): LinkSnap generates
  wrappers before updating links; successful linkage is not service liveness.
- [handlers.go](../../../overlord/snapstate/handlers.go#L1959): doLinkSnap writes
  the sequence projection before backend linking, then commits state at
  [handlers.go](../../../overlord/snapstate/handlers.go#L2145).
- [handlers.go](../../../overlord/snapstate/handlers.go#L3278): doUnlinkSnap
  unlinks on remove/disable, then sets Active false without clearing Current.
- [link_test.go](../../../overlord/snapstate/backend/link_test.go#L274):
  TestLinkDoUndoCurrentSymlink checks both resolved revision paths and their
  removal by UnlinkSnap. Parallel-instance path/shared-directory behavior is
  tested at [link_test.go](../../../overlord/snapstate/backend/link_test.go#L309).
  These tests use mocked system boundaries, not real crash durability.

## Oracle, Faults And Boundary

The independent admission ledger selects instance, successful operation and
expected revision/Active value. A controlled fixture manifest supplies mount
metadata/content identity and expected wrapper names; never use the links to
compute their own expected target. Readlink plus canonical path resolution,
mount-table/source inspection and fixture metadata discriminate dangling links
and correct-looking directories that are not the expected mounted snap.
Read errors/missing eligible resources fail, rather than silently skipping.

Crash between link replacements, after wrappers, or before snapstate checkpoint;
recover then compare. Interleave independent instance operations to expose wrong
path selection. Violation runs the wrong revision or selects the wrong data.
Stop admissions and drain/prevent affecting background handlers while observing:
a state lock, one Done task, change readiness or Settle nil alone is insufficient.
The barrier is proposed, not an existing API.

Initially use successful install/refresh/revert/enable and explicit disable of
ordinary apps, no application writes during the snapshot. Disabled is not
uninstalled; Active does not mean services are running. Exclude failed removal
after data destruction, try-mode, components, snapd self-refresh, boot/reboot,
remodel and preseeding. Parallel instances require an instance-aware later
fixture; never normalize away the instance key. In-flight link disagreement is
not a violation at this boundary.

## Instrumentation And Questions

**Missing**, per [existing-assertions.md](../existing-assertions.md): its Hold
assertion does not check links. Proposed workload stable oracle is primary;
backend link outcomes can supply optional Reachable search anchors, not proof
of pair atomicity. Fixture/barrier/fault wiring remains the catalog-wide plan in
[deployment-topology.md](../deployment-topology.md).

**Open Questions:** None within this initial scope.

### Investigation Log

#### Can pair equality be required during linking or for disabled apps?

Examined updateCurrentSymlinks, doUnlinkSnap and the backend tests above. Found
separate replacements and explicit link removal on disable. Conclusion: gate
on stable success, use disabled absence separately; do not test an imaginary
atomic pair transaction or infer installation from Active.