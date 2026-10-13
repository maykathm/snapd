---
sut_path: /home/katie.may@canonical.com/source/snapd
commit: e88ec08852fbc8af019dc39e22097e5720aa6dfd
updated: 2026-10-13
external_references: []
---

# Wildcard Evaluation

Scope answer (verbatim): "just this directory". Fresh evaluation of the
current targeted catalog, SUT analysis, topology, assertion placement and
existing assertion inventory, with selected property evidence and local source.
No SUT changes, external research or spawned agents. Findings are not
categorized; synthesis belongs to the orchestrator. These are weaknesses in
the proposed evaluation contract, not confirmed snapd defects.

Other lenses supplied: Antithesis Fit checks sweet spot/types; Coverage Balance
compares the portfolio to targeted risks; Implementability checks observable,
feasible predicates. This pass questions how a seemingly feasible recovery
check could certify the wrong experiment or result.

## Findings

### 1. Admission And Expected Outcome Need Independent Contracts

**Properties:** catalog-wide, especially `recovery-cohort-completes`,
`replay-preserves-semantic-effects`, `rollback-preserves-unrelated-snaps` and
`retained-revisions-have-resources`.

**Scope:** catalog-wide.

**Concern:** an independent ledger is necessary but its admission and outcome
rules are unspecified. An API timeout is not evidence that no operation exists.
Conversely, allowing whatever terminal success/rollback snapd reports to select
the expected result can certify unnecessary rollback as correct recovery. A
healthy, supported interruption campaign needs an explicit allowed-outcome set;
consistency alone does not establish the requested operation was delivered.

**Evidence:** [postSnap](../../../daemon/api_snaps.go#L170) locks state,
creates the change at [the admission boundary](../../../daemon/api_snaps.go#L214),
requests ensure work, and returns an asynchronous response at
[the response boundary](../../../daemon/api_snaps.go#L235). Deferred Unlock runs
before the caller receives that response, so response loss can follow change
creation/persistence. The cohort evidence asks to check "every admitted ID";
the replay evidence says to "independently classify" success or rollback but
does not specify recovery of an unknown change ID or which failures authorize
rollback. The retained-resource oracle relies on completed-operation history.

**Suggested action:** ledger intent before sending; distinguish acknowledged,
definitely rejected and outcome-unknown requests. For the first campaign,
serialize outstanding requests per full instance and reconcile unknown requests
with change history before retry/pruning. Do not claim API idempotency or invent
a supported request token. Define allowed results before faulting: supported
restart with restored dependencies versus an intentionally failed refresh are
different experiments. Keep unexpected errors, cancellations and disappearing
changes visible rather than reclassifying them as expected rollback.

**Discriminating check:** lose the response after change creation, then recover.
The ledger must account for that operation without blindly resubmitting it.
Separately feed a terminal rollback to a success-required fixture case; the
oracle must reject it despite internally consistent old resources.

### 2. Independent Does Not Automatically Mean Trusted

**Properties:** catalog-wide resource/ledger checks, especially
`accepted-blob-digest` and `replay-preserves-semantic-effects`.

**Scope:** catalog-wide.

**Concern:** topology separates the checker logically, but does not establish
its trust and fault boundary. A manifest refreshed from the faulted store or
post-operation SUT can agree with the same wrong bytes. Lost checker obligations
can turn a universal finite-cohort check into an empty-cohort success. Read-only
access to SUT paths does not make the checker ledger durable or independent of
those paths. This is oracle validity, not merely access to observations.

**Evidence:** [topology](../deployment-topology.md) proposes either a checker
container or an external runner, plus shared paths/socket or checker RPC; its
fault/storage questions remain open. [Blob evidence](../properties/accepted-blob-digest.md)
explicitly assumes fixture authority and checker are trusted and fixes identity
before admission. [Replay evidence](../properties/replay-preserves-semantic-effects.md)
already rejects S1/S2 equality alone and requires both to match the ledger.
These are sound intended safeguards, not an implemented trust protocol.

**Suggested action:** freeze fixture ID/revision/digest/size and expected tokens
before the campaign, separately from writable store/SUT state. Declare checker
restart/fault policy and preserve outstanding intents across permitted restarts.
Treat missing ledger, manifest, RPC response or eligible resource observations
as failed checks or explicit invalid experiments, never as no eligible work.
Record a nonempty cohort witness. Do not duplicate SUT decoding/selection logic
as the only expected-result computation.

**Discriminating check:** checker self-tests must reject a stable wrong revision
in both S1 and S2, a matching-size wrong blob, and a missing ledger entry. These
are proposed harness tests, not additional SUT mutation properties.

### 3. A Second Restart Is Not A Second Replay

**Properties:** `replay-preserves-semantic-effects`, `recovery-cohort-completes`.

**Scope:** property-specific.

**Concern:** recovering once and restarting the settled system again tests
post-recovery stability, not repetition of the interrupted do/undo effect. The
catalog properly avoids exactly-once invocation and arbitrary double-handler
calls, but the phrase "second recovery" can overstate its idempotence evidence.
A recovery that is itself interrupted after its next partial effect is the
more demanding case.

**Evidence:** [runner dispatch](../../../overlord/state/taskrunner.go#L192)
re-enters Doing/Undoing; [completion](../../../overlord/state/taskrunner.go#L281)
transitions to Done/Undone. A clean second restart need not re-enter either
handler. [Link completion](../../../overlord/snapstate/handlers.go#L2185)
explicitly prevents committed mutation from being rerun. Replay evidence
requests direction/attempt observations and distinct replay anchors, but its
S1/S2 experiment begins only after an eligible stable outcome.

**Suggested action:** retain S1/S2 as a stability check with that name. In a
dedicated replay campaign require the same task ID and direction to have a new
handler attempt from persisted Doing/Undoing, with a verified effect-before-
checkpoint interruption. Also interrupt recovery itself and recover again;
check the original ledger obligations, not a new baseline made from partial
recovery. No manual handler invocation or status rewriting is needed.

**Discriminating check:** a clean restart with no resumed task must not satisfy
the do/undo replay witness. An interrupted recovery must preserve the same
operation obligations across its third attempt. Source establishes the
distinction; actual termination windows remain untested prerequisites.

### 4. Quiescence Must Not Be A Precondition For Judging Progress

**Properties:** catalog-wide stable checks, especially
`recovery-cohort-completes` and `ensure-requests-progress`.

**Scope:** catalog-wide.

**Concern:** the proposed barrier drains/prevents affecting work, while resource
checks run only once stable. If entering that barrier waits for the very stuck
handler the cohort should detect, the deadline assertion may never run. If the
barrier prevents retries or manager work needed to recover, it manufactures
failure instead. A deadline in the same blocked execution context cannot
resolve this circularity. Separately, preemptively eliminating all background
activity narrows the experiment to isolated recovery, not interference recovery.

**Evidence:** [topology](../deployment-topology.md) requires a daemon-side drain
and admission barrier; [placement](../assertion-placement.md) says it must also
exclude background affecting work. [Cohort evidence](../properties/recovery-cohort-completes.md)
requires retries to run and all obligations to resolve by a terminal deadline.
Replay/retention evidence likewise gates snapshots on drained background work.
The catalog already recognizes that Settle nil is insufficient, but does not
state whether barrier failure itself is judged independently.

**Suggested action:** separate closing workload admission, allowing recovery
execution, and acquiring a bounded read-only snapshot barrier. Run the cohort
deadline from a checker context that does not wait indefinitely for the barrier;
a missing stable observation by that deadline cannot silently skip evaluation.
Prevent new background admissions only at observation, and document any
campaign-wide suppression as a limitation. Exercise a selected unrelated
ordinary-app operation during recovery before freezing observations; do not
expand this into a broad background-feature audit.

**Discriminating check:** simulate a never-returning affecting handler. The
deadline must still report the unresolved obligation/barrier timeout. With a
due retry, requesting observation must not stop the retry needed to complete.

### 5. Ordinary-App Removal Includes A Snapshot Path

**Properties:** `removal-is-scoped`, `recovery-cohort-completes`,
`replay-preserves-semantic-effects`.

**Scope:** property-specific, with a campaign-scope consequence.

**Concern:** ordinary-app scope does not by itself exclude special lifecycle
work. Default full removal can create an automatic snapshot before destructive
deletion. Installed-resource disappearance and preservation of unrelated B can
both pass while the intended saved data is wrong. Conversely, the cohort's
success-or-rollback wording must not promise restoration after destructive
removal; the removal evidence correctly rejects that promise.

**Evidence:** [removeTasks](../../../overlord/snapstate/snapstate.go#L3340)
calls AutomaticSnapshot for a full TypeApp removal unless Purge, with optional
size estimation, before unlink and revision deletion. Removal evidence says
archives need not disappear and failed target deletion is not rollback, but
does not verify a successfully created archive against the fixture sentinel.
[Existing fixture acquisition](../../download-snaps.sh#L8) also stages core and
core24 beside hello-world: existing scripts are not proof that each new app
campaign avoids excluded base/boot lifecycle work.

**Suggested action:** explicitly choose Purge for the initial no-snapshot
removal campaign and record that restriction. Alternatively, retain default
removal and add a narrowly scoped snapshot/content expectation for controlled
tokens, with an interruption between snapshot completion and deletion. Define
failed destructive removal as partial target loss with unrelated preservation,
not generic target rollback. Validate provisioned bases and fixture task kinds
before claiming the ordinary-app campaign excludes boot/self-refresh work;
unexpected special tasks invalidate that campaign claim rather than being
silently filtered from its ledger.

**Discriminating check:** compare full-removal task plans with and without
Purge. For a default-removal fixture, a wrong/missing expected saved sentinel
must fail even if all installed resources are correctly absent. This is a
bounded app/snapshot interaction, not a full snapshot, Core or security audit.

## Passes

- Evidence already rejects stable-but-wrong S1/S2 equality alone, derives
  retained expectations from the ledger before consulting SUT state, and counts
  missing eligible resources as failures. Do not report those as absent ideas.
- Disabled apps, non-last deletion, shared ownership and destructive-removal
  limits are already distinguished. Parallel instances/components are openly
  deferred rather than accidentally advertised as covered.
- The sole existing Hold assertion is inventoried and its premise challenged;
  no duplicate instrumentation is proposed by this evaluation.

## Assumptions And Uncertainties

No harness checker/barrier implementation or run was available to verify the
proposed protocol. Findings identify contracts to settle and checks to add, not
observed oracle failures. Fault availability, storage persistence and deadline
calibration remain the documented deployment questions. The other lenses'
actual findings were not read; only their supplied remit was used.

Full Ubuntu Core/remodel, security, broad version compatibility, uncontrolled
hook/application effects and migration remain explicitly outside scope. Only
local targeted evidence was consulted. No catalog, evidence, topology, SUT or
other evaluation file is changed by this pass.