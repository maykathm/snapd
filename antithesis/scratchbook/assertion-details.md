---
sut_path: /home/katie.may@canonical.com/source/snapd
commit: 2b2a1c2e9fba3b6dbc4b80f9d4bf844912c136e0
updated: 2026-11-20
external_references:
  - https://antithesis.com/docs/product/writing_tests/assertions/
  - https://antithesis.com/docs/reference/sdk/go/
  - https://antithesis.com/docs/best_practices/sometimes_assertions/
---

# Assertion Details

This document describes every Antithesis SDK assertion currently embedded in
the snapd source tree on the `antithesis-testing` branch. Each entry records
the callsite, the exact property message, what the assertion is doing, the
conditions under which it holds or fails, and why adding it is correct.

The inventory itself, including the coverage assessment and validation
history, lives in [existing-assertions.md](existing-assertions.md). Placement
rationale and alternatives are in
[assertion-placement.md](assertion-placement.md).

## Conventions

- `assert.Always(condition, ...)` records a property that must be true every
  time the callsite is reached. A false encounter is a correctness failure of
  the system under test.
- `assert.AlwaysOrUnreachable(condition, ...)` is the same, except that the
  callsite itself may legitimately never be reached; if it is reached, the
  condition must hold.
- `assert.Reachable(...)` has no condition: it is a coverage witness. It
  proves that a recovery or fault-handling path is actually exercised by the
  workload, not that any boolean holds.
- All callsites run under the `state.State` lock (or an equivalent
  serialization) unless noted. The SDK emits events to the Antithesis
  harness; it never mutates snapd behavior or panics on a false condition.

Grouping below follows the four instrumented subsystems: the state engine,
the state package (state, task, change, task runner), snapstate, and the
store download path.

## 1. `overlord/state/state.go` — state checkpointing

### 1.1 `dirty unlock completes checkpoint before releasing state lock`

| Attribute | Value |
| --- | --- |
| Callsite | `State.Unlock`, `overlord/state/state.go:308` |
| Type | `Always` |
| Guard | Deferred; fires only when `returnedNormally` is true |

**What it is doing.** `State.Unlock` releases the global state mutex and, if
the state was modified, checkpoints the serialized state to the backend
first. The checkpoint retries for up to `unlockCheckpointRetryMaxTime` (5
minutes) at `unlockCheckpointRetryInterval` (3 seconds) intervals, and
`logger.Panicf` terminates the daemon if every attempt fails. The assertion
is a deferred postcondition check: it verifies that whenever `Unlock` returns
normally while holding a backend and dirty state, the checkpoint succeeded
(`checkpointSucceeded`) and the dirty flag was cleared (`!s.modified`).

**Conditions.**

- *Holds:* every normal return after a successful `Backend.Checkpoint` call.
  In that branch the code sets `checkpointSucceeded = true` and
  `s.modified = false` immediately before returning, so the conjunction is
  true by construction.
- *Does not fire:* clean unlocks (`!s.modified`), backend-less states
  (`s.backend == nil`, used by some tests), and the terminal
  `logger.Panicf` path all return or panic before `returnedNormally` is set,
  so the deferred check does not assert in those cases.
- *Fails:* only if a new return path is introduced between the dirty-state
  check and the retry loop that releases the lock with `s.modified` still
  set, or if `Backend.Checkpoint` returns `nil` while leaving
  `s.modified` semantics violated — i.e. exactly the class of silent
  divergence between memory and disk that this property exists to catch.

**Why it is correct to add.** It restates the documented contract of
`Unlock` ("does not return until the state is correctly checkpointed") as a
machine-checked postcondition at the single choke point. It observes the same
variables the function itself manages, adds no new control flow, and is
excluded from the panic and no-op paths so it never fires spuriously. It does
not claim the checkpointed bytes are durable or correct — only that the
success branch was taken before the lock was released — which is precisely
what the local variables can prove.

## 2. `overlord/state/task.go` — abort precedence in status setters

Both setters share one behavior: when a task has been aborted because a
parallel task in its change failed, a *late* completion request arriving
from the still-running handler must not overwrite the abort, otherwise the
task would be marked Done/Wait and never be undone. Each assertion observes
that the existing abort-preserving branch did its job.

### 2.1 `aborted task rejects competing done commit`

| Attribute | Value |
| --- | --- |
| Callsite | `Task.SetStatus`, `overlord/state/task.go:273` |
| Type | `AlwaysOrUnreachable` |
| Guard | Deferred; installed only when `old == AbortStatus && new == DoneStatus` |

**What it is doing.** When `SetStatus(DoneStatus)` is requested on a task
already in `AbortStatus`, the function returns early without changing the
status (comment: "keep it at aborted so it can transition to Undo"). The
deferred check verifies the final status is still `AbortStatus` after the
call.

**Conditions.**

- *Holds:* the early `return` at the top of the abort branch leaves
  `t.status` untouched, so `t.status == AbortStatus` is trivially true.
- *Is unreachable:* in workloads that never race a handler completion
  against an abort. This is why the type is `AlwaysOrUnreachable` rather
  than `Always`: absence of the race in a campaign is not a failure.
- *Fails:* only if the abort branch is changed to perform a status
  transition (e.g. a future refactor that calls `changeStatus` before the
  early return), or if a competing goroutine mutated `t.status` in between —
  which the state lock precludes.

**Why it is correct to add.** The competing-Done race is the core of the
abort protocol described in `overlord/README.md`: an in-flight handler that
finishes after its change was aborted must lose. Asserting the losing
outcome at the exact setter documents and protects the invariant without
changing any behavior. The state lock is held (`t.state.writing()` was
called), so the observed status is stable and the check is race-free.

### 2.2 `aborted task rejects competing wait commit`

| Attribute | Value |
| --- | --- |
| Callsite | `Task.SetToWait`, `overlord/state/task.go:306` |
| Type | `AlwaysOrUnreachable` |
| Guard | Deferred; installed only when `old == AbortStatus` |

**What it is doing.** `SetToWait` has the same early-return shape: an
aborted task requested to enter `WaitStatus` (a handler returning `&Wait{}`
while the change is being aborted) stays aborted. The deferred check verifies
two things: `t.status` is still `AbortStatus` *and* the pre-existing
`t.waitedStatus` was preserved (`t.waitedStatus == waitedStatus`, captured
before the branch).

**Conditions.**

- *Holds:* the early `return` skips both the `t.waitedStatus = resultStatus`
  assignment and the `changeStatus` call, so both equalities hold by
  construction.
- *Is unreachable:* as above, when the workload never races a wait request
  against an abort.
- *Fails:* if the abort branch ever clobbers `waitedStatus` (which would
  corrupt the restore-after-wait protocol for the *undo* pass) or performs a
  status transition.

**Why it is correct to add.** It extends the same abort-precedence
invariant to the second legal completion request (`Wait`), and additionally
guards the `waitedStatus` side channel that `SetToWait` owns. Capturing
`waitedStatus` before the branch makes the check self-contained: it compares
the observed value against a snapshot taken under the same lock, so no
torn read is possible.

## 3. `overlord/state/change.go` — abort acceptance

### 3.1 `snap abort accepted during in-flight task`

| Attribute | Value |
| --- | --- |
| Callsite | `Change.abortTasks`, `overlord/state/change.go:802` |
| Type | `Reachable` |
| Guard | `taskEffectiveStatus(t) == DoingStatus` case |

**What it is doing.** A pure coverage witness on the branch where lane
abort logic stops a task that is *currently executing* (`SetStatus(AbortStatus)`
on a Doing task). No condition is asserted; the event proves the workload
exercises the in-flight abort path rather than only the cheaper
pending-task (`HoldStatus`) and done-task (`UndoStatus`) branches.

**Conditions.**

- *Fires:* whenever a change containing parallel tasks has one task fail
  while a sibling in the same lane is still Doing. The
  `abort-accepted` spread test exists specifically to drive this branch.
- *Never fires:* in workloads where failures only affect pending or already
  completed tasks. That is a coverage gap in the workload, not a snapd bug,
  which is exactly what a `Reachable` property is meant to surface.

**Why it is correct to add.** Antithesis fault injection targets recovery
paths; the in-flight abort (handler killed mid-execution, tomb
termination, transition to undo) is the most complex recovery path in the
task engine and the one most likely to regress. Placing the witness on the
exact `DoingStatus` arm — after `SetStatus(AbortStatus)`, before any lane
bookkeeping — means the event maps 1:1 to "an in-flight task accepted the
abort". It cannot affect behavior because `Reachable` has no branch.

## 4. `overlord/state/taskrunner.go` — handler finalization, cleanup, dispatch

### 4.1 `aborted handler completion follows cancellation transition`

| Attribute | Value |
| --- | --- |
| Callsite | `TaskRunner.run` locked epilogue, `overlord/state/taskrunner.go:327` |
| Type | `AlwaysOrUnreachable` |
| Guard | Deferred-shape: fires only when `wasAborted` was observed |

**What it is doing.** When a handler finishes (its tomb is reaped under
`r.mu` plus the state lock), `run` must translate the handler result into the
*correct terminal status even if the task was aborted mid-flight*. Before the
result switch, the code snapshots `wasAborted := t.Status() == AbortStatus`
and computes the expected outcome independently of the switch:

| Handler result (`err`) | Expected final status |
| --- | --- |
| aborted, `nil` | `UndoStatus` |
| aborted, `*Retry` / `*Wait`, undo handler present | `UndoStatus` |
| aborted, `*Retry` / `*Wait`, no undo handler | `HoldStatus` |
| aborted, other error | `ErrorStatus` |

Note the shutdown normalization above (`r.stopped` converts foreign errors to
`*Retry`) happens *before* the expectation is computed, so shutdown
cancellation is accounted for. The assertion, placed after the result
switch, checks `t.Status() == expectedAbortStatus`.

**Conditions.**

- *Holds:* each arm of the result switch performs exactly the transition the
  table predicts: `Retry`/`Wait` on an aborted task call `r.tryUndo(t)` (which
  settles on Undo or Hold depending on undo-handler availability); `nil`
  transitions AbortStatus→UndoStatus directly; the default arm sets
  `ErrorStatus`. Because expectation and implementation are computed
  independently, agreement is a genuine check, not a tautology.
- *Is unreachable:* when no aborted task's handler completes in the
  workload.
- *Fails:* if any result arm mishandles the aborted case — e.g. a nil result
  leaving the task in AbortStatus (it would be re-aborted forever), a
  Retry arm marking it Done instead of Undo, or an error arm transitioning
  to Undo and hiding the failure.

**Why it is correct to add.** This is the single most subtle state machine
transition in the runner: the cross product of {handler result} x {aborted}
x {undo handler presence} x {shutdown normalization}. Encoding the expected
table independently and checking it at the end of the locked epilogue turns
an implicit protocol (currently guaranteed only by reading the switch)
into an explicit, falsifiable property. It observes only committed task
status under the state lock, so it is race-free.

### 4.2 `cleanup starts only after owning change is ready`

| Attribute | Value |
| --- | --- |
| Callsite | `TaskRunner.clean`, `overlord/state/taskrunner.go:364` |
| Type | `AlwaysOrUnreachable` |
| Guard | Fires on the handler-present path (after the `!ok` early return) |

**What it is doing.** `Task.SetClean` documents that "cleaning a task must
only be done after the change is ready". `clean` implements this by returning
early when `!t.Change().IsReady()`. This assertion states the positive form
on the path that actually launches a cleanup handler: `changeReady` is true
whenever we reach the `tomb.Go(cleanup...)` dispatch.

**Conditions.**

- *Holds:* the only way past the top of `clean` is `changeReady == true`
  (the function returned otherwise), so the condition is true by
  construction on this path.
- *Is unreachable:* when no task with a registered cleanup handler ever
  reaches a ready change in the workload.
- *Fails:* only if a future edit adds a second dispatch path that bypasses
  the `IsReady` gate — precisely the regression the property protects
  against.

**Why it is correct to add.** Running cleanups early is a real hazard:
cleanup handlers delete task-local temporary data, and executing them while
the change can still fail (and tasks can still be undone and re-run) would
destroy data a retry needs. The property is intentionally placed *after* the
gate rather than inside the `if`, so it observes the launch of real work,
not the no-op return. It adds one lock-held comparison; no behavior change.

### 4.3 `runner clean commit follows eligible cleanup or no-handler path` (two callsites)

| Attribute | Value |
| --- | --- |
| Callsite 1 | `TaskRunner.clean` no-handler path, `overlord/state/taskrunner.go:351` |
| Callsite 2 | `TaskRunner.clean` successful-cleanup path, `overlord/state/taskrunner.go:385` |
| Type | `AlwaysOrUnreachable` |
| Guard | Callsite 1: `!ok`; callsite 2: `tomb.Err() == nil` |

**What it is doing.** `clean` may mark a task clean (`t.SetClean()`) on
exactly two paths: (a) there is no cleanup handler registered for the kind
(`!ok`), so the default `SetClean` applies; (b) a cleanup handler ran and
returned no error. The two callsites share one message but record which path
was taken via the `cleanup-handler-present` / `cleanup-outcome` details, and
both assert the full context: readiness, handler eligibility, and (for the
second) success of the handler itself.

**Conditions.**

- *Holds (path 1):* reached only when the change is ready and the kind has
  no handler; `changeReady && !ok` is true by construction.
- *Holds (path 2):* reached only inside the `tomb.Err() == nil` branch of the
  cleanup goroutine's locked epilogue; `changeReady && ok && tomb.Err() == nil`
  is true by construction.
- *Is unreachable:* when the workload never completes a change whose tasks
  have (or lack) cleanup handlers.
- *Fails:* if a task is marked clean through any other condition — e.g. a
  future change calling `SetClean` after a failed cleanup, or from outside
  `clean` while the change is not ready.

**Why it is correct to add.** `IsClean` gates whether `Ensure` re-runs
cleanup; marking a task clean without eligible justification would silently
leak temporary data across restarts. The paired callsites make the two legal
commit paths explicit and symmetric, and the shared message keeps them as
one property in the Antithesis catalog with path-distinguishing details.
Both run under the state lock (the goroutine epilogue re-acquires it), so
observations are stable.

### 4.4 `task dispatch respects runner scheduling gates`

| Attribute | Value |
| --- | --- |
| Callsite | `TaskRunner.Ensure` dispatch loop, `overlord/state/taskrunner.go:541` |
| Type | `Always` |

**What it is doing.** The dispatch loop applies a sequence of gates before
`r.run(t)` may be called; the assertion verifies the complete conjunction at
the moment of dispatch:

- runner not stopped (`!r.stopped`),
- status is dispatchable (`DoStatus`, `DoingStatus`, `UndoStatus`, or
  `UndoingStatus`),
- a handler exists for the direction (`handlers.do`, or `handlers.undo` for
  undo statuses),
- no tomb is already active for the task (`tb == nil`),
- dependencies satisfied (`!dependenciesBlocked`, from `mustWait`),
- retry time reached (`retryDue`, i.e. no scheduled `AtTime` in the future),
- no blocked predicate matched (`!blockedByPredicate`).

To expose each gate to the assertion, the loop was refactored: the
`ConsiderTasks` label and `continue` statements were replaced by named
booleans (`dependenciesBlocked`, `retryDue`, `blockedByPredicate`), and the
`retryDue` inversion preserves the original
`!tWhen.IsZero() && ensureTime.Before(tWhen)` skip logic. The accompanying
`taskrunner_assertions_test.go` verifies the refactored loop is
behavior-equivalent.

**Conditions.**

- *Holds:* by construction — every named boolean encodes a `continue` branch
  that was taken (or not) earlier in the same iteration, and reaching the
  `assert` line means none of the gates fired. `dispatchStatusValid` and
  `handlerAvailable` re-derive conditions the earlier `switch`/`if`
  statements already guaranteed.
- *Fails:* if any gate is added, removed, or reordered such that dispatch
  happens while a gate condition is false — e.g. dispatching a task whose
  dependencies are not Done, or running a second tomb over a live one.
  Because the booleans are computed independently of the control flow, a
  regression in the loop logic breaks the conjunction even when behavior
  *appears* unchanged in the happy path.

**Why it is correct to add.** This is the schedulability core of the whole
overlord: every manager's progress funnels through this loop. The original
labeled-continue structure made the gate set implicit; making each gate a
named value both documents the scheduling protocol and lets one `Always`
property hold the implementation to it. The refactor was kept semantic-only
(verified by tests), the check runs under the state lock, and
`Always` (not `AlwaysOrUnreachable`) is appropriate because any workload
that completes a task must pass through this line.

## 5. `overlord/stateengine.go` — manager visitation

### 5.1 `completed ensure pass visits every registered manager`

| Attribute | Value |
| --- | --- |
| Callsite | `StateEngine.Ensure`, `overlord/stateengine.go:192` |
| Type | `Always` |
| Guard | Deferred; fires only when `returnedNormally` is true |

**What it is doing.** `StateEngine.Ensure` iterates the registered managers
and calls `m.Ensure()` on each. A manager skipped by this loop would never
dispatch its tasks — its changes would sit forever. The instrumentation adds
two per-manager counters, `entered` and `returned`, incremented immediately
before and after each `m.Ensure()` call, plus a `returnedNormally` flag. The
deferred check asserts that on a normal pass every manager slot was both
entered and returned-from exactly once, and that the counter slices match
the manager list length.

**Conditions.**

- *Holds:* on every normal completion, including passes where some managers
  returned errors: manager errors are collected into `errs` (and logged),
  not used to `return` or `panic` mid-loop, so the counters still cover all
  managers before `returnedNormally = true` executes.
- *Does not fire:* when a manager panics or the goroutine is otherwise
  unwound before the loop completes; `returnedNormally` remains false and
  the deferred check exits early. (This is deliberate: a manager panic is
  already a daemon failure surfaced through the deferred recover-less
  unwinding; the property would only add noise.)
- *Does not fire:* when the engine was never started (`!se.startedUp`) or
  was already stopped — those return before any counting.
- *Fails:* if the loop gains an early `return`/`break`/`continue` that skips
  a manager, or if `se.managers` is mutated concurrently during the pass
  (precluded by `mgrLock`, held for the whole function).

**Why it is correct to add.** The `ensureError` aggregation design means
"loop completes" is the engine's central liveness contract; encoding it as
`Always` with per-slot evidence (`entered`/`returned` slices in the details)
gives triage an exact pointer to any skipped manager. The counters add two
slice increments per manager per pass — negligible for the ensure cadence
(roughly once per second plus `EnsureBefore` nudges), and the
`se.ensurePass` counter disambiguates passes in the log stream. The
nine-scenario subprocess matrix in `stateengine_assertions_test.go` verified
encounters, slot counts, duplicate registration, vacuous empty success,
lifecycle rejection, panic exclusion and post-panic recovery.

## 6. `overlord/snapstate/snapstate.go` — sequence membership on write

### 6.1 `committed app current belongs to its revision sequence`

| Attribute | Value |
| --- | --- |
| Callsite | `snapstate.Set`, `overlord/snapstate/snapstate.go:4253` |
| Type | `Always` |
| Guard | `snapst.SnapType == string(snap.TypeApp) && !snapst.TryMode`, on the store (non-delete) path |

**What it is doing.** `Set` is the single write boundary for per-snap state:
it serializes the `SnapState` and stores it under `state("snaps")`. For
non-try-mode app snaps, the assertion scans `snapst.Sequence.Revisions` for
a non-nil revision whose `rev.Snap.Revision == snapst.Current` and asserts
one exists (`currentInSequence`).

**Conditions.**

- *Holds:* whenever the caller passes a structurally consistent `SnapState`
  — the invariant snapd's own task handlers maintain: `Current` is always
  one of the revisions in `Sequence`, including for disabled instances.
- *Does not apply:* to deletion (`snapst == nil` or empty sequence deletes
  the entry), non-app snap types, and try-mode states (`TryMode` snapshots
  legitimately carry out-of-sequence experimental revisions).
- *Does not apply:* to unset `Current` — the scan condition includes
  `!snapst.Current.Unset()`, so a freshly seeded app state with no current
  revision yet is not required to match (this also keeps the property true
  for sideload-first-install flows).
- *Fails:* if any code path builds a `SnapState` whose `Current` references
  a revision absent from its `Sequence` — e.g. a botched sequence pruning or
  a refresh that swaps the current pointer without updating the sequence.
  Persisting such a state would corrupt every later reader
  (`CurrentRevisionSequence` lookups, revert, removal).

**Why it is correct to add.** The check runs after successful
`json.Marshal`, before the raw message is written into the state, so it
gates exactly what gets committed; a false condition changes nothing about
serialization (no rejection, no panic). `Always` is correct because
`Set` on a non-try app with a set current is a mandatory pass through this
line in any install/refresh/remove workload. The details
(`instance`, `current`, `active`, `sequence-length`) are enough to identify
the offending snap in triage. What it does *not* prove: that the intended
revision was selected, or that installed blob resources match the recorded
state — those need independent oracles noted in
[existing-assertions.md](existing-assertions.md).

## 7. `store/store_download.go` — download recovery witnesses

These four assertions are all `Reachable` coverage witnesses. They assert no
condition; each proves that a specific fault-recovery branch inside
`Store.Download` is actually exercised. Antithesis fault injection (corrupted
cache files, truncated partial downloads, tampered blobs) is designed to
drive exactly these paths, and a campaign that never fires them is a campaign
coverage gap, not a snapd bug.

### 7.1 `snap download recovered a valid cache entry`

| Attribute | Value |
| --- | --- |
| Callsite | `Store.Download` cache recovery, `store/store_download.go:170` |
| Type | `Reachable` |
| Guard | Second cache fetch succeeded and `isDownloadLikelyNotCorrupted` passed |

**What it is doing.** Witness on the recovery branch: the preexisting target
path was found corrupted, was removed, and a fresh pull from the download
cache (`s.cacher.Get`) yielded a file that passes the corruption heuristic.
The download is served from cache without network traffic.

**Conditions.**

- *Fires:* when a download target exists but fails validation, and the
  cache holds a good copy — the classic partial-download-plus-restart
  scenario the cache exists for.
- *Never fires:* when the cache is empty or also corrupt (control falls
  through to cache eviction and re-download).

**Why it is correct to add.** This branch previously existed as a bare
`return nil` after a `logger.Debugf`; without a witness nothing in the
test evidence would distinguish "recovery works" from "recovery never
triggers". The surrounding `if` was restructured (single condition split
into nested checks) to expose both outcomes — a semantic-preserving change
verified by the store SDK-output matrix.

### 7.2 `snap download rejected a wrong-size cache entry`

| Attribute | Value |
| --- | --- |
| Callsite | `Store.Download` cache rejection, `store/store_download.go:179` |
| Type | `Reachable` |
| Guard | `os.Lstat` succeeded, expected size known, sizes differ |

**What it is doing.** Witness on the negative outcome of cache recovery:
the re-fetched cache entry is also unusable, and specifically the failure is
observable as a size mismatch between the file on disk and
`downloadInfo.Size`.

**Conditions.**

- *Fires:* when the cached blob has been corrupted in a way that changes its
  length (truncation, partial write) — the shape of corruption Antithesis
  disk faults produce.
- *Never fires:* for corruption that preserves size (the corruption check
  above is heuristic), for missing files (`Lstat` fails), or when
  `downloadInfo.Size` is unknown (zero), since a missing expected size
  cannot prove a mismatch.

**Why it is correct to add.** Together with 7.1 it gives the cache-recovery
`if` a two-outcome matrix: recovery succeeded, or recovery failed with
evidence. Without it, a campaign that silently always re-downloads (cache
never populated, or always corrupt) would look identical to one where
recovery works.

### 7.3 `snap download resumes from a nonzero offset`

| Attribute | Value |
| --- | --- |
| Callsite | `Store.Download` resume path, `store/store_download.go:256` |
| Type | `Reachable` |
| Guard | `resume > 0` inside the `downloadInfo.Size == 0 || resume < downloadInfo.Size` arm |

**What it is doing.** Witness that an interrupted download is resumed from
its partial `.partial` file rather than restarted: the file is opened,
seeked to end, and `resume` records the surviving byte count.

**Conditions.**

- *Fires:* when a previous download attempt left a non-empty `.partial`
  file smaller than the full blob — i.e. after a killed/interrupted
  download of the same snap.
- *Never fires:* on first download, or when the partial file was removed by
  the error cleanup (`LeavePartialOnError` unset).

**Why it is correct to add.** Resume correctness (Range request from
`resume`, hash over the concatenated result) is only exercised when the
branch is taken at all; the witness anchors campaign coverage of the
interrupted-download scenario, which the fault harness is expected to
generate.

### 7.4 `snap download retries after a hash mismatch`

| Attribute | Value |
| --- | --- |
| Callsite | `Store.Download` hash-error retry, `store/store_download.go:282` |
| Type | `Reachable` |
| Guard | `err` is a `HashError` after download or full-file verification |

**What it is doing.** Witness on the single retry: a downloaded (or
reconstructed) file whose SHA3-384 does not match the store's expected digest
is truncated and re-downloaded from scratch. The `err.(HashError)` type
assertion was refactored to a checked binding (`hashErr, ok :=`) to carry
actual-vs-expected digests into the details.

**Conditions.**

- *Fires:* on any hash mismatch — whether from a corrupted transfer, a
  tampered cache/medium (the Antithesis fault), or a fully-downloaded file
  verified in the `resume >= downloadInfo.Size` arm.
- *Never fires:* on clean downloads. A campaign with zero hash-mismatch
  events means corruption faults are not reaching the download path.

**Why it is correct to add.** Hash mismatch is the terminal integrity check
of the whole download pipeline; the retry (with truncation) is a stateful
recovery that could itself regress (e.g. retrying without truncating would
append). The witness records both digests so triage can confirm the
mismatch was injected corruption, not a digest-computation bug.

## Cross-cutting notes

- **Locking.** Every condition-bearing assertion runs while the state lock
  (or `mgrLock`/`r.mu` for the engine/runner) is held, so observed values are
  stable and the assertions are race-free; the artifact daemon is built with
  `-race` and the suites pass under it.
- **No behavior change.** All assertions observe values computed by existing
  or equivalent control flow; where control flow was refactored
  (`TaskRunner.Ensure` gates, the download cache `if`, the `HashError`
  binding), equivalence is covered by the `*_assertions_test.go` files,
  which also run under `-tags=no_antithesis_sdk` to confirm the SDK can be
  compiled out.
- **Catalog.** The SDK generates the assertion catalog from these literals
  at build time; all messages are embedded in the snapd artifact. There are
  intentionally no `Sometimes` or `Unreachable` callsites in the SUT.
- **Limits.** These properties observe internal consistency at the
  instrumented boundaries; they do not independently validate stored bytes
  (checkpoint), intended revision selection (sequence membership), or
  fault semantics in a real Antithesis run. See
  [existing-assertions.md](existing-assertions.md) for the full coverage
  assessment and open questions.