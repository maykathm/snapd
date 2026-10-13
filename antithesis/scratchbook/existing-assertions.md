---
sut_path: /home/katie.may@canonical.com/source/snapd
commit: e88ec08852fbc8af019dc39e22097e5720aa6dfd
updated: 2026-10-13
external_references: []
---

# Existing Antithesis Assertions

Scope answer (verbatim): "just this directory".

## Inventory

| File and line | Function | Type | Exact message |
| --- | --- | --- | --- |
| `overlord/state/change.go:451` | `Change.notifyStatusChange` | `Always` | `change never enters hold status` |

The predicate is `new != HoldStatus`; details include change ID, kind, and
status. This is existing instrumentation, not a proposed addition. Its premise
is too broad: `Change.SetStatus(HoldStatus)` is supported, and aborting an
all-pending change produces aggregate Hold through task-status notifications.
See `overlord/state/change.go:408`, `:800`, `overlord/state/change_test.go:158`,
`:168`, `:475`, and `overlord/state/taskrunner.go:366`. Empty-change construction
alone need not encounter the assertion. Do not generalize it to tasks; replace
its premise with scoped cancellation invariants in an implementation pass.

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