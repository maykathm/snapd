# retained-revisions-have-resources

Scope answer (verbatim): "just this directory"; external_references: [].
Focus: integrity/lifecycle. Confidence: high for completed ordinary-app fixtures.

## Property

**P0 | Safety | Always**: at a stable boundary every revision retained by the
independent completed-operation ledger and committed ordinary-app sequence has
its correct blob, mount unit and actual mounted fixture content; completed
fixture revisions also retain expected system data and controlled sentinels.
Message: `settled retained app revisions keep expected resources`. Require the
ledger's expected retained set to match state first; otherwise a lost state
entry could conceal a deleted resource. Always fits loss prevention at every
eligible observation, not existential progress.

## Verified Evidence

- [setup.go](../../../overlord/snapstate/backend/setup.go#L57): SetupSnap sets
  the instance key, installs the blob at MountFile, creates MountDir and adds
  its mount unit. RemoveSnapFiles at
  [setup.go](../../../overlord/snapstate/backend/setup.go#L209) stops/removes the
  mount and blob, with a seeded-symlink ownership exception.
- [copydata.go](../../../overlord/snapstate/backend/copydata.go#L54):
  CopySnapData creates common/system revision data on first install, copies old
  revision data on refresh, and does nothing for an identical revision.
- [handlers.go](../../../overlord/snapstate/handlers.go#L3516): doDiscardSnap
  refuses the active Current, selects a retained replacement when needed,
  removes external resources before Set, and retries file-removal errors.
- [setup_test.go](../../../overlord/snapstate/backend/setup_test.go#L95):
  TestSetupDoUndoSimple checks blob, mount unit What/Where and directory, then
  their removal. Its instance counterpart begins at
  [setup_test.go](../../../overlord/snapstate/backend/setup_test.go#L131).
- [handlers_discard_test.go](../../../overlord/snapstate/handlers_discard_test.go#L172):
  active Current cannot be discarded; the non-current discard test at
  [handlers_discard_test.go](../../../overlord/snapstate/handlers_discard_test.go#L204)
  preserves Current. [snapstate_test.go](../../../overlord/snapstate/snapstate_test.go#L1247)
  shows disable tasks contain no discard/clear operation.

## Oracle, Faults And Boundary

Admit two known signed app revisions, record successful lifecycle outcomes and
retention/discard decisions outside SUT state. Fixture hashes and mounted
content tokens supply identity; expected paths retain the full instance name.
Inspect every retained revision, not only current: blob digest, mount unit
source/target, real mount-table source and mounted metadata, controlled system
data/sentinel bytes. Directory existence alone is insufficient. Only require
per-user directories/sentinels explicitly provisioned by the fixture.

Interrupt setup, refresh copy, discard or undo between external deletion and
checkpoint; interleave another instance's install/removal. After recovery a
retained old revision can silently become non-revertible if its blob/mount/data
was removed. The stable barrier must stop admissions and drain/prevent all
affecting work including background refresh/cleanup; it is not an existing API.
Do not evaluate the partial discard window or use Settle nil as stability.

Disabled ordinary apps still retain blob/mount/sequence; do not require current
links or running services. Initially exclude try-mode, seeded symlinks,
components, snapd self-refresh, boot/reboot/remodel, preseeding and failed
destructive removal. Require system data only for completed fixture revisions,
not every synthetic sequence ever constructible. Shared instance resources need
later ownership-aware fixtures, not unconditional deletion/absence rules.

## Instrumentation And Questions

**Missing**, per [existing-assertions.md](../existing-assertions.md): no resource
assertion exists. Proposed primary placement is the independent stable checker;
discard outcome anchors can guide fault search but do not replace it. Fixture,
preserved storage, barrier and quiet budget remain catalog-wide implementation
plans in [deployment-topology.md](../deployment-topology.md).

**Open Questions:** None within this initial scope.

### Investigation Log

#### Does inactive mean resources may be absent, and can data be universal?

Examined disable task composition, setup/removal, copy and discard tests above.
Found disable does not discard; active non-current discard is allowed. Data
creation belongs to completed install/copy, not arbitrary sequence membership.
Conclusion: check active and disabled retained fixtures equally, qualify data
by fixture history, and wait through removal/undo before observation.