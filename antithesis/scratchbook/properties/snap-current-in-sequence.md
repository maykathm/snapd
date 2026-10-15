# snap-current-in-sequence

Scope answer (verbatim): "just this directory"; external_references: [].
Focus: integrity/lifecycle. Confidence: high in the state-write contract, not proof
of fault tolerance. Source assertion implemented on 2026-10-15.

## Property

**P0 | Safety | Always**: at a locked committed-state observation, every
installed ordinary application instance has a set Current occurring in its
Sequence. An absent instance is valid only when the independent admission
ledger permits absence. Use the fixed message
`committed app current belongs to its revision sequence`: every eligible
observation must satisfy this, not merely one Sometimes witness.

## Verified Evidence

- [snapmgr.go](../../../overlord/snapstate/snapmgr.go#L471): IsInstalled rejects
  unset Current with a nonempty sequence. CurrentSideInfo at
  [snapmgr.go](../../../overlord/snapstate/snapmgr.go#L518) panics if the selected
  revision is absent; inspect raw fields rather than invoking this panic path.
- [handlers.go](../../../overlord/snapstate/handlers.go#L1850): doLinkSnap adds
  or reorders the candidate before setting Current and Active.
- [snapstate.go](../../../overlord/snapstate/snapstate.go#L4040): Set removes an
  empty sequence entry. Its new assertion observes nonempty, explicitly typed
  app entries outside try-mode after serialization and before committing the
  replacement. It checks raw revision membership without panic-prone accessors.
- [snapstate_test.go](../../../overlord/snapstate/snapstate_test.go#L5532):
  TestCurrentSideInfoOutOfOrder accepts an older Current. Inconsistency tests at
  [snapstate_test.go](../../../overlord/snapstate/snapstate_test.go#L5542)
  reject unset/missing Current; the empty-state test is at
  [snapstate_test.go](../../../overlord/snapstate/snapstate_test.go#L5507).

## Oracle, Faults And Boundary

Record admitted instance, operation, old revision and fixture-selected target
before execution; after a successful refresh/revert independently require the
ledger-selected Current as well as membership. A wrong-but-present revision
must fail that companion check. Do not derive expected identity from Current.
Observe serialized committed SnapState under its lock, never a handler's
partially edited local candidate. At recovery use the stable-check plan in
[assertion-placement.md](../assertion-placement.md), not a lone Done task.

Crash around candidate insertion, external linking and checkpointing, or
interleave independent instances' commits. A lost sequence entry can make
current-info queries panic and break subsequent lifecycle work. Disabled apps
still have Current and retained sequence; Active is not a membership guard.
Do not require the highest or last revision. Try-mode, snapd self-refresh and
boot-participating snap types are excluded from the source assertion. The
membership check concerns parent snap revisions even if component metadata is
present; it makes no claim about component resources. Component lifecycle,
reboot and remodel campaigns still need separate fixtures. This does not assert
disk equality during in-flight work.

## Instrumentation And Questions

**Partial:** `snapstate.Set` now emits the fixed-message `Always` assertion at
the shared locked write boundary, covering handler do/undo and other SnapState
writers without duplicating callsites. Nil/empty entries are deletion, not
membership encounters. Untyped and non-app states and try-mode are excluded.
Disabled apps remain eligible. A false condition is reported without rejecting,
repairing or changing the serialized state.

`assertions_test.go` runs each case in a fresh subprocess with SDK local output,
checking the actual message, type, condition, details and encounter gating.
Cases cover active/disabled apps, an older Current, local revisions, absent and
unset Current, a zero revision, malformed nil entries and excluded/deleted
states. The child verifies unchanged serialization/deletion even when safety
is false.

The SDK-output matrix and selected sequence/link/unlink/discard/enable/disable
tests pass under the race detector. Lifecycle local telemetry reports a
successful membership encounter without a failure. Nearby state behavior also
passes with the SDK disabled. These are local validations, not campaign results.

An independent ledger-selected revision checker, recovered-state observer,
stable-disk oracle and quiescence barrier remain unimplemented. Membership does
not prove the intended revision was selected or that any mounted resource is
correct. Actual harness catalog/report verification and campaign validation
remain deferred; see [existing-assertions.md](../existing-assertions.md) and
[deployment-topology.md](../deployment-topology.md).

**Open Questions:** None within this initial scope.

### Investigation Log

#### Must Current be highest, and does disabled mean uninstalled?

Examined the accessor, insertion path and out-of-order/empty/inconsistent tests
above. Found membership, not revision ordering, is required; installation is
determined by Current, not Active. No unresolved per-property question remains;
special device/component cases are explicitly excluded rather than generalized.