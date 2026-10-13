# Recovery Cohort Completes

Canonical ID: `recovery-cohort-completes`. Priority P0; liveness with a terminal
safety oracle and a separate Sometimes progress witness.

## Evidence and Check Boundary

`overlord/state/taskrunner.go:192` resumes Doing/Undoing work; `:383` applies
scheduling gates, and `:314` handles cleanup. `overlord/overlord.go:605` implements
Settle, but its return alone is not evidence every change is ready or clean.
`overlord/state/taskrunner_test.go:752` tests shutdown-error replay behavior;
`:1049` and `:1225` cover cleanup behavior. `overlord/overlord_test.go:1094`
exercises settling. These tests support boundaries, not crash correctness proof.

Admit a finite set of ordinary-app operations into an independent ledger.
The admitted reversible cohort is install/refresh/enable/disable, with allowed
success or completed rollback predeclared for each scenario. Destructive terminal
removal errors are not rollback obligations in this cohort; their preservation
of unrelated survivors is checked under `removal-is-scoped`.

Stop new submissions, restore fixture store connectivity, allow scheduled retries,
and exclude manual/reboot waits and intentionally perpetual retry scenarios.
Before the calibrated terminal quiet-phase deadline, check every admitted ID
against expected success or rollback and its corresponding resource projection.
Reconcile results before pruning removes change history. Change Ready alone is
insufficient if undo, cleanup or fixture effects are still expected.

`Always(allLedgerObligationsResolved && expectedResourcesMatch)` is evaluated at
the terminal check: one unresolved operation is a violation of bounded progress
under these explicit recovery assumptions. `Sometimes(interruptedWorkRecovered
&& consistent)` is useful search guidance but cannot prove all IDs completed.
Keep these two messages distinct.

## Failure Scenario

One parallel task recovers while another is starved by blocked dependencies,
cleanup or replay. A broad Sometimes assertion sees the first completion and
passes; the finite-cohort oracle detects the unresolved second obligation.

## Instrumentation Status

Missing. `../existing-assertions.md` inventories only the existing Hold assertion.
Proposed SUT observations record attempts, runner direction, completion and
cleanup. Proposed workload ledger and barrier are not existing snapd APIs.

## Assumptions

Evaluation refinement: ledger admission intent before submitting requests and
reconcile lost responses against persistent change/resource observations. Do not
omit accepted-but-unacknowledged operations or silently permit any failure result.
Predeclare allowed success/rollback outcomes. Observe the terminal deadline from
outside SUT locks and the snapshot barrier; a stuck barrier cannot disable the
progress check. Protect expected fixture tokens from the SUT and verify that
synthetic stable-but-wrong projections fail the checker.

Use controlled synthetic fixtures and explicit expected rollback; arbitrary hooks,
application writes, reboot waits and unsupported disk failures are out of scope.
Termination availability, preserved storage and deadline calibration are
catalog-wide deployment prerequisites, not established code facts.

## Open Questions

None within this scoped campaign.