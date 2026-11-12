# Antithesis assertion and test expansion plan
This is the single authoritative implementation plan for the Antithesis
scratchbook. Evaluation and property documents retain findings, contracts and
evidence; they do not define a separate execution order.

## Goal

Expand the existing Antithesis campaign to test snapd under network, thread-pausing,
and disk I/O faults. Build on the properties in `property-catalog.md` and the
current assertion inventory in `existing-assertions.md`.

Scope the first implementation to ordinary application snaps and controlled
fixtures. Do not treat a transient Spread command failure as proof of a snapd
correctness violation: check the resulting state and resources independently.

## Current Status

- The local race-enabled artifact and unfaulted baseline have been verified. The
  current selection has ten symlink targets and eleven Spread jobs; all eleven
  passed with zero aborts on disposable Ubuntu 26.04 Incus containers.
- Dispatch, cleanup, accepted-abort and four download-recovery assertions have
  focused SDK-output tests. The accepted-abort task passed standalone and in
  the refreshed baseline.
- No tenant faulted campaign has been run. Network fault reachability, disk
  fault semantics, preserved storage and actual tenant reporting remain
  unverified.
- The signed-fixture acceptance oracle, paused handler interleavings, shared
  workload ledger, stable observation barrier and independent lifecycle
  checker are not implemented.

## Workstream 1 — Verify the harness and baseline

**Status: Partial.** The previous instrumented artifact and local baseline were
verified; the current source needs a refreshed artifact and fault qualification.

**Owner scope:** `antithesis/`, instrumented snap build and test selection.

1. [x] Keep the active inventory aligned with `antithesis/tests/main/`: it contains
  ten selected symlink targets; `install-refresh-remove-hooks` expands to two
  variants, for eleven jobs.
2. [ ] Rebuild and verify the current daemon has the expected assertion catalog, coverage
  symbols and runtime encounters, including the four Workstream 3 messages.
  The earlier artifact inspection predates those download anchors.
3. [ ] Confirm that snapd-to-fakestore traffic crosses a boundary reachable by
  the tenant's fault injector. The local Incus route uses the external fakestore
  container, but no network fault is configured. Record tenant disk-fault
  behavior: errors,
  delays, successful-but-incorrect reads/writes, or a combination.
4. [x] Run each selected test once without injected faults on an isolated system.
  The refreshed run completed with all eleven jobs passing. Keep fixture,
  base-snap, runtime, setup and cleanup dependencies with the baseline record.

**Deliverable:** inventory and reproducible local baseline are complete; the
latest artifact and faulted-campaign readiness are not yet verified. Do not
install packages, change services, or run snapd on the host.

## Workstream 2 — Thread-pausing assertions and cancellation test

**Status: Partial.** Assertions, local SDK tests and the accepted-abort Spread
task are implemented. The explicit pause/interleaving scenarios below remain.

**Owner scope:** `overlord/state/taskrunner.go`; focused state tests; a new
Antithesis Spread task.

- [x] Add an `Always` check immediately before task dispatch (`r.run(t)`): no active
  invocation for that task in this runner; the retry time is due; and the
  dependency requirements for its actual Do/Doing/Undo/Undoing status hold.
  Capture decisions already made by blocking predicates. Do not invoke those
  predicates again for the assertion. Do not impose fresh-Do dependency rules
  on Doing/Undoing replay.
- [x] Add separate `AlwaysOrUnreachable` checks that cleanup starts only after
  owning-change readiness and that runner-owned clean commits follow eligible
  successful cleanup or the no-handler path. An expected cleanup error may retry.
- [x] Create a task that starts an asynchronous operation, observes it in flight,
  requests `snap abort`, and checks the resulting status and resources. Include
  an accepted-abort coverage anchor. The existing `tests/main/abort/` checks
  invalid and terminal aborts; it does not supply this scenario.
- [ ] Exercise scheduling and cancellation with pauses around unlocked handler work,
  another Ensure pass, and handler completion. Preserve legal Hold behavior.
- [ ] Add controlled pause/resume cases that prove another Ensure cannot duplicate
  an active handler and that cancellation remains correct when handler completion
  races with the accepted abort. Current Doing/Undoing matrix cases are in-process
  status tests, not persisted daemon-restart replay.

**Validation:** focused Go/gocheck tests, applicable race tests, Spread shell
and format checks, then an isolated unfaulted task run.

## Workstream 3 — Network downloads and accepted-content oracle

**Status: Partial.** The four download-path `Reachable` anchors and focused
SDK-output tests are implemented. Fixture-backed acceptance and network-fault
Spread scenarios remain.

**Owner scope:** `store/store_download.go`,
`overlord/assertstate/assertmgr.go`, download tests and fixtures.

- [x] Add distinct fixed-message `Reachable` anchors for nonzero-offset resume,
  valid-cache recovery, wrong-size cache rejection, and hash-error retry.
  Keep outcome identifiers in details rather than dynamically generated messages.
- [ ] For a controlled signed fixture, check at successful `doValidateSnap`
  completion that the computed digest and size match an independently recorded
  manifest for the admitted snap/revision. Use `Always` for eligible acceptances.
  Do not equate `Store.Download` success with cryptographic acceptance: cache
  hits can use a size-only heuristic.
- [ ] Adapt `tests/main/resume-partial-snap-downloads/` and
  `tests/main/snap-download-corrupted-cleanup/` for the Antithesis selection.
  Both currently start a second fakestore in the SUT and point snapd to
  `localhost:11028`, bypassing the external network boundary. Use the shared
  fakestore, reconcile fixture seeding, and verify the final blob against its
  independent digest as well as existing Range/cache observations.
- [ ] In the isolated cache campaign, exercise wrong-size and bit-flip cases
  with expected fixture data outside SUT-writable paths; rejection followed by
  clean re-download is valid.
- [ ] Add negative oracle tests with a wrong digest and a same-size bit-flipped blob;
  neither may pass as accepted signed content.

**Validation:** focused download/validation tests, oracle tests with deliberately
incorrect blobs, Spread checks and unfaulted isolated baselines.

## Shared Campaign Prerequisites

These prerequisites are shared by Workstreams 3-5; details in evaluation and
topology documents are rationale, not separate plans.

- [ ] Freeze signed fixture IDs, revisions, digests, sizes and data tokens before
  admission. Keep the fixture authority and checker ledger outside SUT-writable
  paths; missing manifest or checker observations must fail or invalidate the
  experiment, never become an empty successful cohort.
- [ ] Record operation intent before submission. Distinguish acknowledged,
  definitely rejected and outcome-unknown requests; reconcile unknown responses
  against change/resource identity before retrying or pruning.
- [ ] Build a bounded observation barrier that closes new admissions and excludes
  affecting handlers, cleanup and background writers without holding locks needed
  for their completion. Keep the liveness deadline in an independent checker so
  a stuck barrier cannot hide stalled work.
- [ ] Define campaign-specific reachability witnesses separately from safety
  assertions. Require only outcomes deliberately constructed by that campaign;
  do not infer coverage from a passing optional invariant or a submitted request.
- [ ] Verify catalogs and reporting from the actual SUT and checker binaries, including
  the pinned SDK/cgo build requirements, before interpreting a tenant run.

## Workstream 4 — Disk checkpoint oracle

**Status: Not started; tenant disk-fault semantics are unconfirmed.**

**Owner scope:** a gated Antithesis-only check around
`overlordStateBackend.Checkpoint` and focused tests.

- [ ] After a successful production checkpoint, independently read its target
  before another writer can run and compare it with the *exact bytes passed to
  Checkpoint*. Do not compare a fresh `MarshalJSON`: notice timestamps can
  legitimately change outside the state mutex.
- [ ] Keep expensive readback out of ordinary production execution. Distinguish an
  injected read error from a successful read of incorrect bytes; define the
  reportable outcome after confirming the tenant's disk-fault semantics.
- [ ] For crash-generation checks, persist the baseline and candidate payload
  identity in an independent ledger. Acknowledge attempt registration before
  allowing the write; record completion only after a successful return. Treat
  an unobserved completion as ambiguous, and allow old-or-attempted bytes only
  when success was not confirmed. Inspect the checkpoint while snapd is stopped,
  before startup can write it again.
- [ ] Before replay, compare the restored task/change graph and ID history with an
  independently decoded checkpoint projection. Normalize absent/default waited
  status to Done, including same-version tasks, and include unlinked persisted
  tasks; do not use snapd's own decoder as the only oracle.
- [ ] Add a small workload that admits distinguishable state changes, encounters
  checkpoint retries/failures, and checks eventual readable state and all
  admitted outcomes after a calibrated quiet period. A checkpoint error followed
  by retry is permitted; a successful checkpoint publishing wrong bytes is not.
- [x] Retain the existing dirty-Unlock assertion as a separate control-flow check.

**Validation:** checkpoint success, retry, read-error and wrong-byte tests;
then an isolated unfaulted and faulted campaign.

## Workstream 5 — Lifecycle and rollback outcome tests

**Status: Not started; depends on the shared fixtures, ledger and observation
barrier above.**

**Owner scope:** Spread selection, controlled fixtures and an independent checker.

- [ ] Adapt `tests/main/refresh-all-undo/` and
  `tests/main/refresh-many-transactional-undo/` as a pair. Predeclare their
  different expected outcomes: the good snap can update in the per-snap case,
  while an all-snaps transaction rolls it back. Reconcile their fakestore setup.
- [ ] Use two controlled revisions plus an unrelated snap with distinct revision
  and data tokens. Record intent before submission and reconcile lost API
  responses against change/resource identity; never silently drop an admitted
  operation.
- [ ] After stable successful activation or completed rollback, compare both
  current links, mounted/content identity, retained resources, launch output
  and unrelated snap data against the independent fixture ledger.
- [ ] Check the sequence-file writer against its captured input at successful write
  return; do not require perpetual equality between sequence files and SnapState.
- [ ] Check committed Current against the independently expected revision after
  recovery, in addition to the existing source-side Current/Sequence invariant.
- [ ] Build a stable observation boundary that excludes affecting background
  handlers and cleanup as well as new client submissions. Do not require the
  two links to agree during an in-flight link operation.
- [ ] At a calibrated quiet-phase deadline, check every admitted reversible
  operation. Observe the deadline outside the SUT locks and snapshot barrier
  so a blocked barrier cannot conceal stalled work.
- [ ] After successful install, refresh, enable or completed rollback, launch a
  deterministic CLI fixture through the normal command path and compare its
  revision/data tokens with the independent ledger. Do not infer launchability
  from links or mounts alone.
- [ ] For removal, check unrelated survivors after both success and terminal failure.
  Only successful removal requires complete target deletion. Choose purge for
  the initial campaign or define an explicit saved-snapshot content oracle; do
  not promise restoration of destructively removed target data after failure.
- [ ] Keep the initial workload to confirmed ordinary application fixtures. Verify
  the task plan does not introduce excluded base/boot/self-refresh work; treat
  missing fixture/base resources or an unexpected special task as an invalid
  experiment, not an empty or filtered cohort.
- [ ] Maintain a campaign matrix with distinct Reachable witnesses for constructed
  do/undo replay, rollback restoration, successful cleanup, last/non-last
  removal, accepted cancellation, resumed transfer and verified cache reuse.
  A launch campaign also witnesses successful install/refresh/enable outcomes.
  Keep these obligations separate from the corresponding safety checks.

**Validation:** tests that reject deliberately wrong stable snapshots, Spread
checks, an unfaulted isolated run, then faulted runs with outcome encounters
and failures inspected separately.

## Sequence and handoff

1. Finish the Workstream 2 pause/interleaving tests and verify the current
  instrumented artifact.
2. Complete Workstream 3's signed-fixture oracle, wrong-blob tests and external
  fakestore adaptation; run an unfaulted isolated baseline before faulting.
3. Confirm tenant fault routing, disk behavior and storage/termination support.
  Do not claim network, disk or crash coverage before the relevant fault is
  demonstrated at the SUT boundary.
4. Implement the shared ledger, trusted fixture path, bounded observation
  barrier and independent deadline before using Workstreams 4 and 5 as campaign
  evidence.
5. Execute Workstreams 4 and 5 against those shared mechanisms. After each
  implementation, update `existing-assertions.md`, affected property evidence
  and the active-test inventory with verified results.

For every outcome-optional safety assertion, report its constructed Reachable
witness separately. A clean second restart is a stability check, not proof that
the same do/undo task replayed; replay evidence must include the same task and
direction with a new attempt after a verified effect-before-checkpoint window.

Evaluation findings remain in `evaluation/`; their actionable recommendations
are consolidated here. Property pages remain the specifications for individual
invariants and are not separate execution plans.

Crash-generation and do/undo replay properties require an explicit confirmed
process-restart scenario or termination faults. Do not claim those properties
are covered by network, thread-pausing and disk I/O faults alone.
