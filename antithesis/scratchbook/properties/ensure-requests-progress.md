# ensure-requests-progress

## Scope and Property

Scope answer (verbatim): "just this directory". External references: `[]`.
Evidence revision: `e88ec08852fbc8af019dc39e22097e5720aa6dfd` (2026-10-13).
Focus: concurrency, liveness and lifecycle; evidence only.

Priority: **P1 (high)**. Type: **Liveness**, with a bounded quiet-phase safety
oracle. Confidence: **high** for scheduling semantics; deadline is uncalibrated.

Every eligible EnsureBefore request in a finite admission cohort is covered by
a later admitted, completed ensure pass while its engine incarnation remains
running. Requests may coalesce; one completed pass can cover many requests.

## Code and Test Evidence

- [overlord/state/state.go](../../../overlord/state/state.go#L314), `State.EnsureBefore`:
  forwards only with a non-nil backend; nil-backend state is not a loop request.
- [overlord/backend.go](../../../overlord/backend.go#L37): backend forwards to Overlord.
- [overlord/overlord.go](../../../overlord/overlord.go#L451), `ensureTimerSetup`, and
  [overlord/overlord.go](../../../overlord/overlord.go#L468), `ensureBefore`: `ensureLock`
  protects timer updates. No timer panics; an earlier deadline resets the timer,
  a later request does not postpone an earlier deadline, and the expired-timer
  branch preserves a pending wakeup or resets immediately after a successful
  Stop. A call returning does not itself establish a completed pass.
- [overlord/overlord.go](../../../overlord/overlord.go#L500), `Loop`, and
  [overlord/overlord.go](../../../overlord/overlord.go#L510), `loop`: reset precedes Ensure;
  normal-mode errors do not stop looping. Preseed errors may exit the process.
  `ensureDidRun` is a one-bit history marker, not per-request coverage.
- [overlord/overlord.go](../../../overlord/overlord.go#L569), `Stop`, and
  [overlord/overlord.go](../../../overlord/overlord.go#L581), `settle`: shutdown ends the
  loop; Settle is a distinct, nonconcurrent timer mode and collects errors.
  Its timeout check cannot interrupt a manager blocked inside Ensure or Wait.
- [overlord/overlord_test.go](../../../overlord/overlord_test.go#L470),
  `TestEnsureLoopMediatedEnsureBeforeImmediate`, and
  [overlord/overlord_test.go](../../../overlord/overlord_test.go#L500), its delayed variant:
  a second pass is witnessed despite the ten-minute normal interval.
- [overlord/overlord_test.go](../../../overlord/overlord_test.go#L530),
  `TestEnsureBeforeSleepy`, and
  [overlord/overlord_test.go](../../../overlord/overlord_test.go#L561), `TestEnsureBeforeLater`:
  expired timer cases. The outside-Ensure request case is
  [overlord/overlord_test.go](../../../overlord/overlord_test.go#L592).
- [overlord/overlord_test.go](../../../overlord/overlord_test.go#L1131),
  `TestSettleExplicitEnsureBefore`: the task-triggered request leads to two passes.

## Proposed SDK Checks and Safe Condition

Primary universal check: at a qualified quiet-phase deadline, use
`Always(allEligibleRequestsCovered, "quiet eligible ensure requests are covered
by completed passes", details)`. The predicate is proposed. An independent
checker must evaluate it even if the SUT loop is wedged. Check every request,
not just the newest one or a total count. This tests bounded progress under
explicit campaign conditions, not unconditional wall-clock liveness.

Assign request sequence numbers at timer acceptance under `ensureLock`. At each
admitted pass start, snapshot the latest accepted sequence; on normal completion,
advance the completed coverage watermark to that snapshot. A request arriving
during a pass needs a subsequent pass, not credit from that in-flight pass.
Aggregated manager errors count as completed visitation, not successful repair.
Use engine incarnation plus generation to avoid credit across restarts. Export
observations without acquiring `mgrLock` from the request callback: managers can
issue requests while dispatch already holds that lock.

Secondary semantic witness:
`Sometimes(cohortNonempty && allEligibleRequestsCovered, "ensure request cohort
reaches completed pass coverage", details)`. It guides exploration and replay;
one true encounter is **not** proof of universal per-request liveness. Do not
replace the primary cohort check with `Sometimes(true)` or `ensureRun != 0`.

Admission requires a real backend, initialized loop timer, started engine and
a running incarnation. Exclude pre-loop panic, rejected startup/stopped calls,
nil-backend calls, intentional shutdown and preseed exit from this running-loop
contract. Do not silently drop unexplained outstanding requests: record cohort
cancellation or an interrupted incarnation explicitly. Restart recovery is a
new cohort; requests themselves are not claimed durable across process death.

Quiet qualification stops new workload admissions, restores required dependency
availability, permits scheduled requests/retries to become eligible and verifies
the chosen fault-free execution conditions. The finite quiet deadline must be
calibrated catalog-wide against fixtures, timer/retry schedules and available
faults. A supplied delay is a scheduling target, not a hard real-time completion
bound during starvation, clock disturbance or a blocked manager. Do not require
full quiescence as a prerequisite to checking progress: that would hide stalls.

## Scenario, Fault Angle and Impact

Issue immediate and delayed requests both inside a manager and between passes;
pause near timer expiry/reset and request acceptance. Check coalescing and the
expired timer branch, then restore execution for the qualified quiet cohort.
A lost wakeup or blocked pass leaves requests uncovered even if earlier passes
succeeded. Impact: install, undo and retry work can remain indefinitely pending.

Cheap discriminating check: the mediated and outside-Ensure tests require a
second pass. Their code was inspected, not executed; their two-second waits
are unit-test guards, not proposed production or Antithesis deadlines.

## Instrumentation Status

**Missing**: request/pass sequence ledger, independent quiet-cohort oracle and
both proposed SDK checks. Existing timer fields and `ensureRun` are scheduling
state, not assertions or adequate coverage accounting.
[antithesis/scratchbook/existing-assertions.md](../existing-assertions.md)
contains no request-progress instrumentation. SUT observations are required for
causality; workload-only task completion cannot cover all EnsureBefore calls.

## Open Questions

None for request acceptance/coalescing semantics. Catalog-wide quiet-deadline,
fault configuration and oracle/barrier calibration remain implementation gates,
as recorded in the supplied topology; they are not per-property guarantees.

### Investigation Log

#### Can one pass witness establish every request progressed?

- Examined: backend forwarding, timer branches, loop, Stop and Settle; mediated,
  expired-timer, outside-Ensure and explicit-Settle request tests.
- Found: requests coalesce, requests during Ensure can schedule another pass,
  ordinary manager errors continue the loop, and Settle's timeout is cooperative.
- Missing: runtime per-request coverage and a calibrated catalog-wide deadline.
- Conclusion: semantic question resolved with incarnation-scoped watermarks and
  a universal finite-cohort oracle; Sometimes remains only a coverage witness.