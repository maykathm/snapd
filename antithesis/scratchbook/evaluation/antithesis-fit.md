---
sut_path: /home/katie.may@canonical.com/source/snapd
commit: e88ec08852fbc8af019dc39e22097e5720aa6dfd
updated: 2026-10-13
external_references: []
---

# Antithesis Fit Evaluation

Scope answer (verbatim): "just this directory".
Fresh evaluation of the eighteen-property targeted portfolio, not discovery.
No properties, harness files or production instrumentation were changed.
Observation categories below describe this lens's concerns; synthesis owns
subsequent classification and disposition.

## Basis and Overall Assessment

Read `property-catalog.md`, `sut-analysis.md`, `deployment-topology.md`,
`existing-assertions.md` and `assertion-placement.md`. Examined the evidence
files for dirty unlock, manager visitation, checkpoint crash generations and
semantic replay, and the owning Unlock/Ensure code and nearby test inventory.
HEAD matches the supplied commit. Other property assessments use the supplied
catalog and analysis rather than a fresh subsystem discovery pass.

The strongest fit is real external effects interleaved with durable task state:
split links, deletion, concurrent unrelated operations, cancellation, retries,
and Doing/Undoing recovery. Deterministic tests remain useful but do not exhaust
these combined windows. A smaller part of the portfolio checks serialized
control flow or fixed-input serialization; keep those as cheap safeguards,
not primary search objectives. Integrity severity and marginal search value
are different measures: P0 does not by itself justify substantial run budget.

Assertion semantics are evaluated against the in-directory research guidance
and placement document. No external documentation or tenant was consulted.
This is a source/design assessment, not evidence of encounter rates, successful
reporting, calibrated deadlines or platform fault availability.

## Findings

### Search Budget: Serialized Control-Flow Checks

**Properties:** `dirty-unlock-checkpointed`, `ensure-pass-visits-managers`.
**Scope:** catalog-wide initial sequencing, with property-specific rationale.

The catalog says "Start with dirty unlock" and includes ensure visitation in
the first group. These are sensible instrumentation smoke checks, but relatively
weak standalone Antithesis objectives at this revision. `State.Unlock`
(`overlord/state/state.go:294`) holds the state lock and returns normally from
the dirty/backend path only after checkpoint success and clearing `modified`.
Crashes and retry exhaustion cannot encounter its normal-return predicate.
`properties/dirty-unlock-checkpointed.md` distinguishes this from independent
readback and cites `TestImplicitCheckpointRetry`,
`TestImplicitCheckpointPanicsAfterFailedRetries` and modified-only tests.

`StateEngine.Ensure` (`overlord/stateengine.go:167`) holds `mgrLock` across a
fixed manager loop and aggregates errors after the loop. Its proposed entry and
return counts primarily observe that loop. `TestEnsure` and `TestEnsureError`
(`overlord/stateengine_test.go:119`, `:145`) already cover complete visitation
and continuing after errors. A stalled manager never reaches the assertion;
pausing it does not turn this completion check into progress verification.

**Action:** retain cheap checks if useful for regression detection and reporting
smoke tests, with focused deterministic tests for their gates. Do not allocate
dedicated fault campaigns to them or treat passing them as persistence/progress
evidence. Move search effort to `checkpoint-crash-generations`,
`checkpoint-readback-matches`, `ensure-requests-progress` and replay outcomes.
Do not lower integrity severity solely because local control flow is simple.

### Search Budget: Fixed Inputs Versus History-Sensitive Oracles

**Properties:** `checkpoint-restores-task-graph`, `sequence-write-matches-input`,
`snap-current-in-sequence`, `accepted-blob-digest`.
**Scope:** property-specific campaign design.

The first two invariants compare a restored/written projection with captured
input. Fixed valid graph round trips and sequence-field normalization are
deterministic test territory. `sut-analysis.md` already records graph/counter
tests, and explicitly rejects perpetual sequence-file equality with SnapState.
The catalog's Current membership check is also a cheap structural predicate;
ordinary input membership alone does not need state-space exploration.

These properties gain Antithesis value when inputs arise from interrupted
progression, pruning, candidate commit/undo, and recovery, not from repeatedly
generating isolated fixed examples. Similarly, computing a digest is a unit
check, but checking an accepted signed blob after interrupted/resumed transfer
and cache reuse validates a history-sensitive content acceptance boundary.
The catalog explicitly names these histories and restricts digest checking to
known signed fixtures, so the latter is a good fit rather than redundant hashing.

**Action:** unit-test projection normalization and predicates first. Retain these
assertions as companion oracles in lifecycle/recovery/download campaigns;
require varied revisions, graphs and resume/cache histories rather than spending
search budget on repeated unchanged projections. Report the exercised history
in details. No priority reduction is warranted for accepted-content safety.

### Assertion Types: Optional Safety Needs Scenario Coverage

**Properties:** `checkpoint-crash-generations`,
`rollback-preserves-unrelated-snaps`, `replay-preserves-semantic-effects`,
`abort-wins-completion-race`, `cleanup-follows-readiness`.
**Scope:** catalog-wide optional-path campaign policy.

All five correctly use `AlwaysOrUnreachable`: a crash, rollback, cancellation
race or cleanup path need not occur in every general timeline, but every
eligible encounter must satisfy safety. A green optional invariant alone can
mean the path never occurred. The catalog already reserves mandatory Reachable
coverage for a dedicated campaign that constructs the outcome; semantic replay
explicitly supplies distinct do/undo outcome anchors.

**Action:** make that campaign policy an acceptance gate, not an inference from
the safety result. Dedicated checkpoint, rollback, cancellation and cleanup
campaigns should each name the relevant outcome witness, with safety evaluated
separately. For example, witnessing an abort request is not witnessing its race
with successful completion; entering cleanup is not witnessing the guarded
successful clean commit. Do not require these outcomes in unrelated templates,
replace their safety checks with Sometimes, or force SUT statuses to obtain
coverage. This is a handoff requirement, not a claim that the current catalog
incorrectly chose its optional assertion types.

### Replay Guidance: Outcomes and Dangerous Windows Are Complementary

**Properties:** `replay-preserves-semantic-effects`,
`rollback-preserves-unrelated-snaps`, `active-links-match-current`,
`removal-is-scoped`, `checkpoint-crash-generations`.
**Scope:** property-specific placement and recovery campaign search.

`properties/replay-preserves-semantic-effects.md` identifies the handler-before-
terminal-status window in `overlord/state/taskrunner.go:192`, `:281`, and the
special mutation/status commits in `overlord/snapstate/handlers.go:2185`,
`:2660`. It proposes direction, attempt and checkpoint-generation details and
distinct recovered do/undo Reachable anchors. `sut-analysis.md` also identifies
split current links and deletion before state commit. The checkpoint evidence
distinguishes file sync, rename and directory sync and allows a published but
unconfirmed attempted generation.

Recovered outcome anchors are valuable coverage and replay landmarks. They do
not alone identify the earlier narrow window that must be interrupted, nor does
one successful recovery establish that every interrupted obligation resolved.
The independent ledger and second stable recovery comparison are stronger
semantic oracles than invocation counts or equality with partial pre-crash state.

**Action:** preserve distinct do/undo outcome anchors and associate them with
observational window markers around external effects and durable completion.
Use fixed messages and put incarnation, task, direction, attempt and generation
in details. For semantic Sometimes guidance, use a meaningful witnessed state
such as consistent recovery following interruption, not `Sometimes(true)`.
Use Reachable for a pure window/outcome visit. Keep markers non-mutating and
cheap; they guide search/replay but neither prove durability nor replace the
stable safety and finite-cohort checks. Confirm actual encounter frequency in
an isolated pilot before claiming these anchors make rare windows accessible.

### Reliability Blockers: Faults, Quiet Oracles and Finite Progress

**Properties:** catalog-wide; especially crash/replay, settled resource checks,
`ensure-requests-progress` and `recovery-cohort-completes`.
**Scope:** catalog-wide. **Blocking reliable campaign recommendations** until
the relevant prerequisite is demonstrated, not blocking this source evaluation.

The catalog and topology explicitly leave termination/clock fault availability,
preserved storage, exclusion of affecting background work, quiet budgets and
actual binary/catalog reporting unresolved. These are material fit conditions:

- Crash/replay recommendations require real confirmed termination and the same
  preserved storage. Pauses alone do not re-enter Doing/Undoing. A process crash
  is not evidence of whole-machine power-loss durability.
- Settled link/resource/rollback/removal oracles require a barrier that excludes
  affecting handlers and background work. Stopping admissions or holding the
  state lock alone can turn legitimate partial effects into false failures.
- Finite-cohort liveness requires restored dependencies and a calibrated quiet
  deadline accounting for due retries. Sometimes recovery of one task is only
  an existential witness and can coexist with another permanently stuck task.
- Source-level assertion selection cannot establish that the actual SUT/checker
  binaries emit catalogs and report encounters. Existing hello-world execution
  is not a verified crash template or independent recovery oracle.

**Action:** keep high-fit recommendations conditional. Verify termination and
storage, barrier behavior, reporting and quiet deadlines in disposable runs
before declaring readiness or allocating sustained search budget. If crash
support cannot be demonstrated, run pause/interleaving campaigns only and mark
crash properties unexercised, not passed. Retain universal cohort deadline checks
alongside Sometimes guidance; track interruption/recovery witnesses separately
so an unvisited recovery scenario cannot masquerade as successful recovery.

### Existing Instrumentation: Hold Is Not Cancellation Failure

**Properties:** `abort-wins-completion-race`; recovery/rollback campaigns that
can legitimately abort pending work.
**Scope:** property-specific existing assertion premise.
**Blocking trustworthy cancellation findings** if left as the sole active
correctness instrumentation in the campaign.

`existing-assertions.md` inventories `Always(new != HoldStatus)` with message
`change never enters hold status` at `overlord/state/change.go:451`. It cites
explicit Hold and all-pending abort paths and their tests as legitimate behavior.
The catalog correctly invalidates the broad premise and proposes scoped
cancellation transitions instead. Fault exploration can therefore report an
expected Hold as a property failure before testing the intended cancellation
race contract. This is a known instrumentation mismatch, not a new snapd defect.

**Action:** in the later implementation pass, correct the existing premise rather
than duplicate it. Validate legitimate Hold cases and cancellation-race cases
deterministically, then use race exploration with the scoped invariant. Until
then, identify this message as an invalid oracle, not evidence of broken replay.

## Portfolio Passes

Every catalog slug was assessed for fit. Ratings concern search leverage, not
proof of correctness or implementation readiness.

| Property | Assessment |
| --- | --- |
| dirty-unlock-checkpointed | Lower leverage; locked normal-return control-flow safeguard. |
| checkpoint-readback-matches | Useful independent production-publication oracle; pair with varied real writes. |
| checkpoint-crash-generations | Strong partial-failure fit; pre-startup generation observation and crash prerequisites matter. |
| checkpoint-restores-task-graph | Companion recovery oracle; fixed round trips belong in unit tests. |
| accepted-blob-digest | Strong resume/cache/interruption fit with independently known signed content. |
| snap-current-in-sequence | Cheap structural companion at history-sensitive commits. |
| active-links-match-current | Strong split-link/undo fit when observed at a genuinely stable boundary. |
| retained-revisions-have-resources | Strong retained-resource/revert fit under partial setup, discard and rollback. |
| sequence-write-matches-input | Companion publication oracle; fixed projection encoding belongs in unit tests. |
| rollback-preserves-unrelated-snaps | Strong concurrency/partial-undo fit; preserve newer unrelated committed effects. |
| removal-is-scoped | Strong partial-delete/ownership fit; strengthen with supported concurrent survivor activity. |
| replay-preserves-semantic-effects | Strong do/undo crash fit; ledger plus repeated stable recovery avoids exactly-once assumptions. |
| ensure-pass-visits-managers | Lower leverage; serialized completed dispatch does not establish progress. |
| ensure-requests-progress | Strong timer/coalescing/interleaving fit; requires finite quiet deadline. |
| task-scheduling-is-safe | Strong dependency/retry/single-flight interleaving fit; replay gates remain status-specific. |
| abort-wins-completion-race | Strong cancellation/completion race fit; Hold can be legitimate. |
| cleanup-follows-readiness | Strong undo/retry/restart ordering fit; ready and clean are distinct. |
| recovery-cohort-completes | Strong recovery/starvation fit; ledger-wide deadline prevents existential masking. |

Assertion-type passes: mandatory normal-path safety uses Always; optional
recovery/error-path safety uses AlwaysOrUnreachable; do/undo outcome coverage
uses distinct Reachable messages; both progress properties retain universal
finite-cohort deadline predicates with separate Sometimes guidance. No catalog
entry relies on `Sometimes(true)` or a single witness as universal liveness.
There is no source evidence here that a Sometimes goal inherently requires
astronomically unlikely timing: deliberate supported interruption is proposed,
but actual triggerability remains unmeasured.

Priority passes: the P0 lifecycle/rollback/removal/replay properties recognize
unhappy-path integrity risk despite happy-path and mocked backend tests. Their
fault value is not understated. Ordinary-app scope, independent signed fixtures,
one local authoritative writer and real systemd/mount integration are consistent
with the stated target; replicated-consensus goals would not fit this topology.

## Assumptions and Uncertainties

- In-directory SDK descriptions are accepted for this evaluation; tenant/runtime
  semantics and pinned-build reporting were not independently verified.
- Source and existing tests support placement and lower-leverage assessments;
  no tests, campaigns or timing measurements were run in this document-only pass.
- The supplied catalog's per-property "None" open questions do not resolve its
  explicit catalog-wide harness prerequisites. Those prerequisites block reliable
  readiness and budget estimates for affected campaigns, as listed above.
- The topology postpones components and parallel instances. Do not credit their
  concurrency coverage to the initial ordinary-app fixture campaign; extend
  ownership/resource contracts before enabling them.
- Anchor usefulness is a reasoned placement recommendation, not a measured
  reduction in search cost. Reporting/coverage and pilot results are needed to
  compare encounter rates or set run durations.

## Verification

Required post-edit check: `./mdlint.py antithesis/scratchbook/evaluation/antithesis-fit.md`.
Only this evaluation artifact is in the authorized write scope.