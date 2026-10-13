# cleanup-follows-readiness

## Scope and Property

Scope answer (verbatim): "just this directory". External references: `[]`.
Evidence revision: `e88ec08852fbc8af019dc39e22097e5720aa6dfd` (2026-10-13).
Focus: lifecycle, concurrency and replay; evidence only.

Priority: **P1 (high)**. Type: **Safety**. Confidence: **high** for readiness
ordering, not a guarantee that arbitrary cleanup effects are replay-safe.

Runner cleanup starts or marks a task clean only after its entire owning change
is ready. Readiness permits cleanup; it does not mean cleanup has completed.

## Code and Test Evidence

- [overlord/state/taskrunner.go](../../../overlord/state/taskrunner.go#L383), `Ensure`:
  skips an existing task tomb, then routes ready, not-clean tasks to `clean`.
  A single task becoming ready is insufficient to authorize its cleanup.
- [overlord/state/taskrunner.go](../../../overlord/state/taskrunner.go#L314), `clean`:
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
- [overlord/state/taskrunner_test.go](../../../overlord/state/taskrunner_test.go#L1049),
  `TestPrematureChangeReady`: a blocked undo keeps the change unready despite a
  peer error. This tests readiness, not cleanup callback entry directly.
- [overlord/state/taskrunner_test.go](../../../overlord/state/taskrunner_test.go#L1225),
  `TestCleanup`: after tasks finish the change is not yet clean; first cleanup
  errors and remains unclean, second succeeds, later Ensure does not repeat it.
- [overlord/overlord_test.go](../../../overlord/overlord_test.go#L1094),
  `TestSettleChainWCleanup`: Settle observes cleanup effects as well as Done tasks.
- [overlord/README.md](../../../overlord/README.md#L112): cleanup is outside conflict
  protection, so it must be task-local and must not affect another change.

## Proposed SDK Checks and Safe Condition

`AlwaysOrUnreachable(changeReadyAtCleanupAdmission, "task cleanup starts only
after owning change readiness", details)` checks the accepted branch in `clean`
before either immediate SetClean or callback launch. Record task readiness too:
Ensure only calls clean for ready tasks. Use the actual locked IsReady result,
not a change API status read at a different time. Optional-path safety fits
cleanup: campaigns without completed known tasks need not encounter it.

A separate optional completion check,
`AlwaysOrUnreachable(runnerCleanCommitIsAuthorized, "runner cleanup clean commit
has ready owner and successful outcome", details)`, checks the runner's SetClean
sites. Callback completion requires a nil effective tomb result and ready owner;
the no-handler path requires ready owner and no registered cleanup. Do not demand
a callback ran for a kind with no cleanup handler, nor label an expected cleanup
error a property violation. The runner must not newly mark clean because an
attempt failed; this does not prohibit a callback's independently authorized
explicit SetClean. Record pre-clean state and the actor to distinguish them.

Predicates above are proposed. Details carry runner incarnation, task/change ID,
task status, owner IsReady/IsClean, pre/post task clean flag, cleanup attempt,
handler presence and tomb result. Keep check placement observational under the
existing runner/state locks; never call cleanup again to evaluate a predicate.

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

Cheap discriminating check: TestCleanup explicitly has a ready-but-unclean phase
and a failed attempt followed by success. Compare these expectations with clean's
entry guard and nil-result SetClean branch. Inspected, not executed in this pass.

## Instrumentation Status

**Missing**: cleanup-admission and runner-clean-commit SDK assertions.
[antithesis/scratchbook/existing-assertions.md](../existing-assertions.md)
lists no cleanup SDK coverage. The taskCleanChanged panic is present but detects
an invalid clean marking, not early entry into a destructive cleanup callback.
SUT-side observations are needed for that invisible admission window.

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
- Missing: SDK observations at callback admission; tests do not prove real
  filesystem cleanup replay safety, which is not claimed here.
- Conclusion: resolved as an ordering invariant, explicitly separating ready,
  clean, successful outcome and eventual cleanup progress.