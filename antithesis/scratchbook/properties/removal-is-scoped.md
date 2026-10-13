# removal-is-scoped

Scope answer (verbatim): "just this directory"; external_references: [].
Focus: lifecycle/integrity. Confidence: high in initial ownership contract.

## Property

**P0 | Safety | Always**: after a successful admitted ordinary-app removal and
stable recovery, exactly the targeted revision/instance loses its owned
resources and state; retained revisions, common resources with live owners and
unrelated snap/instance semantic projections match independent expectations.
Message: `completed app removal deletes only admitted owned resources`.
Each eligible completion must be correctly scoped, not just one Sometimes
completion. At stable terminal failures, a separate AlwaysOrUnreachable message
checks unrelated survivor preservation without promising target restoration.
A Reachable last/non-last removal anchor can supplement coverage.

## Verified Evidence

- [handlers.go](../../../overlord/snapstate/handlers.go#L3419): doClearSnapData
  checks unknown mounts before deletion, limits non-last mount-control cleanup
  to revision data, and removes common/save/base data only for last revision.
- [handlers.go](../../../overlord/snapstate/handlers.go#L3516): doDiscardSnap
  rejects active Current, removes revision files, then performs last-instance
  config/namespace/cookie/directory/sequence cleanup. Other-instance detection
  precedes shared directory/metadata removal; Set is instance-specific.
- [setup.go](../../../overlord/snapstate/backend/setup.go#L209): RemoveSnapFiles
  uses revision MountDir/MountFile. RemoveSnapDir at
  [setup.go](../../../overlord/snapstate/backend/setup.go#L307) removes the
  shared base only if no other instance uses it, and tolerates nonempty parents.
- [snapdata.go](../../../overlord/snapstate/backend/snapdata.go#L74):
  RemoveSnapDataDir always handles private instance data, but shared base data
  removal is gated by hasOtherInstances.
- [snapstate_remove_test.go](../../../overlord/snapstate/snapstate_remove_test.go#L562):
  TestParallelInstanceRemoveRunThroughOtherInstances checks scoped backend
  operations with otherInstances true and preservation of the second instance.
- [snapstate_remove_test.go](../../../overlord/snapstate/snapstate_remove_test.go#L888):
  TestRemoveOneRevisionRunThrough removes revision 3 from three, retains two and
  scopes mount-control cleanup to its data. Non-last config preservation is
  tested at
  [snapstate_remove_test.go](../../../overlord/snapstate/snapstate_remove_test.go#L1483).
  Backend tests are mocked, so these do not prove real mount/data isolation.

## Oracle, Faults And Boundary

Before removal, ledger the exact full instance name, optional revision, retained
set and ownership map. Provision target A and unrelated B with different
fixture identities/config/data sentinels. For non-last removal require only the
target revision blob/mount/unit/revision data absent; retained A resources,
Current links, common data and config must remain. For full removal require A
state, active links, revision resources and owned data absent; B must keep its
expected state, links, mounted identities, config and sentinel bytes. Count
missing/read-error B observations as failures, not exclusions.

Later add same-name parallel instances with private-path tokens and explicit
shared-resource ownership: retain shared bases/store metadata while B owns
them. Do not indiscriminately assert every parent directory is absent; empty
parent removal is best-effort. Snapshot archives created by removal are not
installed revision resources and need not disappear. Expected deletion comes
from admission/fixture ownership, not the post-removal SUT inventory.

Crash after clear-data/unmount/blob deletion before checkpoint or during retry,
and interleave B's separate install/refresh with A's unlocked deletion. Wrong
scope destroys another app's data or makes retained revisions unusable. Stop
admissions and drain/prevent all affecting work at a proposed barrier before
checking; neither one Done task nor Settle nil is that barrier. During failed
removal require unrelated preservation, not target rollback of already-deleted
data; do not misclassify expected partial target destruction as scope leakage.

Initially ordinary app full/non-current removal, active or disabled. Disabled
retains resources until explicitly removed; removing active Current is handled
by the complete operation, not a raw discard call. Exclude uncontrolled hooks,
manual/unknown mounts, NFS/migration policy, try-mode, seeded/shared component
resources, snapd self-refresh, boot/reboot/remodel. Component revisions are not
snap revisions and require a separate ownership oracle.

## Instrumentation And Questions

Evaluation refinement: initial deletion-only operations use purge to avoid
introducing a new automatic-snapshot obligation. Pre-existing saved archives
are separately owned and must be preserved unless explicitly forgotten/expired;
purge is not permission to delete all snapshot sets. Lost admissions and
concurrent unrelated commits are reconciled against the independent ledger.

**Missing**, per [existing-assertions.md](../existing-assertions.md): no deletion
scope assertion exists. Proposed independent stable checks plus deletion
outcome anchors remain unimplemented. Fixture ownership maps, barrier, parallel
instances and fault support are catalog-wide plans in
[deployment-topology.md](../deployment-topology.md), not existing APIs.

**Open Questions:** None within this initial scope.

### Investigation Log

#### Are common data and shared parents always removal targets?

Examined clear-data, discard, RemoveSnapDataDir/RemoveSnapDir and non-last/
parallel tests above. Found last-revision and other-instance guards, preserved
non-last configuration and best-effort parent deletion. Conclusion: use an
ownership oracle, distinguish revision from whole-instance removal and do not
require unconditional shared-resource or parent-directory absence.