---
sut_path: /home/katie.may@canonical.com/source/snapd
commit: 7f3fc9ae5896ba6fda2b3b29638b4a07ea298d2d
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

## Current Coverage Assessment

The 2026-10-14 source rescan still finds exactly four SDK assertion callsites,
all in `overlord/state`: one dirty-checkpoint control-flow assertion and three
optional cancellation-transition assertions. No SUT `Sometimes`, `Reachable`
or `Unreachable` callsites were found. This is narrow internal instrumentation,
not implementation of the nineteen-property portfolio in `property-catalog.md`.

The eleven selected Spread tests exercise local install, refresh, revert,
interface and service rollback, parallel instances and removal. State-changing
operations should encounter the dirty-Unlock guard. Failed multi-service and
refresh operations can exercise task cancellation, but the selected scenarios
do not guarantee competing Done/Wait setters or aborted-handler finalization.
Actual encounter counts require observing a run; no campaign coverage is claimed.
Their shell checks are scenario checks, not additional SDK assertion callsites.

The current selection is defined by symlinks in `antithesis/tests/main/`, not
the older first-series/future-campaign recommendations in the topology notes:
`revert-sideload`, `install-refresh-remove-hooks`, `refresh-undo`,
`op-install-failed-undone`, `services-disabled-kept-unhappy`,
`parallel-install-basic`, `parallel-install-common-dirs-undo`,
`connections-after-failed-refresh`, `services-multi-service-failing`,
`op-remove-retry`, and `connect-undo`. Selection is not evidence of execution.

Important proposed checks remain absent: independent checkpoint readback,
committed Current/Sequence consistency, stable active links/resources, manager
visitation, and replay-safe lifecycle effects. Source assertions do not currently
independently verify rollback isolation, mounted resources or crash recovery.
The dirty-Unlock assertion observes the same checkpoint-success branch it guards;
it cannot by itself catch incorrect bytes written by a successful backend.

Artifact preparation now stages extracted catalog data at `/symbols` in the
`snapd-testing-image` scratch image, rather than extracting `/catalog` into the
Incus container. The existing local snap failed the earlier catalog extraction
check because it contained no catalog directory. Build wiring therefore does not
establish that the actual artifact has cataloged these four messages or reports
them in Antithesis. Rebuild and inspect the instrumented snap and then verify
runtime encounters before treating the campaign as assertion-enabled.

This targeted status pass refreshes the inventory only: it adds no properties
or source instrumentation and does not repeat portfolio evaluation. Earlier
unit/SDK validation above is historical evidence, not an Antithesis run result.
External SUT scope remains exactly "just this directory"; no new external
documentation claims are needed for this source inventory.

## Assumptions

The catalog describes proposed assertions unless explicitly marked existing.
SDK package presence does not imply every build produces an assertion catalog.

## Open Questions

Confirm assertion catalog generation for the actual harness binary before a run.
Confirm which optional cancellation assertions the selected Spread tests encounter.
No dedicated cancellation test template or instrumented campaign validation was
added by this status pass.