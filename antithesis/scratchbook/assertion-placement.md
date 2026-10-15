---
sut_path: /home/katie.may@canonical.com/source/snapd
commit: 91b61e2873e9621b6300906b31ababe8861ca248
updated: 2026-10-15
external_references: []
---

# Assertion Placement Recommendations

Scope answer (verbatim): "just this directory". Examples are proposed sketches,
not applied code. SDK signatures were checked against cached v0.8.0. Source-only
follow-ups implemented the dirty-Unlock guard, scoped cancellation checks and
Current/Sequence membership check described below; other placements remain
proposals.

## First: Dirty State Must Be Checkpointed

Owner: `State.Unlock`, `overlord/state/state.go:294`. Capture entry dirty/backend
conditions and track a successful checkpoint, then check on normal return while
the mutex is still held. A helper defer must run before the existing deferred
`s.unlock`. Do not turn an expected checkpoint error into an assertion failure.
The existing error retry and panic behavior must remain intact.

Illustrative control-flow insertion, with new observational locals:

```go
required := s.modified && s.backend != nil
checkpointSucceeded := false
returnedNormally := false
defer func() {
    if returnedNormally && required {
        assert.Always(checkpointSucceeded && !s.modified,
            "dirty unlock completes checkpoint before releasing state lock", nil)
    }
}()
```

Set `checkpointSucceeded = true` in the successful Checkpoint branch and set
`returnedNormally = true` before each ordinary return. Register this defer after
`defer s.unlock()`. Nil backend and panic/crash exits are excluded. This tests
control flow only; it does not establish that the backend wrote the right file.

**Implemented:** the source guard is registered after the existing
clean/nil-backend gate and before mutex release. It records attempt count and
excludes panic exits. Focused tests, six local SDK encounter checks and the full
state race suite pass. The sketch above illustrates the contract, not the exact
implemented gating. Instrumented harness cataloging/reporting remains unverified.

Independent check: in `overlord/backend.go:33`, after AtomicWriteFile succeeds
and before returning to Unlock, a test-only readback can compare file bytes to
the exact `data` argument. Record read errors as failures in a controlled healthy
storage campaign. Do not compare a fresh MarshalJSON call: asynchronous notice
timestamps can legitimately differ. Keep readback out of normal production
builds; no-op SDK calls do not avoid argument evaluation or filesystem work.

## Second: Snap State Matches Installed Resources When Stable

Owners: `doLinkSnap` (`handlers.go:1812`), `undoLinkSnap` (`:2439`), unlink and
discard handlers, plus `backend/link.go`. Use cheap local structure checks at
the final candidate commit, but an independent settled oracle for disk resources.

The following helpers are proposed, not existing snapd APIs:

```go
assert.Always(currentInSequence(snapshot),
    "committed app current belongs to its revision sequence", details)

if snapshot.Stable && snapshot.Successful && snapshot.OrdinaryApp {
    assert.Always(activeLinksMatch(snapshot),
        "settled active snap links match committed current revision", details)
}
```

For Active ordinary apps, compare both mount/data current links, actual mounted
metadata, known blob identity and expected wrappers to Current. Disabled snaps
retain sequence/blob/mount; they need a different link predicate. Active does
not mean every service is running. Current need not be the highest revision.

Do not run this across in-flight external work. Stop admissions and use a barrier
that also excludes background affecting operations. Do not infer stability from
a single task's Done status, API reads taken separately, or Settle returning nil.
For sequence files, compare immediately after `writeSeqFile` to its input only;
do not require global perpetual equality with SnapState.

**Source assertion implemented:** `snapstate.Set` checks nonempty explicitly typed
app states outside try-mode, after serialization and before the locked state
write. The fixed message is `committed app current belongs to its revision sequence`.
Disabled apps and older/local Current revisions remain valid; nil/empty entries
delete state and are excluded. The check only observes membership and does not
repair or reject inconsistent state. Tests inspect actual SDK local encounters
and verify that serialization/deletion behavior is preserved.

The independent stable-disk oracle, ledger-selected revision check and safe
barrier are still deferred. This source assertion does not implement the
`activeLinksMatch` sketch or verify mounts, blobs, wrappers or data.

## Third: All Managers Are Visited in a Completed Ensure Pass

Owner: `StateEngine.Ensure`, `overlord/stateengine.go:167`. Freeze the expected
manager set for the pass under `mgrLock`, maintain observational entry/return
counts per manager, and check before both success and aggregated-error returns.

Proposed local predicate:

```go
assert.Always(allManagersReturnedExactlyOnce(pass),
    "completed ensure pass visits every registered manager", details)
```

Use an engine incarnation and pass generation in details. Exclude pre-start and
post-stop rejection. A count increment at dispatch observes invocation but does
not establish useful work occurred inside a manager. Internal helper functions
need separate guard-aware checks; they must not all run unconditionally.

A pass that never returns never reaches this check. Separately track EnsureBefore
requests and check at a quiet-phase deadline that all eligible requests have been
covered by a later completed pass; allow coalescing. A Sometimes witness can
guide exploration but cannot prove every request is fulfilled.

## Fourth: Test Replay-Safe Effects, Not Exactly-Once Tasks

Owner: `TaskRunner.run`, `overlord/state/taskrunner.go:192`, and each real
handler's mutation/ownership boundary. Record task ID, direction, attempt,
pre-status, and checkpoint generation. Interrupt between external effect and
durable completion; exercise Doing and Undoing recovery separately.

```go
assert.AlwaysOrUnreachable(recoveredOutcomeMatchesLedger(snapshot, ledger),
    "recovered app lifecycle replay preserves expected semantic effects", details)
assert.Sometimes(snapshot.Recovered && snapshot.Consistent,
    "interrupted lifecycle work reaches a consistent recovered state", details)
```

Helpers and snapshot fields above are proposed. Compare the result to fixture
and admission-ledger expectations. Prove the same task/direction actually
executes repeatedly through attempt and persisted pre-status observations.
Interrupt supported replayable work again, without manually invoking handlers.
A second clean restart is only a supplementary stability check. Compare a
semantic projection: sequence membership, Current/Active,
configuration, links, mount identities and controlled data sentinels. Exclude
logs, timestamps, retry counters and temporary download files. Replaying partial
work is not equality with the pre-crash partial snapshot. User hooks/application
effects require their own contract; arbitrary handlers are not safe to invoke
twice manually. Never mutate state solely to probe an assertion.

## Additional High-Value Checks

Prioritize rollback scope, cancellation winning a completion race, task graph
ownership/dependencies, one active invocation per task per runner, retained
revision resources, accepted blob digest, and cleanup only after change readiness.
Use Reachable at distinct replay outcomes (do and undo) as search anchors;
AlwaysOrUnreachable fits safety checks on optional undo/error paths.

Matching resources also needs a user-visible postcondition: run a controlled
fixture through both the real `snap run` CLI and generated wrapper after stable
activation. Compare output to immutable independently known revision/data
tokens, not the SUT's own Current or SNAP_REVISION. See `settled-app-launches`
in the catalog for remaining barrier/security and fixture-budget questions.

Record admission intent before submission; reconcile lost responses against
durable changes/resources instead of silently forgetting potentially accepted
work or retrying blindly. Predeclare allowed success/rollback outcomes. Protect
fixture/ledger data from SUT writes, and test the checker on synthetic wrong
snapshots. Terminal progress deadlines run outside SUT locks and the snapshot
barrier so a blocked barrier cannot suppress a failure.

The source-only cancellation follow-up removed the invalid
`change never enters hold status` assertion. Three `AlwaysOrUnreachable` checks
now observe competing Done/Wait commits and normalized runner completion after
Abort. Unit tests and local SDK event checks pass; dedicated workload outcome
coverage and actual harness cataloging/reporting remain deferred. See the
`abort-wins-completion-race` evidence file and assertion inventory.

## SDK Semantics and Sources

Always is universal over encounters and expects to be encountered. Optional
safety checks use AlwaysOrUnreachable. Sometimes is an existential witness, not
universal per-task liveness. Reachable checks an outcome was visited. Use fixed,
distinct messages; put instance/task IDs in details, not in message strings.
Failed assertions report outcomes without terminating the program.

- https://antithesis.com/docs/product/writing_tests/assertions/
- https://antithesis.com/docs/reference/sdk/go/
- https://antithesis.com/docs/reference/sdk/define_test_properties/
- https://antithesis.com/docs/best_practices/sometimes_assertions/
- https://antithesis.com/docs/best_practices/optimizing/

These are workflow-required platform semantics, not user-named external SUT
references; provenance records the user's empty external reference list.

Assertion messages in each property's evidence file are the canonical proposed
messages. Other snippets illustrate predicates, not additional callsites that
reuse a message. Use the property's evidence message when implementing it, and
generate a catalog after finalizing all fixed callsite messages.

## Assumptions

Implement in stages with focused unit tests for instrumentation and independent
isolated runs for filesystem/recovery guarantees. No snippets here prove a claim.

## Open Questions

Choose and calibrate the quiet-phase barrier/budget before universal liveness
checks. Confirm cataloged, cgo-enabled harness artifacts and crash availability.