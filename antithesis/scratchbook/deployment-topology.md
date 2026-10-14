---
sut_path: /home/katie.may@canonical.com/source/snapd
commit: 3299c6e61014038add40369d8f11210ce5b9def4
updated: 2026-10-14
external_references: []
---

# Minimal Useful Topology

Scope answer (verbatim): "just this directory".

## Existing Harness

`antithesis/prepare-everything.sh` builds scratch artifact-carrier images.
`incus-allocate.sh` starts testing and fakestore Incus containers; Spread runs
from the host. `build-testing-image.sh` installs real snapd/systemd and stages
instrumentation metadata. `tests/hello-world/task.yaml` currently installs and
runs hello-world. These are useful inputs, not evidence that a standard test
template, independent recovery oracle or crash campaign is wired up.

## Recommended Roles

| Container | Role and image source | Why needed | Connections |
| --- | --- | --- | --- |
| snapd-system | SUT; adapt existing testing image | Real daemon, systemd, squashfs mounts, data and links | Unix API socket to oracle; HTTP to store |
| fakestore | Dependency; existing fakestore image/script | Controlled signed fixtures, revision metadata, interruptible downloads | HTTP requests from snapd |
| workload-oracle | Client; new SDK-enabled checker image or existing external runner | Independent admission ledger, operation driver and stable-snapshot checks | Shared API socket; read-only SUT paths or container-local checker RPC |

One replica per role. An existing external runner can supply the workload role
without adding a third system container. Do not split local systemd/mount
integration away from snapd: it is part of the system being tested. This is a
justified exception to generic single-process container advice.

Keep state, blobs, sequence files and revision data on preserved storage across
daemon/container restart. Start with tiny synthetic ordinary application snaps,
two revisions and controlled data sentinels; include a second unrelated snap for
rollback isolation. Do not use customer data. Add components or parallel
instances only in a later campaign with corresponding fixture expectations.

## Oracle and Fault Wiring

Stop new workload submissions during stable checks. A daemon-side test barrier
must drain affecting handlers and prevent new ones from starting while the
oracle reads state and external resources; locking state alone is insufficient.
Keep checkpoint readback inside the backend boundary while its writer is locked,
or capture a checkpoint generation and reject observations spanning writes.

Place SDK-enabled commands in `/opt/antithesis/test/v1/snap-lifecycle/` and prefix
helpers `helper_`. Emit SetupComplete from container startup after SUT/store
readiness, not from a `first_` command. `eventually_` checks evaluate a finite
admission cohort in a quiet period; use a separate ledger so one completed task
does not conceal another stuck task. This test-template wiring is proposed.

Go SDK v0.8.0 is already pinned. Generate catalogs for both SUT and checker;
verify the actual built binary/catalog, not only source configuration. Current
Go documentation requires cgo for reporting; verify the pinned build too.
SDK no-op mode still evaluates arguments, so gate expensive filesystem checks.

Crash properties require confirmed process termination or explicit isolated
kill/restart commands. Thread pausing requires instrumentation. Do not assume
clock faults, injected disk errors, power loss, nested Incus fault isolation or
storage persistence are available simply because scripts exist.

## Assumptions

Evaluation refinements: admission intent is recorded before API submission, lost
responses are reconciled against durable operation/resource identities, and
fixture manifests/ledger storage are not writable by snapd. A separate deadline
observer must remain able to report failed progress while a barrier or Ensure
is stuck. Establish payload-attempt observations outside the killed process;
only a durable completion observation establishes a known acknowledgment.
Inspect crashed checkpoint bytes before restarted snapd can rewrite them.

The initial deletion-only campaign uses purge and preserves pre-existing saved
archives; non-purge snapshot save/undo/expiry needs a separate ownership model.
The launch campaign runs controlled revision/data-token CLI fixtures; its barrier
must permit necessary security regeneration without generation-crossing or
deadlock. That coordination remains an explicit property open question.

No host services, packages or snaps are changed by this research. All future
system testing must use disposable containers/VMs, not the host daemon.

## Spread Test Selection

Targeted discussion scope: recommend a series of existing `tests/main/` tests,
not implement or execute a campaign. Scope answer (verbatim): "just this directory".
The following ranking is based on inspected task bodies, not measured runtime
or verified compatibility with the Antithesis image.

### First Series

Run each test with its own clean baseline, serially on a disposable SUT:

| Order | Test under `tests/main/` | Useful checks and coverage limits |
| --- | --- | --- |
| 1 | `revert-sideload` | Two local installs and revert; observes x1/x2 selection. A small lifecycle baseline, not an independent data or launch oracle. |
| 2 | `install-refresh-remove-hooks:regular` | Install/configure/pre-refresh/post-refresh/remove hook effects, revision removal versus full purge, and broken install hook rejection. Locally built fixtures; includes non-purge removal and is marked slow in autopkgtest. |
| 3 | `refresh-undo` | Local good/bad service revisions force refresh rollback; checks original service output afterward. Polls systemctl status for roughly 30 seconds; supplement with current revision/link checks for a stronger oracle. |
| 4 | `op-install-failed-undone` | A blocked current path forces failed install; checks task undo and resource cleanup. Its glob checks use numeric revision patterns despite local xN revisions, so do not treat them as comprehensive absence checks without auditing them. |
| 5 | `services-disabled-kept-unhappy` | Seven failed refresh/revert scenarios, renamed services and service-to-app transitions; checks disabled/inactive state and persisted disabled-service metadata. Larger second-step test within this series, using local fixtures. |

These local fixtures still require a preinstalled appropriate base. In particular,
`basic`, `snap-hooks` and the good service fixture have no explicit base and use
the legacy core runtime. Local target snaps alone do not establish offline readiness.

### Next Campaigns

- Pair `refresh-all-undo` with `refresh-many-transactional-undo`: a corrupt
	candidate must leave the good snap updated in the per-snap case, but neither
	snap updated in the all-snaps transaction. Both initially install store snaps,
	then manage a local fakestore and require trusted test keys. Preseed signed
	fixtures and reconcile their store setup with the existing external fakestore.
	These test lane isolation, not arbitrary concurrent unrelated operations.
- Add `parallel-install-basic` and `parallel-install-common-dirs-undo` when
	instance ownership is in scope. The former checks separate instance data and
	requires a prepared test-user session; the latter checks failed-instance shared
	directory cleanup. Restore the parallel-instances flag between tests.
- Add `resume-partial-snap-downloads` for store/download faults. It installs
	core24, builds a 100 MB incompressible fixture, deliberately cuts the download,
	and checks partial-file retention, Range resume and final-file inode reuse.
	It has a five-minute kill timeout, trusted-key and local-fakestore requirements;
	it does not independently verify the accepted blob digest.

### Execution Boundaries

`antithesis/spread.yaml` currently registers only `tests/`, not the repository's
`tests/main/`. The root `spread.yaml` supplies TESTSLIB/TESTSTOOLS and suite
prepare/restore hooks through `tests/lib/prepare-restore.sh`. Preserve or adapt
that lifecycle when exposing selected tests; copying execute blocks alone loses
fixtures, variants, setup and cleanup. Do not blindly import project preparation
that could replace the instrumented SUT build.

Clean the baseline between test cases, not between the operations within one
case. Fixed x1/x2 expectations and shared fixture names make blind repetition
against accumulated state invalid. Run an unfaulted baseline before introducing
faults. Treat shell exit status as a scenario result, not automatically as an SDK
property: interruption of a client or a fixed polling deadline can fail the
script without demonstrating state corruption. Check recovery semantics against
the existing property catalog independently.

Defer `snapd-sigterm` for the initial faulted series: it checks a five-second
wall-clock shutdown deadline (twelve seconds for external ARM) and is not a
mid-task crash/replay oracle. The existing `abort` test only rejects invalid or
already terminal changes; it does not exercise in-flight cancellation safety.
Sideload-only scenarios also cannot cover the signed `accepted-blob-digest`
property. A recovery campaign still needs confirmed do/undo replay observations.

This targeted pass adds no properties and does not repeat the full catalog
evaluation, instrument tests, configure Spread, validate image compatibility,
or execute any system tests. Public Antithesis docs were not consulted under
the directory-only scope; no new platform assertion semantics are prescribed.

## Open Questions

- Confirm tenant fault configuration and independent faulting of nested Incus.
- Confirm preserved storage and the container-local oracle/barrier mechanism.
- Calibrate quiet-phase duration; reboot-aware checks are a separate campaign.
- Verify bases, test helpers, test-user setup and cleanup in the actual image.
- Decide whether selected tests use the existing external fakestore or an
	adapted per-test fakestore; the two setups must not compete for store configuration.