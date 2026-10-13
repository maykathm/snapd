---
sut_path: /home/katie.may@canonical.com/source/snapd
commit: e88ec08852fbc8af019dc39e22097e5720aa6dfd
updated: 2026-10-13
external_references: []
---

# Implementability Evaluation

Scope answer (verbatim): "just this directory". Assigned lens: implementability.
Fresh review of the catalog, SUT analysis, topology, assertion placement,
existing inventory, property evidence and the controlling local source paths.
Findings concern proposed tests, not demonstrated SUT defects. No instrumentation,
fixture, host service or other research document was changed by this evaluation.

## Present Harness Versus Proposed Tests

The [catalog](../property-catalog.md) explicitly proposes eighteen properties.
The [inventory](../existing-assertions.md) records only the existing Hold check;
it is present in [Change.notifyStatusChange](../../../overlord/state/change.go#L451).
The current [Spread task](../../tests/hello-world/task.yaml#L6) installs and runs
hello-world. The [image builder](../../build-testing-image.sh#L84) extracts symbol
catalogs and installs the supplied snap, but does not supply the independent
ledger, stable snapshot RPC, pre-start recovery oracle or controlled replay
campaign described by the [topology](../deployment-topology.md).

The predicates and snapshot fields in [assertion placement](../assertion-placement.md)
are illustrative proposed test code, not callable APIs. Source validation and
unit-test evidence do not establish that these tests work in the current harness.
Local observational checks are feasible; the end-to-end checks need the protocols
below before their stated confidence can mean implementation readiness.

## Findings

### 1. Stable Snapshots Need More Than Admission Gating

**Scope:** catalog-wide prerequisite. **Affected slugs:** `active-links-match-current`,
`retained-revisions-have-resources`, `accepted-blob-digest`,
`rollback-preserves-unrelated-snaps`, `removal-is-scoped`,
`replay-preserves-semantic-effects`, `recovery-cohort-completes`.

**Evidence:** [StateEngine.Wait](../../../overlord/stateengine.go#L198) waits on
registered managers' current activities; it does not prevent later dispatch.
[TaskRunner.Wait](../../../overlord/state/taskrunner.go#L536) waits for tombs,
while [Ensure](../../../overlord/state/taskrunner.go#L383) can start handlers and
cleanup. [SnapManager.Ensure](../../../overlord/snapstate/snapmgr.go#L1647)
includes background work, including cache/download cleanup. Stopping only API
admissions does not stop these producers. A state lock cannot freeze filesystem
effects from a handler that already unlocked for external work.

**Concern:** the proposed barrier is correctly acknowledged but not designed.
Using Wait followed by reads leaves a scheduling window. Holding state while
waiting deadlocks completion paths that reacquire `r.mu` then state at
[handler completion](../../../overlord/state/taskrunner.go#L234) and
[cleanup completion](../../../overlord/state/taskrunner.go#L329).
[Stop](../../../overlord/state/taskrunner.go#L522) kills activities and changes
error/retry behavior; it is not a transparent substitute for a snapshot barrier.

**Action:** specify a test-only gate covering all affecting manager/runner
producers, including cleanup and any selected non-task filesystem writer. Close
the gate before draining; drain without holding state or completion-needed
locks; then collect state and filesystem projections in the SUT's mount namespace.
Release reliably after observations. Alternatively reject a sample if a complete
affecting-work epoch changes, including already-running effects, not merely
checkpoint writes. Name excluded background producers and fixture controls.

**Discriminating check:** pause an unlocked link/delete or cleanup operation,
request a snapshot, and try background dispatch during the read. The barrier
must neither certify the partial state nor deadlock, and must exclude new effects.
Do not require this barrier to complete before the independent progress deadline:
a wedged barrier must not hide a liveness failure.

### 2. Crash Generation Events Need Durable Ordering

**Scope:** property-specific. **Affected slugs:** `checkpoint-crash-generations`,
`checkpoint-readback-matches`, `checkpoint-restores-task-graph`.

**Evidence:** [Checkpoint](../../../overlord/backend.go#L33) receives exact bytes
and returns only an error. [Unlock](../../../overlord/state/state.go#L301)
retries the same bytes; there is no generation ID or independent attempt ledger.
[AtomicFile.commit](../../../osutil/io.go#L157) renames before directory sync;
an unsuccessful return can therefore leave the attempted generation published.
The [generation evidence](../properties/checkpoint-crash-generations.md)
proposes recording an attempt before writing and completion after success, but
does not specify durable recording or acknowledgement of those observations.

**Concern:** an asynchronous/log-only attempt event can be lost while its payload
is published, making a valid file fail the permitted-set oracle. Conversely,
losing the success event forces the oracle to permit old state even though the
writer actually returned successfully. An external ledger also has its own
crash window; recording success before actual writer success is unsound.

**Action:** persist baseline and exact candidate bytes or collision-resistant
identities outside the killed daemon. Durably acknowledge attempt registration
before permitting the write. Record completion only after writer success and
distinguish externally confirmed completion from actual-but-unobserved return.
The latter must remain uncertain, not be claimed as tested acknowledgement
durability. Define a controlled campaign with registered attempts and no
untracked startup/background writes; retries of identical bytes share identity.
Check independent disk bytes, not SDK event presence or a production counter.
Keep successful readback inside the locked backend boundary and compare its
captured argument, not a fresh serialization.

**Discriminating check:** terminate before attempt acknowledgement, after rename
but before success reporting, and after durable completion acknowledgement.
The permitted set must be respectively unchanged, old-or-attempted, and only
the last confirmed generation when no later attempt exists. Missing ledger
records must be reported as oracle incompleteness, not silently ignored.

### 3. Recovery Must Be Observed Before Startup Writes

**Scope:** property-specific. **Affected slugs:** `checkpoint-crash-generations`,
`checkpoint-restores-task-graph`, `task-scheduling-is-safe`,
`cleanup-follows-readiness`, `abort-wins-completion-race`.

**Evidence:** startup [loads state](../../../overlord/overlord.go#L353), then
immediately saves timings and Unlocks, before restart initialization and patches.
The [client task representation](../../../client/change.go#L58) exposes status
and progress but not the complete dependency graph, raw waited status, lanes,
clean flags, counter high-water marks or active runner tombs. The graph evidence
also notes that `State.Tasks()` omits unlinked tasks. Runtime backlinks and ready
channels cannot be inspected through a filesystem JSON read.

**Concern:** a post-start API checker cannot inspect the original recovered
generation or prove transient scheduling/cancellation/cleanup invariants. Calling
MarshalJSON on restored state and using the same deserializer for the expected
projection risks reproducing the same bug in both sides.

**Action:** read authoritative bytes while the daemon is confirmed stopped,
with socket/service activation unable to restart it. Add a proposed test-build
observation immediately after ReadState and before timing writes, initialization
or replay. Independently decode the persisted schema for expected graph fields;
compare complete maps and separately inspect runtime relationships. Internal
dispatch, cancellation and cleanup checks belong at their owning boundaries,
under the existing locks, not in a client poll. Do not allocate tasks or alter
statuses solely to inspect counters or force replay.

**Discriminating check:** distinguish two checkpoint generations and verify the
startup observer sees the loaded one before the first subsequent write. Include
an unlinked persisted task and a default-normalized waited status in checker
tests, with explicit same-version normalization rules.

### 4. An Admission Ledger Cannot Depend Only on Responses

**Scope:** catalog-wide recovery prerequisite. **Affected slugs:**
`recovery-cohort-completes`, `replay-preserves-semantic-effects`,
`rollback-preserves-unrelated-snaps`, `removal-is-scoped`,
`retained-revisions-have-resources`.

**Evidence:** [operation admission](../../../daemon/api_snaps.go#L214) creates
the change and records affected snap names before returning its asynchronous
change ID. The response is not an independent admission transaction. No ledger
or client-token reconciliation is present in the reviewed harness. The evidence
requires an independently admitted cohort and reconciliation before pruning.

**Concern:** a crash or connection failure after admission but before receiving
the ID leaves an unknown accepted operation. Ignoring it undercounts obligations;
blind retry can create another operation. Independent concurrent success also
makes a frozen pre-operation global snapshot invalid for unrelated resources.

**Action:** persist intent before submission and represent pending, rejected,
accepted-ID and ambiguous outcomes explicitly. Correlate accepted changes through
a proposed admission observation/token protocol, or constrain the campaign to
unambiguous single-in-flight operations with independently verified attribution.
Reconcile ambiguous intents and completions before pruning; never infer expected
results solely from terminal status or post-operation inventory. Record allowed
success/rollback results, retained revisions, ownership and concurrent unrelated
commits independently. Persistence must survive the faults applied to the checker
as well as those applied to snapd, or checker faults must be explicitly excluded.

**Discriminating check:** lose the response after change creation, restart, and
verify the operation is neither omitted nor blindly resubmitted. Also commit B
during A's undo and verify B against its latest admitted expected result.

### 5. Quiet Deadlines Need Independent Observations

**Scope:** property-specific. **Affected slugs:** `ensure-requests-progress`,
`recovery-cohort-completes`.

**Evidence:** [ensureBefore](../../../overlord/overlord.go#L468) coalesces timer
requests without request IDs. The proposed request/pass watermark in
[property evidence](../properties/ensure-requests-progress.md) is absent today.
[Settle](../../../overlord/overlord.go#L581) panics when used concurrently with
Loop and checks its timeout only outside Ensure/Wait calls. It can block past
that timeout in a manager or handler. A later retry remains legitimate work.

**Concern:** a checker using Settle inside the real daemon or obtaining all
observations through the wedged state/manager lock cannot make the terminal
assertion when it matters. Source alone cannot supply a meaningful quiet budget.

**Action:** keep deadlines and cohort records in an independent checker; publish
request acceptance, pass-start watermark and pass completion without adding a
reverse `ensureLock`/`mgrLock` dependency. Credit only requests preceding the
pass start, with incarnation-qualified IDs and explicit interrupted cohorts.
Calibrate due retries, dependency restoration and fault-free execution for chosen
fixtures. Check unresolved obligations at deadline even if snapshot collection
is blocked; report unavailable observations separately from resolved work.

**Discriminating check:** deliberately block a manager and a handler completion;
the checker must still emit a failed terminal obligation check. Requests arriving
during a pass must not receive completion credit from that pass.

### 6. Scenario Construction Is Not Yet Supplied

**Scope:** catalog-wide campaign prerequisite. **Affected slugs:**
`accepted-blob-digest`, `retained-revisions-have-resources`,
`rollback-preserves-unrelated-snaps`, `removal-is-scoped`,
`replay-preserves-semantic-effects`, `abort-wins-completion-race`,
`recovery-cohort-completes`.

**Evidence:** the present hello-world task has no second revision, unrelated
snap, sentinel/config ownership manifest, induced post-effect failure, abort,
or confirmed crash/restart command. The [topology](../deployment-topology.md)
proposes these roles and warns that nested Incus fault isolation and storage
preservation are unconfirmed. Pausing a process is not termination or undo.

**Action:** prepare two distinct signed ordinary-app revisions and an unrelated
fixture with expected digest, mount identity, retained set and controlled data.
Provide a safe, repeatable post-effect failure or accepted abort to reach undo;
store unavailability alone may only retry or fail before effects. Confirm do and
undo re-entry separately, preserve storage, and inspect mounts from the correct
namespace using mount/loop identity plus mounted fixture content. Keep parallel
instances/components as later campaigns, as proposed. Validate branch reachability
before requiring campaign-specific coverage; no manual handler re-invocation.

### 7. SDK Pinning Is Not Binary Compatibility Verification

**Scope:** catalog-wide. **Affected slugs:** all eighteen catalog entries.

**Evidence:** [go.mod](../../../go.mod#L41) pins v0.8.0 and the
[snap build](../../../build-aux/snap/snapcraft.yaml#L272) pins its tool-exec
version too. [Image staging](../../build-testing-image.sh#L86) verifies that
some symbol TSV exists, not that every intended assertion is in the executed
binary. Existing source demonstrates `Always(bool, string, map[string]any)`.
The repository's vendor tree does not contain the SDK implementation. The
placement document reports checking cached signatures, but that cache is outside
this evaluation's directory-only scope.

**Concern and action:** full v0.8.0 compatibility of proposed
`AlwaysOrUnreachable`, `Sometimes`, replay anchors, SetupComplete and reporting
cannot be independently certified from these local files. Compile proposed
calls against the exact pinned dependency in a later authorized build; check
catalog messages in both the executed SUT and checker, cgo/reporting linkage,
and a controlled failing report. Do not infer reporting from dependency presence
or a nonempty catalog directory. Gate expensive readback/hashing outside SDK
argument evaluation. No dependency change is justified by this review.

## Checks That Pass

- `dirty-unlock-checkpointed`: the proposed defer registered after `s.unlock`
  runs while locked. An explicitly normal-return flag excludes marshal panic,
  retry exhaustion and process termination. Retrying checkpoint errors must
  remain ordinary control flow, and the existing panic must not be suppressed.
  This is a control-flow guard, not independent durability proof.
- `checkpoint-readback-matches` and `sequence-write-matches-input`: exact captured
  writer input plus independent readback avoids comparing a later mutated state.
  Never assert perpetual sequence-file/SnapState equality.
- `ensure-pass-visits-managers`: the expected manager slots are stable under
  mgrLock; count actual entry and return, including aggregated errors. Do not
  populate counts from the expected list or equate visitation with useful work.
- `task-scheduling-is-safe`: the proposed status table matches fresh Do/Undo
  dependency gates and Doing/Undoing replay. Capture activity before tomb
  insertion and schedule before clearing it. Do not rerun stateful blocked
  predicates; record their actual decisions. Add independent callback activity
  accounting if claiming more than correctness of the existing tomb gate.
- `snap-current-in-sequence`, `accepted-blob-digest`,
  `replay-preserves-semantic-effects`: committed-entry scope, signed validation
  rather than size-only cache success, and ledger-qualified S1/S2 avoid the
  identified invalid premises. A consistently wrong S1/S2 must still fail.
- `abort-wins-completion-race` and `cleanup-follows-readiness`: runner branches
  expose feasible local observation sites. Preserve legal Hold and no-handler
  cleanup semantics. Replace the existing broad Hold assertion in a future
  implementation; do not duplicate it or use assertion outcomes to alter status.

## Assumptions And Uncertainty

This review validates source-level feasibility, not an operating campaign.
No SUT tests, builds, crashes, tenant queries or external documentation fetches
were performed. Property evidence was treated as leads, not execution proof.
The pinned SDK cache was not read outside the requested directory.

Fault availability, nested-container targeting, storage guarantees, independent
ledger persistence, barrier coverage and quiet budgets remain unverified.
The scope excludes power-loss durability, arbitrary hook/application effects,
boot/remodel and cross-version migration. The catalog's per-property "None"
questions do not remove these implementation prerequisites. Most properties
are plausible once these contracts are supplied; none of the findings alone
establishes a snapd correctness failure.