---
sut_path: /home/katie.may@canonical.com/source/snapd
commit: e88ec08852fbc8af019dc39e22097e5720aa6dfd
updated: 2026-10-13
external_references: []
---

# Coverage Balance Evaluation

Scope answer (verbatim): "just this directory". Fresh evaluation of the current
18-property portfolio, not a whole-repository audit. This report evaluates the
targeted ordinary-application scope: persistence, state/resource consistency,
ensure scheduling, cancellation and real task replay. Only this report is
written; no catalog, SUT, instrumentation or harness changes are made.

## Inputs And Method

Read [property-catalog.md](../property-catalog.md),
[sut-analysis.md](../sut-analysis.md),
[deployment-topology.md](../deployment-topology.md),
[existing-assertions.md](../existing-assertions.md) and
[assertion-placement.md](../assertion-placement.md), following the repository's
[property-evaluation reference](../../../.agents/skills/antithesis-research/references/property-evaluation.md).
Followed the evidence for accepted blobs, retained resources, replay, recovery,
rollback, removal, active links and cancellation. Checked nearby backend link
and data-copy code and the existing hello-world task where useful. Sources are
local working-tree artifacts associated with the supplied SHA; this is not a
claim that every research artifact is committed at that SHA.

The discriminating portfolio question is whether an admitted operation can
satisfy all eligible resource/control predicates while a meaningful targeted
failure outcome or execution path remains unchecked. In particular, a safety
check after successful completion cannot certify an outcome it never observes.
Findings below distinguish missing portfolio obligations from details already
present in the deeper evidence. No finding alleges a confirmed snapd defect.

## Portfolio Map

There are 16 safety properties and two liveness properties; 14 are P0 and four
are P1. The assertion spelling does not determine the property type: both
liveness properties use a universal finite-cohort deadline check plus a separate
Sometimes witness. There is no standalone reachability property, but replay has
explicit do/undo Reachable obligations and several other evidence files suggest
optional outcome anchors. Counts alone are not evidence of imbalance.

| Targeted risk or analysis section | Corresponding property slugs | Assessment |
| --- | --- | --- |
| Persistence control flow, independent bytes, interrupted publication | dirty-unlock-checkpointed; checkpoint-readback-matches; checkpoint-crash-generations | Distinct contracts, not three interchangeable persistence checks. |
| Restored ownership, dependencies and identifier history | checkpoint-restores-task-graph | Complements correct bytes with restored graph semantics. |
| Store content accepted after resume/cache reuse | accepted-blob-digest | Safety present; scenario coverage is not yet mandatory. |
| Current/Sequence and installed projections | snap-current-in-sequence; active-links-match-current; retained-revisions-have-resources; sequence-write-matches-input | Covers active and retained revisions without asserting perpetual state/disk equality. |
| External effects before durable status, undo and unrelated operations | rollback-preserves-unrelated-snaps; removal-is-scoped; replay-preserves-semantic-effects | Strong completed-outcome coverage; failed destructive removal needs an explicit survivor contract. |
| Manager visitation versus useful progress | ensure-pass-visits-managers; ensure-requests-progress | Separates normally completed dispatch from passes that never return. |
| Runner eligibility, single-flight and cancellation races | task-scheduling-is-safe; abort-wins-completion-race | Safety present; uncommon race outcomes need coverage obligations. |
| Readiness, cleanup and whole-cohort recovery | cleanup-follows-readiness; recovery-cohort-completes | Complements eligible-boundary safety with finite-cohort liveness. |
| Backend wrappers, run inhibition and real systemd | active-links-match-current; replay-preserves-semantic-effects; recovery-cohort-completes | Resource identities partly covered; actual application launch is not an explicit postcondition. |

### Topology Distribution

- **snapd-system:** Most local assertions correctly belong to the single state
  writer, runner and backend. Real mounts, systemd and revision data remain
  together; container count should not dictate equal property counts.
- **fakestore:** `accepted-blob-digest` covers authorized content, while
  `recovery-cohort-completes` requires restored connectivity. Cross-boundary
  download/validation/recovery scenarios need observable coverage, not a new
  property about fakestore's own correctness.
- **workload-oracle:** Independent ledger, fixture identity, data sentinels and
  stable resource observations support the end-to-end properties. They are
  proposed mechanisms, not implemented checks. Launch outcomes would naturally
  belong here too.

## Findings

### CB-1: Rare Outcomes Can Remain Unexercised

**Scope:** Catalog-wide composition and campaign coverage.

**Affected slugs:** `checkpoint-crash-generations`, `accepted-blob-digest`,
`rollback-preserves-unrelated-snaps`, `removal-is-scoped`,
`abort-wins-completion-race`, `cleanup-follows-readiness`,
`replay-preserves-semantic-effects`, `recovery-cohort-completes`.

**Concern:** Safety and liveness are meaningfully represented, but reachability
coverage is concentrated in do/undo replay. Other high-value windows can remain
absent without contradicting their eligible-boundary safety checks. One recovered
operation also does not demonstrate resumed transfers, cache acceptance,
rollback isolation, or cancellation during handler completion.

**Evidence:** The catalog explicitly makes crash, rollback, replay, abort-race
and cleanup safety optional. The
[replay evidence](../properties/replay-preserves-semantic-effects.md) requires
distinct do/undo recovery anchors, whereas
[rollback evidence](../properties/rollback-preserves-unrelated-snaps.md) says a
Reachable rollback anchor "can drive coverage", and
[removal evidence](../properties/removal-is-scoped.md) says last/non-last anchors
"can supplement coverage". The
[blob evidence](../properties/accepted-blob-digest.md) names resume and cache
reuse and correctly says delta hashing evidence does not imply delta coverage.
The [existing task](../../tests/hello-world/task.yaml#L7) only installs and runs
hello-world; it does not establish these campaigns. The topology proposes two
revisions and a second unrelated snap, but does not require observed overlap
between unrelated work and rollback/deletion.

**Actionable fix:** Define a small campaign coverage matrix alongside the
existing safety properties. In campaigns that deliberately construct them,
require fixed, distinct Reachable outcomes for do replay, undo replay, completed
refresh rollback overlapping an unrelated committed operation, last/non-last
removal, accepted abort/completion race, resumed download and cache reuse.
Include disabled/enabled resource-state observations when those operations are
admitted. Distinguish an observed branch/outcome from merely submitting an API
request. Keep crash publication-stage observations conditional on confirmed
termination support; do not demand every scenario on every timeline or add
delta/components/parallel-instance campaigns to the initial scope.

### CB-2: Resource Consistency Does Not Establish Launchability

**Scope:** Property-specific cross-subsystem postconditions.

**Affected slugs:** `active-links-match-current`,
`retained-revisions-have-resources`, `replay-preserves-semantic-effects`,
`recovery-cohort-completes`.

**Concern:** The portfolio can verify Current, mounts, links, wrapper identity
and data tokens without explicitly requiring a controlled application to launch
after successful activation or recovered rollback. The catalog correctly says
Active does not imply services are running, but that leaves the user-visible
execution boundary without a stated campaign contract.

**Evidence:** [LinkSnap](../../../overlord/snapstate/backend/link.go#L170)
generates wrappers, updates current links and then removes run inhibition.
Thus current-link success and launch enablement are separate effects. The
[active-link evidence](../properties/active-links-match-current.md) includes
wrapper names and metadata, and the
[replay evidence](../properties/replay-preserves-semantic-effects.md) includes
wrapper identities and sentinels; neither projection names launch-inhibitor
state or a successful execution result. Backend
[StartServices and StopServices](../../../overlord/snapstate/backend/link.go#L248)
are separate operations, including partial-stop undo and filtering of disabled
services. The hello-world task already makes application execution a local
test expectation, but only for its one install happy path.

**Actionable fix:** Add an explicit workload postcondition for a deterministic,
non-writing CLI fixture after successful install/refresh/enable and completed
rollback: launch through the normal supported command path and compare its
revision token and controlled data token to the independent ledger. Check under
restored dependencies and a calibrated execution budget, then stop application
activity before stable filesystem comparisons. First keep this to ordinary CLI
snaps. If a service fixture is deliberately admitted, separately specify its
expected enabled/disabled behavior and bounded startup/stop result; never assert
that all Active snaps have running services. This tests lifecycle usability,
not security enforcement, arbitrary application behavior or hook effects.

### CB-3: Failed Removal Needs A Survivor-Only Check

**Scope:** Property-specific failure disposition coverage.

**Affected slugs:** `removal-is-scoped`,
`rollback-preserves-unrelated-snaps`, `recovery-cohort-completes`.

**Concern:** The catalog's removal invariant is gated on completed removal, and
refresh rollback is gated on completed restoration. A terminal failed
destructive removal may legitimately lose target data, yet must still preserve
unrelated resources. Without a separate eligible failure observation, this
survivor guarantee can fall between the success and rollback predicates.

**Evidence:** [Removal evidence](../properties/removal-is-scoped.md) explicitly
says, "During failed removal require unrelated preservation, not target rollback
of already-deleted data". Its formal Property section, however, starts "after a
successful admitted ordinary-app removal"; the catalog likewise says
"Completed removal". [Rollback evidence](../properties/rollback-preserves-unrelated-snaps.md)
excludes destructive removal rollback. The
[recovery evidence](../properties/recovery-cohort-completes.md) admits expected
success or rollback and does not define a terminal partially destructive error
result. This is a mismatch between an existing evidence-level safety intention
and the eligible portfolio outcomes, not a claim that data sentinels are absent.

**Actionable fix:** Make `removal-is-scoped`'s survivor projection apply at stable
terminal failure as well as success, recording unrelated operations' latest
independent ledger effects. Only successful removal must satisfy complete target
deletion. Explicitly decide whether the initial finite cohort admits failed
destructive removals: if yes, record an expected terminal-error disposition and
survivor obligations without promising target restoration; if no, state that
restriction and retain it as a later ordinary-app fault campaign. Do not exempt
missing or unreadable survivor data from the check.

## Passes

- Every high-value window explicitly listed in the targeted SUT analysis has a
  corresponding property: link-before-checkpoint, delete-before-sequence update,
  undo partial effects, checkpoint publication, abort/completion and scheduling.
  The concerns above concern coverage and outcome qualification, not wholesale
  absence of those risk areas.
- The four persistence checks cover control flow, independent stored bytes,
  interrupted generations and restored graph semantics. They deserve separate
  checks; consolidating them purely to balance counts would lose contracts.
- Stable resource checks cover retained revisions, not only Current. The
  [retention evidence](../properties/retained-revisions-have-resources.md) checks
  actual mount identity and system/provisioned-user sentinel bytes. Revision
  data copying and replay are already in scope; no generic data-preservation
  property is missing merely because the overview is compact.
- Cross-snap rollback/removal checks preserve concurrent unrelated committed
  work rather than a frozen whole-state baseline. The two-snap topology supports
  this. Parallel instances and components need later ownership-aware fixtures,
  not automatic expansion of this pass.
- Both liveness properties address universal finite cohorts rather than relying
  on Sometimes alone. Manager visitation and task eligibility do not pretend to
  prove eventual completion. Cleanup readiness is kept separate from cleanliness.
- Accepted blob validation spans store, assertion validation and installed
  resources with an independent fixture digest. Size-only cache success and
  transient partial files are not mistaken for accepted content.
- Existing Hold instrumentation is identified as incompatible with legitimate
  abort/Hold behavior. It is neither counted as a nineteenth valid portfolio
  property nor mistaken for implemented cancellation/replay coverage.
- No whole-repo security, full Ubuntu Core/remodel/reboot, broad version
  compatibility, migration, uncontrolled hooks, customer-data or distributed
  consensus coverage is demanded. These explicit exclusions are not findings.

## Assumptions

The supplied SHA/date and current scoped artifacts define this evaluation.
Fixture/store/checker authority and independent ledger are trusted. No external
references were consulted and no sub-agents were spawned. Real launch checks
must use isolated SUT containers, never the host snapd. Platform fault support is
not inferred from source scripts.

## Uncertainties

- None of the 18 proposed properties is implemented by these artifacts; the
  inventory contains only the broad Hold assertion. Portfolio design coverage
  must not be reported as measured runtime coverage.
- Confirmed termination, storage survival, clock fault support, nested Incus
  isolation and actual binary/catalog reporting remain topology prerequisites.
  No process-crash observation would establish power-loss durability.
- The quiet barrier and recovery/launch budgets remain unimplemented and
  uncalibrated. A stable safety check cannot be credited if the harness never
  reaches its boundary; draining must not hide blocked admitted obligations.
- The initial fixture selection does not establish service coverage or a
  repeatable failed-removal trigger. CLI launch is justified by the existing
  task; service and destructive-error campaigns require explicit fixture and
  fault contracts before claiming coverage.
- Local unit-test expectations are evidence of intended boundaries, not proof
  of fault correctness or a comprehensive bug-history investigation. External
  incidents and broader subsystem auditing were not consulted or inferred.

## Handoff

CB-1 is catalog-wide; CB-2 and CB-3 concern the named postconditions. Resolve
campaign coverage obligations first, then make launch and failed-removal
dispositions explicit without broadening the ordinary-app scope. Categorization
and any catalog changes belong to the orchestrator, not this evaluation.