# cleanup-follows-readiness

## Scope and Property

Scope answer (verbatim): "just this directory". External references: `[]`.
Evidence revision: `d7d23f20732844eb538dab1169f8b8b372376911` (2026-11-12).
Focus: lifecycle, concurrency and replay; evidence only.

Priority: **P1 (high)**. Type: **Safety**. Confidence: **high** for readiness
ordering, not a guarantee that arbitrary cleanup effects are replay-safe.

Runner cleanup starts or marks a task clean only after its entire owning change
is ready. Readiness permits cleanup; it does not mean cleanup has completed.

## Code and Test Evidence

- [overlord/state/taskrunner.go](../../../overlord/state/taskrunner.go#L434), `Ensure`:
  skips an existing task tomb, then routes ready, not-clean tasks to `clean`.
  A single task becoming ready is insufficient to authorize its cleanup.
- [overlord/state/taskrunner.go](../../../overlord/state/taskrunner.go#L342), `clean`:
  first checks `t.Change().IsReady()`. Without a cleanup handler it calls SetClean;
  otherwise it publishes a tomb and starts cleanup asynchronously. Completion
  reacquires runner/state locks; only a nil tomb result makes the runner call
  SetClean. Errors leave cleanup eligible for a later Ensure attempt.
- [overlord/state/taskrunner.go](../../../overlord/state/taskrunner.go#L166), `AddCleanup`:
  cleanup runs regardless of final task status, independently of task wait order,
  and errors are retryable. Normal blocking and dependency gates do not order it.
- [overlord/state/change.go](../../../overlord/state/change.go#L85), `Status.Ready`:
  Done, Undone, Hold and Error are ready; ready does not mean successful.
- [overlord/state/change.go](../../../overlord/state/change.go#L491), `Ready`, and
  [overlord/state/change.go](../../../overlord/state/change.go#L542), `IsReady`:
  readiness is a closed-channel history, distinct from aggregate status. An empty
  newly-created change can have Hold status but IsReady false. Status overrides
  are supported; do not silently substitute all-task success for this API.
- [overlord/state/change.go](../../../overlord/state/change.go#L551), `taskCleanChanged`:
  unready change cleaning panics; the change clean flag is set only after all
  tasks' clean flags are set. This is an existing guard, not an SDK assertion.
- [overlord/state/task.go](../../../overlord/state/task.go#L318), `SetClean`:
  idempotent clean flag update, notifying the owning change when present.
- [overlord/state/taskrunner_test.go](../../../overlord/state/taskrunner_test.go#L1127),
  `TestPrematureChangeReady`: a blocked undo keeps the change unready despite a
  peer error. This tests readiness, not cleanup callback entry directly.
- [overlord/state/taskrunner_test.go](../../../overlord/state/taskrunner_test.go#L1303),
  `TestCleanup`: after tasks finish the change is not yet clean; first cleanup
  errors and remains unclean, second succeeds, later Ensure does not repeat it.
- [overlord/overlord_test.go](../../../overlord/overlord_test.go#L1094),
  `TestSettleChainWCleanup`: Settle observes cleanup effects as well as Done tasks.
- [overlord/README.md](../../../overlord/README.md#L112): cleanup is outside conflict
  protection, so it must be task-local and must not affect another change.

## Implemented SDK Checks and Safe Condition

`AlwaysOrUnreachable(changeReady, "cleanup starts only after owning change is
ready", details)` is emitted before the registered cleanup callback starts.
The locked `IsReady` result is captured once; an unready change returns without
starting cleanup. Ensure also requires the task status to be ready and its clean
flag to be false before calling `clean`.

`AlwaysOrUnreachable(changeReady && (noHandler || cleanupSucceeded), "runner
clean commit follows eligible cleanup or no-handler path", details)` is emitted
immediately before runner-owned `SetClean`. The no-handler path records
`cleanup-outcome=no-handler`; a callback path is eligible only after a nil tomb
result and records `cleanup-outcome=success`. A cleanup error emits no commit
assertion and remains retryable. Callback-owned `SetClean` remains a separate
actor and is not covered by this runner assertion.

Details carry task/change ID, kind, handler presence and cleanup outcome. The
checks use the readiness and tomb-result decisions already made by the runner;
they do not call cleanup again to evaluate a predicate.

Do not assert `IsReady == IsClean`, require Done-only changes, impose do/undo
dependency order on cleanup, or claim global conflict exclusion. State locking
alone does not freeze cleanup filesystem effects. This property applies to
normal owning-change lifecycle, not deliberate test-only ready-channel/status
rewrites. An already-clean task is a skip; no-handler SetClean is valid.

## Scenario, Fault Angle and Impact

Complete one task while a sibling or undo remains blocked: its temporary undo
data must remain available until whole-change readiness. Then finish the change,
pause cleanup outside the state lock, overlap unrelated admissions, return an
error, and retry successfully. Interrupt after cleanup effects but before clean
checkpoint and recover: re-entry is allowed, not exactly-once cleanup. External
effect idempotence needs a fixture-specific oracle beyond this ordering check.

Pauses, rollback interleavings and restarts explore early deletion of undo data
and lost cleanup commits. Impact: prematurely discarded recovery data can break
rollback; deferred/repeated cleanup can leak or damage resources if not task-local.

Validation: `TestTaskCleanupAssertions` checks no-handler commit, successful
cleanup commit, error-then-retry, and an unready owning change with no cleanup
encounter. Existing `TestCleanup` also passes. The full `overlord/state` race
suite and SDK-disabled state suite passed. These checks cover ordering and retry
control flow, not filesystem cleanup idempotence or faulted replay.

## Instrumentation Status

**Implemented locally**: separate optional assertions cover cleanup admission
and runner-owned clean commits. The existing `taskCleanChanged` panic remains a
separate guard against cleaning an unready change; it is not substituted for
the callback-admission assertion.

Cleanup convergence is separate: a future finite quiet cohort can require every
eligible ready task to become clean, with an independent oracle and a deadline
calibrated catalog-wide. A Sometimes successful-clean witness cannot establish
every task eventually cleans, and Settle returning nil is not a general proof
that all unready changes completed.

## Open Questions

None within cleanup admission/commit ordering. Catalog-wide quiet calibration
and fixture-specific cleanup-effect recovery are not assumed by this property.

### Investigation Log

#### Does ready mean clean, and can cleanup fail or replay?

- Examined: Ensure, AddCleanup, clean, Task.SetClean, Change readiness/clean flags,
  TestCleanup, TestPrematureChangeReady and TestSettleChainWCleanup.
- Found: whole-change IsReady gates entry; clean is separate; errors retry;
  no-handler marking is legal; persisted unclean work can re-enter after restart.
- Missing: filesystem cleanup replay safety and faulted-campaign observations,
  which are not claimed here.
- Conclusion: implemented the ordering invariant, explicitly separating ready,
  clean, successful outcome and eventual cleanup progress.