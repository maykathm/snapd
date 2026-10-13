# checkpoint-readback-matches

## Property

**Priority:** P0. **Type:** Safety / `Always`. **Confidence:** high.
After the real checkpoint backend reports a successful write, an independent
read of its target must succeed and equal the exact byte payload passed to that
write, before another writer can intervene. Wrong-but-valid JSON can lose task
or snap state just as surely as a torn file.

Scope answer (verbatim): "just this directory"; `external_references: []`.
Discovery lenses: targeted data integrity and failure recovery.

## Verified Evidence

- [overlordStateBackend.Checkpoint](../../../overlord/backend.go#L33) passes
  `data` to `osutil.AtomicWriteFile` with mode 0600.
- [State.Unlock](../../../overlord/state/state.go#L294) holds the mutex across
  serialization and backend calls; it retries the same bytes, not a freshly
  serialized state for each attempt.
- [AtomicWriteFile](../../../osutil/io.go#L242) wraps the bytes in a reader;
  [AtomicWriteChown](../../../osutil/io.go#L250) copies into a temporary file
  and commits it. [AtomicFile.commit](../../../osutil/io.go#L157) orders file
  sync, close, rename, then directory sync when unsafe test IO is disabled.
- [State.MarshalJSON](../../../overlord/state/state.go#L210) includes the last
  notice timestamp. [State.UnmarshalJSON](../../../overlord/state/state.go#L229)
  explains that other notice backends update timestamps without the state lock.
  Fresh serialization is therefore not a valid equality oracle.
- [TestImplicitCheckpointAndRead](../../../overlord/state/state_test.go#L248)
  restores manager values from the fake backend's captured payload; it does
  not independently read the real checkpoint file.

## Assertion and Placement

Proposed message: `successful checkpoint readback equals supplied payload`.
In a test-only wrapper around the real backend, retain the exact `data`, call
the real atomic writer, and on nil error read its actual configured target.
Assert read success AND byte equality using
`assert.Always(condition, message, details)`; SDK v0.8.0 arguments are
`bool, string, map[string]any`. Every successful checkpoint in this campaign
requires equality, so `Always` rather than `Sometimes` is appropriate.

The readback runs before returning to `Unlock`, while the single state writer
is still excluded. Compare exact bytes, not merely successful JSON decoding,
nor a fresh `MarshalJSON`, nor an unlocked later read. Include payload length
and test-only generation/hash in details. The wrapper and generation ledger
are proposed instrumentation, not existing APIs or persisted snapd fields.

**Instrumentation status: missing**, per
[existing-assertions](../existing-assertions.md#L11); the inventory has only
the change-Hold assertion. Gate the expensive readback to the research build:
SDK no-op mode does not prevent filesystem argument evaluation.

## Workload, Fault Timing, and Boundaries

The workload creates distinct payloads through real operations and retains
expected operation identities independently. SUT-side readback isolates the
write boundary and gives immediate search feedback; workload recovery checks
catch semantic loss and cannot alone attribute it to this exact checkpoint.

Exercise interruptions during write/rename/sync and concurrent admissions
waiting on the mutex. Only successful backend returns are eligible. A failed
directory sync after rename may already have published the new bytes; do not
require failed writes to preserve the old file. A crash before readback belongs
to [checkpoint-crash-generations](checkpoint-crash-generations.md).

## Assumptions and Exclusions

Use the real configured path, one authoritative writer, preserved local storage,
and a healthy-storage campaign with no external edits between write and read.
This tests present readability and equality, not power-loss durability or graph
semantics. Injected read errors require a separately specified campaign rather
than silently treating a failed read as equal. Harness-wide prerequisites stay
in [deployment-topology](../deployment-topology.md#L55).

## Open Questions

None.

### Investigation Log

#### Is fresh state serialization a safe comparison payload?

- Examined: `Unlock`, `MarshalJSON`, and notice timestamp restoration above.
- Found: the exact checkpoint argument is stable across retries; notice
  timestamps can change independently of the state mutex.
- Not found: a guarantee of fresh serialization equality after a write.
- Conclusion: resolved; compare the captured argument under writer exclusion.