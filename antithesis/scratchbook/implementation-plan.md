# Antithesis assertion and test expansion plan

## Goal

Expand the existing Antithesis campaign to test snapd under network, thread-pausing,
and disk I/O faults. Build on the properties in `property-catalog.md` and the
six existing SDK assertion sites inventoried in `existing-assertions.md`.

Scope the first implementation to ordinary application snaps and controlled
fixtures. Do not treat a transient Spread command failure as proof of a snapd
correctness violation: check the resulting state and resources independently.

## Workstream 1 — Verify the harness and baseline

**Owner scope:** `antithesis/`, instrumented snap build and test selection.

1. Reconcile documentation with the current harness: `antithesis/tests/main/`
   contains nine selected symlinked Spread tests, not the eleven described in
   parts of the scratchbook.
2. Verify that the actual built daemon has an assertion catalog, coverage
   instrumentation, symbols, and runtime SDK encounters. Thread pausing depends
   on coverage instrumentation, not merely SDK imports.
3. Confirm that snapd-to-fakestore traffic crosses a faulted network boundary.
   Record the disk fault behavior relevant to the oracles: errors, delays,
   successful-but-incorrect reads/writes, or a combination.
4. Run each selected test once without injected faults on an isolated system.
   Record fixture, base-snap, runtime, setup, and cleanup dependencies.

**Deliverable:** corrected coverage inventory and a reproducible baseline.
Do not install packages, change services, or run snapd on the host.

## Workstream 2 — Thread-pausing assertions and cancellation test

**Owner scope:** `overlord/state/taskrunner.go`; focused state tests; a new
Antithesis Spread task.

- Add an `Always` check immediately before task dispatch (`r.run(t)`): no active
  invocation for that task in this runner; the retry time is due; and the
  dependency requirements for its actual Do/Doing/Undo/Undoing status hold.
  Capture decisions already made by blocking predicates. Do not invoke those
  predicates again for the assertion. Do not impose fresh-Do dependency rules
  on Doing/Undoing replay.
- Add separate `AlwaysOrUnreachable` checks that cleanup starts only after
  owning-change readiness and that runner-owned clean commits follow eligible
  successful cleanup or the no-handler path. An expected cleanup error may retry.
- Create a task that starts an asynchronous operation, observes it in flight,
  requests `snap abort`, and checks the resulting status and resources. Include
  an accepted-abort coverage anchor. The existing `tests/main/abort/` checks
  invalid and terminal aborts; it does not supply this scenario.
- Exercise scheduling and cancellation with pauses around unlocked handler work,
  another Ensure pass, and handler completion. Preserve legal Hold behavior.

**Validation:** focused Go/gocheck tests, applicable race tests, Spread shell
and format checks, then an isolated unfaulted task run.

## Workstream 3 — Network downloads and accepted-content oracle

**Owner scope:** `store/store_download.go`,
`overlord/assertstate/assertmgr.go`, download tests and fixtures.

- Add distinct fixed-message `Reachable` anchors for nonzero-offset resume,
  valid-cache recovery, wrong-size cache rejection, and hash-error retry.
  Keep outcome identifiers in details rather than dynamically generated messages.
- For a controlled signed fixture, check at successful `doValidateSnap`
  completion that the computed digest and size match an independently recorded
  manifest for the admitted snap/revision. Use `Always` for eligible acceptances.
  Do not equate `Store.Download` success with cryptographic acceptance: cache
  hits can use a size-only heuristic.
- Adapt `tests/main/resume-partial-snap-downloads/` into the Antithesis test
  selection. Reconcile its per-test fakestore setup with the existing separate
  fakestore before enabling it. Check the final blob against the fixture digest
  as well as the existing partial-file and Range-request observations.
- In an isolated cache campaign, adapt the wrong-size and bit-flip cases of
  `tests/main/snap-download-corrupted-cleanup/`. Keep expected fixture data
  outside SUT-writable paths; rejection followed by clean re-download is valid.

**Validation:** focused download/validation tests, oracle tests with deliberately
incorrect blobs, Spread checks and unfaulted isolated baselines.

## Workstream 4 — Disk checkpoint oracle

**Owner scope:** a gated Antithesis-only check around
`overlordStateBackend.Checkpoint` and focused tests.

- After a successful production checkpoint, independently read its target
  before another writer can run and compare it with the *exact bytes passed to
  Checkpoint*. Do not compare a fresh `MarshalJSON`: notice timestamps can
  legitimately change outside the state mutex.
- Keep expensive readback out of ordinary production execution. Distinguish an
  injected read error from a successful read of incorrect bytes; define the
  reportable outcome after confirming the tenant's disk-fault semantics.
- Add a small workload that admits distinguishable state changes, encounters
  checkpoint retries/failures, and checks eventual readable state and all
  admitted outcomes after a calibrated quiet period. A checkpoint error followed
  by retry is permitted; a successful checkpoint publishing wrong bytes is not.
- Retain the existing dirty-Unlock assertion as a separate control-flow check.

**Validation:** checkpoint success, retry, read-error and wrong-byte tests;
then an isolated unfaulted and faulted campaign.

## Workstream 5 — Lifecycle and rollback outcome tests

**Owner scope:** Spread selection, controlled fixtures and an independent checker.

- Adapt `tests/main/refresh-all-undo/` and
  `tests/main/refresh-many-transactional-undo/` as a pair. Predeclare their
  different expected outcomes: the good snap can update in the per-snap case,
  while an all-snaps transaction rolls it back. Reconcile their fakestore setup.
- Use two controlled revisions plus an unrelated snap with distinct revision
  and data tokens. Record intent before submission and reconcile lost API
  responses against change/resource identity; never silently drop an admitted
  operation.
- After stable successful activation or completed rollback, compare both
  current links, mounted/content identity, retained resources, launch output
  and unrelated snap data against the independent fixture ledger.
- Build a stable observation boundary that excludes affecting background
  handlers and cleanup as well as new client submissions. Do not require the
  two links to agree during an in-flight link operation.
- At a calibrated quiet-phase deadline, check every admitted reversible
  operation. Observe the deadline outside the SUT locks and snapshot barrier
  so a blocked barrier cannot conceal stalled work.

**Validation:** tests that reject deliberately wrong stable snapshots, Spread
checks, an unfaulted isolated run, then faulted runs with outcome encounters
and failures inspected separately.

## Sequence and handoff

1. Complete Workstream 1 before interpreting campaign results.
2. Workstreams 2, 3 and 4 can proceed in parallel once the harness baseline and
   disk-fault semantics are known.
3. Workstream 5 depends on the controlled fixtures and independent observation
   mechanism; reuse these for download and checkpoint outcome checks where useful.
4. After each implementation, update `existing-assertions.md`, the affected
   property evidence files, and the active-test inventory with verified results.

Crash-generation and do/undo replay properties require an explicit confirmed
process-restart scenario or termination faults. Do not claim those properties
are covered by network, thread-pausing and disk I/O faults alone.
