# checkpoint-crash-generations

## Property

**Priority:** P0. **Type:** Safety / `AlwaysOrUnreachable`. **Confidence:** high
in the process-crash oracle; storage-wide durability is an explicit exclusion.
Before restarted snapd changes the file, the authoritative checkpoint must be
readable and exactly one permitted complete generation: the established baseline
or a subsequently attempted payload interrupted before a confirmed completion.
With a confirmed completed checkpoint and no later attempt, only that completed
generation is permitted. Torn, mixed, missing, or older-than-baseline state fails.
Violation can prevent startup or silently lose/recombine operation state.

Scope answer (verbatim): "just this directory"; `external_references: []`.
Discovery lenses: targeted data integrity and failure recovery.

## Verified Evidence

- [State.Unlock](../../../overlord/state/state.go#L294) submits one serialized
  payload repeatedly until success; [real Checkpoint](../../../overlord/backend.go#L33)
  uses `AtomicWriteFile`.
- [NewAtomicFile](../../../osutil/io.go#L77) creates the temporary file in the
  target directory. [AtomicWriteChown](../../../osutil/io.go#L250) copies its
  input before commit.
- [AtomicFile.commit](../../../osutil/io.go#L157) syncs the file at
  [line 174](../../../osutil/io.go#L174), closes it, renames at
  [line 189](../../../osutil/io.go#L189), then syncs the directory at
  [line 195](../../../osutil/io.go#L195). Failure after rename cannot roll back
  publication: [Cancel](../../../osutil/io.go#L130) checks `renamed`.
- [Unsafe IO default](../../../osutil/io.go#L42) skips sync in test binaries
  by default. [SafeIoAtomicTestSuite](../../../osutil/io_test.go#L541) explicitly
  disables that shortcut. [TestAtomicWriteFile](../../../osutil/io_test.go#L41)
  checks bytes and temporary cleanup;
  [TestAtomicWriteFileOverwrite](../../../osutil/io_test.go#L68) checks replacement.
  Neither is a process-crash generation test.
- [Startup](../../../overlord/overlord.go#L329) constructs new state when the
  checkpoint is absent; [existing-file loading](../../../overlord/overlord.go#L353)
  calls `ReadState`, then saves timings and applies patches. A missing file is
  therefore a failure after baseline creation, not successful fresh recovery.
- [ReadState](../../../overlord/state/state.go#L664) decodes JSON and reports
  errors. Decoding alone does not prove complete-generation equality.

## Assertion and Observation Protocol

Proposed message: `interrupted checkpoint recovers a permitted complete generation`.
At the isolated restart oracle, use
`assert.AlwaysOrUnreachable(condition, message, details)` with SDK v0.8.0's
`bool, string, map[string]any` signature. Crashes are optional encounters;
every encountered eligible recovery must satisfy safety. Do not use `Sometimes`
to excuse even one corrupted recovery. A separate reachability witness can guide
crash-window exploration but is not the correctness assertion.

Establish a successfully completed baseline before faulting. A proposed
independent ledger retains exact payload bytes/hash, attempt order and confirmed
successful-return observations. Record an attempt before invoking the writer;
record completion only after success. Retries of identical bytes are one content
generation. No production generation counter or existing ledger API is claimed.

On termination, stop admissions and keep the daemon stopped while the oracle
opens the authoritative path once, reads it fully, and compares exact bytes to
the permitted set. Restrict candidates to the last confirmed complete generation
plus attempts since it; if a failure published bytes after rename without a
confirmed success, those attempted bytes remain candidates. Decode the matching
payload as an additional usability check. Observe before restart timing writes,
migrations, pruning or task replay. The expected graph is that loaded generation,
not the latest volatile state before termination.

**Instrumentation status: missing**, per
[existing-assertions](../existing-assertions.md#L11). Proposed SUT attempt/success
observations identify the narrow window; the independent workload-side file
oracle prevents self-validation by the writer and verifies restart input.

## Fault Timing and Check Boundaries

Interrupt temporary-file creation/copy, file sync, close, rename, or directory
sync; distinguish pre-publication from published-but-not-confirmed outcomes.
Vary real state mutations so stale and mixed generations cannot masquerade as
identical bytes. Preserve the ledger outside the terminated daemon.

Exclude first boot without a baseline, other writers, explicit deletion,
filesystem/media corruption, whole-machine power loss and cross-version
migration. Temporary `*~` files are not authoritative and their retention after
a crash is not a violation. This property is stronger than JSON decodability
but does not establish operation convergence or exactly-once side effects.

## Assumptions

Evaluation refinement: attempt/completion observations must survive the killed
process and be reconciled for lost observations. An unobserved success is
ambiguous, not a confirmed completion. Treat its attempted payload as a possible
generation. A durable external completion marker after backend success supplies
the stronger acknowledged-generation obligation. Correlate only independent
payload/operation records; never let the recovered file define its own expected
generation. A fake stale-but-valid JSON payload must fail the oracle.

Use process termination with the same preserved filesystem and safe sync behavior.
No checker/restart writes may precede the observation. Tenant crash support and
storage behavior are catalog-wide deployment questions recorded in
[deployment-topology](../deployment-topology.md#L55); they are not duplicated
as unresolved per-property claims.

## Open Questions

None.

### Investigation Log

#### Must an unsuccessful checkpoint leave only the baseline generation?

- Examined: atomic commit ordering, cancellation and startup loading above.
- Found: rename precedes directory sync; sync failure can occur after the new
  target is visible, and cancellation cannot undo that rename.
- Not found: rollback of a published target on a later error.
- Conclusion: resolved; permit the attempted complete payload even without
  a success marker, but never arbitrary valid JSON or pre-baseline state.