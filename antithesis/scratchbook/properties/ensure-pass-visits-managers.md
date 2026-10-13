# ensure-pass-visits-managers

## Scope and Property

Scope answer (verbatim): "just this directory". External references: `[]`.
Evidence revision: `e88ec08852fbc8af019dc39e22097e5720aa6dfd` (2026-10-13).
Focus: concurrency and lifecycle; evidence only, no production edits.

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

## Proposed SDK Check and Safe Condition

`Always(allSlotsEnteredAndReturnedExactlyOnce, "completed ensure pass visits
every registered manager", details)` checks a safety condition on every admitted
normal completion. This is a proposed predicate, not an existing helper. Keep
the message fixed; details carry engine incarnation, pass generation, slot index,
entry/return counts and manager errors.

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
Those paths were inspected; tests were not executed in this evidence-only pass.

## Instrumentation Status

**Missing**: per-pass slot entry/return accounting and this SDK assertion.
[antithesis/scratchbook/existing-assertions.md](../existing-assertions.md)
inventories only the Hold assertion in Change notifications; it does not cover
manager visitation. Suggested accounting is observational and must not call
managers again or alter their guarded behavior. SUT-side placement is needed:
API change outcomes cannot identify a skipped manager or a useful replay anchor.

## Open Questions

None within this property's dispatch scope. Quiet-deadline calibration and
campaign fault availability are catalog-wide, not visitation assumptions.

### Investigation Log

#### Does an error or lifecycle guard change the expected visitation set?

- Examined: engine Ensure, StartUp, AddManager and Stop; TestEnsure,
  TestEnsureError and TestStop; SnapManager.Ensure guards.
- Found: stable registered slots under `mgrLock`, error aggregation after all
  calls, explicit pre-start/stopped rejection and intentional helper guards.
- Missing: no local semantic ambiguity remains; runtime accounting is absent.
- Conclusion: resolved by limiting the invariant to admitted normal returns,
  not all function invocations or all internal helpers.