---
sut_path: /home/katie.may@canonical.com/source/snapd
commit: 5c611563419407fb3920cd0c992640fd56216d5e
updated: 2026-10-14
external_references: []
---

# Existing Antithesis Assertions

Scope answer (verbatim): "just this directory".

## Inventory

| File and line | Function | Type | Exact message |
| --- | --- | --- | --- |
| `overlord/state/state.go:308` | `State.Unlock` deferred postcondition | `Always` | `dirty unlock completes checkpoint before releasing state lock` |
| `overlord/state/task.go:273` | `Task.SetStatus` deferred postcondition | `AlwaysOrUnreachable` | `aborted task rejects competing done commit` |
| `overlord/state/task.go:306` | `Task.SetToWait` deferred postcondition | `AlwaysOrUnreachable` | `aborted task rejects competing wait commit` |
| `overlord/state/taskrunner.go:327` | `TaskRunner.run` locked finalization | `AlwaysOrUnreachable` | `aborted handler completion follows cancellation transition` |

The source-only follow-up removes the broad `change never enters hold status`
assertion. Explicit Hold and aborting pending work are supported outcomes, not
correctness failures. The replacements observe immediate cancellation
transitions under the existing state lock; none promises eventual rollback or
forbids a later legal Done status.

The setter checks retain Abort after a competing Done or Wait request; Wait also
preserves its previous waited-status. Runner finalization checks the normalized
tomb result: nil requires Undo, Retry/Wait requires Undo or no-undo Hold, and
other errors require Error. Shutdown error normalization precedes the check.

The dirty-Unlock check runs before mutex release, only for dirty state with a
backend and a normal return. It records checkpoint success, cleared dirty state
and attempt count. It does not independently validate stored bytes or durability.

Validation: the full state package passed with `-mod=readonly -race -count=1`.
Cancellation validation reported successful local SDK encounters of all three
optional assertions. Six isolated checkpoint scenarios additionally verified
successful events for checkpoint success, retry-success and recovery after a
backend panic, with no events for clean state, nil backend or retry exhaustion.
This does not verify catalogs or reporting from the actual harness binary, or
demonstrate campaign coverage.

`go.mod:41` already requires `github.com/antithesishq/antithesis-sdk-go v0.8.0`.
`build-aux/snap/snapcraft.yaml` contains Antithesis Go tool-exec build support.

Scan: repository Go, C, headers, Python, shell, YAML, module and checksum files
for SDK imports and assertion spellings. Vendor contains no matching SDK calls.
Generated artifacts and external binaries are not treated as SUT source.

## Assumptions

The catalog describes proposed assertions unless explicitly marked existing.
SDK package presence does not imply every build produces an assertion catalog.

## Open Questions

Confirm assertion catalog generation for the actual harness binary before a run.
The existing Incus/Spread harness is unchanged; no runnable Compose configuration
or dedicated cancellation test template was added in this source-only pass.