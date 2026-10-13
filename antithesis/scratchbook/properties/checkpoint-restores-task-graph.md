# checkpoint-restores-task-graph

## Property

**Priority:** P0. **Type:** Safety / `Always`. **Confidence:** high.
Restoring a captured, same-version checkpoint must preserve its task/change
identities, ownership, dependency edges, lanes, persisted statuses and scheduling,
and ID allocation counters, with usable backlinks and ready-channel semantics.
Lost edges can reorder installation or undo; lost ownership/lanes can broaden
rollback; reused IDs can confuse persistent operations.

Scope answer (verbatim): "just this directory"; `external_references: []`.
Discovery lenses: targeted data integrity and failure recovery.

## Verified Evidence

- [State.MarshalJSON](../../../overlord/state/state.go#L210) persists changes,
  tasks, and last-ID counters; [State.UnmarshalJSON](../../../overlord/state/state.go#L229)
  restores counters and backlinks, then calls `finishUnmarshal` for changes.
- [Task.UnmarshalJSON](../../../overlord/state/task.go#L143) restores ownership,
  wait/halt IDs, lanes, clean flag, statuses, progress, data and schedule. It
  normalizes absent/default waited status to Done for backward compatibility.
- [Change.UnmarshalJSON](../../../overlord/state/change.go#L219) restores task
  IDs; [Change.finishUnmarshal](../../../overlord/state/change.go#L249) closes
  the ready channel when the reconstructed status is ready.
- [ReadState](../../../overlord/state/state.go#L664) decodes and rebuilds
  transient maps, returning clean state. [Startup loading](../../../overlord/overlord.go#L353)
  subsequently saves timings and applies migrations: compare before those.
- [TestNewTaskAndCheckpoint](../../../overlord/state/state_test.go#L471)
  checks task IDs/kinds/data/status, change backlink, lanes, wait/halt edges,
  progress and AtTime. [TestNewChangeAndCheckpoint](../../../overlord/state/state_test.go#L378)
  checks ready closure; [TestNewChangeAndCheckpointTaskDerivedStatus](../../../overlord/state/state_test.go#L431)
  checks derived Done status and ready closure.
- [TestCheckpointPreserveLastIds](../../../overlord/state/state_test.go#L647)
  checks subsequent task/change/lane allocation;
  [TestCheckpointPreserveCleanStatus](../../../overlord/state/state_test.go#L678)
  checks clean flags. These are fake-backend round trips, not interrupted
  real-daemon recovery proofs.

## Assertion and Placement

Proposed message: `checkpoint restoration preserves persisted task graph`.
Use `assert.Always(condition, message, details)` with SDK v0.8.0's
`bool, string, map[string]any` arguments. Every eligible restoration must
preserve this projection; a single successful `Sometimes` cannot prove it.

Capture the exact checkpoint projection independently. After `ReadState`, before
managers, migrations, timing saves or replay run, compare task/change map keys
and IDs, kinds, persisted statuses with waited-status normalization, clean flags, task-owned
data, task/change membership, wait/halt edges, lanes, schedules and counters.
Compare collections according to their defined semantics, not Go map order.
Normalize an absent/default waited status to Done in the independent expected
projection before comparison, even for newly created same-version tasks.
`Task.UnmarshalJSON` applies this normalization unconditionally; it is not only
a legacy-migration exception. Other persisted statuses remain exact comparisons.
Check restored tasks point at the restored state/change and that ready channels
agree with computed ready status; do not compare pointer identity to the old
process. For valid input graphs, also verify all serialized references resolve
and wait/halt pairs remain reciprocal. Do not require every task to have a
change: [State.Tasks](../../../overlord/state/state.go#L436) intentionally skips
unlinked tasks; compare the complete serialized task map instead.

Counter preservation can be checked without allocating tasks solely for an
assertion; ordinary subsequent admissions independently check non-reuse.
The snapshot/comparison mechanism is proposed, not an existing helper API.

**Instrumentation status: missing**, per
[existing-assertions](../existing-assertions.md#L11). Serialization tests and
the unrelated existing Hold assertion do not implement this SDK property.

## Workload, Fault Timing, and Boundaries

Create real multi-task changes with dependencies and independent lanes; capture
Doing/Undoing, Wait and terminal checkpoints where naturally reachable. Restart
around checkpoint publication and restoration. SUT instrumentation catches
invisible ownership/edge loss before replay can obscure it; the workload checks
expected operation outcomes and isolation after recovery. Compare to the
generation actually loaded, not a later pre-crash in-memory graph.

This is restoration safety, not a demand for exactly-once handlers, acyclicity
validation of arbitrary malicious JSON, or eventual completion. Do not manually
re-run handlers or mutate graph/status just to exercise an assertion.

## Assumptions and Exclusions

Start with valid graphs generated by this SUT version; exclude schema migration
and apply the documented waited-status normalization. Runtime caches, mutexes,
handler registrations and pointer addresses are not persisted. Replay may
legitimately change statuses after the comparison. Independent ledger and
storage prerequisites are catalog-wide; see
[deployment-topology](../deployment-topology.md#L40).

## Open Questions

None.

### Investigation Log

#### Which graph fields and runtime relationships survive restoration?

- Examined: state/task/change deserialization and the round-trip tests above.
- Found: persisted fields, counter preservation, rebuilt state backlinks and
  computed ready closure; default waited-status normalization is explicit.
- Not found: a requirement that unlinked tasks appear in `State.Tasks`, or that
  pointer identity/runtime caches survive.
- Conclusion: resolved; compare the complete serialized graph before replay,
  with semantic ready/backlink checks and same-version input.