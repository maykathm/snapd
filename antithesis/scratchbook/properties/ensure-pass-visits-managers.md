# ensure-pass-visits-managers

## Scope and Property

Scope answer (verbatim): "just this directory". External references: `[]`.
Evidence revision: `114df3f4470d29b961205b33b56574dcb468514b` (2026-10-15).
Focus: concurrency and lifecycle; source assertion now implemented.

Priority: **P1 (high)**. Type: **Safety**. Confidence: **high** for the
dispatch contract, not proof of useful work inside each manager.

Every admitted, normally returning StateEngine Ensure pass invokes and receives
a return from every registered top-level manager slot exactly once, including
passes returning aggregated manager errors.

## Code and Test Evidence

- [overlord/stateengine.go](../../../overlord/stateengine.go#L167), `StateEngine.Ensure`:
  `mgrLock` protects the manager list throughout dispatch. The pre-start return
  and stopped return reject the pass. The loop continues after manager errors;
  both the aggregated-error return and nil return follow the complete loop.
- [overlord/stateengine.go](../../../overlord/stateengine.go#L191), `AddManager`:
  registration uses the same mutex. Capture the expected slots under that lock;
  count slots, not distinct object pointers, since registration can repeat an
  object. No process-global manager set is implied.
- [overlord/stateengine_test.go](../../../overlord/stateengine_test.go#L119),
  `TestEnsure`: pre-start rejection and two ordered, complete passes.
- [overlord/stateengine_test.go](../../../overlord/stateengine_test.go#L145),
  `TestEnsureError`: both failing managers are visited and both errors reported.
- [overlord/stateengine_test.go](../../../overlord/stateengine_test.go#L189), `TestStop`:
  Ensure after Stop reports `state engine already stopped`.
- [overlord/snapstate/snapmgr.go](../../../overlord/snapstate/snapmgr.go#L1637),
  `SnapManager.Ensure`: preseed, seeded and device-context guards intentionally
  omit work. Top-level visitation is not unconditional visitation of every
  internal ensure helper, nor successful task completion.

## SDK Check and Safe Condition

`Always(allSlotsEnteredAndReturnedExactlyOnce, "completed ensure pass visits
every registered manager", details)` checks a safety condition on every admitted
normal completion. The implementation computes this predicate in a defer; no
separate helper is introduced. Details carry process-local engine pointer
identity, admitted pass number, expected slot count and per-slot entry/return
counts. The pointer is not a durable cross-process incarnation ID. Manager
error count is included; errors retain their existing logging and aggregation
behavior.

Freeze the expected list after the lifecycle rejection guards, under `mgrLock`.
Increment entry immediately before each call and return immediately after it.
Evaluate before **both** the aggregated-error return and nil return. Ordinary
manager errors are not exclusions or assertion failures by themselves. The
pre-start and stopped returns have no admitted pass and must not evaluate this
predicate; inspect every return path when implementing the instrumentation.
StartUp sets `startedUp` even when it returns initialization errors, so admission
means the engine guards passed, not that initialization was error-free.

Crashes, panics, process termination and a manager that never returns cannot
reach the completion assertion. Do not infer liveness from its absence. The
request-progress property supplies a separate finite-cohort progress oracle.
An empty expected list is a vacuous safety result; the campaign needs real
registered managers to produce meaningful coverage.

## Scenario, Fault Angle and Impact

Pause a manager while a concurrent registration or stop waits on `mgrLock`;
release it with an error and verify later managers still return in the same
pass. Interrupt and restart separately, using a new engine incarnation rather
than demanding the interrupted pass complete. Scheduling pauses and error
returns explore skipped-tail and duplicate-dispatch risks. A violated property
can starve an entire manager and its tasks despite apparent loop activity.

Cheap discriminating check: compare `TestEnsureError`'s complete call list with
both return sites. An early error return would falsify the proposed guarantee.
Those paths are covered by the existing engine tests and the SDK-local matrix.

## Instrumentation Status

**Source implemented:** per-pass slot entry/return accounting and the fixed
`Always` assertion now live in `StateEngine.Ensure`. Expected slots are captured
after lifecycle rejection under `mgrLock`; a normal-completion-gated defer runs
before its unlock on both success and aggregated-error returns. Panic unwinding
does not emit the assertion. Counts and pass number are observational, with no
extra manager calls or persistent state mutations.

`stateengine_assertions_test.go` uses fresh subprocesses and actual SDK-local
output to verify success, aggregated errors, duplicate slots, empty passes,
pre-start/stopped rejection, panic exclusion, recovery after a panic and
admission after startup errors. Children independently verify the exact manager
call list, error behavior and mutex release. The panic-recovery case verifies
the next admitted pass number and counts.

Validation: the complete state-engine suite and nine-case SDK-local matrix
passed with the race detector; the engine suite also passed with the SDK
disabled. The current toolchain required `GODEBUG=rsa1024min=0` for existing
small-RSA test fixtures. Documentation lint and whitespace checks passed.

See [existing-assertions.md](../existing-assertions.md) for the updated inventory.
Actual harness catalog/report verification, fault campaigns and the separate
ensure-request progress oracle remain unimplemented. This check observes dispatch
control flow; it cannot establish useful manager work or detect a stalled pass.

## Open Questions

None within this property's dispatch scope. Quiet-deadline calibration and
campaign fault availability are catalog-wide, not visitation assumptions.

### Investigation Log

#### Does an error or lifecycle guard change the expected visitation set?

- Examined: engine Ensure, StartUp, AddManager and Stop; TestEnsure,
  TestEnsureError and TestStop; SnapManager.Ensure guards.
- Found: stable registered slots under `mgrLock`, error aggregation after all
  calls, explicit pre-start/stopped rejection and intentional helper guards.
- Missing: no local semantic ambiguity remains; campaign validation is absent.
- Conclusion: resolved by limiting the invariant to admitted normal returns,
  not all function invocations or all internal helpers.