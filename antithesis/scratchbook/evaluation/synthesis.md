---
sut_path: /home/katie.may@canonical.com/source/snapd
commit: e88ec08852fbc8af019dc39e22097e5720aa6dfd
updated: 2026-10-13
external_references: []
---

# Evaluation Synthesis

Scope answer (verbatim): "just this directory". Four fresh-context reviewers
evaluated Antithesis fit, coverage balance, implementability and wildcard
assumptions. Detailed evidence is in the corresponding evaluation files. A
targeted launchability gap pass extended the same resource/recovery category;
it did not initiate a whole-system research expansion.

## Categorized Findings and Actions

| Category | Finding | Action taken |
| --- | --- | --- |
| Refinement | Dirty-unlock and manager visitation are cheap local guards, not the strongest fault-search targets. | Retained them for the user's requests; prioritize independent crash/replay and resource oracles for search budget. |
| Refinement | Optional-path safety alone hides unexercised recovery branches. | Added dedicated campaign Reachable outcome obligations for do/undo replay, rollback, cancellation, scoped removal and resumed download; distinct fixed messages. |
| Gap | Links and mounts can match while execution is inhibited or unusable. | Added `settled-app-launches` evidence/catalog entry; real CLI plus wrapper and independent fixture tokens. |
| Refinement | Successful-removal-only checks omit survivor damage on failure. | Added separate optional failure-path scope checks; target restoration is not promised after destructive deletion. |
| Refinement | Clean second restart is not repeated task execution. | Require same task/direction repeated-attempt evidence and ledger correctness; retain second restart only as additional stability checking. |
| Refinement | Lost responses can hide admitted work; post-hoc outcome classification can excuse bugs. | Intent-first ledger, ambiguous-admission reconciliation and predeclared permitted outcomes added to catalog, topology and recovery evidence. |
| Refinement | Checkpoint acknowledgment observations can disappear on crash. | Require durable independent attempt/completion tracking and pre-startup read; ambiguous success permits attempted-new rather than claiming known acknowledgment. |
| Refinement | A snapshot barrier/deadline can deadlock or conceal starvation. | Require independent deadline observation outside SUT locks/barrier; barrier excludes affecting background work, not only new API input. |
| Refinement | Stable wrong results can validate themselves. | Protect manifests/ledger from SUT writes and require wrong synthetic snapshots to fail oracle tests. |
| Refinement | Removal implicitly introduces automatic snapshot ownership. | Use purge initially while preserving pre-existing archives; defer non-purge snapshot lifecycle to its own scoped campaign. |
| Bias | Ordinary-app install/recovery focus does not cover hooks, full Core, remodel, migration, components or all versions. | Explicit scope limits retained and presented to the user; broad expansion needs a prioritization decision, not an inferred guarantee. |
| Bias | Current harness happy path does not establish fault targeting or durability. | Documented proposed topology versus existing nested Incus/Spread setup; fault/storage/calibration prerequisites remain visible. |

## Applied Results

The catalog now has nineteen concrete property IDs with corresponding evidence.
Safety, liveness and campaign-specific reachability are represented. Existing
Hold instrumentation is inventoried and its broad premise is invalidated by
local supported Hold/abort tests; no duplicate assertion is proposed.

Every top-level artifact records SUT path, current commit, update date and empty
external SUT reference list. Platform SDK documentation was consulted as required
workflow grounding, not as an external claim about snapd.

## Assumptions

Additional self-review refinements applied: normalize default waited-status to
Done on graph restoration even for same-version inputs; use the replay evidence's
canonical optional safety message/type in examples; restrict cohort rollback
claims to reversible operations; qualify failed cleanup commits as runner-owned.

Campaign coverage handoff: require distinct fixed Reachable outcomes for verified
cache reuse, resumed verified download, successful cleanup, do replay, undo replay,
rollback restoration, accepted cancellation, and scoped last/non-last removal.
Launch campaign additionally requires successful install/refresh/enable outcomes.
These are concrete missing instrumentation obligations, not implemented anchors.
The implementation order honors the user's cheap persistence/ensure guards;
fault-search budget prioritizes external effects and recovery rather than spending
most exploration on already unit-tested dispatch loops.

This is research, not an implemented workload or passing Antithesis campaign.
Generated examples use proposed observational variables/helpers where labeled.
Documentation lint and structural checks cannot validate runtime correctness.

## Open Questions and Biases to Escalate

- Confirm actual tenant crash/clock availability, storage preservation and
  independent faulting in the nested Incus topology.
- Calibrate quiet-phase deadlines and implement a safe resource barrier.
- Launch-property partial questions are mirrored in the catalog and logged in
  its evidence: security-regeneration coordination, fixture/base and budget.
- Decide whether later campaigns should broaden to arbitrary hooks, Core/remodel,
  components, non-purge snapshots or version migration; this pass makes no claims
  about those contracts.