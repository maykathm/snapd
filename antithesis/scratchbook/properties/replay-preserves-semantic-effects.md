# replay-preserves-semantic-effects

Scope answer (verbatim): "just this directory"; external_references: [].
Focus: idempotency/lifecycle/integrity. Confidence: high in recovery contract;
crash campaign and independent projection checker are not implemented.

## Property

**P0 | Safety | AlwaysOrUnreachable**: whenever interrupted ordinary-app do or
undo work has recovered to an eligible stable outcome, its semantic effects
match the independent admission/fixture oracle; repeated attempts of the same
task/direction preserve the expected effects. A second clean restart is an
additional stability test, not evidence that a handler was executed again.
Message: `recovered app lifecycle replay preserves expected semantic effects`.
Recovery is optional, so AlwaysOrUnreachable checks every encountered outcome
without demanding a crash on every timeline. Distinct Reachable do-recovery and
undo-recovery anchors guide exploration. A Sometimes consistent-recovery witness
would not prove universal convergence or safety and is not the invariant.

## Verified Evidence

- [taskrunner.go](../../../overlord/state/taskrunner.go#L192): run dispatches
  DoingStatus to do and UndoingStatus to undo, supporting re-entry. The handler
  executes before the runner reacquires state and supplies terminal status at
  [taskrunner.go](../../../overlord/state/taskrunner.go#L281), leaving a
  completion window unless the handler commits its own status.
- [handlers.go](../../../overlord/snapstate/handlers.go#L2145): doLinkSnap
  commits candidate snapstate; its completion logic at
  [handlers.go](../../../overlord/snapstate/handlers.go#L2185) explicitly avoids
  replay of committed mutation. Undo combines restored state and UndoneStatus
  at [handlers.go](../../../overlord/snapstate/handlers.go#L2660).
- [taskrunner_test.go](../../../overlord/state/taskrunner_test.go#L110): sequence
  cases include initial `was-doing` re-entry, retry and handler-set-ready
  outcomes; TestSequenceTests starts at
  [taskrunner_test.go](../../../overlord/state/taskrunner_test.go#L150).
- [link_test.go](../../../overlord/snapstate/backend/link_test.go#L444) and
  [link_test.go](../../../overlord/snapstate/backend/link_test.go#L500): repeated
  backend link/unlink tests check wrappers and both current links.
- [copydata_test.go](../../../overlord/snapstate/backend/copydata_test.go#L467)
  and [copydata_test.go](../../../overlord/snapstate/backend/copydata_test.go#L503):
  repeated copy/undo tests check resulting data population/removal. These are
  narrow mocked-boundary tests, not permission to run arbitrary handlers twice
  or evidence that all partial crash windows recover correctly.
- [io.go](../../../osutil/io.go#L42): test binaries default to unsafe I/O;
  ordinary unit test success does not establish storage crash durability.

## Oracle, Faults And Boundary

Record operation cohort, full instance, pre-operation revision/config/data
tokens, intended target and independent fixture identities before admission.
Interrupt real runner work, preserve storage and allow ordinary runner recovery;
never manually call a handler twice or alter statuses to force replay. Exercise
Doing and Undoing separately around copy/link/delete external effects and the
checkpoint/terminal-status boundary. Record task direction/attempt/checkpoint
generation as proposed observational details, not new persistent mutations.

After recovery, independently classify each admitted operation's stable success
or completed rollback and check its ledger-defined result (old revision for
rollback, target for success), including unrelated-instance expectations. Do
not accept any terminal status as proof that effects are correct. Capture S1
only after this check; restart without new admissions, recover normally, capture
S2 at the same stable boundary and assert projection(S2) equals projection(S1)
and both match the ledger. A consistently wrong result must fail the ledger
check; equality alone is tautological reassurance.

Projection: instance presence, sequence revision membership/identity, Current,
Active, controlled config values, blob/mounted identities, link destinations,
fixture wrapper identities and revision/common-data sentinel bytes. Normalize
only semantically unordered sets; exclude logs, notices/timestamps, task runtime,
retry counts, transient downloads and cleanup artifacts. Do not compare to the
pre-crash partial snapshot. Stop applications/hooks capable of new writes before
the campaign comparison; background refresh/admissions and affecting cleanup
must be prevented/drained by a proposed barrier. A state lock, change readiness
or Settle nil is insufficient. Waiting forever never encounters this safety
assertion: deadline/progress is a separate catalog-wide liveness plan.

Crash/interleaving can duplicate effects, overwrite newer state, lose copied
data or resurrect deleted resources. Initially use controlled ordinary apps;
disabled remains inactive with absent active links unless admitted otherwise.
Exclude uncontrolled hook/application external side effects, try-mode, seeded
resources, components, snapd self-refresh, boot/reboot/remodel and destructive
removal rollback promises. Later extensions need explicit operation contracts,
not whole-state equality or arbitrary twice-handler invocation.

## Instrumentation And Questions

Evaluation refinement: prove repeated execution through task ID, direction,
attempt and persisted pre-status observations. Interrupt supported runner work
again while it is replayable to exercise multiple attempts. Do not manually
invoke handlers or corrupt statuses. Reconcile lost API responses with durable
change/resource observations and predeclare allowed outcomes. Keep the fixture
manifest and ledger protected from SUT writes; wrong stable synthetic projections
must fail the checker. A blocked barrier must not suppress an independent
recovery deadline. These are missing harness mechanisms, not present APIs.

**Missing**, per [existing-assertions.md](../existing-assertions.md): no replay
effect invariant or do/undo recovery anchors exist. Proposed placement combines
runner/handler observational outcome anchors with an independent stable checker;
the existing Hold assertion is not a replay oracle. Fixture choice, barrier,
preserved storage, fault availability and calibrated quiet budget remain the
catalog-wide plan in [assertion-placement.md](../assertion-placement.md) and
[deployment-topology.md](../deployment-topology.md), not existing APIs.

**Open Questions:** None within this initial scope.

### Investigation Log

#### Is replay exactly-once invocation, or equality with partial pre-crash state?

Examined runner dispatch/completion, link mutation/status commits and backend
repeat-operation tests above. Found do/undo re-entry is real while handler
terminal-status commits prevent unsafe committed mutation replay. Tests cover
particular effects, not arbitrary double invocation. Conclusion: check recovered
ledger effects first, then stable S1/S2 under no new writes; volatile state and
special lifecycle effects are excluded, with liveness budget a catalog-wide plan.