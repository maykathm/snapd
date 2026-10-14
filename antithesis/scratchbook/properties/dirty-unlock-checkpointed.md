# dirty-unlock-checkpointed

## Property

**Priority:** P0. **Type:** Safety / `Always`. **Confidence:** high in the
boundary and testability, not a claim of proven fault correctness.
Every normally returning `State.Unlock` entered with dirty state and a non-nil
backend must have observed a successful checkpoint and cleared `modified`
before releasing the state mutex. Losing this boundary can lose persistent
operations while later handlers proceed as though their state were saved.

Scope answer (verbatim): "just this directory"; `external_references: []`.
Discovery lenses: data integrity and failure recovery, targeted to persistence.

## Verified Evidence

- [State.Unlock](../../../overlord/state/state.go#L294) defers mutex release,
  skips clean/nil-backend state, serializes once, retries the same payload,
  and clears `modified` only on checkpoint success at
  [the successful branch](../../../overlord/state/state.go#L307).
- [Retry parameters](../../../overlord/state/state.go#L278) default to five
  minutes with three-second intervals. Exhaustion panics, not normal success.
- [TestImplicitCheckpointAndRead](../../../overlord/state/state_test.go#L248)
  checks one implicit checkpoint and recovered manager data.
- [TestImplicitCheckpointRetry](../../../overlord/state/state_test.go#L289)
  expects success on the second attempt;
  [TestImplicitCheckpointPanicsAfterFailedRetries](../../../overlord/state/state_test.go#L312)
  expects a panic;
  [TestImplicitCheckpointModifiedOnly](../../../overlord/state/state_test.go#L334)
  checks that clean unlocks do not write again.

## Assertion and Placement

Implemented message: `dirty unlock completes checkpoint before releasing state lock`.
Uses `assert.Always(condition, message, details)` with SDK v0.8.0's
`bool, string, map[string]any` signature. The condition is successful-checkpoint
observed AND dirty flag cleared, gated by the entry dirty/backend conditions and
normal return. `Always` is universal over these required encounters; neither an
existential `Sometimes` nor an unconditional no-panic property matches it.

Observational locals distinguish normal return from panic unwinding. The
observer defer is registered after the existing unlock defer, past the
clean/nil-backend gate, so the assertion runs before mutex release. Expected
checkpoint errors remain retry outcomes, not assertion failures. Details record
attempt count; no payload serialization, digest, readback, new persistent state
or helper API is added for instrumentation.

**Instrumentation status: source implemented**, on HEAD
`5c611563419407fb3920cd0c992640fd56216d5e` plus working-tree changes (2026-10-14).
The [assertion inventory](../existing-assertions.md) records the callsite.
Actual instrumented harness cataloging/reporting and campaign coverage remain
unverified; the existing Incus/Spread harness is unchanged.

## Local Validation

The full state suite passed with
`LANG=C.UTF-8 go test -mod=readonly -race -count=1 ./overlord/state`.
Focused tests cover successful checkpoint/read, retry-success, clean restored
state, nil backend, retry exhaustion and backend panic followed by recovery.
The retry test additionally verifies identical payload bytes across attempts,
cleared dirty state and no extra checkpoint on a following clean Unlock.
The backend-panic test checks retained dirty data and successful relocking and
checkpointing after the panic.

Six isolated `ANTITHESIS_SDK_LOCAL_OUTPUT` checks verified one passing mandatory
event for initial success (one attempt), retry-success (two attempts), and the
successful checkpoint after backend panic (one attempt). Clean state, nil backend
and retry exhaustion emitted no checkpoint assertion encounters. No scenario
emitted a failed checkpoint assertion. These checks do not validate production
file contents or process-crash recovery.

## Workload, Fault Timing, and Boundaries

Submit real operations that mutate state; SUT instrumentation sees the dirty
entry and successful retry boundary that an API client cannot observe. The
workload independently checks persisted outcomes after restart, complementing
but not replacing the local control-flow check. A backend that returns nil
without correct bytes can satisfy this property and fail
[checkpoint-readback-matches](checkpoint-readback-matches.md).

Pause or interrupt before checkpoint, during retries, or between successful
checkpoint and mutex release. Crash/panic exits cannot reach the normal-return
assertion and are excluded, as are nil-backend in-memory states and clean unlocks.
This is not a bounded-liveness guarantee and does not require each failed
checkpoint attempt to leave the old file unchanged.

## Assumptions

The campaign exercises dirty state with the real backend. Assertions observe
without altering retry, panic, or lock behavior. Harness-wide fault availability
and storage prerequisites remain in
[deployment-topology](../deployment-topology.md#L55), not per-property questions.

## Open Questions

None.

### Investigation Log

#### Does retry exhaustion permit a normal unlock without persistence?

- Examined: `State.Unlock` and the three retry/modified-only tests above.
- Found: only the success branch clears dirty state; exhaustion panics, while
  the deferred mutex release also runs on panic.
- Not found: a normal-return path after failed retries.
- Conclusion: resolved; gate on normal return, not simply on mutex release.