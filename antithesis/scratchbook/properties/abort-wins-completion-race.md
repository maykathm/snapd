# abort-wins-completion-race

## Scope and Property

Scope answer (verbatim): "just this directory". External references: `[]`.
Evidence revision: `e88ec08852fbc8af019dc39e22097e5720aa6dfd` (2026-10-13).
Focus: concurrency, lifecycle and replay; evidence only.

Priority: **P0 (critical)**. Type: **Safety**. Confidence: **high** for the
locked transition contract; this does not prove rollback eventually succeeds.

When cancellation has put a task in AbortStatus before a competing success or
wait commit, the commit preserves cancellation; runner finalization consumes
Abort into its defined undo/hold/error path rather than ordinary success.

## Code and Test Evidence

- [overlord/state/change.go](../../../overlord/state/change.go#L685), `Change.Abort`, and
  [overlord/state/change.go](../../../overlord/state/change.go#L792), `abortTasks`:
  pending Do becomes Hold, Doing becomes Abort and Done becomes Undo. Effective
  Wait status is used. AbortLanes can preserve a task sharing a healthy lane;
  do not apply this property to every task merely because a lane was aborted.
- [overlord/state/task.go](../../../overlord/state/task.go#L262), `SetStatus`:
  a requested Done when old status is Abort is ignored.
- [overlord/state/task.go](../../../overlord/state/task.go#L282), `SetToWait`:
  Abort similarly blocks an explicit handler wait commit.
- [overlord/state/taskrunner.go](../../../overlord/state/taskrunner.go#L225), `run`:
  the tomb result can override the handler result; finalization locks `r.mu`
  then state, removes the tomb and interprets the effective error. Ordinary
  errors during Stop are normalized to Retry before choosing the transition.
- [overlord/state/taskrunner.go](../../../overlord/state/taskrunner.go#L258): Retry or
  Wait with Abort calls `tryUndo`, not schedule retry or commit Wait. Nil with
  Abort at [overlord/state/taskrunner.go](../../../overlord/state/taskrunner.go#L286)
  becomes Undo and requests another pass. Non-retry/wait errors abort lanes
  and set Error, not Done.
- [overlord/state/taskrunner.go](../../../overlord/state/taskrunner.go#L366), `tryUndo`:
  knowingly aborted work without undo becomes Hold; otherwise it becomes Undo.
- [overlord/state/task_test.go](../../../overlord/state/task_test.go#L147),
  `TestSetDoneAfterAbortNoop`, and
  [overlord/state/task_test.go](../../../overlord/state/task_test.go#L159),
  `TestSetWaitAfterAbortNoop`: direct commits preserve Abort.
- [overlord/state/change_test.go](../../../overlord/state/change_test.go#L475), `TestAbort`:
  status-dependent cancellation, including Wait with effective Done.
- [overlord/state/taskrunner_test.go](../../../overlord/state/taskrunner_test.go#L150),
  `TestSequenceTests`: blocked nil and Retry completions race with peer errors;
  its sequence table and expected statuses include no-undo Hold.
- [overlord/state/taskrunner_test.go](../../../overlord/state/taskrunner_test.go#L551),
  `TestExternalAbort`: a blocking handler must receive tomb cancellation.
- [overlord/state/taskrunner_test.go](../../../overlord/state/taskrunner_test.go#L581),
  `TestUndoSingleLane`: an explicit Done attempt in a slow handler races with
  lane failure; final tasks are Undone/Hold except the failing task's Error.

## Proposed SDK Checks and Safe Condition

Use distinct `AlwaysOrUnreachable` checks on these optional race encounters:

- `AlwaysOrUnreachable(postStatus == AbortStatus, "aborted task rejects competing
  done commit", details)` after SetStatus's Abort/Done guard.
- `AlwaysOrUnreachable(postStatus == AbortStatus, "aborted task rejects competing
  wait commit", details)` after SetToWait's Abort guard.
- `AlwaysOrUnreachable(finalizationMatchesAbortOutcome, "aborted handler completion
  follows cancellation transition", details)` after run's completion switch,
  conditioned on its locked pre-finalization status being Abort.

These are proposed predicates. Optional safety fits better than Sometimes:
each encountered race must be safe, but an ordinary workload may never encounter
it. A distinct Reachable checkpoint for a nil completion consuming Abort can
guide the cancellation window without pretending it proves progress.

Capture pre/post status and the **effective normalized tomb result**, not only
the raw handler result. For Abort before finalization: nil requires Undo;
Retry/Wait requires Undo with an undo handler or Hold without one; other errors
require Error. Observe the immediate transition under the existing locks and
record whether a follow-up Ensure was requested where required. Do not acquire
runner locks from Task setters, which are state-lock-owned boundaries.

The condition is a recorded Abort transition, not an API abort timestamp, global
change error, shutdown tomb signal or blanket lane label. A commit that wins
the state lock first may legally reach Done before later abort changes it to
Undo. Conversely, nil completion of aborted work without undo initially becomes
Undo, then Ensure can legally convert that no-undo Undo to Done. Therefore
"an aborted task can never be Done at any future time" is **not** this invariant.
Manual unrelated status rewrites and retained healthy-lane tasks are excluded.
Undo can fail or retry; rollback liveness and external semantic restoration are
separate checks, with any deadline calibrated catalog-wide.

## Scenario, Fault Angle and Impact

Pause after a do handler's external effect or just before its return; cancel
under the state lock via external abort or a peer task's lane failure. Resume
with nil, Retry, Wait and error results, and with explicit Done/Wait commits.
Repeat with and without undo handlers; restart from a persisted Abort separately.
The fault angle is an unlocked-effect/locked-commit interleaving. Lost cancellation
can leave work reported as successful without taking its required undo path.

Cheap discriminating check: compare the two task guard tests and sequence-test
Hold expectation with the exact normalized-error branches. Expectations were
inspected, not executed; no new defect is alleged.

## Instrumentation Status

**Present but invalid as a general premise**:
[overlord/state/change.go](../../../overlord/state/change.go#L451) already calls
`Always(new != HoldStatus, "change never enters hold status", ...)`.
[antithesis/scratchbook/existing-assertions.md](../existing-assertions.md)
documents it. Legitimate explicit Hold is tested at
[overlord/state/change_test.go](../../../overlord/state/change_test.go#L168), and pending
abort produces Hold. This assertion is not cancellation correctness coverage.
Do **not** add another copy or recommend a global no-Hold invariant. A future
implementation should correct/replace that broad premise with scoped checks.

**Missing**: the three scoped race assertions and nil/Abort replay checkpoint.
SUT-side pre/post observations are necessary: settled change status alone loses
the transition ordering. Existing unit assertions are not Antithesis SDK checks.

## Open Questions

None within the locked cancellation-transition scope. No universal rollback
success or monotonic no-Done guarantee is claimed.

### Investigation Log

#### Can Hold or a later Done be legal after cancellation?

- Examined: Change abort/lane selection, Task Done/Wait guards, run's normalized
  completion branches, tryUndo and no-undo Ensure; direct guard and runner tests.
- Found: pending/no-undo abort can Hold; nil/Abort goes to Undo even without undo;
  later no-undo Undo can become Done; healthy shared lanes can survive lane abort.
- Missing: scoped SDK checks; no unresolved local transition rule remains.
- Conclusion: reject the existing global no-Hold premise and assert the exact
  immediate race transition instead of inventing blanket terminal-status rules.