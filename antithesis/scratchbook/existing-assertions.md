---
sut_path: /home/katie.may@canonical.com/source/snapd
commit: 114df3f4470d29b961205b33b56574dcb468514b
updated: 2026-10-15
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
| `overlord/snapstate/snapstate.go:4064` | `Set` locked SnapState replacement | `Always` | `committed app current belongs to its revision sequence` |
| `overlord/stateengine.go:192` | `StateEngine.Ensure` deferred completion check | `Always` | `completed ensure pass visits every registered manager` |

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

The Current/Sequence check observes explicitly typed app states outside try-mode
at the shared `snapstate.Set` boundary, after successful serialization and before
the replacement is written under the state lock. Every nonempty eligible entry
requires a set Current present in its Sequence, including disabled instances.
Deletion, untyped/non-app entries and try-mode are excluded. A false condition
does not change serialization, reject the write or panic. This does not prove
the intended revision was selected or that installed resources match state.

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

The source inventory now includes six SDK assertion callsites: one dirty-
checkpoint control-flow assertion, three optional cancellation-transition
assertions in `overlord/state`, and the Current/Sequence membership assertion in
`overlord/snapstate`, plus completed Ensure-pass visitation in `overlord`.
No SUT `Sometimes`, `Reachable`
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
stable active links/resources and replay-safe lifecycle
effects. Current/Sequence consistency has a source write-boundary check, but no
independent recovered-state or intended-revision oracle. Source assertions do
not currently independently verify rollback isolation, mounted resources or crash recovery.
The dirty-Unlock assertion observes the same checkpoint-success branch it guards;
it cannot by itself catch incorrect bytes written by a successful backend.

Artifact preparation now stages extracted catalog data at `/symbols` in the
`snapd-testing-image` scratch image, rather than extracting `/catalog` into the
Incus container. The existing local snap failed the earlier catalog extraction
check because it contained no catalog directory. Build wiring therefore does not
establish that the actual artifact has cataloged these six messages or reports
them in Antithesis. Rebuild and inspect the instrumented snap and then verify
runtime encounters before treating the campaign as assertion-enabled.

The 2026-10-15 source follow-up implements the existing membership property; it
does not add property IDs or repeat portfolio evaluation. The new tests inspect
actual SDK-local successful/failed encounters, diagnostic details and gating,
and verify unchanged serialization/deletion behavior. Earlier unit/SDK evidence
above concerns the checkpoint/cancellation changes, not an Antithesis run.
External SUT scope remains exactly "just this directory".

Validation for this follow-up: the thirteen-case SDK-output matrix and selected
sequence/link/unlink/discard/enable/disable tests passed under the race detector.
Lifecycle SDK-local output contained a successful membership encounter and no
membership failure event. Nearby state tests also passed with
`-tags=no_antithesis_sdk`. Tests used `GODEBUG=rsa1024min=0` for the repository's
existing small RSA test keys on the current Go toolchain.

The Ensure-visitation follow-up adds an `Always` check under `mgrLock` for
normal admitted completions, including aggregated manager errors. Its nine-case
SDK-local subprocess matrix checks actual encounters, slot counts, pass details,
duplicate registration, vacuous empty success, lifecycle rejection, panic
exclusion and successful recovery after panic. No useful-work or progress
guarantee is implied, and real harness reporting remains unverified.
The complete state-engine suite, including the nine SDK-local scenarios, passed
with `-race`; the engine suite also passed with `-tags=no_antithesis_sdk`.
Both commands used the small-RSA test compatibility setting noted above.

## Assumptions

The catalog describes proposed assertions unless explicitly marked existing.
SDK package presence does not imply every build produces an assertion catalog.

## Open Questions

Confirm assertion catalog generation for the actual harness binary before a run.
Confirm which optional cancellation assertions the selected Spread tests encounter.
No dedicated cancellation test template or instrumented campaign validation was
added by this status pass.