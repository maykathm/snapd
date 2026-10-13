---
sut_path: /home/katie.may@canonical.com/source/snapd
commit: e88ec08852fbc8af019dc39e22097e5720aa6dfd
updated: 2026-10-13
external_references: []
---

# Targeted Snapd Assertion Analysis

Scope answer (verbatim): "just this directory". This is targeted research for
snap state versus disk, ensure scheduling, persistence, and task replay; it is
not a whole-repository security or device-lifecycle audit. No production
instrumentation is changed by this research.

## Persistence Boundary

`overlord/state/state.go:291` implements `State.Unlock`. It serializes dirty
state with a non-nil backend while holding the state mutex, retries checkpoint
errors, clears `modified` only after a successful checkpoint, and releases the
mutex through a defer. Retry exhaustion panics. A nil backend is a legitimate
in-memory state mode and is excluded from persistence assertions.

Local hypothesis: a normally returning dirty unlock with a backend must have
completed a successful checkpoint before releasing the lock. A local assertion
can observe that control flow; an independent disk read is needed to test the
backend's persistence claim. Equality during an in-flight task is a different
property and must not be assumed.

`State.MarshalJSON` serializes persisted data, task/change graphs and counters,
not runtime caches. The notice timestamp has a separate mutex and documented
out-of-lock updates: comparing a fresh serialization to a previously written
checkpoint can create a false mismatch. Compare the exact checkpoint payload,
or a defined stable projection, instead.

## Architecture and Data Flow

The daemon accepts operations through its API and constructs persistent changes
and task DAGs. State managers coordinate desired state; TaskRunner executes
eligible do/undo handlers. SnapState contains revision/component sequence,
Current, Active, and undo-related metadata. The backend materializes blobs,
mount units, mounted metadata, revision data, current links, and wrappers.
The store is an HTTP dependency. There is one local authoritative state writer,
not a replicated consensus system.

## State and Disk Are Several Distinct Projections

- Checkpoint: exact serialized payload versus `/var/lib/snapd/state.json`.
- Installed snap: Current/Active/Sequence versus links, mounts, blobs and data.
- Sequence file: the projection supplied to `writeSeqFile`, used by recovery
	helpers, not an always-current mirror of every SnapState mutation.

`doLinkSnap` (`overlord/snapstate/handlers.go:1812`) writes the sequence file
and changes external links before committing snapstate. `doDiscardSnap`
(`:3516`) removes external resources before changing the sequence. In-flight
mismatch is therefore expected. The paired current links are not one atomic
transaction (`overlord/snapstate/backend/link.go:98`).

Current is the active or last-active revision, not necessarily the greatest
revision. A disabled snap can retain Current, sequence, blob and mount without
current links. Components have independent revisions. Snapd self-refresh,
kernel/base reboot boundaries, seeded resources and remodel require specialized
oracles; initial application checks explicitly exclude these cases.

`TestDoDiscardSnapKeepsSeqFileForNonLastRevision` in
`overlord/snapstate/handlers_discard_test.go:326` explicitly expects a retained
sequence file after non-last discard. Do not assert global sequence-file equality.

## Concurrency and Replay

The state mutex protects persistent reads/writes. Handlers release it around
external operations, so a locked state read does not freeze the filesystem.
StateEngine's manager mutex serializes dispatch; TaskRunner can run independent
tasks concurrently. Lanes control failure domains, not serialization.

`StateEngine.Ensure` (`overlord/stateengine.go:167`) visits all registered
top-level managers and collects errors rather than stopping after the first.
This does not mean every internal ensure helper should run unconditionally:
helpers often have feature, time, seed or device guards. A completed pass can
check visitation; a blocked pass needs a separate progress oracle.

`TaskRunner.run` (`overlord/state/taskrunner.go:192`) re-enters Doing/Undoing
tasks after restart. Idempotence is a claimed recovery contract to test, not
exactly-once invocation or permission to call arbitrary handlers twice.
Handlers need durable prior-state/ownership metadata and safe partial cleanup.
Atomic mutation-plus-terminal-status is required where replaying the mutation
would be unsafe. Ready changes are not necessarily already cleaned; Settle
returning nil is not a universal completion proof.

## Failure-Prone Areas and Existing Tests

High-value windows are external link before snapstate checkpoint, deletion
before sequence removal, undo after partial effects, checkpoint rename before
directory sync, abort while a handler returns, and manager/runner scheduling
under pauses. Disk failures are not presumed enabled platform faults.

The atomic writer syncs the temporary file, renames it, then syncs its directory
(`osutil/io.go:174`, `:189`, `:195`). Test binaries skip syncing by default,
so unit tests do not establish crash durability. Nearby state tests cover
checkpoint retries, counters, graph restoration and modified-only writes.
Backend idempotence tests cover LinkSnap/UndoLinkSnap/SetupSnap but mock enough
system behavior that real mount/restart testing remains valuable.

Existing Hold instrumentation conflicts with legitimate abort/explicit Hold
behavior; see `existing-assertions.md`. No new defect is alleged here.

## Research Lenses and Limits

Targeted reviews covered architecture/data flow, persistence, concurrency,
safety, liveness, existing test strategy, partial failure, dependencies,
product impact and unproven assumptions. Bug-history research is limited to
local test expectations, not externally reported incidents. Security, remote
cluster consensus, broad version migration and full Ubuntu Core lifecycle
research are outside this requested pass.

## Assumptions

Repository comments and design guarantees are test targets, not proof that the
guarantees hold. The existing assertion inventory is maintained separately.

## Open Questions

The tenant's termination/clock fault availability and durable storage behavior
are not discoverable from source. A quiet recovery budget must be calibrated
against the chosen fixtures and retry schedules before implementation.