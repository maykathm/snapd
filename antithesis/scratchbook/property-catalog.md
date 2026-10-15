---
sut_path: /home/katie.may@canonical.com/source/snapd
commit: 91b61e2873e9621b6300906b31ababe8861ca248
updated: 2026-10-15
external_references: []
---

# Targeted Property Catalog

Scope answer (verbatim): "just this directory". Nineteen cataloged properties;
dirty-Unlock control flow, cancellation safety and Current/Sequence membership
now have source instrumentation and tests, but no dedicated workload or campaign
validation. The other properties remain proposed.
P0 means integrity/recovery-critical,
P1 supporting progress or consistency. Confidence is high for named code
boundaries; the harness predicates/barrier still need implementation and testing.
Evidence is in `properties/{slug}.md`. See `assertion-placement.md` for sketches.

Start with dirty unlock, independent checkpoint readback, active links after
stable successful operations, ensure visitation, and replay-safe semantic effects.
Then add scheduling, rollback isolation and cohort progress. The invalid Hold
instrumentation has been replaced with scoped cancellation checks; see
`existing-assertions.md`.

## Persistence and Content Integrity

These properties distinguish correct persistence control flow from independent
validation of stored bytes and accepted content. Discovery lenses: data integrity
and failure recovery.

### dirty-unlock-checkpointed

| Field | Specification |
| --- | --- |
| Priority / Type | P0 / Safety |
| Property | A normally returning dirty Unlock with a backend checkpointed its payload before releasing the mutex. |
| Invariant | `Always(checkpointSucceeded && !modified)` on eligible normal returns, while locked; every encounter must satisfy it. |
| Antithesis Angle | Pauses and checkpoint retries between mutation, acknowledgment and unlock. |
| Why It Matters | Avoid losing durable changes and undo metadata. |

**Implementation:** The source guard and focused tests are implemented. Local
SDK checks verified success/retry encounters and clean/nil-backend/panic-exit
gating; the full state suite passed under the race detector. Actual harness
cataloging/reporting remains unverified. This is a control-flow safeguard, not
independent evidence of correct file contents or crash durability.

**Open Questions:** None.

### checkpoint-readback-matches

| Field | Specification |
| --- | --- |
| Priority / Type | P0 / Safety |
| Property | A successful production checkpoint publishes exactly the supplied payload. |
| Invariant | `Always(readErr == nil && bytes.Equal(disk, capturedPayload))` before another writer; independent readback checks safety rather than trusting acknowledgment. |
| Antithesis Angle | Publication timing under pauses and repeated writes. |
| Why It Matters | Detect a successful return with wrong or missing persisted state. |

**Open Questions:** None.

### checkpoint-crash-generations

| Field | Specification |
| --- | --- |
| Priority / Type | P0 / Safety |
| Property | An interrupted checkpoint leaves a permitted complete recoverable generation. |
| Invariant | `AlwaysOrUnreachable(validJSON && permittedGeneration)` before startup writes, permitting old or attempted-new for unacknowledged writes but only new after confirmed durable completion; crash path is optional. |
| Antithesis Angle | Termination across write, file sync, rename and directory sync; requires confirmed termination and preserved storage. |
| Why It Matters | Prevent torn checkpoints; process-crash evidence is not proof of power-loss durability. |

**Open Questions:** None.

### checkpoint-restores-task-graph

| Field | Specification |
| --- | --- |
| Priority / Type | P0 / Safety |
| Property | Loading a valid checkpoint preserves the persisted task/change graph and identifier history. |
| Invariant | `Always(restoredProjection == normalizedIndependentDecodedProjection)` before replay; normalize default/absent waited-status to Done even for same-version tasks. Ownership, edges, other statuses, lanes, clean flags and counters must agree. |
| Antithesis Angle | Restart around concurrent task progression and pruning. |
| Why It Matters | Avoid misordered work, wrong rollback and reused identifiers. |

**Open Questions:** None.

### accepted-blob-digest

| Field | Specification |
| --- | --- |
| Priority / Type | P0 / Safety |
| Property | Successfully accepted signed fixture blobs match independently known digest and size. |
| Invariant | `Always(actualSize == fixtureSize && actualSHA3_384 == fixtureDigest)` at accepted download/cache outcomes; signed-fixture safety is universal. |
| Antithesis Angle | Interrupted/resumed downloads, cache reuse and restart. |
| Why It Matters | Avoid installing the wrong or partial content; unsigned local snaps are outside this predicate. |

**Open Questions:** None.

## Snap Lifecycle and Replay

Observe independent stable projections, not global instantaneous state/disk
equality. Initial scope is controlled ordinary application snaps. Discovery
lenses: data integrity, lifecycle transitions, concurrency and idempotency.

### snap-current-in-sequence

| Field | Specification |
| --- | --- |
| Priority / Type | P0 / Safety |
| Property | Committed installed SnapState has a Current represented in its nonempty Sequence. |
| Invariant | `Always(currentInSequence)` for committed installed entries; absent snaps have no entry, Current need not be greatest. |
| Antithesis Angle | Interruptions across candidate preparation, state commit and undo. |
| Why It Matters | Ensure subsequent lifecycle/revert operations refer to a real retained revision. |

**Implementation:** Partial. `snapstate.Set` checks nonempty explicitly typed app
entries outside try-mode at the locked write boundary. Disabled apps are eligible;
Current need not be newest, and local revisions are supported. SDK-local tests
check successful/failed encounters and excluded cases without changing persisted
state or deletion behavior. Independent expected-revision/recovered-state checks,
stable resource comparisons and actual harness validation remain deferred.

**Open Questions:** None.

### active-links-match-current

| Field | Specification |
| --- | --- |
| Priority / Type | P0 / Safety |
| Property | Settled successful ordinary-app activation selects committed Current in both system links. |
| Invariant | `Always(mountCurrent == Current && dataCurrent == Current)` for stable active results; completed disable has a separate absent-link predicate. |
| Antithesis Angle | Split current-link updates, refresh and undo interruption. |
| Why It Matters | Prevent running the wrong code or selecting the wrong data; Active does not mean all services are running. |

**Open Questions:** None.

### retained-revisions-have-resources

| Field | Specification |
| --- | --- |
| Priority / Type | P0 / Safety |
| Property | Ledger-retained revisions retain their expected resources after stable successful lifecycle operations. |
| Invariant | `Always(expectedBlobsMountsMetadataAndDataPresent)` using actual mount identity and fixture expectations, not directory existence alone. |
| Antithesis Angle | Setup, non-last discard and rollback overlap. |
| Why It Matters | Preserve revertability and revision data. Components require separate reference expectations. |

**Open Questions:** None.

### settled-app-launches

| Field | Specification |
| --- | --- |
| Priority / Type | P1 / Safety |
| Property | Stable successful ordinary fixture activation allows real CLI and wrapper execution of the expected revision. |
| Invariant | `Always(exitSuccess && outputMatchesIndependentRevisionAndDataToken)` in a dedicated successful-activation campaign; do not catalog this as mandatory in campaigns that never activate a snap. |
| Antithesis Angle | Refresh/replay across wrapper generation, security setup and run-inhibition removal. |
| Why It Matters | Matching links alone cannot establish launchability; controlled apps avoid service-running assumptions and external network dependencies. |

**Open Questions:**

- Coordinate the barrier with CLI security regeneration. (partial: launch gates identified; safe barrier not implemented)
- Choose the fixture/base, user-data baseline and calibrated execution budget. (partial: hello-world exists; independent two-revision/data oracle does not)

### sequence-write-matches-input

| Field | Specification |
| --- | --- |
| Priority / Type | P1 / Safety |
| Property | A successful sequence-file write records its captured input projection. |
| Invariant | `Always(readback == writerInputProjection)` at write success; normalize documented omitted/default fields. |
| Antithesis Angle | Atomic replacement and crash/replay around link. |
| Why It Matters | Keep failover-helper metadata valid; perpetual equality to SnapState is explicitly not asserted. |

**Open Questions:** None.

### rollback-preserves-unrelated-snaps

| Field | Specification |
| --- | --- |
| Priority / Type | P0 / Safety |
| Property | Completed scoped refresh rollback restores the surviving old target and preserves unrelated committed state. |
| Invariant | `AlwaysOrUnreachable(targetRestored && unrelatedLedgerEffectsPreserved)` after optional rollback; include concurrently committed unrelated operations, not a frozen pre-operation global snapshot. |
| Antithesis Angle | Crash in undo, partial candidate link and concurrent unrelated work. |
| Why It Matters | Avoid incorrect revision restoration or collateral state/data loss. |

**Open Questions:** None.

### removal-is-scoped

| Field | Specification |
| --- | --- |
| Priority / Type | P0 / Safety |
| Property | Successful removal deletes only operation-owned resources; terminal failures also preserve unrelated surviving resources. |
| Invariant | Distinct `Always` success and optional `AlwaysOrUnreachable` failure messages check scoped deletion and survivor preservation against ownership expectations. Failure need not restore deleted target data. Choose purge initially; saved snapshot archives are separately owned. |
| Antithesis Angle | Partial delete before state commit and concurrent instance activity. |
| Why It Matters | Prevent collateral data loss and stale final installation resources. |

**Open Questions:** None.

### replay-preserves-semantic-effects

| Field | Specification |
| --- | --- |
| Priority / Type | P0 / Safety |
| Property | Supported do/undo replay produces the expected stable semantic result without duplicated or lost effects. |
| Invariant | `AlwaysOrUnreachable(recoveredMatchesLedger && repeatedAttemptPreservesEffects)` on optional recovery; prove the same task/direction actually replayed. A clean second restart is only an additional stability check, not proof of replay idempotence. |
| Antithesis Angle | Termination after external effects but before durable completion, then repeated recovery. |
| Why It Matters | Test the claimed task idempotence contract where it matters. Separate Reachable messages mark do-replay and undo-replay outcomes as explicit coverage obligations in a recovery campaign. |

**Open Questions:** None.

## Scheduling, Cancellation and Progress

These properties prevent safety checks at completed boundaries from hiding
starvation or cancellation errors. Discovery lenses: concurrency, liveness,
lifecycle and cross-cutting recovery.

### ensure-pass-visits-managers

| Field | Specification |
| --- | --- |
| Priority / Type | P1 / Safety |
| Property | Every admitted normally completed Ensure pass visits every registered manager slot once, even if managers return errors. |
| Invariant | `Always(allEnteredAndReturnedExactlyOnce)` under mgrLock before normal success or aggregated-error return; rejected passes excluded. |
| Antithesis Angle | Paused dispatch and errors in earlier managers. |
| Why It Matters | Detect skipped top-level managers; guarded internal helpers need different predicates. |

**Open Questions:** None.

### ensure-requests-progress

| Field | Specification |
| --- | --- |
| Priority / Type | P1 / Liveness |
| Property | Every eligible ensure request in a finite quiet cohort is covered by a later completed pass. |
| Invariant | `Always(allCohortRequestsCovered)` at the calibrated quiet-phase deadline; `Sometimes(laterPassCompleted && allManagersVisited)` is separate progress guidance, not universal proof. |
| Antithesis Angle | Timer reset/expiry races, manager stalls and CPU pauses. |
| Why It Matters | Ensure requested work is revisited; coalescing is legal. |

**Open Questions:** None.

### task-scheduling-is-safe

| Field | Specification |
| --- | --- |
| Priority / Type | P0 / Safety |
| Property | Dispatch obeys status-specific eligibility and per-runner single-flight rules. |
| Invariant | `Always(noExistingInvocation && correctStatusSpecificGates)` while locked; Do/Undo dependency rules are not imposed blindly on Doing/Undoing replay. |
| Antithesis Angle | Concurrent Ensure, delayed retries, dependency completion and restart. |
| Why It Matters | Prevent duplicate/premature external effects; lanes are not serialization. |

**Open Questions:** None.

### abort-wins-completion-race

| Field | Specification |
| --- | --- |
| Priority / Type | P0 / Safety |
| Property | Concurrent successful completion does not erase an accepted task cancellation. |
| Invariant | `AlwaysOrUnreachable(correctCancellationTransition)` on optional races, including Abort-to-Done/Wait suppression and scoped lane propagation; Hold is legal. |
| Antithesis Angle | Abort against handler return or explicit terminal commit. |
| Why It Matters | Preserve cancellation and undo obligations without rejecting legitimate Hold outcomes. |

**Implementation:** Partial. Three optional SUT-side safety assertions and a
fourteen-case deterministic completion matrix are implemented. The full state
suite passed under the race detector, and all three assertions emitted successful
local SDK encounters. Dedicated cancellation workload, outcome coverage anchors,
actual harness cataloging/reporting and campaign validation remain deferred.

**Open Questions:** None.

### cleanup-follows-readiness

| Field | Specification |
| --- | --- |
| Priority / Type | P1 / Safety |
| Property | Cleanup and clean commits occur only for ready changes and successful eligible cleanup. |
| Invariant | `AlwaysOrUnreachable(changeReady && correctCleanupOwnership)` at optional cleanup admission/runner commit; the runner must not newly mark clean because cleanup failed. Independently authorized callback marking is a separate actor. |
| Antithesis Angle | Blocked undo, retrying cleanup and restart. |
| Why It Matters | Avoid premature loss of recovery metadata; readiness and cleanliness differ. |

**Open Questions:** None.

### recovery-cohort-completes

| Field | Specification |
| --- | --- |
| Priority / Type | P0 / Liveness |
| Property | Every admitted reversible ordinary-app install/refresh/enable/disable operation resolves to predeclared success or completed rollback after supported interruption and quiet recovery. |
| Invariant | `Always(allLedgerObligationsResolved && expectedResourcesMatch)` at the calibrated terminal deadline; separately `Sometimes(interruptedWorkRecovered && consistent)` witnesses meaningful recovery. |
| Antithesis Angle | Do/undo crashes, retry completion and cleanup delays; require controlled restored dependencies. |
| Why It Matters | One recovered task must not mask another stuck task. Reconcile the ledger before change pruning. |

Destructive removal failures are excluded from this reversible cohort and checked
under `removal-is-scoped`; never demand recreation of already-deleted target data.

**Open Questions:** None.

## Invalidated Premises

- "State and disk always match": invalid across legitimate partial lifecycle work.
- "Sequence file always equals SnapState": invalid for documented non-last
  discard and component update paths.
- "Change never enters Hold": invalid for supported explicit Hold/abort paths.
- "Every task runs exactly once": invalid for Doing/Undoing recovery.
- "Settle returning nil proves all changes ready": not supported by its contract.

These premises are replaced by the scoped properties above, not active catalog IDs.

## Assumptions

All messages must be fixed and specific. IDs/generations belong in details.
Optional paths use AlwaysOrUnreachable; use mandatory Reachable coverage only in
the dedicated campaign that constructs that outcome. No assertion should mutate
state or repair the condition it is checking. Expensive disk oracles are gated.

The admission ledger records intent before submission and reconciles requests
whose response is lost against durable changes/resource identities. Do not
silently omit accepted work, retry mutating requests blindly, or decide after a
failure that any terminal result is acceptable. Predeclare permitted outcomes
for each fixture scenario. Protect fixture manifests and ledger from SUT writes;
validate oracles against deliberately wrong synthetic snapshots.

Run progress deadlines outside SUT locks and outside the stable-snapshot barrier.
A blocked barrier is a failed/unfinished obligation, not a reason to skip the
terminal check. Full checkpoint crash classification requires externally durable
attempt/completion observations; an unobserved acknowledgment is ambiguous and
must not be misclassified as known durable completion.

Dedicated campaigns need distinct Reachable outcome messages for do replay,
undo replay, rollback restoration, accepted cancellation, scoped removal and
resumed verified download. Keep these campaign coverage obligations separate
from optional safety messages; no global message reused across callsites.

## Open Questions

- Confirm tenant termination/clock fault availability and preserved storage.
- Implement a barrier excluding affecting background work, not merely API input.
- Calibrate quiet-phase budget and due retries for selected fixture cohorts.
- Confirm binary catalogs/cgo reporting. Security, full Core/remodel, hook effects,
  migration and broad version-compatibility properties remain outside this pass.