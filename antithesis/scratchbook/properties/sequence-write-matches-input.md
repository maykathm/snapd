# sequence-write-matches-input

Scope answer (verbatim): "just this directory"; external_references: [].
Focus: integrity. Confidence: high in the writer-scoped contract.

## Property

**P1 | Safety | Always**: immediately after a successful writeSeqFile, before
another writer/remover can affect that instance file, independently read and
decode the file and compare its sequence, Current string and migration flags to
the immutable input projection captured before writing. Message:
`successful sequence write matches captured input projection`. Every successful
eligible write must match; a single Sometimes success cannot establish this.
Do not assert perpetual equality with global SnapState.

## Verified Evidence

- [handlers.go](../../../overlord/snapstate/handlers.go#L1658): writeSeqFile
  marshals Sequence, Current.String and two migration flags; an empty sequence
  forces both flags false. It writes through AtomicWriteFile with mode 0644.
- [handlers.go](../../../overlord/snapstate/handlers.go#L1959): link writes for
  failover before backend linkage and committed snapstate; later candidate
  failure/undo can cause further writes.
- [handlers_link_test.go](../../../overlord/snapstate/handlers_link_test.go#L318):
  TestDoLinkSnapSeqFile checks the exact two-revision JSON and selected Current.
  Undo of first install checks empty sequence, `unset` and false flags at
  [handlers_link_test.go](../../../overlord/snapstate/handlers_link_test.go#L418).
- [handlers_discard_test.go](../../../overlord/snapstate/handlers_discard_test.go#L292):
  last discard removes the file; the non-last test at
  [handlers_discard_test.go](../../../overlord/snapstate/handlers_discard_test.go#L326)
  retains it. [handlers.go](../../../overlord/snapstate/handlers.go#L3618)
  removes the file only in the last-revision branch, with no non-last rewrite.
- [io.go](../../../osutil/io.go#L157): atomic commit syncs the temporary file,
  closes, renames then syncs the directory unless unsafe I/O is enabled. That
  control flow is evidence for a durability test target, not crash proof.

## Oracle, Faults And Boundary

Capture a deep, immutable projection of the actual input, including ordered
revision side-info/component encoding if later supported. Decode independently
using structured JSON; compare values, not formatting. Do not call the writer's
serializer twice and label that disk verification. For initial app fixtures,
also cross-check selected revision and revision identities against the separate
admission/fixture ledger: correct serialization of wrong input must not count as
lifecycle correctness. Use full instance identity for path selection.

Readback is proposed inside the serialized writer boundary after nil return,
not a delayed global check. Missing/unreadable/malformed file fails in the
healthy-storage campaign. Crash before return has no successful-write encounter;
explore rename/sync windows and replay, then check the next completed write.
Power-loss/storage-error guarantees require a separately confirmed fault model;
an error return is not itself a violation of this successful-return property.
Violation supplies failover helpers the wrong revision or migration state.

Initially cover ordinary apps and empty failed-install undo projections; both
active and disabled input are legal and Active is not serialized. Exclude
try-mode, seeded/special snapd failover, boot/reboot/remodel and components from
the initial lifecycle oracle; writer schema fidelity is distinct from their
semantics. Do not add assertions to the non-last discard path based on stale
file equality. No new SUT code is applied by this research.

## Instrumentation And Questions

**Missing**, per [existing-assertions.md](../existing-assertions.md): no sequence
readback assertion exists. Proposed writer-local readback must be gated to test
builds/campaigns because SDK no-op mode still evaluates expensive arguments.
Fixtures and barrier/fault wiring remain catalog-wide plans in
[assertion-placement.md](../assertion-placement.md) and
[deployment-topology.md](../deployment-topology.md), not existing helpers.

**Open Questions:** None within this initial scope.

### Investigation Log

#### Is this file a perpetual state mirror, including empty undo?

Examined writer schema, link/undo JSON expectations and both discard tests.
Found empty undo intentionally writes `unset`/false flags, while non-last discard
does not refresh the file. Conclusion: verify successful writes against captured
input only; use an independent admission check for input semantic correctness.