# snap-current-in-sequence

Scope answer (verbatim): "just this directory"; external_references: [].
Focus: integrity/lifecycle. Confidence: high in the proposed contract, not proof
of fault tolerance. No production changes.

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
- [snapstate.go](../../../overlord/snapstate/snapstate.go#L4038): Set removes an
  empty sequence entry; it does not validate membership itself.
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
Do not require the highest or last revision. Initially exclude try-mode,
components, snapd self-refresh, boot-participating snaps, reboot and remodel;
their expanded contracts need separate fixtures. This does not assert disk
equality during in-flight work.

## Instrumentation And Questions

**Missing**: [existing-assertions.md](../existing-assertions.md) inventories only
the Hold assertion, not this invariant. Proposed placement is immediately
before committed SnapState writes plus a recovered-state checker; neither an
oracle helper nor a quiescence barrier is claimed to exist. Fixture selection,
barrier implementation and fault availability remain catalog-wide plans in
[deployment-topology.md](../deployment-topology.md).

**Open Questions:** None within this initial scope.

### Investigation Log

#### Must Current be highest, and does disabled mean uninstalled?

Examined the accessor, insertion path and out-of-order/empty/inconsistent tests
above. Found membership, not revision ordering, is required; installation is
determined by Current, not Active. No unresolved per-property question remains;
special device/component cases are explicitly excluded rather than generalized.