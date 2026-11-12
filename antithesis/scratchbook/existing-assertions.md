---
sut_path: /home/katie.may@canonical.com/source/snapd
commit: d7d23f20732844eb538dab1169f8b8b372376911
updated: 2026-11-12
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
| `overlord/state/taskrunner.go:328` | `TaskRunner.run` locked finalization | `AlwaysOrUnreachable` | `aborted handler completion follows cancellation transition` |
| `overlord/snapstate/snapstate.go:4254` | `Set` locked SnapState replacement | `Always` | `committed app current belongs to its revision sequence` |
| `overlord/stateengine.go:192` | `StateEngine.Ensure` deferred completion check | `Always` | `completed ensure pass visits every registered manager` |
| `overlord/state/taskrunner.go:542` | `TaskRunner.Ensure` captured dispatch gates | `Always` | `task dispatch respects runner scheduling gates` |
| `overlord/state/taskrunner.go:364` | `TaskRunner.clean` cleanup admission | `AlwaysOrUnreachable` | `cleanup starts only after owning change is ready` |
| `overlord/state/taskrunner.go:352` | `TaskRunner.clean` no-handler clean commit | `AlwaysOrUnreachable` | `runner clean commit follows eligible cleanup or no-handler path` |
| `overlord/state/taskrunner.go:386` | `TaskRunner.clean` successful cleanup commit | `AlwaysOrUnreachable` | `runner clean commit follows eligible cleanup or no-handler path` |
| `overlord/state/change.go:802` | `Change.abortTasks` accepted in-flight abort | `Reachable` | `snap abort accepted during in-flight task` |
| `store/store_download.go:170` | `Store.Download` recovered valid cache entry | `Reachable` | `snap download recovered a valid cache entry` |
| `store/store_download.go:179` | `Store.Download` rejected wrong-size cache entry | `Reachable` | `snap download rejected a wrong-size cache entry` |
| `store/store_download.go:256` | `Store.Download` nonzero-offset resume | `Reachable` | `snap download resumes from a nonzero offset` |
| `store/store_download.go:282` | `Store.Download` hash-error retry | `Reachable` | `snap download retries after a hash mismatch` |

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

The source inventory includes fifteen SDK assertion callsites and fourteen
unique property messages. It covers the existing state, snapstate and
state-engine checks; task dispatch, cleanup and accepted abort; and four
download-path `Reachable` anchors for resume, cache recovery, wrong-size cache
rejection and hash-error retry. No SUT `Sometimes` or `Unreachable` callsites
were found. This remains narrow instrumentation, not implementation of the
nineteen-property portfolio in `property-catalog.md`.

The four download anchors have a focused SDK-output matrix over the existing
store tests; all emitted one true `Reachable` event. They record recovery-path
encounters only. They do not compare accepted content to an independent fixture
manifest, validate retained blobs, or establish that a faulted Antithesis run
encounters these paths.

The original nine-test baseline exercised local install, refresh, revert,
interface and service rollback, parallel instances and removal. It ran as ten
jobs because `install-refresh-remove-hooks` has `regular` and `parallel`
variants. All ten jobs succeeded with zero aborted tasks on disposable Ubuntu
26.04 Incus containers. After Workstream 2, the refreshed selection ran all
eleven jobs, including `abort-accepted`, against the rebuilt artifact; all
eleven succeeded with zero aborted tasks. The abort task also passed separately
before the refreshed run. These are unfaulted scenario results, not a faulted
Antithesis campaign. The scenarios do not guarantee competing Done/Wait setters
or aborted-handler finalization.

The current selection is defined by symlinks in `antithesis/tests/main/`, not
the older first-series/future-campaign recommendations in the topology notes:
`abort-accepted`, `revert-sideload`, `install-refresh-remove-hooks`, `refresh-undo`,
`op-install-failed-undone`, `services-disabled-kept-unhappy`,
`parallel-install-common-dirs-undo`, `connections-after-failed-refresh`,
`services-multi-service-failing`, and `op-remove-retry`. The original nine were
executed as ten jobs in the original baseline. The refreshed eleven-job run
executed all ten selected symlink targets, including both hook variants and
`abort-accepted`. Selection alone is not evidence of execution.

Important proposed checks remain absent: independent checkpoint readback,
stable active links/resources and replay-safe lifecycle
effects. Current/Sequence consistency has a source write-boundary check, but no
independent recovered-state or intended-revision oracle. Source assertions do
not currently independently verify rollback isolation, mounted resources or crash recovery.
The dirty-Unlock assertion observes the same checkpoint-success branch it guards;
it cannot by itself catch incorrect bytes written by a successful backend.

The rebuilt artifact `built-snap/snapd_1337.2.78_amd64.snap.keep` is 74 MB.
It contains the snapd daemon built with `-race` and 208 Go `*.sym.tsv` coverage
symbol files under `catalog/`.
All ten unique assertion message literals are embedded in the daemon. The pinned SDK
generates assertion catalog registrations as Go init code, so these are not
separate files under `catalog/`.

A local SDK-output probe against the updated isolated testing image recorded
eight runtime hits across eight properties; every hit condition was true. The
hits covered dirty-Unlock checkpointing, Current/Sequence membership,
Ensure-pass visitation, task dispatch, cleanup admission/commit, accepted abort
and aborted-handler completion. The competing Done/Wait setter assertions were
cataloged but not encountered. The host Spread runner's `sdk.jsonl` contained
only its setup-complete event because the local Incus SUT does not receive
Antithesis' `ANTITHESIS_OUTPUT_DIR` mount. This verifies local SDK output, not
reporting in a real Antithesis run.

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

Confirm runtime reporting in an Antithesis run and which optional cancellation
assertions the selected workload encounters. The repository does not configure
network or disk fault injection, so the baseline does not establish tenant
fault semantics or disk error/corruption behavior.