---
sut_path: /home/katie.may@canonical.com/source/snapd
commit: e88ec08852fbc8af019dc39e22097e5720aa6dfd
updated: 2026-10-13
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

## Open Questions

- Confirm tenant fault configuration and independent faulting of nested Incus.
- Confirm preserved storage and the container-local oracle/barrier mechanism.
- Calibrate quiet-phase duration; reboot-aware checks are a separate campaign.