# settled-app-launches

Scope answer (verbatim): "just this directory"; external_references: [].
Targeted gap filling for CB-2 in
[coverage-balance.md](../evaluation/coverage-balance.md), using the current
[SUT analysis](../sut-analysis.md), [topology](../deployment-topology.md),
[catalog](../property-catalog.md) and [inventory](../existing-assertions.md).
Followed the local research property-catalog and validating-claims references.
Confidence: high in the named launch gates; campaign wiring remains proposed.
No defect, implemented assertion, or new harness API is claimed.

## Compact Catalog Entry

| Slug | Priority / Type | Property / Invariant | Antithesis Angle | Open Questions |
| --- | --- | --- | --- | --- |
| settled-app-launches | P1 / Safety / Always | At stable successful ordinary CLI fixture install, refresh or enable, real execution exits zero within a calibrated budget and emits exactly the independently expected revision and data tokens. | Interrupt wrapper/link/inhibitor/profile integration, recover, then execute through the supported CLI and generated wrapper. | Stable launch barrier and security readiness; fixture and execution budget calibration. |

P1 adds a user-visible usability postcondition to the P0 resource/recovery
checks. Consistent links, mounted identity and wrapper existence do not prove
execution. This is a guarantee to test, not proof that every activation works.

## Property And Assertion Semantics

Semantic contract: **Always** at every eligible stable successful activation,
not one successful launch among broken outcomes. Proposed fixed message:
`settled ordinary CLI fixture launches expected revision and data`.

Implement this catalog property as **Always** only in the dedicated campaign
that constructs and requires successful activation and evaluates its launch
postcondition. It is not a mandatory catalog property in a general workload
that never activates fixtures. Never emit a passing result for an absent eligible
observation. A different optional campaign needs its own distinct message/type,
not an ambiguous type for this catalog ID. Separate fixed Reachable outcomes for stable successful
install, refresh and enable can make that campaign's coverage explicit; request
submission alone is not an outcome. A launch failure must not suppress the
activation outcome anchor. These assertions and messages are proposals.

The admission ledger independently records instance/app, operation outcome and
fixture identity. A fixture manifest maps each admitted revision to a distinct
immutable payload token. Provisioned system/user revision-data sentinels supply
the independently known data token. Expected output must not be derived from
SnapState.Current, current links, launch output, or just SNAP_REVISION; otherwise
the wrong executable could certify itself. Refresh expects the admitted new
token, enable the retained revision token. Controlled hooks must not alter the
sentinel. Missing/unreadable eligible data, malformed output, nonzero exit and
timeout are failures, not eligibility exclusions.

Completed refresh rollback may use the same execution oracle against the
ledger's surviving old revision, under the existing rollback/replay properties.
Do not demand the failed candidate's token or successful target execution after
a partially destructive removal.

## Verified Implementation And Test Anchors

- [link.go](../../../overlord/snapstate/backend/link.go#L170), `Backend.LinkSnap`:
  generates wrappers, updates current links, then calls `runinhibit.Unlock` at
  [link.go](../../../overlord/snapstate/backend/link.go#L220). Thus link selection
  and removal of startup inhibition are distinct effects.
- [link.go](../../../overlord/snapstate/backend/link.go#L270), `generateWrappers`,
  calls `EnsureSnapBinaries` alongside service/activation/desktop setup.
  [binaries.go](../../../wrappers/binaries.go#L208), `EnsureSnapBinaries`, skips
  services and builds CLI symlinks to `/usr/bin/snap`.
- [inhibit.go](../../../cmd/snapd/cli/inhibit.go#L61), `waitWhileInhibited`,
  rejects remove/disable hints, waits for refresh for non-service apps and
  reloads current app information when uninhibited. Services have a different
  old-revision behavior; they are not this fixture's execution contract.
- [cmd_run.go](../../../cmd/snapd/cli/cmd_run.go#L622), `snapRunApp`, holds or
  rechecks inhibition around launch and calls `runSnapConfine`.
  [cmd_run.go](../../../cmd/snapd/cli/cmd_run.go#L1559), `runSnapConfine`, checks
  for the helper, prepares user data, and constructs `snap-confine` execution
  with the app security tag and `snap-exec`. A direct payload invocation would
  bypass precisely this integration boundary.
- [handlers.go](../../../overlord/ifacestate/handlers.go#L597),
  `setupProfilesForAppSet`, invokes `setupSecurityByBackend` for the affected
  app sets. Links alone do not observe whether that setup supports execution.
- [link_test.go](../../../overlord/snapstate/backend/link_test.go#L89),
  `TestLinkDoUndoGenerateWrappers`, checks wrapper creation and removal, not
  actual confined execution.
- [cmd_run_test.go](../../../cmd/snapd/cli/cmd_run_test.go#L370),
  `TestSnapRunAppRunsChecksRemoveInhibitionLock`, and
  [cmd_run_test.go](../../../cmd/snapd/cli/cmd_run_test.go#L384),
  `TestSnapRunAppRunsChecksDisableInhibitionLock`, expect launch errors for the
  respective hints.
- [cmd_run_test.go](../../../cmd/snapd/cli/cmd_run_test.go#L398),
  `TestSnapRunAppNewRevisionAfterInhibition`, expects `SNAP_REVISION=x3` after
  refresh inhibition ends. It mocks execution, so is not an end-to-end oracle.
- [task.yaml](../../tests/hello-world/task.yaml#L7) installs hello-world and
  requires `snap run hello-world` output matching `^Hello World!$`. This is an
  existing real-CLI happy-path expectation, not a two-revision campaign or SDK
  launch assertion.

## Oracle, Faults And Scope

Use two small strictly confined ordinary CLI fixture revisions in the disposable
real snapd/systemd/mount environment. The payload prints its baked-in revision
token and reads the provisioned data token, then exits. No network, GUI, service,
randomness, wall-clock dependence or background child is needed. Required base
and helpers are provisioned before the campaign; downloads may need the store,
but fixture execution does not. This checks security integration usability,
not whether confinement blocks every forbidden action.

For each eligible activation, run both `snap run <instance>.<app>` and the
fixture's canonical generated wrapper path with controlled arguments, user and
environment, capturing bounded output and exit status. The wrapper invocation
prevents a working `snap run` from hiding a missing/broken wrapper. Compare each
result to the manifest/ledger, not to the other invocation. Do not run the
payload directly or use `--shell`/debug modes. Details should include operation
ID, fixture revision, expected/actual tokens, exit/timeout and stderr.

Stop new admissions and drain/prevent work affecting this app, its dependencies
and security setup; retain that stable generation across both executions.
Restore required dependencies and calibrate the execution deadline in the
isolated campaign. State locking, one Done task, change readiness or Settle nil
alone is not a filesystem/launch barrier. Never gate on a successful probe,
wrapper presence or clear inhibition: those are outcomes being tested. Faults
during an explicitly stable check must follow the campaign's recovery/budget
rules rather than silently exempting a broken result.

Explore interruptions after wrapper generation, between link updates, before
inhibition unlock or durable activation commit, and across security setup and
supported do/undo recovery. Use confirmed fault support only. Check recovered
stable outcomes, not transient refresh blocking.

The payload itself must not write application data. CLI launch can nevertheless
create user data directories/current links and runtime artifacts (see
`runSnapConfine` above). Before replay comparisons, stop all checker-launched
processes and exclude narrowly identified test-generated artifacts from the
semantic projection or restore their owned baseline in the isolated fixture.
Do not mask payload/sentinel changes or delete unrelated user/runtime data.
Keep a consistent probe schedule across first and repeated recovery.

No universal claim that Active snaps have running services is made. Services,
uncontrolled hooks, try mode, components, parallel instances, snapd self-refresh,
boot/reboot/remodel and arbitrary customer apps need distinct campaigns.

## Removal Ownership Recommendation

CB-3 is adjacent evidence, not another file edit: at stable terminal removal
failure **as well as success**, preserve unrelated snaps' latest independently
ledgered state, resources, config and sentinels, including unrelated committed
operations. Only successful removal requires all admitted target resources
gone; failed destructive removal does not promise target data restoration.

[handlers.go](../../../overlord/snapstate/handlers.go#L3419), `doClearSnapData`,
removes revision data and only removes common/save/base data at the last
revision. [handlers.go](../../../overlord/snapstate/handlers.go#L3516),
`doDiscardSnap`, guards active Current and scopes final instance cleanup using
other-instance ownership. These paths can fail after destructive work.
[snapstate_remove_test.go](../../../overlord/snapstate/snapstate_remove_test.go#L562),
`TestParallelInstanceRemoveRunThroughOtherInstances`, is a mocked isolation
anchor, not proof of faulted filesystem preservation.

Ledger removal mode and archive ownership separately. In
[snapstate.go](../../../overlord/snapstate/snapstate.go#L3340), `removeTasks`,
`Purge` skips creation of an automatic snapshot; non-purge full app removal
requests one before unlink/data deletion, subject to policy and ErrNothingToDo.
[snapshotstate.go](../../../overlord/snapshotstate/snapshotstate.go#L129),
`AutomaticSnapshotExpiration`, permits retention `no` and disables automatic
snapshots by default on non-classic systems.
[snapshotstate.go](../../../overlord/snapshotstate/snapshotstate.go#L447),
`AutomaticSnapshot`, creates a set-owned `save-snapshot` task when enabled.
[snapstate_remove_test.go](../../../overlord/snapstate/snapstate_remove_test.go#L104),
`TestRemoveTasksAutoSnapshotDisabledByPurgeFlag`, verifies the purge task list.

Recommend purge for the initial deletion-only campaign, with no new automatic
snapshot expected, not deletion of all saved snapshots. Preserve pre-existing
target and unrelated saved archives unless a separately admitted forget/expiry
operation owns their deletion. For non-purge, ledger the new set and its
save/undo disposition separately; saved archives are not installed revision
resources. Do not require an automatic archive on every terminal failure or
promise purge makes all target-related bytes, including archives, disappear.

## Instrumentation And Open Questions

**Missing**, per the current inventory: no settled-launch SDK assertion exists.
The hello-world task and mocked unit tests are evidence anchors, not this
instrumentation. The independent ledger, two-token fixture, stable barrier,
execution budget and campaign outcome assertions are unimplemented proposals;
no proposed API is claimed present. Catalog/inventory/topology remain unchanged.

- How will the stable barrier allow required CLI security regeneration without
  deadlocking or crossing generations? (partial: inhibition/helper paths and
  profile setup are identified; no implemented launch barrier was established)
- Which fixture/base, user-data baseline and budget will reliably distinguish
  a broken activation from incomplete environmental readiness? (partial: real
  hello-world execution exists, but not an independent two-revision/data oracle)

Non-purge snapshot-set disposition is excluded from this initial campaign, not
an unresolved claim of this launch property. Before expanding scope, investigate
save/undo and expiry outcomes separately. The retained investigation log below
records what is known; purge does not delete pre-existing archives.

### Investigation Log

#### Stable launch barrier and security readiness

Examined LinkSnap, wrapper generation, waitWhileInhibited, snapRunApp,
runSnapConfine and setupProfilesForAppSet at the anchors above. Found separate
launch gates and user-data preparation beyond link identity. The topology only
proposes a barrier; this pass did not establish an implementation or safe
coordination with profile regeneration. Keep the barrier question partial and
do not treat a state lock as the answer.

#### Fixture identity and execution budget

Examined the hello-world task and CLI refresh/inhibition tests above. Found a
real install/CLI output check and mocked new-revision selection, not a manifest
with two independent revision tokens, controlled sentinels or calibrated fault
budget. These must be constructed and validated in the dedicated campaign.

#### Snapshot ownership after failed removal

Examined removeTasks, doClearSnapData, doDiscardSnap, automatic retention,
AutomaticSnapshot and the purge/parallel-instance tests above. Found separate
installed-resource and snapshot-set lifecycles and conditional snapshot
creation. Snapshot handler undo/expiry behavior was not established by this
targeted pass. Start with purge and preservation of pre-existing archives;
investigate the new set's precise failure disposition before admitting
non-purge snapshot outcomes. No target rollback guarantee is inferred.