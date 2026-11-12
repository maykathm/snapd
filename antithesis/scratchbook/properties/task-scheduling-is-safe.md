# task-scheduling-is-safe

## Scope and Property

Scope answer (verbatim): "just this directory". External references: `[]`.
Evidence revision: `d7d23f20732844eb538dab1169f8b8b372376911` (2026-11-12).
Focus: concurrency and replay; evidence only.

Priority: **P0 (critical)**. Type: **Safety**. Confidence: **high** for runner
dispatch gates, not a claim of global serialization or handler idempotence.

Each do/undo dispatch obeys its status-specific gates and has no existing active
handler or cleanup for that task in the same runner incarnation.

## Code and Test Evidence

- [overlord/state/taskrunner.go](../../../overlord/state/taskrunner.go#L434), `Ensure`:
  holds `r.mu`, then the state lock; stopped runners return without dispatch.
  Unknown kinds with nil do handlers are skipped, including kinds owned by
  another runner. An existing task tomb prevents another dispatch or cleanup.
- [overlord/state/taskrunner.go](../../../overlord/state/taskrunner.go#L570), `mustWait`:
  fresh Do waits for every WaitTask to be Done; fresh Undo waits for every
  HaltTask to be ready. Doing and Undoing deliberately bypass these dependency
  checks to resume previously attempted work. Wait is not dispatched.
- [overlord/state/taskrunner.go](../../../overlord/state/taskrunner.go#L498): Undo without
  an undo handler waits for dependencies first, then becomes Done without a
  handler invocation. This does not license nil-handler dispatch.
- [overlord/state/taskrunner.go](../../../overlord/state/taskrunner.go#L510): a future
  AtTime prevents dispatch; Ensure tracks the earliest future schedule. Blocking
  predicates see existing tomb tasks and previously dispatched tasks appended
  to `running` during this pass. The predicates can be stateful.
- [overlord/state/taskrunner.go](../../../overlord/state/taskrunner.go#L194), `run`:
  selects direction, promotes Do/Undo to Doing/Undoing, clears AtTime, publishes
  a tomb before starting the handler, and finalizes under the same lock order.
  Handler return precedes tomb removal. Single flight is about handler activity,
  not the absence of a briefly exiting goroutine after tomb removal.
- [overlord/state/taskrunner_test.go](../../../overlord/state/taskrunner_test.go#L105),
  `sequenceTests`, executed by
  [overlord/state/taskrunner_test.go](../../../overlord/state/taskrunner_test.go#L150),
  `TestSequenceTests`: dependency sequencing, resumed Doing, retries and rollback.
- [overlord/state/taskrunner_test.go](../../../overlord/state/taskrunner_test.go#L939),
  `TestRetryAfterDuration`: Doing remains scheduled and cannot rerun too early;
  at eligibility it reruns, completes and clears its schedule.
- [overlord/state/taskrunner_test.go](../../../overlord/state/taskrunner_test.go#L1016),
  `testTaskSerialization`, and its SetBlocked/AddBlocked callers at
  [overlord/state/taskrunner_test.go](../../../overlord/state/taskrunner_test.go#L1092)
  and [overlord/state/taskrunner_test.go](../../../overlord/state/taskrunner_test.go#L1108):
  a repeated Ensure cannot start another task while the predicate blocks it;
  completing the first requests a new pass.
- [overlord/state/taskrunner_test.go](../../../overlord/state/taskrunner_test.go#L1198),
  `TestUndoSequence`: reverse dependency ordering across tasks without undo.
- [overlord/state/taskrunner.go](../../../overlord/state/taskrunner.go#L541), `Ensure`:
  an `Always` check immediately before `run` validates a dispatch snapshot using
  the already-captured status, handler pair, tomb, dependency-blocked result,
  retry-due result and short-circuiting blocked-predicate result.
- [overlord/state/taskrunner_assertions_test.go](../../../overlord/state/taskrunner_assertions_test.go#L99),
  `TestTaskDispatchAssertion`: isolated SDK-output cases cover Do/Undo, Doing/
  Undoing replay with unsatisfied fresh dependencies, blocked Do/Undo, a future
  retry time and a stateful blocker evaluated exactly once.

## Implemented SDK Check and Safe Condition

`Always(dispatchSnapshotIsEligible, "task dispatch respects runner scheduling
gates", details)` runs immediately before `run`. The snapshot uses the actual
status after Abort-to-Undo/Hold handling, the captured handler pair, whether a
tomb already existed, the single status-sensitive `mustWait` result, whether
AtTime was due, and the result of the blocked-predicate loop. The predicates are
not invoked again for the assertion. Details record task/change ID, kind,
status, direction, handler availability, active-tomb result, dependency-blocked
result, retry-due result, blocker result and retry time.

| Pre-dispatch status | Required dependency gate | Other dispatch gates |
| --- | --- | --- |
| Do | All WaitTasks are Done | Owned do handler, due, unblocked, no task tomb |
| Doing | No fresh dependency gate | Owned do handler, due, unblocked, no task tomb |
| Undo | All HaltTasks are ready | Owned do and undo handlers, due, unblocked, no task tomb |
| Undoing | No fresh dependency gate | Owned do and undo handlers, due, unblocked, no task tomb |

Also require the runner is not stopped. An Abort candidate is first transformed
by `tryUndo`; capture the actual status after that transformation. Ready, Wait,
unknown-kind and future/blocked candidates are skips, not dispatches. Cleanup
uses a separate readiness property and bypasses normal do/undo gates.

Capture inputs before `run` changes status and clears schedule. Record existing
predicate results; **do not invoke predicates again** for an assertion, since
even test predicates mutate observational state. Record preexisting activity
before inserting the new tomb. The guard is runner-local: it does not assert
global ownership across TaskRunner instances or process incarnations.

Single flight is **per runner**, not global across independent TaskRunner
instances or across process incarnations. Ownership discipline is a separate
contract. Independent tasks can run concurrently, and lanes are failure domains,
not serialization gates. Doing/Undoing replay is legal and is not exactly-once
execution; handler side effects still need their own semantic recovery oracle.

## Scenario, Fault Angle and Impact

Pause a handler outside the state lock while another Ensure runs; combine a
dependency DAG, independent tasks, stateful blocking predicates and timed Retry.
Restart from persisted Doing and Undoing separately, then attempt scheduling
before and after eligibility. Pauses explore same-pass and cross-pass overlap;
restart explores replay direction. Premature or duplicate dispatch can corrupt
external effects, run undo out of order or violate subsystem blocking contracts.

Validation: `TestTaskDispatchAssertion`, `TestRetryAfterDuration`, the full
`overlord/state` race suite, and the SDK-disabled state suite passed. The local
SDK matrix observed encounters for all four dispatch statuses and no encounters
for blocked, not-due, or predicate-blocked cases. It simulates Doing/Undoing
status replay in-process; it does not test persistence across a daemon restart.

## Instrumentation Status

**Implemented locally**: the dispatch snapshot `Always` check and its focused
SDK-output matrix are present. The tomb map remains the single-flight gate; the
assertion verifies its pre-dispatch state. No Reachable replay anchors or
persistent Doing/Undoing restart scenario have been added. SUT-side placement is
needed because an eventual correct outcome can conceal transient duplicate or
premature execution.

## Open Questions

None within the per-runner dispatch contract. Global task ownership and arbitrary
handler-effect idempotence are explicitly outside this property's premise.

### Investigation Log

#### Do replay and fresh tasks share all gates, and is single flight global?

- Examined: Ensure, mustWait, run, tryUndo, cleanup tombs; sequence, timed-retry,
  serialization and undo-sequence tests; the supplied Overlord task guidance.
- Found: dependency gates differ by status; AtTime and blocking still apply to
  replay; tomb ownership is per runner; no-undo Undo is a non-dispatch transition.
- Missing: restart-based Doing/Undoing replay and real faulted-campaign runtime
  accounting; no global lock/ownership guarantee was found in this runner
  boundary, and none is assumed.
- Conclusion: implemented status-specific dispatch snapshots and explicitly
  runner-local single flight, without an exactly-once or lane-serialization claim.