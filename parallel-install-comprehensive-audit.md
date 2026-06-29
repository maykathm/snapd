### Classification Key

- **COMPATIBLE**: Parallel instances work correctly for plug-side usage. Verified by test.
- **COMPATIBLE (plug-side only)**: Plug-side works; slot-side has conflicts (e.g., D-Bus
  name ownership). Most snaps only use the plug side.
- **COMPATIBLE EXCEPT FOR SHARED RESOURCE**: Parallel instances work at the snapd policy
  layer, but they still contend for a shared hardware/session/user resource.
- **POTENTIALLY COMPATIBLE**: Should work but has minor caveats or was not fully verified.
- **NOT COMPATIBLE**: Fundamental issue that prevents parallel instances from working
  correctly even for plug-side usage.



## Executive Summary

### Confirmed runtime issues in snapd code

1. **D-Bus activation file naming** (`wrappers/dbus.go:137`): Service files are named by
   bus name (e.g., `com.dbustest.HelloWorld.service`), NOT by instance. Last-installed
   instance wins the activation file.
2. **D-Bus interface AppArmor peer labels** (`interfaces/builtin/dbus.go:84-87`): The
   code explicitly acknowledges parallel installs of D-Bus services are not supported.
   AppArmor labels are instance-specific, meaning consumer_foo can only talk to
   provider_foo, but D-Bus routing sends to whoever owns the name (usually the original).
3. **`$SNAP_COMMON` expansion uses SnapName()** (`snap/info.go:829`): For
   `PerspectiveSelf`, `ExpandSnapVariables` uses `SnapName()` (base name without instance
   key). This means mount-control path matching treats all instances identically.

### Key finding

The previous audit over-classified many interfaces as "NOT COMPATIBLE" by conflating
plug-side consumer behavior with slot-side provider behavior. In practice, 7 interfaces
previously marked "NOT COMPATIBLE" are fully functional for parallel installs on the
plug side, as proven by passing spread tests.


### Genuine incompatibilities confirmed

| Interface | Root cause | Code location |
|-----------|-----------|---------------|
| system-dbus (generic) | D-Bus well-known name uniqueness + activation file naming | `wrappers/dbus.go:137`, `interfaces/builtin/dbus.go:84-87` |
| mount-control | `$SNAP_COMMON` expanded with `SnapName()` not `InstanceName()` | `snap/info.go:829`, `ctlcmd/mount.go:68` |
| location-control (slot-side) | D-Bus name uniqueness for provider | Same D-Bus pattern |
| desktop-launch (file launching) | Desktop file uses `+` separator, userd regex rejects it | `snap/info.go:975`, `usersession/userd/privileged_desktop_launcher.go:196` |
| network-manager (slot-side) | D-Bus name `org.freedesktop.NetworkManager` singleton + shared runtime paths | `network_manager.go:196-202`, `network_manager.go:100-123` |
| bluez (slot-side) | D-Bus names `org.bluez`, `org.bluez.obex`, `org.bluez.mesh` are singletons | `bluez.go:86-103` |
| udisks2 (slot-side) | D-Bus name `org.freedesktop.UDisks2` singleton + shared `/run/udisks2/` | `udisks2.go:87-89`, `udisks2.go:113-114` |
| cups (provider slot) | Socket path uses `PerspectiveSelf`/`SnapName()` instead of `PerspectiveOther`/`InstanceName()` | `cups.go:130` |
| posix-mq | POSIX MQ names are kernel-global; parallel instances share the same queue | `posix_mq.go:272-282` (raw path in mqueue rules, no instance scoping) |
| shared-memory (non-private) | SHM names are kernel-global; parallel instances clobber each other's data | `shared_memory.go:209-232` (raw path in AppArmor rules, no instance scoping) |
| upower-observe (slot-side) | D-Bus name `org.freedesktop.UPower` singleton | `upower_observe.go:72-74` |
| ofono (slot-side) | D-Bus name `org.ofono` singleton + shared `/run/ofono/` and device paths | `ofono.go:123-125`, `ofono.go:57-120` |
| modem-manager (slot-side) | D-Bus name `org.freedesktop.ModemManager1` singleton + shared device paths | `modem_manager.go:106-108` |
| unity7 | D-Bus path wildcard leaks access to parallel instances' indicator paths | `unity7.go:534-549,679-682` (documented known issue) |


---

### D-Bus Service Interfaces (Slot-Side Singleton) — 11 interfaces

These interfaces provide D-Bus services with `dbus (bind)` owning well-known bus names. They exhibit the same fundamental incompatibility pattern as `bluez`, `ofono`, `udisks2`, and `modem-manager` documented above: only one process can own a well-known D-Bus name at a time, making parallel slot providers impossible. Plug-side consumers are likely compatible.

**Interfaces:** `avahi-control`, `fwupd`, `maliit`, `media-hub`, `mir`, `mpris`, `storage-framework-service`, `ubuntu-download-manager`, `unity8`, `unity8-calendar`, `unity8-contacts`

**Common code pattern:** Each interface has `dbus (bind)` in its permanent slot AppArmor rules and `DBusPermanentSlot` generates bus policy granting `<allow own="..."/>` for a hardcoded D-Bus well-known name. The plug side only uses `dbus (send/receive)`, so plug-side parallel instances would work as D-Bus clients.

---

### D-Bus Client Interfaces — 9 interfaces

These interfaces use D-Bus as a client only (send/receive, no `dbus (bind)`). They follow the same pattern as `network-control`, `avahi-observe`, and `upower-observe` (plug-side) that were verified COMPATIBLE in the main audit. Multiple parallel instances are just additional D-Bus clients.

**Interfaces:** `autopilot-introspection`, `desktop-legacy`, `gconf`, `login-session-control`, `login-session-observe`, `network-manager-observe`, `screencast-legacy`, `screen-inhibit-control`, `time-control`

**Reasoning:** No D-Bus name ownership means no singleton conflict. Multiple clients accessing the same session/system bus service is the normal operating mode.

---

### Container and Virtualization Socket Interfaces — 7 interfaces

These interfaces provide client access to container/VM management daemons via UNIX sockets. Multiple clients connecting to the same daemon is standard behavior.

**Interfaces:** `docker`, `lxd`, `microceph`, `microovn`, `openvswitch`, `podman`, `libvirt`

**Reasoning:** All are client-side socket access. The daemon manages concurrent connections. No D-Bus ownership, no shared memory conflicts.

---

### Socket Client Interfaces — 2 interfaces

These interfaces are also client-side access patterns, but they are not container/VM managers. Both are ordinary clients of a daemon or shared subsystem, so parallel instances are just concurrent clients.

**Interfaces:** `jack1`, `pcscd`

**Reasoning:** `jack1` uses POSIX shared memory (`/dev/shm/jack-*`) as part of JACK1 client/server communication. `pcscd` is a PC/SC client socket (`/run/pcscd/pcscd.comm`). Neither interface owns a singleton name or a per-instance resource.

---

### Instance-Safe Interfaces — 4 interfaces

These interfaces explicitly use `SNAP_INSTANCE_NAME` in their implementation or use per-snap namespace isolation, making them already aware of parallel installs.

**Interfaces:** `bool-file`, `cifs-mount`, `nfs-mount`, `gpio-chardev`

**Reasoning:**
- `bool-file`: Uses `SNAP_INSTANCE_NAME` for path resolution
- `cifs-mount`/`nfs-mount`: Mount to instance-specific paths under `/var/snap/{INSTANCE_NAME}/`
- `gpio-chardev`: Uses per-snap virtual device paths at `/dev/snap/gpio-chardev/<snap>/<name>`

These should all be COMPATIBLE based on code analysis.

---

### Read-Only and Informational Interfaces — 11 interfaces

These provide read-only access to system information. No writes, no D-Bus ownership, no named resource conflicts.

**Interfaces:** `appstream-metadata`, `kernel-module-observe`, `ros-opt-data`, `system-backup`, `system-packages-doc`, `system-source-code`, `system-trace`, `juju-client-observe`, `netlink-driver`, `qualcomm-ipc-router`, `core-support`

**Reasoning:** All are read-only or use capability-based permissions (syscalls, not named paths). Multiple readers accessing the same system information is the normal case. `core-support` is empty/logistical with no AppArmor rules.

---

### Pure Capability Interfaces — 2 interfaces

These grant syscall-level capabilities with no named resources, paths, or D-Bus involvement.

**Interfaces:** `fuse-support`, `ppp`

**Reasoning:** `fuse-support` grants `/dev/fuse` access and mount permission — multiple instances can mount FUSE filesystems into their own namespaces without conflict. `ppp` grants PPP device and socket access — parallel instances connecting to different modems would work; connecting to the same modem would conflict at the hardware level.

---

### Other Interfaces — 4 interfaces

**Interfaces:** `confdb`, `custom-device`, `empty`, `network`

- `confdb`: Accesses a confdb through a view. It is not read-only: plugs can read/write and optionally act as custodian.
- `custom-device`: User-defined device paths from gadget snap. Depends entirely on gadget definition — needs per-gadget analysis.
- `empty`: Testing-only interface. No-op, no rules. No compatibility concern.
- `network` (basic): Client network access (DNS resolution, outbound connections). Same pattern as `network-bind` which was verified COMPATIBLE. Likely COMPATIBLE.


---

## Additional Interface Analyses

### custom-device
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Hardware Device Access


**Code analysis:**
- The slot definition is gadget-driven and intentionally open-ended.
- `custom-device` defaults the slot attribute to the slot name if unspecified.
- Connection approval is keyed on the plug attribute matching the slot value.
- The interface validates paths and udev rules carefully, but it does not inject snap-instance-specific naming.

**Reasoning:** there is no snap-instance naming or collision point in the interface code itself. The behavior is gadget-defined, but that does not make the interface incompatible for parallel installs.

**Verification:** No verification has yet been done.

### confdb
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE (no side-specific divergence documented in this entry).

**Type:** Snapd/Policy Management


**Code analysis:**
- Auto-connection is driven by publisher account matching.
- The plug requires explicit `account` and `view` attributes.
- Plugs can read/write confdb data and may use the optional `custodian` role.
- No instance-name or snap-name scoping is used in the interface itself.

**Reasoning:** parallel instances of the same snap will generally behave like two clients using the same confdb view, so snapd does not introduce an instance collision. The remaining caveat is that they are still sharing the same confdb data for that view/account.

**Verification:** No verification has yet been done.

### raw-volume
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE (no side-specific divergence documented in this entry).

**Type:** Filesystem/Mount Interface


**Code analysis:**
- The slot must point at a concrete disk partition.
- The accepted device paths are explicit partition nodes only.
- AppArmor and udev rules are generated from the slot path, not from instance naming.
- Auto-connect is allowed only for declarations, but the slot is still tied to the chosen partition.

**Reasoning:** this is not a snap-instance naming problem. Parallel instances can both access the same partition if connected to the same slot, but that still means they are sharing raw disk hardware and can interfere at the filesystem/data level.

**Verification:** No verification has yet been done.

### opengl
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE (no side-specific divergence documented in this entry).

**Type:** Desktop/Graphics/Media Integration


**Code analysis:**
- Access is to GPU driver stacks, DRM render nodes, and vendor libraries.
- The rules are broad and intentionally allow multiple GPUs / render nodes.
- The interface uses instance-agnostic paths and does not key access on snap instance identity.
- Some vendor-specific state is shared, but the code treats it as normal multi-client GPU access.

**Reasoning:** the interface reads like a shared-client GPU interface rather than a per-snap singleton. Parallel instances are fine at the snapd policy layer, but they still contend for the same GPU resources and performance.

**Verification:** No verification has yet been done.

### jack1
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE (no side-specific divergence documented in this entry).

**Type:** Daemon/Socket Client


**Code analysis:**
- Access is to JACK1 shared memory endpoints under `/dev/shm/jack-*`.
- The rules are based on JACK's server/client naming convention, not on snap instance names.
- There is no snap-specific namespace logic in the interface.

**Reasoning:** The JACK client/server model is fine for parallel installs at the snapd policy layer, but the same JACK session namespace and shared memory are still in play. Two instances can coexist as clients, yet they can interfere through the shared JACK server/session resources.

**Verification:** No verification has yet been done.

### pcscd
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE (no side-specific divergence documented in this entry).

**Type:** Daemon/Socket Client


**Code analysis:**
- Client access is via `/run/pcscd/pcscd.comm`.
- The interface also grants read access to OpenSC config files.
- No singleton service ownership or instance-specific pathing is involved.

**Reasoning:** The interface is policy-safe, but the PC/SC daemon and the smart cards/readers behind it are shared resources. Parallel instances can coexist as clients, yet they can still contend for the same smart card or reader session.

**Verification:** No verification has yet been done.

### network
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Network/Netlink Interface


**Code analysis:**
- Client-side network access only.
- Uses `systemd-resolved` and `systemd` D-Bus APIs as a client.
- No snap-instance-specific pathing or service ownership.
- The seccomp snippet is generic networking support, not a singleton resource.

**Reasoning:** this is the canonical shared-client networking case.

**Verification:** No verification has yet been done.

### network-manager-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** D-Bus/IPC Client


**Code analysis:**
- The interface only observes NetworkManager state and settings.
- It uses D-Bus as a client and subscribes to signals; it does not own the NetworkManager bus name.
- The code adjusts the peer label depending on classic vs confined NetworkManager, but not on snap instance identity.

**Reasoning:** multiple instances are just multiple observers of the same NetworkManager service.

**Verification:** No verification has yet been done.

### openvswitch
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Daemon/Socket Client


**Code analysis:**
- Access is to Open vSwitch management sockets such as `/run/openvswitch/db.sock` and `*.mgmt`.
- The interface is client-side and does not define a singleton service.
- The rules are broad enough to cover per-bridge sockets and runtime control sockets.

**Reasoning:** this is a socket client interface. Parallel instances should be able to talk to the same OVS daemon concurrently.

**Verification:** No verification has yet been done.

### libvirt
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Daemon/Socket Client


**Code analysis:**
- Access is to libvirt sockets (`/run/libvirt/libvirt-sock*`) plus a few config paths.
- The seccomp rules allow socket operations needed by libvirt clients.
- There is no instance-name scoping or service-name ownership.

**Reasoning:** parallel instances should behave like ordinary libvirt clients, sharing the daemon socket.

**Verification:** No verification has yet been done.

### docker
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Daemon/Socket Client


**Code analysis:**
- Access is to the Docker daemon socket (`/run/docker.sock` or `/var/run/docker.sock`).
- The interface is explicit about privileged socket access, but it is still client-side.
- No snap-instance-specific naming is involved.

**Reasoning:** multiple instances can act as concurrent Docker clients. The risk is operational privilege, not snap-instance collision.

**Verification:** No verification has yet been done.

### podman
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Daemon/Socket Client


**Code analysis:**
- Access is to both the system Podman socket and the rootless user socket.
- The AppArmor rules are socket-path based and not instance-scoped.
- The interface is client-side; it does not own a service name.

**Reasoning:** parallel instances should work as concurrent Podman clients.

**Verification:** No verification has yet been done.

### docker-support
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Container/Virtualization Support


**Code analysis:**
- Interface is explicitly for operating as the Docker daemon and container runtime (`interfaces/builtin/docker_support.go:35`, `interfaces/builtin/docker_support.go:71-76`).
- AppArmor and seccomp are intentionally broad (including `@unrestricted` paths/syscalls in privileged mode), plus extensive mount/cgroup/profile control (`interfaces/builtin/docker_support.go:70-277`, `interfaces/builtin/docker_support.go:279-734`).
- Uses `controlsDeviceCgroup` and service delegate semantics (`interfaces/builtin/docker_support.go:883-885`, `interfaces/builtin/docker_support.go:736`).

**Reasoning:** This is host-level orchestration authority, not an instance-scoped client interface. Parallel instances would contend over shared daemon/runtime state and system resources.

**Verification:** No verification has yet been done.

### kubernetes-support
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Container/Virtualization Support


**Code analysis:**
- Interface is intended for running Kubernetes services (`interfaces/builtin/kubernetes_support.go:34`).
- Grants broad cgroup, mount, ptrace, and systemd-run interactions depending on flavor (`interfaces/builtin/kubernetes_support.go:50-229`, `interfaces/builtin/kubernetes_support.go:320-383`).
- Includes `controlsDeviceCgroup` and service delegation (`interfaces/builtin/kubernetes_support.go:103`, `interfaces/builtin/kubernetes_support.go:300-312`).

**Reasoning:** Kubernetes node control is system-global orchestration. Parallel instances would compete over shared host cgroups, mounts, and runtime coordination.

**Verification:** No verification has yet been done.

### lxd-support
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Container/Virtualization Support


**Code analysis:**
- Interface is for operating as the LXD service (`interfaces/builtin/lxd_support.go:33`).
- Grants profile-changing/unconfined behavior, unrestricted seccomp, and device cgroup control (`interfaces/builtin/lxd_support.go:49-69`, `interfaces/builtin/lxd_support.go:128-130`).
- Supports optional unconfined mode via plug attribute (`interfaces/builtin/lxd_support.go:81-113`).

**Reasoning:** LXD service operation is host-global VM/container management. Parallel instances are not isolated and would conflict on shared runtime and host control surfaces.

**Verification:** No verification has yet been done.

### microceph-support
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Container/Virtualization Support


**Code analysis:**
- Interface is for operating as the MicroCeph service (`interfaces/builtin/microceph_support.go:22`).
- Grants rw access to global block devices and RBD management sysfs under `/sys/bus/rbd/**` (`interfaces/builtin/microceph_support.go:38-56`).
- Policy is device/system-path based, not instance-scoped.

**Reasoning:** Storage orchestration here is host-global. Parallel instances would contend over shared block/rbd resources and mutable storage state.

**Verification:** No verification has yet been done.

### microstack-support
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Container/Virtualization Support


**Code analysis:**
- Interface is for operating as MicroStack (OpenStack services stack) (`interfaces/builtin/microstack_support.go:38`).
- Grants extensive host device, cgroup, mount, AppArmor management, and capability access (`interfaces/builtin/microstack_support.go:54-229`).
- Declares `controlsDeviceCgroup` and a broad set of kernel modules (`interfaces/builtin/microstack_support.go:248-277`).

**Reasoning:** This is broad host orchestration authority across compute/network/storage subsystems. Parallel instances are expected to interfere on shared system control planes.

**Verification:** No verification has yet been done.

### multipass-support
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Container/Virtualization Support


**Code analysis:**
- Interface is for operating as the Multipass service (`interfaces/builtin/multipass_support.go:40`).
- Allows AppArmor policy manipulation and profile transitions for spawned utilities (`interfaces/builtin/multipass_support.go:56-86`).
- Grants privilege-separation and file-owner-changing syscalls/capabilities for daemon-managed helper processes (`interfaces/builtin/multipass_support.go:71-115`).

**Reasoning:** Multipass daemon behavior is host-global VM/runtime orchestration. Multiple parallel instances would share and compete for the same host virtualization resources.

**Verification:** No verification has yet been done.

### nomad-support
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Container/Virtualization Support


**Code analysis:**
- Interface enables running Hashicorp Nomad as a service (`interfaces/builtin/nomad_support.go:24-29`).
- Grants cgroup hierarchy management and ownership-changing privileges (`interfaces/builtin/nomad_support.go:44-76`).
- Uses `controlsDeviceCgroup` and service delegation (`interfaces/builtin/nomad_support.go:91-109`).

**Reasoning:** Nomad scheduler/agent control is host-global orchestration. Parallel instances would conflict on shared cgroup tree and scheduling state.

**Verification:** No verification has yet been done.

### nvidia-drivers-support
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Container/Virtualization Support


**Code analysis:**
- Interface is for NVIDIA userspace driver system setup (`interfaces/builtin/nvidia_drivers_support.go:22`).
- Grants character-device creation and rw access to global `/dev/nvidia*` nodes (`interfaces/builtin/nvidia_drivers_support.go:45-56`, `interfaces/builtin/nvidia_drivers_support.go:58-66`).
- Operates on shared host device namespace, not instance-specific paths.

**Reasoning:** Managing global NVIDIA driver device nodes is host-global setup work. Parallel instances are not independently scoped and can interfere over the same device namespace.

**Verification:** No verification has yet been done.

### openvswitch-support
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Container/Virtualization Support


**Code analysis:**
- Interface is for operating as the Open vSwitch service (`interfaces/builtin/openvswitch_support.go:22`).
- Declares kernel module control/loading for `openvswitch` (`interfaces/builtin/openvswitch_support.go:32-42`).
- No per-instance namespacing is introduced in the interface definition.

**Reasoning:** OVS service/kernel-module management is a shared host control surface. Parallel service instances are not isolated at interface level and are expected to conflict.

**Verification:** No verification has yet been done.

### can-bus
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE (no side-specific divergence documented in this entry).

**Type:** Network/Netlink Interface


**Code analysis:**
- The interface grants CAN network access and allows AF_CAN sockets.
- No instance-specific pathing or ownership is present.
- The kernel handles CAN bus concurrency; the interface is just a client to that medium.

**Reasoning:** parallel instances can use CAN concurrently and there is no snap-instance naming collision in this interface. They still share the same bus and can interfere at protocol/application level if they use overlapping identifiers.

**Verification:** No verification has yet been done.

### kernel-crypto-api
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Hardware Device Access


**Code analysis:**
- Access is to the Linux kernel crypto API through AF_ALG and NETLINK_CRYPTO.
- The implementation explicitly notes the API is intended for any process and requires no special privileges.
- No instance-specific paths or service names are involved.

**Reasoning:** this is a shared kernel service interface. Multiple instances should behave like concurrent clients of the same kernel crypto subsystem.

**Verification:** No verification has yet been done.

### avahi-control
**Status:** Plug-side: COMPATIBLE. Slot-side: not separately classified in this entry (provider behavior out of scope here).

**Type:** D-Bus Service/Provider


**Code analysis:**
- The interface explicitly imports and extends `avahi-observe` behavior.
- Plug-side rules only send to the Avahi server and manage entry groups; they do not own the Avahi bus name.
- Slot-side rules are only applied when running as an application snap, and the code handles the system-vs-snap Avahi distinction.
- D-Bus ownership is only relevant for a snap acting as the Avahi service.

**Reasoning:** a parallel client snap using `avahi-control` should behave like any other client. A parallel provider snap would still be constrained by the singleton Avahi service name.

**Verification:** No verification has yet been done.

### fwupd
**Status:** Plug-side: not separately classified in this entry. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
- Permanent slot rules bind `org.freedesktop.fwupd` on the system bus.
- The slot side carries extensive privileged access to firmware, EFI variables, TPM, MEI, NVMe, USB, and systemd D-Bus control paths.
- The plug side uses D-Bus as a client to query/stop fwupd and inspect systemd state.
- The interface is explicitly a service interface with privileged system access.

**Reasoning:** parallel instances cannot both act as the fwupd service. As a client interface, multiple instances should be fine, but the service-provider side is a hard singleton.

**Verification:** No verification has yet been done.

### maliit
**Status:** Plug-side: not separately classified in this entry. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
- The slot binds the well-known session-bus name `org.maliit.server`.
- After address negotiation, communication moves to a private per-client Unix socket under `@/tmp/maliit-server/dbus-*`.
- The plug and slot both use D-Bus and per-client socket rules, but the address service itself is the singleton.
- The code is explicitly structured around one server brokering individual client channels.

**Reasoning:** parallel consumers are fine, but parallel providers cannot both own the Maliit server name.

**Verification:** No verification has yet been done.

### mpris
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** D-Bus Service/Provider


**Code analysis:**
- The slot binds `org.mpris.MediaPlayer2.<name>` based on a `name` attribute, defaulting to `SNAP_INSTANCE_NAME`.
- The code explicitly warns that snaps using this interface must adjust themselves for parallel installs.
- The plug side discovers and talks to the player over the session bus.
- The implementation is careful about per-snap naming, but the well-known bus name still represents a provider identity.

**Reasoning:** parallel clients are fine, and parallel providers are handled by default because the well-known name falls back to `SNAP_INSTANCE_NAME`. The interface code already expects snaps to use per-instance naming, so parallel installs do not introduce a snapd-side collision.

**Verification:** No verification has yet been done.

### pipewire
**Status:** Plug-side: COMPATIBLE. Slot-side: not separately classified in this entry (provider behavior out of scope here).

**Type:** Daemon/Socket Client


**Code analysis:**
- The plug accesses PipeWire sockets at `/run/user/[0-9]*/pipewire-[0-9]` for classic/system slots.
- For app-provided slots, the plug uses instance-aware paths:
  - `/run/user/[0-9]*/snap.<SLOT_INSTANCE_NAME>/pipewire-[0-9]` (line 50, 93: uses `slot.Snap().InstanceName()`)
  - `/var/snap/<SLOT_INSTANCE_NAME>/common/pipewire-[0-9]` for system mode (line 52, 96: uses `slot.Snap().InstanceName()`)
- The slot provider creates sockets at `/run/user/[0-9]*/pipewire-[0-9]` and `/run/user/[0-9]*/pipewire-[0-9]-manager` (lines 68-69).
- No D-Bus name ownership in this interface.
- Shared memory via `shmctl` syscall (line 56, 80) is used for audio IPC, same pattern as pulseaudio.

**Reasoning:** The plug-side correctly uses `slot.Snap().InstanceName()` for instance-aware path resolution when connecting to an app-provided slot. Multiple parallel plug instances connecting to the same PipeWire server (system or snap-provided) is the normal multi-client audio pattern. The slot-side would conflict if two parallel instances tried to create sockets at the same runtime path, but that's the expected slot-side singleton pattern.
The remaining shared SHM/socket state is client-server audio IPC, not a parallel-install collision.

**Verification:** No verification has yet been done.

### cups
**Status:** Plug-side: COMPATIBLE. Slot-side: NOT COMPATIBLE.

**Type:** Daemon/Socket Client


**Code analysis:**
The `cups` interface (distinct from `cups-control`) lets a provider snap expose a CUPS socket to consumers via bind-mount and path-based mediation.

1. **Socket path resolution uses wrong perspective** (`interfaces/builtin/cups.go:130`):
   `validateCupsSocketDirSlotAttr()` expands the slot's `cups-socket-directory` using `ExpandSnapVariables()` with `PerspectiveSelf`, which resolves `$SNAP_COMMON` via `SnapName()` instead of `InstanceName()`.

2. **Parallel provider expands to base-name path**: for `cups-provider_foo` and
   `cups-socket-directory: $SNAP_COMMON/cups-socket`, expansion becomes
   `/var/snap/cups-provider/common/cups-socket` instead of
   `/var/snap/cups-provider_foo/common/cups-socket`.

3. **MountConnectedPlug uses the wrong source path** (`interfaces/builtin/cups.go:188-206`):
   the bind mount into the consumer namespace is generated from that wrongly-expanded host path.

4. **AppArmor rules inherit the same mismatch** (`interfaces/builtin/cups.go:170`):
   permissions are granted for the wrong source directory, so even policy alignment is against the base-name path.

5. **No D-Bus ownership model here**: unlike singleton service interfaces, `cups` has no D-Bus `bind` ownership semantics and no `LabelExpression()` peer matching; behavior is purely UNIX socket path + mount based.

6. **Contrast with `content`**: `content` uses `PerspectiveOther` for provider path expansion (`interfaces/builtin/content.go:234`), which is the missing behavior here.

**Reasoning:** Plug-side parallel consumers are fine because they are normal clients of a mounted CUPS socket. Slot-side parallel providers are not safe: provider path resolution collapses to the base snap name, so parallel provider instances cannot reliably bind their own instance-specific socket directories.

**Verification:**
- Plug-side: passed on noble (`test-snapd-cups-consumer_foo` connected and communicated through provider socket; remained functional after removing original consumer).
- Slot-side parallel provider: not verified by spread in this audit; expected failure remains due to `interfaces/builtin/cups.go:130` path expansion behavior.

### serial-port
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Slots are provided by core or gadget snaps only (lines 41-43), not by application snaps.
- The slot requires a `path` attribute pointing to a specific device node (e.g., `/dev/ttyUSB0`) or a udev symlink with USB vendor/product attributes.
- AppArmor rules grant access to the specific device path from the slot (line 179: `cleanedPath`), not based on snap instance names.
- UDev rules tag the specific device by kernel name or USB vendor/product (lines 200-210).
- No snap-instance-specific paths are involved; the interface is purely device-path-based.
- No D-Bus, no shared memory, no sockets that could conflict.

**Reasoning:** The serial-port interface grants access to a specific physical device declared in the slot. Parallel instances of a plug snap can all connect to the same serial-port slot and access the same device. Whether this is safe depends on the application: two processes reading/writing the same serial port would interfere at the protocol level, but that's an application concern, not a snapd interface conflict. The interface itself has no instance-naming issues.

**Verification:** No verification has yet been done.

### hidraw
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Slots are provided by core or gadget snaps only (lines 39-41), not by application snaps.
- The slot requires a `path` attribute pointing to a specific hidraw device node (e.g., `/dev/hidraw0`) or a udev symlink with USB vendor/product attributes.
- Device node pattern: `/dev/hidraw[0-9]{1,3}` (line 66).
- Udev symlink pattern: `/dev/hidraw-[a-z0-9]+` (line 71).
- AppArmor rules grant access to the specific device path from the slot (line 153: `cleanedPath`), or a broad pattern `/dev/hidraw[0-9]{,[0-9],[0-9][0-9]}` when using USB attributes (line 143).
- UDev rules tag the specific device by kernel name or USB vendor/product (lines 182-187).
- No snap-instance-specific paths are involved; the interface is purely device-path-based.
- No D-Bus, no shared memory, no sockets.

**Reasoning:** Like serial-port, the hidraw interface grants access to a specific physical HID device declared in the slot. The interface is device-path-based with no instance-naming involved. Parallel instances of a plug snap can all connect to the same hidraw slot and access the same device. Two processes accessing the same hidraw device would interfere at the HID protocol level, but that's an application concern, not a snapd interface conflict.

**Verification:** No verification has yet been done.

### i2c
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Slots are provided by gadget or core snaps only (lines 39-41), not by application snaps.
- The slot can specify either a `path` attribute (e.g., `/dev/i2c-0`) or a `sysfs-name` attribute, but not both (lines 86-93).
- Device node pattern: `/dev/i2c-[0-9]+` (line 79).
- Sysfs name pattern: `[a-zA-Z0-9_-]+` (line 82).
- AppArmor rules grant access to the specific device path (line 131) or sysfs path (line 120) from the slot.
- Parametric snippets are used for sysfs paths under `/sys/devices/platform/` (lines 133-135).
- UDev rules tag the specific device by kernel name (line 144).
- No snap-instance-specific paths are involved; the interface is purely device-path-based.
- No D-Bus, no shared memory, no sockets.

**Reasoning:** The i2c interface grants access to a specific I2C bus controller declared in the slot. The interface is device-path-based with no instance-naming involved. Parallel instances of a plug snap can all connect to the same i2c slot and access the same bus. Whether concurrent access is safe depends on the I2C devices on the bus and the application protocol; the kernel's I2C subsystem handles bus arbitration but not higher-level conflicts. The interface itself has no instance-naming issues.

**Verification:** No verification has yet been done.

### media-control
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Desktop/Graphics/Media Integration


**Code analysis:**
- Slot is provided by core only (lines 32-33), with implicit slots on core and classic (lines 55-56).
- AppArmor rules grant access to `/dev/media[0-9]*` and `/dev/v4l-subdev[0-9]*` (lines 39-43).
- UDev rules tag media and v4l-subdev devices by subsystem and kernel name (lines 46-49).
- No snap-instance-specific paths are involved; the interface is purely device-path-based.
- No D-Bus, no shared memory, no sockets.

**Reasoning:** The interface is policy-safe for parallel installs, but the underlying media controller device is shared hardware. Parallel instances can coexist, yet they can still interfere with one another if they try to control the same media pipeline or device.

**Verification:** No verification has yet been done.

### gsettings
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** D-Bus/IPC Client


**Code analysis:**
- Slot is provided by core only (lines 27-28), with implicit slot on classic (line 53).
- AppArmor rules grant access to the user's dconf database:
  - `/{,var/}run/user/*/dconf/user` (line 41)
  - `@{HOME}/.config/dconf/user` (line 42)
- D-Bus rules allow send/receive to `ca.desrt.dconf.Writer` on the session bus (lines 43-46).
- The interface uses `#include <abstractions/dconf>` for standard dconf access patterns.
- No snap-instance-specific paths; all paths are user-session-scoped, not snap-scoped.
- No D-Bus name ownership (client only).

**Reasoning:** The interface is policy-safe, but the dconf/gsettings database is a shared per-user state store. Parallel instances can coexist, yet they can overwrite or react to each other's settings changes because they are using the same user database.

**Verification:** No verification has yet been done.

### lxd
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Daemon/Socket Client


**Code analysis:**
- Slot installation is denied by default, requires snap-declaration (lines 26-28).
- AppArmor rules grant access to the LXD socket at `/var/snap/lxd/common/lxd/unix.socket` (line 35).
- Seccomp rules allow `AF_NETLINK` socket creation (line 42).
- The socket path is hardcoded to the `lxd` snap's location, not parameterized by instance name.
- No D-Bus, no shared memory.
- This is a client interface to the LXD daemon.

**Reasoning:** The lxd interface grants client access to the LXD daemon's Unix socket. Multiple parallel instances of a plugging snap would all connect to the same LXD daemon as concurrent clients, which is normal socket-client behavior. The LXD daemon manages concurrent connections. No instance-naming issues exist since this is purely client access to a fixed socket path.

**Verification:** No verification has yet been done.

### microceph
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Daemon/Socket Client


**Code analysis:**
- Slot installation is denied by default, requires snap-declaration (lines 25-28).
- AppArmor rules grant access to the MicroCeph socket at `/var/snap/microceph/common/state/control.socket` (line 34).
- Seccomp rules allow `AF_NETLINK` socket creation (line 40).
- The socket path is hardcoded to the `microceph` snap's location, not parameterized by instance name.
- No D-Bus, no shared memory.
- This is a client interface to the MicroCeph daemon.

**Reasoning:** The microceph interface grants client access to the MicroCeph control socket. Multiple parallel instances of a plugging snap would all connect to the same MicroCeph daemon as concurrent clients. The daemon manages concurrent connections. No instance-naming issues since this is client access to a fixed socket path.

**Verification:** No verification has yet been done.

### microovn
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Daemon/Socket Client


**Code analysis:**
- Slot installation is denied by default, requires snap-declaration (lines 25-28).
- AppArmor rules grant access to the MicroOVN socket at `/var/snap/microovn/common/state/control.socket` (line 34).
- Seccomp rules allow `AF_NETLINK` socket creation (line 40).
- The socket path is hardcoded to the `microovn` snap's location, not parameterized by instance name.
- No D-Bus, no shared memory.
- This is a client interface to the MicroOVN daemon.

**Reasoning:** The microovn interface grants client access to the MicroOVN control socket. Multiple parallel instances of a plugging snap would all connect to the same MicroOVN daemon as concurrent clients. The daemon manages concurrent connections. No instance-naming issues since this is client access to a fixed socket path.

**Verification:** No verification has yet been done.

### appstream-metadata
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Observability/Diagnostics


**Code analysis:**
- Slot is provided by core only (lines 35-40), with implicit slot on classic (line 126).
- AppArmor rules grant read access to AppStream metadata under `/usr/share/{metainfo,appdata,app-info,swcatalog}` and apt list metadata (lines 47-61).
- Mount rules bind host metadata directories into the snap namespace, and those paths are based on host filesystem locations rather than snap names (lines 79-120).
- No snap-instance-specific names are used.

**Reasoning:** AppStream metadata is host-wide read-only documentation and metadata. Parallel instances just read the same data and the mount logic is based on host paths, not instance-specific paths.

**Verification:** No verification has yet been done.

### bool-file
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Filesystem/Mount Interface


**Code analysis:**
- Slots are provided by core or gadget snaps only (lines 34-40).
- Slot validation accepts only LED brightness and GPIO value paths (lines 76-92).
- AppArmor rules are built from the dereferenced slot path, so the connected plug mediates the exact file the slot identifies (lines 106-125).
- For GPIO slots, the permanent-slot rules expose export/unexport and direction handling (lines 94-103).
- No snap-instance-specific paths are involved.

**Reasoning:** This is a specific-file interface with path validation. Parallel installs can use the same or different hardware-backed paths based on the slot; the code doesn’t key anything off snap instance names.

**Verification:** No verification has yet been done.

### cifs-mount
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Filesystem/Mount Interface


**Code analysis:**
- Slot is provided by core only (lines 24-29), with implicit slots on core and classic (lines 71-72).
- AppArmor and seccomp permissions are for mount/umount of CIFS filesystems (lines 32-65).
- The policy explicitly uses both `SNAP_NAME` and `SNAP_INSTANCE_NAME` for writable mount targets, to cover parallel installs (lines 45-56).
- No D-Bus or sockets are involved.

**Reasoning:** The interface is already written to handle parallel-instance mount targets explicitly. The mount rules include both base and instance names, so there is no obvious instance collision in the code.

**Verification:** No verification has yet been done.

### empty
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Test/Meta Interface


**Code analysis:**
- This interface intentionally contributes no permissions.
- `BeforeConnectPlug()` and `BeforeConnectSlot()` only mutate plug/slot attributes (lines 65-85).
- AppArmor connection handlers are no-ops (lines 87-93).
- `AutoConnect()` always returns true (lines 95-97).
- No snap-instance-specific paths are used.

**Reasoning:** The interface is a no-op sandbox for testing. It doesn’t introduce any resource conflicts or instance-scoped policy.

**Verification:** No verification has yet been done.

### fuse-support
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Slot is provided by core only (lines 28-33), with implicit slots on core and classic except old Ubuntu 14.04 (lines 100-101).
- AppArmor grants access to `/dev/fuse`, `sys_admin`, and mount targets under snap-specific writable directories (lines 43-92).
- The mount rules explicitly use `SNAP_INSTANCE_NAME` for per-user home snap directories, and `SNAP_NAME`/`SNAP_INSTANCE_NAME` for system snap directories (lines 67-77).
- UDev tags the `fuse` device (line 94).
- No hardcoded snap-instance path conflicts are visible.

**Reasoning:** FUSE support is deliberately instance-aware in the mount rules. The interface is one of the examples that already accounts for parallel instances via `SNAP_INSTANCE_NAME` and `SNAP_NAME`.

**Verification:** No verification has yet been done.

### nfs-mount
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Filesystem/Mount Interface


**Code analysis:**
- Slot is provided by core only (lines 24-29), with implicit slots on core and classic (lines 85-86).
- AppArmor and seccomp permissions are for NFS mount/umount operations (lines 32-79).
- The policy explicitly uses both `SNAP_NAME` and `SNAP_INSTANCE_NAME` for writable mount targets, covering parallel installs (lines 45-61).
- No D-Bus or sockets are involved.

**Reasoning:** Like cifs-mount, this interface is already instance-aware in its mount target rules. Parallel instances do not create a mount-path collision in the code.

**Verification:** No verification has yet been done.

### optical-drive
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Slot is provided by core only (lines 32-43), with implicit slot on classic only (line 107).
- AppArmor grants read access to optical drive device nodes and supporting SCSI/udev files; optional write access is gated by a plug attribute (lines 45-54, 85-99).
- UDev rules tag the relevant SCSI device types (lines 56-63).
- No snap-instance-specific paths are used.

**Reasoning:** The interface is attribute/device based, not instance-name based, so there is no snap-instance collision. Optical drives are still shared physical hardware and concurrent read/write operations can interfere.

**Verification:** No verification has yet been done.

### physical-memory-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Observability/Diagnostics


**Code analysis:**
- Slot is provided by core only (lines 24-29), with implicit slots on core and classic (lines 49-50).
- AppArmor grants read-only `/dev/mem` and `/proc/*/pagemap` access (lines 32-41).
- UDev tags the `mem` device (line 43).
- No snap-instance-specific paths are involved.

**Reasoning:** Read-only physical memory observation is global system state, not snap-instance state. The interface code does not introduce any parallel-install collision point.

**Verification:** No verification has yet been done.

### pkcs11
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Identity/Credentials/Secrets


**Code analysis:**
- The slot provides a `pkcs11-socket` attribute and must live under `/run/p11-kit` (lines 71-93).
- `BeforePrepareSlot()` validates the path and disallows AppArmor-regex characters (lines 95-105).
- AppArmor and Seccomp rules use the socket path as supplied by the slot (lines 107-155).
- The interface is path-driven by the slot, not by snap instance names.

**Reasoning:** This is a named socket interface whose path is set by the slot, not by the snap instance. Parallel instances talk to the same p11-kit service or different sockets as declared by the slot, so there is no snap-instance collision in the code.

**Verification:** No verification has yet been done.

### system-packages-doc
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Observability/Diagnostics


**Code analysis:**
- Slot is provided by core only (lines 31-36), with implicit slot on classic (line 204-205).
- AppArmor grants read access to documentation directories under `/usr/share`, `/usr/local/share`, and `/var/lib/snapd/hostfs`-backed locations (lines 39-53).
- Mount rules bind host documentation into the snap namespace (lines 59-196).
- The code uses host paths and generic doc paths; there are no snap-instance-specific names.

**Reasoning:** Documentation files are shared read-only host resources. Parallel instances can all mount/read them, and the policy is path-based rather than instance-name-based.

**Verification:** No verification has yet been done.

### display-control
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Desktop/Graphics/Media Integration


**Code analysis:**
- Slot is provided by core only (lines 34-39), with implicit slot on classic (line 137).
- AppArmor rules cover backlight and keyboard backlight sysfs nodes plus UPower and GNOME Settings Daemon D-Bus APIs (lines 46-91).
- The interface discovers backlight paths dynamically via sysfs symlinks (lines 97-127).
- No snap-instance-specific paths are involved.

**Reasoning:** Display/backlight control is global device state. Parallel instances can adjust the same display settings, and the policy code does not key anything off snap instance names.

**Verification:** No verification has yet been done.

### desktop-legacy
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** D-Bus/IPC Client


**Code analysis:**
- Slot is provided by core only (lines 33-38), with implicit slot on classic (line 441).
- This is a plug-only interface for clients to access legacy desktop methods.
- AppArmor rules grant access to:
  - Accessibility services via D-Bus (a11y bus) and Unix socket at `/run/user/*/at-spi/bus*` (lines 44-126)
  - Speech-dispatcher socket at `/run/user/*/speech-dispatcher/speechd.sock` (line 60)
  - Input method services: ibus, mozc, gcin, fcitx via Unix sockets and D-Bus (lines 128-238)
  - GTK/gvfs mounts via D-Bus (lines 240-250)
  - dbusmenu, app-indicators, notifications via D-Bus (lines 271-404)
- Uses `getDesktopFileRules(plug.Snap())` at line 427 which correctly uses snap identity.
- All D-Bus interactions are with system services (unconfined) or well-known desktop services.
- No snap-instance-specific paths; all paths are user-session-scoped.
- No D-Bus name ownership conflicts (binds `org.kde.StatusNotifierItem-[0-9]*` at line 324, which uses PID-based uniqueness).

**Reasoning:** The interface is policy-safe, but it depends on shared desktop/session services (accessibility, input methods, notifications, etc.). Parallel instances can coexist, yet they can still interfere through the same user-session services and shared desktop state.

**Verification:** No verification has yet been done.

### gconf
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** D-Bus/IPC Client


**Code analysis:**
- Slot is provided by core only (lines 28-33), with implicit slot on classic (line 70).
- AppArmor rules grant access to the GConf D-Bus service:
  - Send to `/org/gnome/GConf/Server` to get database (lines 45-49)
  - Receive notifications from `/org/gnome/GConf/{Client,Server}` (lines 52-56)
  - All operations on `/org/gnome/GConf/Database/*` (lines 59-63)
- This is a legacy configuration system (predates dconf/gsettings).
- GConf is explicitly a shared per-user database with no application isolation (noted in comment at lines 24-27).
- No snap-instance-specific paths; all paths are user-session-scoped.
- No D-Bus name ownership (client only).

**Reasoning:** The interface is policy-safe, but the GConf database is shared per-user state. Parallel instances can coexist, yet they can affect each other by writing to the same settings database.

**Verification:** No verification has yet been done.

### login-session-control
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** D-Bus/IPC Client


**Code analysis:**
- Slot is provided by core only (lines 24-29), with implicit slots on core and classic (lines 68-69).
- AppArmor rules grant D-Bus access to systemd-logind:
  - Properties on `/org/freedesktop/login1/{seat,session}/**` (lines 37-42)
  - Full access to `org.freedesktop.login1.Seat` interface (lines 44-48)
  - Full access to `org.freedesktop.login1.Session` interface (lines 50-54)
  - Manager methods: ActivateSession, GetSession, GetSeat, KillSession, ListSessions, LockSession, TerminateSession, UnlockSession (lines 56-61)
- This is a client interface to systemd-logind on the system bus.
- No snap-instance-specific paths; access is to system-wide login/session state.
- No D-Bus name ownership (client only).

**Reasoning:** The login-session-control interface grants D-Bus client access to systemd-logind for managing login sessions. Multiple parallel instances would all interact with the same logind service as concurrent D-Bus clients. The logind service manages concurrent access. No instance-naming issues since this is client access to system services.

**Verification:** No verification has yet been done.

### login-session-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** D-Bus/IPC Client


**Code analysis:**
- Slot is provided by core only (lines 24-29), with implicit slots on core and classic (lines 123-124).
- AppArmor rules grant:
  - Read access to login tracking files: `/var/log/wtmp`, `/run/utmp`, `/var/log/lastlog`, `/var/log/faillog` (lines 36-43)
  - Read access to systemd session files at `/run/systemd/sessions/` (lines 46-47)
  - Execute `who`, `lastlog`, `faillog`, `loginctl` binaries (lines 35, 39, 42, 57)
  - D-Bus read access to systemd-logind for introspection and property queries (lines 62-112)
- This is a read-only interface for observing login session state.
- No snap-instance-specific paths; access is to system-wide login state.
- No D-Bus name ownership (client only).

**Reasoning:** The login-session-observe interface grants read-only access to system login/session information. Multiple parallel instances would read the same system-wide login state, which is the intended behavior. No instance-naming issues since this is purely observational access to system state.

**Verification:** No verification has yet been done.

### screen-inhibit-control
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** D-Bus/IPC Client


**Code analysis:**
- Slot may be provided by app or core snaps (lines 31-43), with implicit slot on classic (line 213).
- When slot is from core (implicit system slot), plug rules target `unconfined` (lines 188-191).
- When slot is from an app snap, plug rules use `slot.LabelExpression()` (line 193).
- AppArmor rules for plugs grant D-Bus send access to various screen saver APIs:
  - GNOME Session Manager Inhibit/Uninhibit (lines 51-56)
  - Unity Screen API (lines 59-70)
  - freedesktop.org ScreenSaver (lines 74-79)
  - xfce4-power-manager (lines 83-94)
  - GNOME/KDE/Cinnamon screensavers (lines 104-110)
- AppArmor rules for slots grant corresponding receive permissions (lines 113-178).
- Both plug and slot rules use `###SLOT_SECURITY_TAGS###` / `###PLUG_SECURITY_TAGS###` placeholders.
- Uses `slot.LabelExpression()` and `plug.LabelExpression()` which are instance-aware.
- No snap-instance-specific paths; D-Bus communication only.

**Reasoning:** The screen-inhibit-control interface allows snaps to inhibit screen savers. The D-Bus rules use `LabelExpression()` which correctly identifies snap instances. Multiple parallel instances can independently inhibit/uninhibit screen savers through separate D-Bus calls. No instance-naming issues.

**Verification:** No verification has yet been done.

### time-control
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** D-Bus/IPC Client


**Code analysis:**
- Slot is provided by core only (lines 24-29), with implicit slots on core and classic (lines 143-144).
- AppArmor rules grant:
  - D-Bus access to `org.freedesktop.timedate1` for setting time (lines 42-69)
  - Execute `timedatectl` and `hwclock` binaries (lines 75, 110)
  - Capability `sys_time` for direct time setting (line 87)
  - Read/write access to `/dev/rtc[0-9]*` RTC devices (line 89)
  - Read/write access to `/sys/class/rtc/` sysfs nodes (lines 93-97)
  - Read/write access to `/dev/pps[0-9]*` PPS devices (line 101)
- Seccomp rules allow time-setting syscalls: settimeofday, adjtimex, clock_adjtime*, clock_settime* (lines 119-125)
- UDev rules tag RTC and PPS devices (lines 134-137)
- No snap-instance-specific paths; access is to system time hardware and services.
- No D-Bus name ownership (client only).

**Reasoning:** The time-control interface grants access to system time control via D-Bus, syscalls, and device nodes. Multiple parallel instances would all have the same capability to modify system time, which is inherently a system-wide singleton resource. The kernel and systemd manage concurrent access. No instance-naming issues since this is access to global system state.

**Verification:** No verification has yet been done.


### alsa
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Hardware Device Access


**Code analysis:**
- AppArmor rules grant access to `/dev/snd/` and `/dev/snd/*` (read/write)
- UDev rules match sound devices by kernel name patterns (`c116:[0-9]*`, `+sound:card[0-9]*`)
- No D-Bus usage, no shared memory, no instance-specific paths
- Multiple instances access the same physical devices, which is the intended behavior for
  audio (the kernel/ALSA manages concurrent access)

**Reasoning:** Audio devices are global hardware resources. Multiple snaps (parallel or
not) accessing `/dev/snd/*` is already the normal case. The AppArmor rules are purely
device-path-based and don't reference snap names at all.

**Verification:**
PASSED on noble.

### pulseaudio
**Status:** Plug-side: COMPATIBLE. Slot-side: not separately classified in this entry (provider behavior out of scope here).

**Type:** Daemon/Socket Client


**Code analysis:**
- Shared memory: `/{run,dev}/shm/pulse-shm-* mrwk,` (`pulseaudio.go:49`, also `:118`)
  grants access to PulseAudio shared memory segments. These are NOT namespaced per snap
  instance. However, this is intentional -- all PulseAudio clients share the same SHM
  segments with the server. Multiple clients is the normal operating mode.
- **No D-Bus usage**: The pulseaudio interface does NOT use D-Bus at all. Communication
  is exclusively via UNIX sockets (`/run/user/*/pulse/native`) and POSIX shared memory.
  The previous audit incorrectly claimed "Global D-Bus name binding".
- Instance-aware runtime paths: `slot.Snap().InstanceName()` at `pulseaudio.go:164` is
  used to scope the runtime socket directory, meaning each slot provider gets its own
  socket path.
- Plug-side: The connected plug template uses `###SLOT_SECURITY_TAGS###` which is
  replaced with the slot's instance name, correctly scoping which server a client talks
  to.

**Reasoning:** PulseAudio is designed for multiple simultaneous clients. The shared
memory segments (`pulse-shm-*`) are created by the PA server and shared with all
connected clients -- having two snap instances connect as clients is no different from
having two different snaps connect. Slot-side (running multiple PA servers) would
conflict, but that's not a parallel-install concern.

**Previous audit errors**:
- Claimed "Global D-Bus name binding" -- INCORRECT. No D-Bus is used.
- Claimed "NOT COMPATIBLE" -- INCORRECT. Plug-side works fine.

**Verification:**
PASSED on noble.


### x11
**Status:** Plug-side: COMPATIBLE. Slot-side: not separately classified in this entry (provider behavior out of scope here).

**Type:** Desktop/Graphics/Media Integration


**Code analysis:**
- Slot-side creates sockets at `/tmp/.X11-unix/X[0-9]*`. Multiple X servers on
  different display numbers (X0, X1) can coexist.
- Plug-side accesses the slot's private tmp via bind mount. The mount path uses
  instance-aware naming: `/tmp/snap-private-tmp/snap.INSTANCE_NAME/tmp/.X11-unix/`
- Instance name comparison at the interface code uses `plug.Snap().InstanceName()` and
  `slot.Snap().InstanceName()` for correct scoping.
- `LabelExpression()` used for AppArmor peer matching uses `InstanceName()`, so
  cross-instance connections work correctly.

**Reasoning:** When a plug connects to a specific slot, the mount namespace setup
correctly isolates the socket sharing. Parallel instances of a client snap each get their
own mount namespace entry. Parallel instances of a server snap would use different
display numbers.

**Verification:**
PASSED on noble (parallel instances communicate correctly via
  instance-scoped private tmp).



### wayland
**Status:** Plug-side: COMPATIBLE. Slot-side: not separately classified in this entry (provider behavior out of scope here).

**Type:** Desktop/Graphics/Media Integration


**Code analysis:**
- Plug-side accesses `/run/user/[0-9]*/wayland-[0-9]*` sockets provided by the
  compositor (slot). Multiple client snaps connecting to the same Wayland compositor is
  the normal use case.
- `plug.Snap().InstanceName()` at the interface code is used for instance-specific mount
  namespace setup.
- Shared memory paths in the connected slot use instance-aware naming via
  `###PLUG_SECURITY_TAGS###` substitution.

**Reasoning:** Wayland is inherently multi-client. Multiple snap instances connecting as
clients to the same compositor is functionally identical to having multiple different
snaps as clients. Slot-side (running multiple compositors) would require coordination
over socket naming but is out of scope for parallel installs of a client snap.

**Previous audit errors**:
- Claimed "NOT COMPATIBLE" due to "Shared memory" and "Global socket paths" -- INCORRECT
  for plug-side usage.

**Verification:**
PASSED on ubuntu-22.04-64 (noble is disabled for this test).




### network-control
**Status:** Plug-side: COMPATIBLE. Slot-side: not separately classified in this entry (provider behavior out of scope here).

**Type:** Network/Netlink Interface


**Code analysis:**
- The connected plug AppArmor rules at `network_control.go:81-151` only use `dbus send`
  (sending messages to `org.freedesktop.resolve1`). The interface acts as a **D-Bus
  client**, it does NOT own/bind any D-Bus name.
- The interface grants broad network capabilities (raw sockets, netlink, WPA supplicant
  access, network namespace management), but these are all global system resources that
  multiple consumers can use simultaneously.
- No `SNAP_NAME` or `SNAP_INSTANCE_NAME` is used in the AppArmor rules -- they are
  purely capability-based.

**Reasoning:** network-control grants system-level network manipulation capabilities.
Multiple instances with network-control all get the same privileges, just like multiple
different snaps with network-control. They can all modify routing tables, ARP entries,
etc. without conflicting at the interface/AppArmor level (though they could conflict at
the operational level if they set contradictory routes).

**Previous audit errors**:
- Claimed "Global D-Bus names: Lines 88-153 bind to org.freedesktop.resolve1" --
  INCORRECT. The interface only SENDS to resolved, it never binds/owns.
- Claimed test "failed on noble, as expected" -- INCORRECT. Test passed.

**Verification:**
PASSED on noble.



### network-bind
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Network/Netlink Interface


**Code analysis:**
- Grants capability to bind to network ports and accept connections.
- No D-Bus name ownership, no shared memory, no instance-specific paths.
- Multiple instances can each bind to different ports without conflict.

**Reasoning:** Pure network capability. Same as two different snaps each binding a port.

**Verification:**
PASSED on noble.



### network-status
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Network/Netlink Interface


**Code analysis:**
- Read-only D-Bus access to the `org.freedesktop.portal.NetworkMonitor` portal.
- No D-Bus ownership, no writes, no shared state.
- Multiple consumers reading network status simultaneously is the normal case.

**Verification:**
PASSED on noble.



### network-setup-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Network/Netlink Interface


**Code analysis:**
- Read-only file access to netplan configuration (`/etc/netplan/`, `/etc/network/`)
- Read-only D-Bus access to Netplan Info API
- No write operations, no shared resources, no instance-specific paths

**Verification:**
PASSED on noble.



### network-manager
**Status:** Plug-side: not separately classified in this entry. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
The network-manager interface is a system singleton service with multiple fatal conflicts
for parallel installs:

1. **D-Bus well-known name ownership** (`network_manager.go:196-202`): The permanent slot
   AppArmor rules hardcode `dbus (bind) bus=system name="org.freedesktop.NetworkManager"`.
   Only one process can own this name. Two parallel instances would race for ownership.

2. **D-Bus bus policy** (`network_manager.go:380,408-413`): The `DBusPermanentSlot`
   generates bus config with `<allow own="org.freedesktop.NetworkManager"/>`. While
   file names are instance-specific (via security tag), the content allows both instances
   to own the same name -- creating a race condition.

3. **Shared filesystem state** (`network_manager.go:100-123`): Permanent slot AppArmor
   grants `rw` access to hardcoded global paths:
   - `/run/NetworkManager/{,**}` -- runtime state
   - `/etc/netplan/{,**}` -- network configuration
   - `/run/resolvconf/{,**}` -- DNS resolution
   Two parallel instances writing to these paths would corrupt each other's state.

4. **Connected plug/slot rules ARE instance-aware**: `AppArmorConnectedPlug` (line 543)
   uses `slot.LabelExpression()` and `AppArmorConnectedSlot` (line 563) uses
   `plug.LabelExpression()`, so cross-snap connections are correctly scoped. But this
   doesn't help when the D-Bus name routing sends to the wrong instance.

**Reasoning:** NetworkManager is architecturally a system-wide singleton. The D-Bus
well-known name `org.freedesktop.NetworkManager` is defined by the upstream
freedesktop.org specification and cannot be per-instance. The shared runtime state paths
reflect that NM manages global system network configuration.

**Verification:**
Expected failure on Ubuntu Core 18. The `_foo` nmcli initially works
  while the original is present (both instances share the original's NM service via
  D-Bus). After `snap remove --purge network-manager`, snapd disconnects
  `network-manager_foo:nmcli` from the removed `network-manager:service` slot. The
  `_foo` nmcli then gets `Error: Could not create NMClient object: Could not connect:
  Permission denied` because it can no longer reach the system D-Bus socket
  (`apparmor="DENIED" operation="connect" profile="snap.network-manager_foo.nmcli"
  name="/run/dbus/system_bus_socket"`).




### location-control
**Status:** Plug-side: COMPATIBLE. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
- The SLOT permanently binds `dbus (bind) bus=system name="com.ubuntu.location.Service"`
- The PLUG only sends/receives on that bus name
- When a parallel instance provides the slot, it tries to own the same D-Bus name. Only
  one process can own a well-known D-Bus name at a time.
- AppArmor peer labels are instance-specific (`snap.INSTANCE_NAME.app`), so consumer_foo
  is only allowed to talk to provider_foo, but D-Bus routing sends to whoever currently
  owns the name (the original provider).

**Reasoning:** The fundamental issue is D-Bus well-known name uniqueness. Two instances
of the same provider snap cannot both own `com.ubuntu.location.Service`. A parallel
consumer connecting to the system's location service (not a parallel slot) would work
fine.

**Verification:**
Expected failure. `org.freedesktop.DBus.Error.AccessDenied: An AppArmor
  policy prevents this sender from sending this message to this recipient;
  label="snap.test-snapd-location-control-provider_foo.consumer (enforce)"
  destination=... label="snap.test-snapd-location-control-provider.provider (enforce)"`.
  The parallel consumer_foo tries to reach its own provider_foo, but D-Bus routes to the
  original provider (which owns the well-known name), and AppArmor denies the mismatch.



### avahi-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: not separately classified in this entry.

**Type:** D-Bus/IPC Client


**Code analysis:**
- The `dbus (bind) bus=system name="org.freedesktop.Avahi"` rule exists ONLY in
  `avahiObservePermanentSlotAppArmor` (`avahi_observe.go:77`) which is applied to the
  **slot-providing snap** (a snap running the Avahi daemon).
- The `AppArmorPermanentSlot` function at `avahi_observe.go:447` explicitly checks
  `implicitSystemPermanentSlot(slot)` -- when the slot is the system (core/snapd), the
  bind rules are NOT applied (the system's own avahi-daemon handles this outside of snap
  confinement).
- The connected PLUG rules (`avahiObserveConnectedPlugAppArmor`) only use `dbus (send)`
  and `dbus (receive)` to communicate with `org.freedesktop.Avahi`. This is read-only
  consumption of the Avahi service.
- Multiple plug-side consumers simultaneously querying Avahi is the normal use case.

**Reasoning:** avahi-observe is a consumer interface. The "NOT COMPATIBLE" label in the
previous audit confused the slot-side (a snap trying to run Avahi) with the plug-side
(a snap querying Avahi). For parallel installs, the relevant question is "can two
instances of my snap both query Avahi?" -- and the answer is yes.

**Previous audit errors**:
- Claimed "NOT COMPATIBLE" due to "Global D-Bus name: binds to org.freedesktop.Avahi" --
  MISLEADING. The bind rule is only for the slot provider, not the plug consumer.

**Verification:**
PASSED on noble.



### contacts-service
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** D-Bus/IPC Client


**Code analysis:**
- Session bus D-Bus access to Evolution Data Server
- Session bus allows multiple simultaneous clients
- No ownership of bus names by the plug-side snap

**Verification:**
PASSED on noble.



### accounts-service
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** D-Bus/IPC Client


**Code analysis:**
- Session bus D-Bus access to `org.gnome.OnlineAccounts` (GNOME Online Accounts)
- The plug only sends/receives on the session bus -- it does not own any bus name
- Multiple instances reading the same per-user account data is the normal use case
- Account state lives in `~/.config/goa-1.0/accounts.conf`, shared across all instances

**Reasoning:** GNOME Online Accounts is a per-user session service. Multiple snap
instances are just additional D-Bus clients reading the same account list.

**Verification:**
PASSED on noble.



### location-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: not separately classified in this entry (provider behavior out of scope here).

**Type:** D-Bus/IPC Client


Same architecture as `location-control` plug-side. A consumer observing location data
from the system service does not conflict with other instances doing the same.

**Verification:** Not separately tested, but same reasoning as avahi-observe applies.



### online-accounts-service
**Status:** Plug-side: COMPATIBLE. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
- Slot binds `dbus (bind) bus=session name="com.ubuntu.OnlineAccounts.Manager"`
- Same D-Bus name uniqueness issue as location-control slot-side



### autopilot-introspection
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** D-Bus/IPC Client


**Code analysis:**
- Slot is provided by core only (lines 24-29), with implicit slots on core and classic (lines 69-70).
- AppArmor rules are session-bus only and read-oriented:
  - Introspection of `/com/canonical/Autopilot/**` (lines 38-43)
  - `GetVersion` and `GetState` on `/com/canonical/Autopilot/Introspection` (lines 44-55)
- Seccomp allows only message-passing syscalls (`recvmsg`, `sendmsg`, `sendto`) (lines 57-63).
- No snap-instance-specific paths are involved.
- No name ownership or bind rules; this is a client-only interface.

**Reasoning:** This interface is for inspecting an application's UI status over D-Bus. Multiple parallel instances are just multiple session-bus clients talking to the same service, and the policy does not depend on snap instance naming. No instance collision points are visible in the code.

**Verification:** No verification has yet been done.

### dbus
**Status:** Plug-side: COMPATIBLE. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
- This interface is explicitly built around a well-known D-Bus name provided by the slot snap.
- Permanent slot policy binds the requested bus name with `dbus (bind)` and grants ownership in the generated D-Bus policy (lines 49-150).
- `getAttribs()` validates the `bus` and `name` attributes and rejects names ending in `-NUMBER` to avoid overlap with parallel-install instance naming (lines 240-265).
- `AppArmorConnectedPlug()` and `AppArmorConnectedSlot()` both compare plug/slot attributes and only emit policy when the names match (lines 316-350, 402-429).
- The generated AppArmor peer labels use `slot.LabelExpression()` and `plug.LabelExpression()`, so the security labels are instance-aware, but the D-Bus well-known name itself is a singleton resource.
- `DBusPermanentSlot()` only emits bus policy for system services, but a parallel app slot still cannot have two instances both binding the same bus name.
- D-Bus activation files are keyed only by bus name (`busName + ".service"`), so parallel providers with the same well-known name overwrite each other's activation entry (`wrappers/dbus.go:137`).

This is the most well-documented incompatibility:

1. **D-Bus activation file conflict** (`wrappers/dbus.go:137`): The activation file is
   named `busName + ".service"` (e.g., `com.dbustest.HelloWorld.service`). This is NOT
   instance-namespaced. When `test-snapd-dbus-provider_foo` is installed, it overwrites
   the activation file that was for `test-snapd-dbus-provider`.

2. **D-Bus bus policy allows both to own** (`interfaces/builtin/dbus.go:353-368`): Each
   instance gets its own policy file (named by security tag), but both grant
   `<allow own="com.dbustest.HelloWorld"/>`. D-Bus only allows ONE process to own a
   well-known name at a time.

3. **AppArmor peer labels are instance-specific**: The connected plug template substitutes
   `###SLOT_SECURITY_TAGS###` with `slot.LabelExpression()` which uses `InstanceName()`.
   So consumer_foo's AppArmor profile expects to talk to
   `snap.test-snapd-dbus-provider_foo.*`, but the actual D-Bus message is routed to
   whoever owns the name -- which is `snap.test-snapd-dbus-provider.*` (the original).

4. **Code acknowledgement** (`interfaces/builtin/dbus.go:84-87`):
   ```
   # Note, snapd does not allow declaring a 'well-known' name that ends with
   # '-[0-9]+' or that contains '_'. Parallel installs of DBus services aren't
   # supported at this time, but if they were, this could allow a parallel
   # install's well-known name to overlap with the normal install.
   ```

**Reasoning:** The `dbus` interface is the canonical singleton-service case. Parallel instances of a provider snap cannot both own the same well-known D-Bus name, so slot-side is not compatible. Plug-side use is fine because multiple consumers can talk to the same service if the connection is set up correctly.

**Verification:** Expected failure observed for parallel provider installs (consumer AppArmor peer label mismatch once D-Bus routes to the winning provider name owner). `org.freedesktop.DBus.Error.AccessDenied: An AppArmor
  policy prevents this sender from sending this message to this recipient;
  label="snap.test-snapd-dbus-consumer_foo.dbus-system-consumer (enforce)"
  destination=... label="snap.test-snapd-dbus-provider.system-provider (enforce)"`.
  Both providers compete for `com.dbustest.HelloWorld`; consumer_foo's AppArmor profile
  expects peer `snap.test-snapd-dbus-provider_foo.*` but D-Bus routes to the original.


### ubuntu-download-manager
**Status:** Plug-side: COMPATIBLE. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
- The permanent slot binds the well-known session-bus name `com.canonical.applications.Downloader` (lines 127-130).
- The permanent slot also grants D-Bus ownership and listen/accept permissions for that daemon role (lines 131-151).
- Connected plug rules are client-only and use `slot.LabelExpression()` for the security peer label (lines 215-221).
- Connected slot rules use `plug.LabelExpression()` and substitute `###PLUG_NAME###` with `plug.Snap().InstanceName()` (lines 228-236), which is instance-aware.
- The download directories under `~/snap/<plug-instance>/common/Downloads/` are instance-specific because the plug name substitution uses `InstanceName()`.

**Reasoning:** Plug-side consumer access is fine: each parallel instance gets its own download directory and talks to the same download service as a client. Slot-side is a singleton service because the session bus name is globally unique, so two parallel provider instances cannot both own `com.canonical.applications.Downloader`.

**Verification:** No verification has yet been done.

### system-trace
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Observability/Diagnostics


**Code analysis:**
- Slot is provided by core only (lines 24-29), with implicit slots on core and classic (lines 71-72).
- AppArmor rules grant access to kernel tracing files under `/sys/kernel/debug/{kprobes,tracing}` and `/sys/kernel/tracing` plus `/usr/src` headers (lines 32-56).
- Seccomp permits `bpf` and `perf_event_open` (lines 58-65).
- No snap-instance-specific paths are used.
- No D-Bus, sockets, or mounts are involved.

**Reasoning:** Kernel tracing is a global system facility. Multiple parallel instances would simply be concurrent consumers of the same tracing APIs. The interface code does not introduce any snap-instance scoping that could conflict.

**Verification:** No verification has yet been done.

### media-hub
**Status:** Plug-side: not separately classified in this entry. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
- The permanent slot binds the well-known session-bus name `core.ubuntu.media.Service` (lines 64-68).
- The slot AppArmor rules also allow request/release-name operations on the session bus and talk to unconfined clients for the service path (lines 49-99).
- The connected slot and plug rules both key access on the security label of the opposite side, but the actual service name remains a singleton resource (lines 102-152).
- The interface exposes session management and MPRIS-like APIs over the same well-known bus object paths.
- No snap-instance-specific filesystem paths are used.

**Reasoning:** Media Hub is a D-Bus service provider interface. Parallel consumers are fine, but parallel providers cannot both own the same well-known service name, so the slot side is a singleton conflict.

**Verification:** No verification has yet been done.

### mir
**Status:** Plug-side: not separately classified in this entry. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
- The permanent slot owns the Mir server runtime resources, including `/run/mir_socket`, `/run/user/[0-9]*/mir_socket`, `/dev/tty[0-9]*`, and `/dev/input/*` (lines 42-71).
- The slot AppArmor also includes `/dev/shm/\#[0-9]*` shared-memory objects and `sys_admin` / `sys_tty_config` capabilities (lines 42-71).
- The Seccomp profile permits server-side socket/listen/accept and netlink uevent handling (lines 73-85).
- The connected plug only gets client access to Mir sockets and shared-memory objects (lines 87-100).

**Reasoning:** Mir is a display-server service interface. Parallel clients are fine, but parallel service providers would compete for the same Mir server runtime paths and privileged system resources, making the slot side a singleton.

**Verification:** No verification has yet been done.

### storage-framework-service
**Status:** Plug-side: not separately classified in this entry. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
- The permanent slot binds `com.canonical.StorageFramework.Registry` and `com.canonical.StorageFramework.Provider.*` on the session bus (lines 55-73).
- The slot AppArmor also writes to `/sys/kernel/security/apparmor/.access` and reads `/sys/module/apparmor/parameters/enabled` and `/proc/*/mounts` as part of policy introspection (lines 42-54).
- Connected slot and plug rules are client-only and use label expressions for peer mediation (lines 75-109).
- The service name is the actual singleton resource; the path patterns are not instance-scoped.

**Reasoning:** This is a D-Bus service provider interface. Parallel consumers are fine, but parallel providers cannot both own the registry/provider bus names.

**Verification:** No verification has yet been done.

### unity8
**Status:** Plug-side: not separately classified in this entry. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
- The connected plug talks to Unity 8 session services over the session bus, including `com.canonical.URLDispatcher` and `com.ubuntu.content.dbus.Service` (lines 45-89).
- The URL dispatcher peer is a well-known bus name, and the content-hub-style interface is presented as a shared session service.
- The slot side is intended to represent the desktop service provider; multiple providers would contend for the same session-bus identities.
- No snap-instance-specific filesystem paths are involved.

**Reasoning:** Unity 8 is a desktop service interface built around well-known D-Bus services. Parallel clients are fine, but parallel service providers would collide on the same bus names.

**Verification:** No verification has yet been done.

### unity8-calendar
**Status:** Plug-side: not separately classified in this entry. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
- The permanent slot binds `org.gnome.evolution.dataserver.Calendar7`, `org.gnome.evolution.dataserver.Subprocess.Backend.Calendar*`, and `com.canonical.SyncMonitor` on the session bus (lines 33-47).
- The slot AppArmor exposes the calendar factory/view/subprocess paths and sync-monitor endpoints to unconfined clients (lines 48-75).
- The connected plug is client-only to the same calendar service paths (lines 77-109).
- The service paths are fixed names and object paths, not snap-instance-scoped resources.

**Reasoning:** This is a calendar service provider interface. Parallel clients are fine, but parallel providers would contend for the same well-known calendar and sync-monitor bus names.

**Verification:** No verification has yet been done.

### unity8-contacts
**Status:** Plug-side: not separately classified in this entry. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
- The permanent slot binds `org.gnome.evolution.dataserver.AddressBook9`, `org.gnome.evolution.dataserver.Subprocess.Backend.AddressBook*`, `com.canonical.pim`, and `com.meego.msyncd` on the session bus (lines 33-54).
- The slot AppArmor exposes address book factory/view/subprocess paths and Canonical PIM paths to unconfined clients (lines 55-93).
- The connected plug is client-only to the same address book service paths (lines 95-183).
- No snap-instance-specific filesystem paths are used.

**Reasoning:** Unity 8 Contacts is another D-Bus service provider interface. Parallel consumers are fine, but parallel providers would collide on the same well-known bus names.

**Verification:** No verification has yet been done.

### screencast-legacy
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: not separately classified in this entry (provider behavior out of scope here).

**Type:** D-Bus/IPC Client


**Code analysis:**
- The plug talks to gnome-shell screenshot/screencast interfaces on the session bus (lines 32-53).
- The API allows absolute file names as method arguments, so the caller can direct output to arbitrary paths permitted by the user.
- The interface does not own a bus name itself, but the permissions are explicitly tied to the desktop session service.
- No snap-instance-specific pathing is used by snapd.

**Reasoning:** The interface is intentionally powerful and can write arbitrary files via gnome-shell. That is not a snap-instance collision per se, but it is not a safe parallel-install interface to analyze as compatible; it is a privileged client-side desktop capability.

**Verification:** No verification has yet been done.

### ros-opt-data
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Filesystem/Mount Interface


**Code analysis:**
- The plug gets read-only access to `/var/lib/snapd/hostfs/opt/ros/**` and common ROS file extensions under that tree (lines 31-49).
- The interface is implicit on classic and not on core, which matches a host filesystem read-only pattern.
- No sockets, mounts, or D-Bus names are involved.
- No snap-instance-specific names are used.

**Reasoning:** ROS static data is read-only host content. Parallel instances can all read the same files without snapd-level collisions.

**Verification:** No verification has yet been done.

### system-backup
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Observability/Diagnostics


**Code analysis:**
- The plug gets read-only access across the host filesystem through `/var/lib/snapd/hostfs/` exclusions and `dac_read_search` (lines 32-47).
- The policy explicitly excludes `/dev`, `/sys`, and `/proc` from the broad read rule and then re-adds narrow cases as needed.
- No D-Bus, sockets, or instance-specific mount paths are present.

**Reasoning:** This is a broad read-only backup interface. Parallel instances are just concurrent readers of the same host data, and the policy does not encode snap-instance-specific paths.

**Verification:** No verification has yet been done.

### system-source-code
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Observability/Diagnostics


**Code analysis:**
- The plug gets read-only access to `/usr/src/{,**}` (line 38).
- The interface is implicit on core and classic and otherwise just exposes source trees/headers.
- No sockets, mounts, or snap-instance-specific names are involved.

**Reasoning:** `/usr/src` is a shared system source tree. Multiple instances can read it concurrently without any instance-name collision.

**Verification:** No verification has yet been done.

### juju-client-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Observability/Diagnostics


**Code analysis:**
- The plug gets read access to `~/.local/share/juju/{,**}` using `owner` file rules (lines 32-35).
- The interface is classic-only and reads the user’s Juju client state; it does not own a bus name.
- No sockets, mounts, or snap-instance-specific names are used.

**Reasoning:** Juju client state is per-user data. Parallel instances under the same user will read the same Juju config/state, which is normal shared-user behavior and not an instance collision.

**Verification:** No verification has yet been done.

### netlink-driver
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Network/Netlink Interface


**Code analysis:**
- The slot is keyed by a numeric `family` attribute and a validated `family-name` (lines 66-100).
- The plug must present a matching `family-name` (lines 104-107, 127-140).
- The connected plug seccomp snippet allows `AF_NETLINK` for the declared family and `bind` (lines 109-124).
- No snap-instance-specific paths are used; the identity is based on the protocol family name, not snap name.

**Reasoning:** Netlink-driver is scoped to a kernel protocol family rather than to snap identity. Parallel instances are safe when they connect to the same declared family or to different families; the interface code does not create a snap-instance collision.

**Verification:** No verification has yet been done.

### core-support
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Hardware Device Access


**Code analysis:**
- This interface is explicitly hollow and grants no permissions (lines 39-41).
- It only exists so callers can test for its presence; `commonInterface` is registered with no AppArmor/seccomp/udev policy.
- No paths, sockets, mounts, or snap-instance-specific logic are present.

**Reasoning:** The interface has no confinement effect at all. Parallel instances cannot collide because there is no policy to collide over.

**Verification:** No verification has yet been done.

### accel
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: NOT COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants access to `/dev/accel/accel*` (lines 4560-4566 in the bucket summary).
- The access is device-node based and tied to global accelerator hardware.
- No instance-specific pathing or name expansion exists in the interface model.

**Reasoning:** Accelerator device nodes are exclusive physical hardware resources. Two parallel instances would contend for the same accelerator device, so this is not a good parallel-install fit.

**Verification:** No verification has yet been done.

### acrn-support
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: NOT COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants access to `/dev/acrn_hsm` (lines 4572-4579 in the bucket summary).
- ACRN management is a single hypervisor control device node.
- No snap-instance-specific logic is involved.

**Reasoning:** This is a single global hypervisor-management device. Parallel instances would compete for the same control node.

**Verification:** No verification has yet been done.

### allegro-vcu
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: NOT COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants access to `/dev/allegroDecodeIP`, `/dev/allegroIP`, and `/dev/dmaproxy` (lines 4583-4590 in the bucket summary).
- These are hardware codec device nodes, not per-instance resources.

**Reasoning:** The codec hardware is shared and effectively exclusive. Parallel instances would contend for the same devices.

**Verification:** No verification has yet been done.

### broadcom-asic-control
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: NOT COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** System Control/Privileged Capability


**Code analysis:**
- The interface grants access to `/dev/linux-user-bde`, `/dev/linux-kernel-bde`, and `/dev/linux-bcm-knet` (lines 4594-4601 in the bucket summary).
- These are ASIC kernel module/device interfaces for a specific hardware platform.

**Reasoning:** Broadcom ASIC control is tied to a single hardware resource and is not instance-isolated.

**Verification:** No verification has yet been done.

### camera
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Desktop/Graphics/Media Integration


**Code analysis:**
- Slot is provided by core only (lines 28-33), with implicit slots on core and classic (lines 80-81).
- AppArmor rules are device-path based and intentionally broad: `/dev/video[0-9]*`, `/dev/vchiq`, and supporting sysfs/udev paths (lines 36-57).
- UDev rules tag video devices (lines 71-74).
- No snap-instance-specific paths are used.
- The interface explicitly notes it allows access to all cameras until better device assignment exists (line 37).

**Reasoning:** The interface is policy-safe for parallel installs, but the camera hardware is shared. Parallel instances can coexist, yet they can still fight over the same camera device or stream.

**Verification:** No verification has yet been done.

### cpu-control
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: NOT COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** System Control/Privileged Capability


**Code analysis:**
- The interface targets `/sys/devices/system/cpu/**` (lines 4628-4635 in the bucket summary).
- It controls governor, scaling, and hotplug settings for the whole system.
- No snap-instance-specific logic is involved.

**Reasoning:** CPU policy is a system-global control surface. Parallel instances changing settings would conflict.

**Verification:** No verification has yet been done.

### dcdbas-control
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: NOT COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** System Control/Privileged Capability


**Code analysis:**
- The interface targets `/sys/devices/platform/dcdbas/*` (lines 4639-4646 in the bucket summary).
- It exposes the Dell Systems Management Base Driver, which is a single system resource.

**Reasoning:** This is a single system-management interface. Parallel instances would contend for the same sysfs knobs.

**Verification:** No verification has yet been done.

### dsp
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: NOT COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants access to `/dev/ucode` and `/dev/iav*` (lines 4650-4657 in the bucket summary).
- These are hardware DSP device nodes.

**Reasoning:** DSP hardware is a single-instance resource. Parallel instances would share/contend for the same device.

**Verification:** No verification has yet been done.

### fpga
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: NOT COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants access to `/dev/fpga[0-9]*` (lines 4661-4668 in the bucket summary).
- These are numbered FPGA device nodes with shared hardware state.

**Reasoning:** FPGA programming/control is hardware-exclusive. Parallel instances programming the same FPGA would conflict.

**Verification:** No verification has yet been done.

### framebuffer
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: NOT COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants access to `/dev/fb[0-9]*` (lines 4672-4679 in the bucket summary).
- Framebuffer devices are global display hardware.

**Reasoning:** Two instances writing the same framebuffer would conflict on the same display device.

**Verification:** No verification has yet been done.

### gpio
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Slots are provided by core or gadget snaps only (lines 35-41), not by app snaps.
- The slot is keyed by a GPIO number attribute and the code resolves the sysfs path via `evalSymlinks()` before emitting rules (lines 83-105).
- The interface also sets up a per-slot systemd service to export/unexport the GPIO line (lines 108-122).
- No snap-instance-specific names are used beyond the slot-supplied GPIO number.

**Reasoning:** GPIO access is tied to a physical pin, not a snap instance. Parallel installs can connect to the same pin or different pins as declared by the slot; there is no instance-name collision in the interface code.

**Verification:** No verification has yet been done.

### gpio-memory-control
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** System Control/Privileged Capability


**Code analysis:**
- Slot is provided by core only (lines 25-30), with implicit slots on core and classic (lines 47-48).
- AppArmor rules grant access to `/dev/gpiomem` (line 38).
- UDev tags the `gpiomem` device (line 41).
- No instance-specific names, sockets, or mounts are used.

**Reasoning:** This is a global GPIO memory device and the interface is just device-path based. Multiple instances can share the same access without snap-instance collisions in snapd policy.

**Verification:** No verification has yet been done.

### hugepages-control
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** System Control/Privileged Capability


**Code analysis:**
- Slot is provided by core only (`hugepages_control.go:29-35`), with implicit slots on core and classic (`hugepages_control.go:74-76`).
- The interface controls system hugepage sysfs and `/proc/sys/vm/*` plus `/{dev,run}/hugepages/` (`hugepages_control.go:39-54`).
- The runtime directory uses `owner`, but that is user/file ownership, not snap-instance scoping (`hugepages_control.go:54`).
- A mount rule permits `/dev/hugepages` (`hugepages_control.go:67`).

**Reasoning:** Hugepages are a global kernel memory facility. Parallel instances would contend for the same system controls.

**Verification:** No verification has yet been done.

### iio
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Slots are provided by core or gadget snaps only (lines 36-42).
- Slot validation requires a device node path under `/dev/iio:deviceN` (lines 77-95).
- AppArmor rules are generated from the specific slot path and derived device name (lines 98-133).
- UDev tags the device by the exact `/dev/iio:deviceN` node (lines 135-141).
- No snap-instance-specific names are used.

**Reasoning:** The interface targets a specific IIO hardware device, not an instance-scoped resource. Parallel installs can connect to the same device or different devices without snapd-level collision.

**Verification:** No verification has yet been done.

### intel-mei
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: NOT COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants access to `/dev/mei[0-9]*` (lines 4727-4734 in the bucket summary).
- Intel MEI is a system-management bus exposed as hardware device nodes.

**Reasoning:** This is a single hardware-management channel. Parallel instances would contend for the same device resource.

**Verification:** No verification has yet been done.

### intel-qat
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: NOT COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants access to `/dev/vfio/*` and IOMMU sysfs (lines 4738-4745 in the bucket summary).
- It targets Intel QuickAssist Technology accelerator hardware.

**Reasoning:** QAT is a shared PCIe accelerator. Parallel instances can’t be treated as isolated consumers in the interface code.

**Verification:** No verification has yet been done.

### io-ports-control
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** System Control/Privileged Capability


**Code analysis:**
- Slot is provided by core only (`io_ports_control.go:24-30`), with implicit slots on core and classic (`io_ports_control.go:57-58`).
- AppArmor grants access to `/dev/port` and `capability sys_rawio` (`io_ports_control.go:32-39`).
- Seccomp allows `ioperm` and `iopl` (`io_ports_control.go:41-49`).
- UDev tags the `port` device (`io_ports_control.go:51`).
- This is full I/O port access for the system.

**Reasoning:** I/O port access is a global machine capability and is inherently not instance-isolated.

**Verification:** No verification has yet been done.

### mediatek-accel
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Slot is provided by core only (lines 33-38), with plug-side `units` selection validated in `BeforePreparePlug()` (lines 94-122).
- The selected units (`apu`, `vcu`) drive AppArmor and udev snippets (lines 71-88, 124-147).
- No snap-instance-specific paths are involved; access is keyed by device type and slot attributes.

**Reasoning:** The interface is device-selector based and not instance-name based. Parallel installs can use the same hardware accelerator devices as long as the declared units match.

**Verification:** No verification has yet been done.

### physical-memory-control
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: NOT COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** System Control/Privileged Capability


**Code analysis:**
- The interface grants read/write access to `/dev/mem` (lines 4805-4813 in the bucket summary).
- This is full physical memory access.

**Reasoning:** This is an extreme system-global privilege and is not a sensible parallel-install target.

**Verification:** No verification has yet been done.

### power-control
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: NOT COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** System Control/Privileged Capability


**Code analysis:**
- The interface targets `/sys/devices/**/power/*` and power-supply knobs (implementation section for `power-control`).
- It controls wakeup, runtime power management, and battery threshold settings for the whole system.

**Reasoning:** Power policy is system-global, so parallel instances would contend for the same controls.

**Verification:** No verification has yet been done.

### ptp
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Network/Netlink Interface


**Code analysis:**
- Slot is provided by core only, with implicit slots on core and classic.
- AppArmor grants access to `/dev/ptp[0-9]*` and related `/sys/class/ptp/` paths.
- UDev tagging is device-based.
- It is a hardware clock device interface with no instance-specific naming.

**Reasoning:** PTP hardware clocks are shared devices. Parallel instances can access the same underlying clock hardware from separate snaps without snapd-level collision.

**Verification:** No verification has yet been done.

### pwm
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Slots are provided by core or gadget snaps only (`pwm.go:36-42`).
- The interface validates `channel` and `chip-number` slot attributes (`pwm.go:53-77`).
- AppArmor rules are generated from the resolved sysfs PWM chip path (`pwm.go:80-107`).
- A systemd service exports/unexports the selected PWM channel (`pwm.go:110-129`).
- It is tied to specific hardware chip/channel values from the slot.

**Reasoning:** There is no snap-instance naming collision in the interface code, so parallel installs are policy-safe. PWM channels are physical outputs, so instances targeting the same chip/channel can still conflict at hardware level.

**Verification:** No verification has yet been done.

### spi
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Slots are provided by core or gadget snaps only (`spi.go:36-43`).
- Slot path validation ensures a concrete `/dev/spidevN.M` node (`spi.go:60-79`).
- AppArmor and UDev rules are generated from the slot path (`spi.go:81-102`).
- It is tied to a numbered SPI bus/chip-select device path.

**Reasoning:** The interface is path/slot-driven and does not introduce snap-instance naming collisions. Parallel instances can still contend if they access the same physical SPI device concurrently.

**Verification:** No verification has yet been done.

### u2f-devices
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE (no side-specific divergence documented in this entry).

**Type:** Identity/Credentials/Secrets


**Code analysis:**
- The interface grants access to `/dev/hidraw*` and related udev/sysfs metadata (`u2f_devices.go:227-243`).
- UDev matching is vendor/product based for known U2F/FIDO tokens (`u2f_devices.go:249-252`).
- It is a physical token interface with device matching rather than instance naming.

**Reasoning:** The interface is policy-safe, but the underlying token is a shared physical device. Parallel instances can contend for the same security key at the application level.

**Verification:** No verification has yet been done.

### uio
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Slots are provided by core or gadget snaps only.
- Slot path validation requires `/dev/uioN` and AppArmor/UDev rules are generated from that path.
- UIO devices are userspace-mapped hardware devices.
- No snap-instance-specific names are involved.

**Reasoning:** The interface is device-based. Multiple instances can share the same access path without snapd-level collision, though the hardware itself may still be shared.

**Verification:** No verification has yet been done.

### usb-gadget
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: NOT COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants broad access to USB gadget configfs (`usb_gadget.go:168-179`).
- FunctionFS mount targets are expanded from the plug snap identity via `expandMountWhereVariable()` (`usb_gadget.go:205`).
- The interface validates persistent mount targets and rejects persistent mounts under `$SNAP_DATA` and `$SNAP_USER_DATA` (`usb_gadget.go:74-81`).
- Configfs remains the system-wide USB peripheral configuration plane.

**Reasoning:** USB gadget configuration is a single system-wide control plane. Parallel instances cannot both safely manage it.

**Verification:** No verification has yet been done.

### vcio
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Slot is provided by core only, with implicit slots on core and classic.
- AppArmor grants access to `/dev/vcio` and related sysfs/udev metadata.
- UDev tagging is device-based.
- It is a single hardware mailbox interface for the VideoCore GPU.

**Reasoning:** This is a shared hardware mailbox rather than a snap-scoped resource. Parallel instances can access it as concurrent clients.

**Verification:** No verification has yet been done.

### auditd-support
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Grants `NETLINK_AUDIT` access and `capability audit_control` (`interfaces/builtin/auditd_support.go:38-53`).
- Allows writing audit daemon state files under `/run` (`interfaces/builtin/auditd_support.go:57-59`).
- Intended to host auditd with kernel audit rule control (`interfaces/builtin/auditd_support.go:22`).

**Reasoning:** Kernel audit configuration is a global control plane. Parallel instances would contend over the same audit subsystem and daemon state.

**Verification:** No verification has yet been done.

### checkbox-support
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Allows `StartTransientUnit` and `KillUnit` on systemd over system bus (`interfaces/builtin/checkbox_support.go:41-57`).
- Receives global job/property signals from systemd (`interfaces/builtin/checkbox_support.go:63-81`).
- Interface purpose is executing arbitrary system tests (`interfaces/builtin/checkbox_support.go:22`).

**Reasoning:** This controls global systemd unit lifecycle and shared host state, so parallel instances can interfere with each other at system level.

**Verification:** No verification has yet been done.

### devlxd
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Grants access to a fixed host socket `/dev/lxd/sock` (`interfaces/builtin/devlxd.go:38-43`).
- Interface is a client API to devlxd inside LXD instances (`interfaces/builtin/devlxd.go:39-40`).

**Reasoning:** No snap-instance naming collision exists in policy; all instances are concurrent clients of the same devlxd endpoint and therefore share daemon state.

**Verification:** No verification has yet been done.

### dm-crypt
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Grants access to device-mapper control, `/dev/dm-*`, `cryptsetup`, and mount operations (`interfaces/builtin/dm_crypt.go:40-57`).
- Allows kernel keyring operations and module loading for dm-crypt (`interfaces/builtin/dm_crypt.go:64-76`).
- Operates on global storage/mount resources under `/run/media` and `/media` (`interfaces/builtin/dm_crypt.go:45-50`).

**Reasoning:** dm-crypt management changes host-wide block-device and mount state; parallel instances can conflict on mapper devices and mount targets.

**Verification:** No verification has yet been done.

### dm-multipath
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Grants read/write access to global multipath config and bindings (`interfaces/builtin/dm_multipath.go:49-53`).
- Grants device-mapper control and multipath daemon socket access (`interfaces/builtin/dm_multipath.go:54-65`).
- Designed to create/reload/remove multipath maps via multipathd (`interfaces/builtin/dm_multipath.go:23-27`).

**Reasoning:** Multipath map management is host-global storage orchestration. Parallel instances can race/override each other while managing the same maps.

**Verification:** No verification has yet been done.

### firmware-updater-support
**Status:** Plug-side: POTENTIALLY COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Interface defines base declarations and identity only; no connected AppArmor/Seccomp snippets (`interfaces/builtin/firmware_updater_support.go:22-46`).
- Intended to identify snaps operating as a firmware updater (`interfaces/builtin/firmware_updater_support.go:22`).

**Reasoning:** The interface itself does not introduce instance-path collisions, but real behavior depends on the updater application/service model using it.

**Verification:** No verification has yet been done.

### greengrass-support
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Grants extensive capabilities for namespaces, mounts, cgroups, ptrace, and device control (`interfaces/builtin/greengrass_support.go:70-353`, `interfaces/builtin/greengrass_support.go:360-400`).
- Uses broad mount/pivot-root rules over snap data paths and host resources (`interfaces/builtin/greengrass_support.go:153-275`).
- Comments note parallel-install handling for SNAP name variables in several rules (`interfaces/builtin/greengrass_support.go:153-155`, `interfaces/builtin/greengrass_support.go:187-189`).

**Reasoning:** Even with explicit parallel-path handling in snippets, this interface manages shared host-level container and cgroup state; multiple instances can interfere materially.

**Verification:** No verification has yet been done.

### iscsi-initiator
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Grants rw access to global iSCSI config/state under `/etc/iscsi/**` (`interfaces/builtin/iscsi_initiator.go:47-65`).
- Grants rw access to iSCSI session/host sysfs control paths (`interfaces/builtin/iscsi_initiator.go:72-85`).
- Connects to shared iscsiadm abstract socket (`interfaces/builtin/iscsi_initiator.go:86-88`).

**Reasoning:** iSCSI initiator configuration and session management are host-global; parallel instances can race on shared config, sessions, and daemon interactions.

**Verification:** No verification has yet been done.

### kernel-module-load
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Interface allows dynamic/on-boot/denied module loading policy via plug attributes (`interfaces/builtin/kernel_module_load.go:56-63`, `interfaces/builtin/kernel_module_load.go:186-223`).
- Supports per-module options and writes module policy through kmod backend (`interfaces/builtin/kernel_module_load.go:190-215`).
- Base declaration denies normal connections by default (`interfaces/builtin/kernel_module_load.go:41-47`).

**Reasoning:** Kernel module load/unload policy is global kernel state; parallel instances can conflict by changing module load behavior and options.

**Verification:** No verification has yet been done.

### remoteproc
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Grants rw access to remoteproc sysfs controls (`firmware`, `state`, `coredump`, `recovery`) (`interfaces/builtin/remoteproc.go:41-46`).
- Controls are addressed by global `remoteprocN` device entries.

**Reasoning:** No snap-instance naming collision appears in policy, but all instances target shared remote processor controls and can interfere.

**Verification:** No verification has yet been done.

### ros-snapd-support
**Status:** Plug-side: POTENTIALLY COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Interface contains only identity/base declarations and no connected security snippets (`interfaces/builtin/ros_snapd_support.go:22-46`).
- Declared purpose is access to snapd apps control API (`interfaces/builtin/ros_snapd_support.go:22`).

**Reasoning:** No direct instance-collision surface exists in interface policy itself; runtime behavior depends on how the consuming snap uses snapd APIs.

**Verification:** No verification has yet been done.

### scsi-generic
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Grants rw access to `/dev/sg[0-9]*` (`interfaces/builtin/scsi_generic.go:38-42`).
- UDev tagging is device-based with no instance naming (`interfaces/builtin/scsi_generic.go:44-47`).

**Reasoning:** Policy is device-path based and not instance-scoped. Parallel instances can be connected, but concurrent access to the same sg device can interfere.

**Verification:** No verification has yet been done.

### shutdown
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Grants system bus calls to reboot/poweroff/halt and login1 shutdown APIs (`interfaces/builtin/shutdown.go:43-55`).
- Adds capability for systemctl socket bind needed by clients (`interfaces/builtin/shutdown.go:81-87`).

**Reasoning:** Shutdown/reboot control is inherently host-global; parallel instances are not isolated and can trigger conflicting system-wide actions.

**Verification:** No verification has yet been done.

### steam-support
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Uses highly permissive AppArmor (`allow all` when supported) and unrestricted seccomp (`@unrestricted`) (`interfaces/builtin/steam_support.go:78-90`, `interfaces/builtin/steam_support.go:386-399`).
- Adds extensive udev access for input/VR devices (`interfaces/builtin/steam_support.go:92-372`).
- No instance-specific pathing is used to separate host-level device access.

**Reasoning:** Parallel instances are likely possible from a naming perspective, but they share the same host input/VR devices and broad privileged host interactions.

**Verification:** No verification has yet been done.

### tee
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Grants rw access to `/dev/tee*`, `/dev/teepriv*`, and `/dev/qseecom` (`interfaces/builtin/tee.go:38-47`).
- UDev rules are device-based and not instance-scoped (`interfaces/builtin/tee.go:49-53`).

**Reasoning:** Interface policy is simple device access with no instance naming collisions. Parallel instances still share the same secure-world device endpoints.

**Verification:** No verification has yet been done.

### uinput
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Grants write access to uinput injection devices (`/dev/uinput`, `/dev/input/uinput`) (`interfaces/builtin/uinput.go:47-53`).
- Interface comments explicitly call out arbitrary input injection risk (`interfaces/builtin/uinput.go:22-33`, `interfaces/builtin/uinput.go:55-63`).

**Reasoning:** Input injection affects global host input state. Multiple parallel instances can interfere by injecting arbitrary events into the same system input stream.

**Verification:** No verification has yet been done.

### userns
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Grants `clone`/`unshare` seccomp permissions for user namespaces (`interfaces/builtin/userns.go:52-56`).
- Adds AppArmor `userns` rule only when parser feature is available (`interfaces/builtin/userns.go:66-91`).
- No fixed shared resource paths or singleton names are involved.

**Reasoning:** This is a capability-style permission rather than shared named resource ownership, so there is no direct parallel-instance naming collision.

**Verification:** No verification has yet been done.

### xilinx-dma
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Grants rw access to XDMA/QDMA device nodes and related sysfs parameters (`interfaces/builtin/xilinx_dma.go:42-61`).
- UDev tagging is subsystem/device based (`interfaces/builtin/xilinx_dma.go:63-68`).
- No snap-instance-specific pathing is used.

**Reasoning:** Interface policy is device-based and does not create instance-name collisions. Parallel instances still contend for the same accelerator hardware and queue resources.

**Verification:** No verification has yet been done.

### raw-input
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants access to `/dev/input/*` and input-device sysfs/udev metadata (lines 44-57 in the implementation).
- UDev tagging is based on input device subsystems, not snap names.
- No snap-instance-specific paths are used.

**Reasoning:** Raw input devices are shared hardware resources. Parallel instances can be granted the same access; the interface does not encode any snap-instance collision point.

**Verification:** Passed on noble. Test at `tests/main/interfaces-raw-input`.

### dvb
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants access to `/dev/dvb/adapter[0-9]*/*` and DVB udev metadata (lines 32-39 in the implementation).
- The interface is device-path based and uses subsystem tagging, not snap naming.

**Reasoning:** DVB adapters are shared hardware devices. Parallel instances can access the same device nodes without snapd-level collision.

**Verification:** Passed on noble. Test at `tests/main/interfaces-dvb`.

### device-buttons
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants access to `/dev/input/event[0-9]*` and supporting input capability files (lines 37-59 in the implementation).
- The interface is backed by udev filtering for GPIO-key events, not by snap-instance-specific paths.

**Reasoning:** Device buttons are input-event hardware. Multiple parallel instances can share the same access; the policy does not key off snap instance names.

**Verification:** Passed on noble. Test at `tests/main/interfaces-device-buttons`.

### uhid
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants write access to `/dev/uhid` (lines 32-38 in the implementation).
- There is no udev tagging because UHID is not represented in sysfs.
- No snap-instance-specific logic is involved.

**Reasoning:** UHID is a shared kernel interface for creating HID devices from userspace. Parallel instances can access the same kernel interface without snapd path collisions.

**Verification:** Passed on noble. Test at `tests/main/interfaces-uhid`.

### block-devices
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE (no side-specific divergence documented in this entry).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants broad access to raw disk block devices, controller character devices, and block-related sysfs/udev metadata (lines 58-132 in the implementation).
- It explicitly avoids partitions in the default policy and only adds partitions when requested.
- No snap-instance-specific names are used.
- The verified test installs a `_foo` instance, connects it independently, verifies it can read the same disk, and confirms it still works after the original snap is removed.

**Reasoning:** Raw block devices are accessible independently to parallel instances at the snapd policy level, which is what the verified test demonstrates. However, the underlying device is still shared hardware, so two snaps can absolutely interfere with each other if they read/write, repartition, mount, format, or otherwise manipulate the same disk at the application level.

**Verification:** Passed on noble. Test at `tests/main/interfaces-block-devices`.

### daemon-notify
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Snapd/Policy Management


**Code analysis:**
- The interface resolves `NOTIFY_SOCKET` from the environment or defaults to `/run/systemd/notify` (lines 56-88 in the implementation).
- It validates the socket path and emits an AppArmor rule for the resolved socket.
- No snap-instance-specific paths are introduced by snapd.

**Reasoning:** This is a client-side notify socket interface. Parallel instances are just concurrent clients talking to systemd’s notify socket; the code does not encode a snap-instance collision.

**Verification:** Passed on noble. Test at `tests/main/interfaces-daemon-notify`.

### browser-support
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Desktop/Graphics/Media Integration


**Code analysis:**
- The interface explicitly uses `@{SNAP_INSTANCE_NAME}` for snap-local runtime socket paths in the sandboxed rules (lines 62-76 in the implementation).
- It also uses owner rules for per-user shared-memory and browser-specific state, and a session D-Bus access to RealtimeKit.
- The policy is intentionally instance-aware for the socket path bits that need it.

**Reasoning:** Browser support already accounts for parallel-install runtime paths with `SNAP_INSTANCE_NAME`. The remaining shared resources are user/session scoped, not snap-scoped.

**Verification:** Passed on noble. Test at `tests/main/interfaces-browser-support`.

### audio-playback
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE.

**Type:** Desktop/Graphics/Media Integration


**Code analysis:**
- Plug-side policy includes instance-aware substitutions for non-implicit slot snaps: `slot.Snap().InstanceName()` is used for both `XDG_RUNTIME_DIR` and `SNAP_COMMON` socket paths (`interfaces/builtin/audio_playback.go:169`, `interfaces/builtin/audio_playback.go:172`).
- Slot-side policy exposes shared audio daemon resources under `/run/pulse`, `/run/user/*/pulse`, and shared memory (`interfaces/builtin/audio_playback.go:97-129`).
- Interface is designed as a shared client/service model with service-side mediation of recording decisions (`interfaces/builtin/audio_playback.go:33-41`).
- The plug side uses PulseAudio/PipeWire shared-memory and socket paths, with an instance-aware path substitution for system mode (`###SLOT_INSTANCE_NAME###`) in the connected plug rules (lines 55-175 in the implementation).
- The slot side exposes standard audio daemon resources and shared memory.
- The interface is designed around shared-client audio IPC, not per-snap exclusive ownership.

**Reasoning:** Parallel instances are handled at the policy level for snap-instance naming, but both sides still interact with a shared audio stack and shared runtime resources.

**Verification:** Passed on noble. Test at `tests/main/interfaces-audio-playback-record`.

### audio-record
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE.

**Type:** Desktop/Graphics/Media Integration


**Code analysis:**
- Interface is explicitly a companion to `audio-playback`, with recording mediation delegated to the audio service (`interfaces/builtin/audio_record.go:28-36`).
- Plug-side adds no distinct exclusive path/name ownership; it just enables the mediated access flow (`interfaces/builtin/audio_record.go:51-55`).
- Slot declaration permits app/core providers and denies auto-connect by default (`interfaces/builtin/audio_record.go:40-49`).

**Reasoning:** There is no snap-instance naming collision in this interface, but recording capability is mediated through a shared audio service and therefore remains a shared runtime resource.

**Verification:** Passed on noble. Covered by `tests/main/interfaces-audio-playback-record`.

### desktop
**Status:** Plug-side: COMPATIBLE. Slot-side: NOT COMPATIBLE.

**Type:** Desktop/Graphics/Media Integration


**Code analysis:**
- Plug-side uses instance-aware paths for document portal mounts via `plug.Snap().InstanceName()` (`interfaces/builtin/desktop.go:737`, `interfaces/builtin/desktop.go:760`).
- Connected plug/slot policy uses label expressions so mediation is per-connection (`interfaces/builtin/desktop.go:724-727`, `interfaces/builtin/desktop.go:813-816`).
- Slot-side permanent policy includes binding well-known desktop service names such as `org.gnome.Shell{,.*}` and `org.gnome.SettingsDaemon{,.*}` (`interfaces/builtin/desktop.go:567-580`).
- Document portal behavior is instance-scoped (`$XDG_RUNTIME_DIR/doc/by-app/snap.<instance>`) and mounted into each snap namespace, which isolates parallel instances at the portal mount layer (`interfaces/builtin/desktop.go:737`, `interfaces/builtin/desktop.go:760-765`).

**Reasoning:** Consumer snaps are parallel-install safe, including the document-portal mount path that is keyed by instance name. Provider snaps attempting to act as a full desktop session service hit singleton D-Bus ownership constraints.

**Verification:** Passed on noble for document-portal mount behavior.

### egl-driver-libs
**Status:** Plug-side: N/A (system/core plug only on classic; parallel app plugs out of scope). Slot-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE.

**Type:** Desktop/Graphics/Media Integration


**Code analysis:**
- Plug installation is limited to `core` and intended as system plug usage on classic (`interfaces/builtin/egl_driver_libs.go:42-50`, `interfaces/builtin/egl_driver_libs.go:169-171`).
- Slot side validates compatibility/priority metadata and exposes vendor files through shared system directories like `/etc/glvnd/egl_vendor.d` (`interfaces/builtin/egl_driver_libs.go:64-93`, `interfaces/builtin/egl_driver_libs.go:105`, `interfaces/builtin/egl_driver_libs.go:108-139`).
- Base declaration explicitly allows multiple slots per plug (`interfaces/builtin/egl_driver_libs.go:47-49`).

**Reasoning:** Interface logic supports multiple providers, but they converge on shared system loader state, so behavior depends on shared global configuration rather than instance isolation.

**Verification:** No verification has yet been done.

### gbm-driver-libs
**Status:** Plug-side: N/A (system/core plug only on classic; parallel app plugs out of scope). Slot-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE.

**Type:** Desktop/Graphics/Media Integration


**Code analysis:**
- Plug installation is restricted to `core` and currently treated as system-plug-only (`interfaces/builtin/gbm_driver_libs.go:46-54`, `interfaces/builtin/gbm_driver_libs.go:177-179`).
- Slot side validates compatibility and exports driver symlinks into architecture-global GBM directories (`interfaces/builtin/gbm_driver_libs.go:70-110`, `interfaces/builtin/gbm_driver_libs.go:121-142`).
- Multiple slots per plug are allowed by base declaration (`interfaces/builtin/gbm_driver_libs.go:51-53`).

**Reasoning:** No snap-instance name collision is encoded, but slot providers share and modify common host graphics-driver resolution paths.

**Verification:** No verification has yet been done.

### nvidia-video-driver-libs
**Status:** Plug-side: N/A (system/core plug only on classic; parallel app plugs out of scope). Slot-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE.

**Type:** Desktop/Graphics/Media Integration


**Code analysis:**
- Plug usage is currently system/core-scoped on classic (`interfaces/builtin/nvidia_video_driver_libs.go:39-47`, `interfaces/builtin/nvidia_video_driver_libs.go:125-127`).
- Slot side validates compatibility and exports shared driver libraries through system library-source integration (`interfaces/builtin/nvidia_video_driver_libs.go:61-83`, `interfaces/builtin/nvidia_video_driver_libs.go:98-106`).
- Declaration allows multiple slots per plug (`interfaces/builtin/nvidia_video_driver_libs.go:44-46`).

**Reasoning:** Designed for composable provider slots, but all providers feed a shared system library environment.

**Verification:** No verification has yet been done.

### opengl-driver-libs
**Status:** Plug-side: N/A (system/core plug only on classic; parallel app plugs out of scope). Slot-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE.

**Type:** Desktop/Graphics/Media Integration


**Code analysis:**
- Plug side is restricted to core/system use on classic (`interfaces/builtin/opengl_driver_libs.go:39-47`, `interfaces/builtin/opengl_driver_libs.go:119-121`).
- Slot side validates compatibility and contributes libraries via shared system library-source plumbing (`interfaces/builtin/opengl_driver_libs.go:61-79`, `interfaces/builtin/opengl_driver_libs.go:92-100`).
- Base declarations allow many slots connected to one system plug (`interfaces/builtin/opengl_driver_libs.go:44-46`).

**Reasoning:** No per-instance ownership conflict is hardcoded, but resulting driver resolution is a shared host-level state.

**Verification:** No verification has yet been done.

### opengles-driver-libs
**Status:** Plug-side: N/A (system/core plug only on classic; parallel app plugs out of scope). Slot-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE.

**Type:** Desktop/Graphics/Media Integration


**Code analysis:**
- Plug side is currently core/system-only on classic (`interfaces/builtin/opengles_driver_libs.go:40-48`, `interfaces/builtin/opengles_driver_libs.go:120-122`).
- Slot side validates compatibility and exports library-source content into shared system resolution paths (`interfaces/builtin/opengles_driver_libs.go:62-80`, `interfaces/builtin/opengles_driver_libs.go:93-101`).
- Multiple slots-per-plug are allowed (`interfaces/builtin/opengles_driver_libs.go:45-47`).

**Reasoning:** Parallel providers are supported structurally, but they still participate in one shared host graphics-library namespace.

**Verification:** No verification has yet been done.

### thumbnailer-service
**Status:** Plug-side: COMPATIBLE. Slot-side: NOT COMPATIBLE.

**Type:** Desktop/Graphics/Media Integration


**Code analysis:**
- Slot side binds a well-known session bus name `com.canonical.Thumbnailer` (`interfaces/builtin/thumbnailer_service.go:60-63`).
- Connected slot policy correctly uses `plug.Snap().InstanceName()` for plug data-path access (`interfaces/builtin/thumbnailer_service.go:130-133`).
- Plug side is a client to the thumbnailer D-Bus API and uses slot label mediation (`interfaces/builtin/thumbnailer_service.go:85-98`, `interfaces/builtin/thumbnailer_service.go:115-119`).

**Reasoning:** Multiple client instances can coexist, but multiple provider instances cannot all own the same well-known D-Bus service name.

**Verification:** No verification has yet been done.

### vulkan-driver-libs
**Status:** Plug-side: N/A (system/core plug only on classic; parallel app plugs out of scope). Slot-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE.

**Type:** Desktop/Graphics/Media Integration


**Code analysis:**
- Plug side is restricted to core/system scope on classic (`interfaces/builtin/vulkan_driver_libs.go:45-53`, `interfaces/builtin/vulkan_driver_libs.go:291-293`).
- Slot side validates compatibility and structured JSON metadata, then populates shared directories `/etc/vulkan/icd.d`, `/etc/vulkan/implicit_layer.d`, and `/etc/vulkan/explicit_layer.d` (`interfaces/builtin/vulkan_driver_libs.go:67-96`, `interfaces/builtin/vulkan_driver_libs.go:107-116`, `interfaces/builtin/vulkan_driver_libs.go:240-259`).
- Base declaration allows `slots-per-plug: *` (`interfaces/builtin/vulkan_driver_libs.go:50-52`).

**Reasoning:** Interface is intentionally multi-provider, but providers act on shared global Vulkan loader state rather than isolated instance-owned state.

**Verification:** No verification has yet been done.

### kerberos-tickets
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE (no side-specific divergence documented in this entry).

**Type:** Identity/Credentials/Secrets


**Code analysis:**
- The interface grants owner access to `/var/lib/snapd/hostfs/tmp/krb5cc*` (line 33 in the implementation).
- It is a file-access interface for Kerberos ticket caches.
- No sockets, mounts, or snap-instance-specific names are used.

**Reasoning:** Kerberos ticket caches are per-user runtime files, so the snapd policy is fine, but parallel instances can still overwrite or invalidate each other's tickets because they share the same cache namespace.
The cache filename is typically session-specific and may look random (for example `krb5cc_*`), so this is not a snap-instance naming collision. The concern here is shared per-user/session state rather than two instances deterministically targeting the same queue or socket name.
`snap run` rewrites `KRB5CCNAME` from the caller's environment into `/var/lib/snapd/hostfs/tmp/krb5cc*`, so different users can naturally end up pointing at different Kerberos caches. That is user/session scoping, not parallel-instance scoping: two instances run by the same user generally share the same cache, while different users can have different caches regardless of snap instance name.

**Verification:** Passed on noble. Test at `tests/main/interfaces-kerberos-tickets`.

### adb-support
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Hardware Device Access


**Code analysis:**
- The interface tags USB devices by vendor ID and emits udev rules for matching devices (lines 129-190 in the implementation).
- The generated udev rules are keyed by the snap security tag, which is instance-aware.
- AppArmor grants access to `/dev/bus/usb/...`, udev metadata, and USB serial number sysfs files.
- No snap-instance-specific paths are involved.

**Reasoning:** ADB support is device- and vendor-based, and the udev mediation uses the snap security tag so parallel instances stay separated at the policy layer. Parallel instances can share the same USB debugging access without snapd-level collision.

**Verification:** Passed on noble. Test at `tests/main/interfaces-adb-support`.

### netlink-audit
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Network/Netlink Interface


**Code analysis:**
- The interface grants `AF_NETLINK - NETLINK_AUDIT` access and netlink-related capabilities (lines 40-60 in the implementation).
- `BeforeConnectPlug()` checks host AppArmor parser support for `cap-audit-read`.
- No snap-instance-specific paths are used.

**Reasoning:** Netlink audit is a shared kernel subsystem. Multiple instances can use it concurrently as clients of the kernel audit facility.

**Verification:** Passed on noble. Test at `tests/main/interfaces-netlink-audit`.

### netlink-connector
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Network/Netlink Interface


**Code analysis:**
- The interface grants `AF_NETLINK - NETLINK_CONNECTOR` access and `CAP_NET_ADMIN` (lines 32-49 in the implementation).
- The policy intentionally allows communications via all netlink connectors.
- No snap-instance-specific paths are used.

**Reasoning:** The connector is a shared kernel messaging facility. Parallel instances can use it concurrently; no snap-instance naming issue exists.

**Verification:** Passed on noble. Test at `tests/main/interfaces-netlink-connector`.

### bluez
**Status:** Plug-side: COMPATIBLE. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
The bluez interface manages Bluetooth services. It follows the same pattern as
network-manager -- a system singleton D-Bus service.

1. **D-Bus well-known name ownership** (`bluez.go:86-103`): The permanent slot AppArmor
   binds four hardcoded names:
   ```
   dbus (bind) bus=system name="org.bluez",
   dbus (bind) bus=system name="org.bluez.obex",
   dbus (bind) bus=system name="org.bluez.obex.*",
   dbus (bind) bus=system name="org.bluez.mesh",
   ```
   These are globally unique. Two parallel slot instances cannot both own them.

2. **D-Bus bus policy** (`bluez.go:213-242`): `DBusPermanentSlot` (line 259) emits
   `<allow own="org.bluez"/>` etc. File names are per-instance (security tag), but
   content grants the same name ownership to all instances.

3. **Connected rules ARE instance-aware** (`bluez.go:266-287`): On Core,
   `AppArmorConnectedPlug` uses `slot.LabelExpression()` (line 272) and
   `AppArmorConnectedSlot` uses `plug.LabelExpression()` (line 282). On classic,
   the plug uses `unconfined` for the system's bluez daemon.

4. **Shared hardware paths** (`bluez.go:59-68`): Permanent slot grants access to
   `/sys/devices/**/bluetooth/**`, `/dev/rfkill` -- inherently global hardware.

5. **UDev** (`bluez.go:289-292`): Tags `KERNEL=="rfkill"` for the plug side.

**Reasoning:** Like network-manager, bluez is architecturally a system singleton. The
D-Bus names (`org.bluez`, etc.) are defined by the upstream BlueZ specification. For
plug-side usage (a snap consuming Bluetooth services from the system), parallel
instances work fine since they're just D-Bus clients. For slot-side (providing the
bluez service), only one instance can operate.

**Verification:** 

- **Result:** PASSED on noble (plug-side). Parallel `bluez_foo` client connected to
original service slot; after original removed, `_foo` self-connected its own service
slot (no D-Bus name conflict with only one instance running).



### bluetooth-control
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** System Control/Privileged Capability


**Code analysis:**
- Slot is provided by core only (lines 24-29), with implicit slots on core and classic (lines 70-71).
- AppArmor rules grant access to Bluetooth kernel interfaces and device nodes (`/sys/devices/**/bluetooth/**`, `/dev/vhci`, `/dev/stpbt`) (lines 32-56).
- Seccomp only adds `bind` (lines 58-62).
- UDev rules match Bluetooth-related subsystems (line 64).
- No snap-instance-specific paths, D-Bus names, or sockets are involved.

**Reasoning:** This interface controls the system Bluetooth stack, which is a global kernel/service resource. Multiple parallel instances can be granted the same access; the code does not create snap-instance collisions.

**Verification:** No verification has yet been done.

### gpio-chardev
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Hardware Device Access


**Code analysis:**
- Slots are provided by gadget snaps (lines 50-55), and the interface uses instance-aware names throughout the setup.
- `slot.Snap().InstanceName()` and `plug.Snap().InstanceName()` are used to build `/dev/snap/gpio-chardev/<instance>/<name>` paths (lines 136-187).
- The systemd service for the slot exports the virtual device using the slot instance name and slot name (lines 127-156).
- UDev tagging uses an instance-aware tag (`snap_<instance>_interface_gpio_chardev_<slot>`) (lines 193-196).
- A conflict with `gpio` is explicitly declared via `conflictingConnectedInterfaces: []string{"gpio"}` (lines 207-210).

**Reasoning:** The interface is carefully namespaced by snap instance for both slot and plug paths, so parallel installs do not collide. The only conflict is with the legacy `gpio` interface, which is intentional and unrelated to parallel naming.

**Verification:** No verification has yet been done.

### kernel-module-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Observability/Diagnostics


**Code analysis:**
- Slot is provided by core only (lines 24-29), with implicit slots on core and classic (lines 54-55).
- AppArmor grants read access to `/proc/modules`, `/sys/module/**`, and modprobe config directories (lines 32-48).
- The interface notes that `kmod` is used only for querying and seccomp/no-SYS_MODULE prevent loading/removal (line 34).
- No snap-instance-specific paths are used.

**Reasoning:** This is read-only kernel module observation. Parallel instances can all read the same global module state without colliding at the interface level.

**Verification:** No verification has yet been done.

### ppp
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Network/Netlink Interface


**Code analysis:**
- Slot is provided by core only (lines 24-29), with implicit slots on core and classic (lines 70-71).
- AppArmor grants access to `/usr/sbin/pppd`, `/etc/ppp/**`, `/dev/ppp`, tty devices, lock files, and log directories (lines 32-52).
- KMod and UDev support are declared for `ppp_generic` and the relevant devices (lines 54-64).
- No snap-instance-specific paths are used.

**Reasoning:** PPP is a global daemon/device interface. Parallel instances behave as ordinary clients of the same system PPP stack; the policy does not encode any instance-specific paths.

**Verification:** No verification has yet been done.

### qualcomm-ipc-router
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Hardware Device Access


**Code analysis:**
- The interface supports both system and app slots, and the app-slot path is fully instance-aware via `slot.LabelExpression()` and `plug.LabelExpression()` (lines 195-241).
- Slot attributes `qcipc` and `address` are validated, and the socket address is injected directly into AppArmor/Seccomp snippets (lines 174-192, 244-263).
- The code explicitly avoids instance-unsafe matching by separating system-slot compatibility and app-slot handling.
- No snap-instance-specific paths are hardcoded; paths are derived from slot attributes.

**Reasoning:** The interface is socket-address based and already uses the snap labels correctly where needed. The code does not show a parallel-install collision surface.

**Verification:** No verification has yet been done.

### tpm
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Slot is provided by core only (lines 24-29), with implicit slots on core and classic (lines 49-50).
- AppArmor grants access to `/dev/tpm[0-9]*` and `/dev/tpmrm[0-9]*` (lines 32-38).
- UDev tags TPM devices (lines 40-43).
- No snap-instance-specific names, sockets, or mounts are involved.

**Reasoning:** TPM is a global hardware device. The interface is pure device access and does not encode any snap-instance-specific scoping.

**Verification:** No verification has yet been done.

### udisks2
**Status:** Plug-side: COMPATIBLE. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
The udisks2 interface manages disk/storage services. Same singleton pattern.

1. **D-Bus well-known name ownership** (`udisks2.go:87-89`): Permanent slot AppArmor
   binds `dbus (bind) bus=system name="org.freedesktop.UDisks2"`. Hardcoded, not
   instance-aware.

2. **D-Bus bus policy** (`udisks2.go:239-247`): `DBusPermanentSlot` (line 420) emits
   `<allow own="org.freedesktop.UDisks2"/>`.

3. **Connected rules ARE instance-aware** (`udisks2.go:427-438`): On Core,
   `AppArmorConnectedPlug` uses `slot.LabelExpression()` (line 433).
   `AppArmorConnectedSlot` (line 472) uses `plug.LabelExpression()`.
   On classic, plug uses `unconfined`.

4. **Shared runtime state** (`udisks2.go:113-114,132-138`): Permanent slot grants
   `/run/udisks2/{,**} rw` -- a hardcoded shared runtime directory. The code comments
   (line 113) acknowledge this should probably use `$SNAP_DATA/run/...` instead.
   Also grants access to `/{,run/}media/**` for mount points.

5. **UDev** (`udisks2.go:447-470`): Reads user-provided udev rules from slot snap's
   `$SNAP/lib/udev/rules.d/` directory.

**Reasoning:** Same as bluez/network-manager. The D-Bus name
`org.freedesktop.UDisks2` is a freedesktop.org specification singleton. The shared
`/run/udisks2/` runtime directory would cause data corruption between parallel
instances. Plug-side (querying disk info) works fine since it's just a D-Bus client.

**Verification:**
- **Results:** PASSED on noble (plug-side). Parallel `test-snapd-udisks2_foo`
queried disk status and objects via the system's UDisks2 service; survived removal
of original snap.



### upower-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
The upower-observe interface provides access to the UPower power management service.

1. **D-Bus name ownership** (`upower_observe.go:72-74`): Permanent slot AppArmor binds:
   ```
   dbus (bind)
       bus=system
       name="org.freedesktop.UPower",
   ```
   Hardcoded singleton. Two parallel slot providers cannot coexist.

2. **DBusPermanentSlot** (`upower_observe.go:259-264`): Guarded by
   `implicitSystemPermanentSlot()` -- only emits bus policy for app snaps (not system
   slot). Policy grants `<allow own="org.freedesktop.UPower"/>`.

3. **Connected plug is system-aware** (`upower_observe.go:266-277`): Uses
   `implicitSystemConnectedSlot()` guard -- on classic (system slot), plug uses
   `peer=(label=unconfined)`. On Core with app slot, uses `slot.LabelExpression()`
   (instance-aware).

4. **Connected slot is instance-aware** (`upower_observe.go:279-287`): Uses
   `plug.LabelExpression()` on Core.

5. **Shared paths in permanent slot** (`upower_observe.go:49-110`): Grants access to
   `/sys/devices/**/power_supply/**`, `/run/udev/data/+power_supply:*` -- global
   hardware/system paths, inherently shared.

**Reasoning:** Same singleton pattern as bluez/udisks2/network-manager. The `org.freedesktop.UPower`
D-Bus name is defined by the freedesktop spec. For plug-side (reading battery/power
info from the system), parallel instances work fine since they're just D-Bus clients.
For slot-side (providing the UPower service), only one instance can operate.

**Verification:**
- **Results:** PASSED on noble.



### ofono
**Status:** Plug-side: not separately classified in this entry. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
The ofono interface provides telephony services via the ofono daemon.

1. **D-Bus name ownership** (`ofono.go:123-125`): Permanent slot AppArmor binds:
   ```
   dbus (bind)
       bus=system
       name="org.ofono",
   ```
   Hardcoded singleton.

2. **DBusPermanentSlot** (`ofono.go:323-326`): Emits bus policy unconditionally (no
   `implicitSystemPermanentSlot` guard). Policy grants:
   ```xml
   <allow own="org.ofono"/>
   <allow send_interface="org.ofono.SimToolkitAgent"/>
   ```

3. **Connected plug** (`ofono.go:328-340`): Uses `slot.LabelExpression()` on Core,
   `unconfined` on classic. Instance-aware for Core connections.

4. **Connected slot** (`ofono.go:342-353`): Uses `plug.LabelExpression()`.
   Instance-aware.

5. **Shared device paths** (`ofono.go:57-120`): Permanent slot grants:
   - `/dev/tty[A-Z]*[0-9]* rw` -- serial/modem devices
   - `/dev/modem* rw`
   - `/dev/cdc-* rw`
   - `/run/udev/data/+usb:*` -- USB device data
   - `/run/ofono/{,**} rw` -- runtime state directory

6. **No `implicitSystemPermanentSlot` guard**: The `DBusPermanentSlot` and
   `AppArmorPermanentSlot` are applied to ALL slot snaps, not just app snaps. This means
   even without parallel installs, every snap with an ofono slot gets the same bus policy.

**Reasoning:** System singleton. The D-Bus name `org.ofono` plus shared `/run/ofono/`
runtime state make this fundamentally single-instance. Additionally, the hardware
device paths (`/dev/tty*`, `/dev/modem*`) are global physical resources.

**Verification:** No spread test exists for this interface. Cannot write a parallel
instance test because there is no test snap or hardware emulation available. The
incompatibility is confirmed by code analysis only (D-Bus singleton `org.ofono` at
`ofono.go:123-125`).



### modem-manager
**Status:** Plug-side: not separately classified in this entry. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
The modem-manager interface provides cellular modem management via ModemManager.

1. **D-Bus name ownership** (`modem_manager.go:106-108`): Permanent slot AppArmor binds:
   ```
   dbus (bind)
       bus=system
       name="org.freedesktop.ModemManager1",
   ```
   Hardcoded singleton.

2. **DBusPermanentSlot** (`modem_manager.go:341-345`): Guarded by
   `!implicitSystemPermanentSlot(slot)`. Policy grants
   `<allow own="org.freedesktop.ModemManager1"/>`.

3. **Connected plug** (`modem_manager.go:347-360`): Uses `slot.LabelExpression()` on
   Core, `unconfined` on classic. Instance-aware.

4. **Connected slot** (`modem_manager.go:362-373`): Uses `plug.LabelExpression()`.
   Instance-aware.

5. **Shared device paths** (`modem_manager.go:49-104`): Permanent slot grants:
   - `/dev/tty[A-Z]*[0-9]* rw` -- serial/modem devices
   - `/dev/cdc-* rw`
   - `/dev/modem* rw`
   - `/dev/wwan* rw`
   - `/run/udev/data/*` -- all udev data
   - `/sys/devices/**/usb[0-9]*/**` -- USB sysfs

6. **UDevPermanentSlot**: Tags multiple modem-related kernel devices
   (`ttyACM*`, `ttyUSB*`, `cdc-wdm*`, `wwan*`, etc.).

**Reasoning:** Same as ofono -- system singleton. The D-Bus name
`org.freedesktop.ModemManager1` is a freedesktop.org specification singleton. Shared
device and runtime paths make parallel slot providers impossible.

**Verification:** No spread test exists for this interface. Cannot write a parallel
instance test because there is no test snap or modem hardware emulation available. The
incompatibility is confirmed by code analysis only (D-Bus singleton
`org.freedesktop.ModemManager1` at `modem_manager.go:106-108`).



### unity7
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: NOT COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Desktop/Graphics/Media Integration


**Code analysis:**
The unity7 interface grants access to Unity7/GNOME desktop session services. It has a
**known, documented parallel-install issue**.

1. **The documented issue** (`unity7.go:679-681`):
   ```go
   // parallel-installs: UNITY_SNAP_NAME is used in the context of dbus
   // mediation, this unintentionally opens access to dbus paths of keyed
   // instances of @{SNAP_NAME} to @{SNAP_NAME} snap
   ```

2. **How `###UNITY_SNAP_NAME###` is replaced** (`unity7.go:682-685`):
   ```go
   new := strings.Replace(plug.Snap().DesktopPrefix(), "-", "_", -1)
   new = strings.Replace(new, "+", "_", -1)
   old := "###UNITY_SNAP_NAME###"
   snippet := strings.Replace(unity7ConnectedPlugAppArmor, old, new, -1)
   ```
   `DesktopPrefix()` (`snap/info.go:975`) returns `name+key` for parallel instances
   (e.g., `mysnap+foo`). After replacing `-` and `+` with `_`, this becomes `mysnap_foo`.
   For the base instance (no key), it returns just `mysnap`.

3. **D-Bus path rules that use the snap name** (`unity7.go:534-549`):
   ```
   # When @{SNAP_NAME} == @{SNAP_INSTANCE_NAME}, this rule
   # allows the snap to access parallel installs of this snap.
   dbus (receive)
       bus=session
       path=/com/canonical/indicator/messages/###UNITY_SNAP_NAME###_*_desktop
   ```
   For the base instance `mysnap`, this expands to:
   `path=/com/canonical/indicator/messages/mysnap_*_desktop`
   The wildcard `*` matches ANY instance key suffix -- so `mysnap` can see D-Bus paths
   for `mysnap_foo`, `mysnap_bar`, etc.

4. **The leakage direction**: The base instance gets a broader wildcard that encompasses
   parallel instances' paths. A parallel instance `mysnap+foo` gets rules with
   `mysnap_foo_*_desktop` which is narrower and doesn't leak back. The issue is
   one-directional: base instance can access parallel instances' D-Bus indicator paths.

5. **dbus (bind) in connected plug** (`unity7.go:405-407`):
   ```
   dbus (bind)
       bus=session
       name=org.kde.StatusNotifierItem-[0-9]*,
   ```
   This is PID-indexed (not snap-name-indexed), so no parallel install conflict here.

6. **No AppArmorConnectedSlot method**: The unity7 interface only has
   `AppArmorConnectedPlug`. The slot is always implicit (system-provided on classic).

**Reasoning:** This is a known, documented code issue. The D-Bus path pattern
`/com/canonical/indicator/messages/###UNITY_SNAP_NAME###_*_desktop` uses
`DesktopPrefix()` which for the base instance produces `snapname`, and the `_*_`
wildcard inadvertently matches parallel instances' indicator paths. This breaks D-Bus
path isolation between parallel instances -- the base snap can receive D-Bus messages
intended for `snap_foo`'s indicator.

**Verification:** No dedicated spread test exists for this interface's parallel-install
issue. The bug is a D-Bus path wildcard leakage (information leak, not a hard failure),
which would require a custom test with two snap instances and D-Bus introspection to
demonstrate. The incompatibility is confirmed by the explicit code comment at
`unity7.go:679-681` acknowledging the issue.




### content
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Filesystem/Mount Interface


**Code analysis:**
The content interface is the most complex interface for parallel installs because it
creates bind mounts between snaps. The code handles parallel instances correctly through
careful use of perspective-based path expansion.

1. **Source/target path resolution** (`content.go:226-245`, `sourceTarget()`):
   ```go
   source := resolveSpecialVariable(relSrc, slot.Snap(), snap.PerspectiveOther)
   target := resolveSpecialVariable(target, plug.Snap(), snap.PerspectiveSelf)
   ```
   - **Source (provider/slot)**: Uses `PerspectiveOther` which calls `InstanceName()`.
     For a parallel slot `producer_foo`, paths resolve to `/snap/producer_foo/rev/...`.
   - **Target (consumer/plug)**: Uses `PerspectiveSelf` which calls `SnapName()`.
     The consumer sees its own data at the base snap name path because the mount
     namespace remaps instance-specific paths to the base name.

2. **AppArmor rules are instance-aware** (`content.go:259-318`): Connected plug rules
   reference the slot's paths via `PerspectiveOther` (includes instance key), and
   connected slot rules reference the plug's target via `PerspectiveSelf` (base name,
   correct for the plug's namespace).

3. **Mount entries** (`content.go:348-362`): `MountConnectedPlug()` creates bind mount
   entries using `sourceTarget()`, so the mount source correctly includes the instance
   key for parallel provider snaps.

4. **Explicit test coverage** (`content_test.go:417-452`): The unit test
   `TestResolveSpecialVariableParallel` validates that path expansion works correctly
   for a snap with `InstanceKey = "foo"`, checking both `PerspectiveOther` (produces
   `name_foo`) and `PerspectiveSelf` (produces `name`).

**Reasoning:** The content interface deliberately uses `PerspectiveOther` when referring
to another snap's paths and `PerspectiveSelf` when referring to the consumer's own mount
target. This means:
- `plug_foo` connecting to `slot_foo` works -- source uses `slot_foo` instance paths
- `plug_foo` connecting to `slot` (non-parallel) also works -- source uses `slot` paths
- Mount paths don't collide between `plug` and `plug_foo` because each has its own
  mount namespace

**Verification:** 
- Result: PASSED on noble. Parallel plug `_foo` connected to same slot provider,
read shared content, survived removal of original plug snap.




### home
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Filesystem/Mount Interface


**Code analysis:**
- AppArmor rules use `owner @{HOME}/` patterns that don't distinguish instances
- Both instances access the same home directory files, which is the intended behavior
- The `@{HOME}/snap/` exclusion pattern prevents access to other snaps' data, but
  parallel instances of the same snap share data directories (by design of the parallel
  install feature)

**Verification:**
PASSED on noble.



### desktop-launch
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Filesystem/Mount Interface


**Code analysis:**
- The snapd API access part (reading `/v2/snaps`, `/v2/icons`) works correctly for
  parallel instances -- the API uses the snap's security label for authorization.
- Desktop file launching via userd's `PrivilegedDesktopLauncher` does NOT work for
  parallel instances due to a naming conflict:
  - `snap/info.go:975` (`DesktopPrefix`): Desktop files for parallel instances use `+`
    as the instance key separator (e.g., `test-app+foo_test-app.desktop`) because `_` is
    already used as the snap/desktop-filename separator.
  - `usersession/userd/privileged_desktop_launcher.go:196` (`isValidDesktopFileID`):
    The validation regex `^[A-Za-z0-9-_]+(\.[A-Za-z0-9-_]+)*.desktop$` does NOT accept
    `+`, so desktop files for parallel instances can never be launched via this path.

**Reasoning:** This is a design tension: `_` separates snap name from desktop file name,
so a parallel instance `snap_key` can't use `_` again for the instance key without
ambiguity. The `+` workaround allows file creation but breaks the userd lookup.

**Verification:**
Expected failure -- desktop file launching is incompatible with parallel
  instances. The error is: `Error org.freedesktop.DBus.Error.Failed: cannot find desktop
  file for "test-app_foo_test-app.desktop"`. API access (tested above the launch
  attempt) works correctly.



### cups-control
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Daemon/Socket Client


**Code analysis:**
- Access to CUPS socket and D-Bus for printing
- Multiple instances can submit print jobs simultaneously
- No global resource contention from plug side

**Verification:**
FAILED -- pre-existing environment issue (no CUPS printer configured).
  Failure occurs at `lpr: Error - No default destination` in the original test code
  before any parallel-instance section. Unrelated to parallel installs. Needs a test
  environment with a configured CUPS printer.



### polkit
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Identity/Credentials/Secrets


**Code analysis:**
The polkit interface installs policy files (`.policy`) and rule files (`.rules`) for
polkit authorization.

1. **File names ARE instance-aware** (`polkit/backend.go:133,151`): Both policy and rule
   file names use `appSet.InstanceName()`:
   - Policy: `snap.<instance_name>.interface.<suffix>.policy`
   - Rules: `70-snap.<instance_name>.<suffix>.rules`
   Parallel instances will NOT have file name collisions.

2. **Source file reads are instance-aware** (`polkit.go:135`): Files are read from
   `plug.Snap().MountDir()` which is instance-specific (`/snap/<instance_name>/<rev>/`).

3. **D-Bus usage is client-only** (`polkit.go:288-299`): The interface grants permission
   to call `CheckAuthorization` on `org.freedesktop.PolicyKit1.Authority` (the system
   polkitd). It does NOT own any D-Bus names.

4. **Minor caveat -- action IDs in XML are not instance-scoped**: The `action-prefix`
   attribute (e.g., `org.example.foo`) is shared across all instances. Both `foo` and
   `foo_bar` would install policy files containing actions under the same prefix. Polkitd
   could see duplicate action definitions, though this is typically harmless (last file
   wins in polkitd's evaluation).

**Reasoning:** The interface is structurally compatible -- file names don't collide, D-Bus
access is client-only, and the backend correctly uses `InstanceName()`. The action ID
duplication caveat is minor and unlikely to cause functional failures.

**Verification:**
 
- **Results:** PASSED on noble (plug-side). Parallel `test-snapd-polkit_foo` installed
instance-specific policy and rule files (e.g.,
`snap.test-snapd-polkit_foo.interface.polkit-action.foo.policy`) alongside the
original's files. After removing the original, the `_foo` files persisted and the
original's files were cleaned up.



### firewall-control
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** System Control/Privileged Capability


**Code analysis:**
- Grants capability to manipulate iptables/nftables rules
- AppArmor rules are purely capability-based (no snap-name-dependent paths)
- No D-Bus ownership, no shared memory, no instance-specific paths
- Multiple instances get the same system-level firewall access

**Reasoning:** Firewall manipulation is a global system capability. Multiple instances
with the plug connected can all modify iptables, same as multiple different snaps with
firewall-control. No snap-name-scoped resources involved.

**Verification:**
PASSED on noble.



### ssh-keys
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Identity/Credentials/Secrets


**Code analysis:**
- Read/write access to `~/.ssh/` files
- No shared memory, no D-Bus, no instance-specific paths
- Multiple instances reading/writing SSH keys is the same as having SSH access

**Verification:**
PASSED on noble.



### ssh-public-keys
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Identity/Credentials/Secrets


**Code analysis:**
- Read access to SSH public keys (`~/.ssh/*.pub`, `/etc/ssh/ssh_host_*_key.pub`)
- No shared memory, no D-Bus, no writes to global resources

**Verification:**
PASSED on noble.



### personal-files
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Filesystem/Mount Interface


**Code analysis:**
The personal-files interface grants access to user-specific file paths declared in plug
attributes. The implementation is in `common_files.go` (shared with `system-files`).

1. **Paths are from plug attributes** (`common_files.go:158-161`): The `read` and
   `write` attributes are lists of absolute paths (e.g., `$HOME/.config/foo`).

2. **Path expansion** (`common_files.go:167-175`): Paths containing `$HOME` are
   expanded to the literal home directory. No snap-name-specific variables (`$SNAP`,
   `$SNAP_DATA`, etc.) are used. The paths are absolute user-space paths.

3. **AppArmor rules are snap-name-agnostic** (`common_files.go:167-175`): The generated
   AppArmor rules use the raw expanded paths directly:
   ```go
   spec.AddSnippet(fmt.Sprintf("\"%s\" rk,", resolvedPath))
   ```
   There is no reference to `SnapName()` or `InstanceName()` in the rule generation.

4. **No instance-specific scoping**: Both a base snap and its parallel instance get
   identical AppArmor rules granting access to the same paths (e.g., both get
   `owner /home/user/.config/foo rw`).

**Reasoning:** personal-files grants access to user-owned paths that are completely
outside the snap's data directories. Two parallel instances accessing the same user
files is identical to two different snaps with the same personal-files declaration.
No snap-name-dependent paths are involved.

**Verification:** 
-Result: PASSED on noble. Parallel instance read/wrote same personal files,
survived removal of original snap.



### system-files
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Filesystem/Mount Interface


**Code analysis:**
Same implementation as personal-files (both use `commonFilesInterface` in
`common_files.go`).

1. **Paths are absolute system paths** from plug attributes (e.g., `/etc/foo`,
   `/var/lib/bar`). No snap-name variables.

2. **AppArmor rules are snap-name-agnostic**: Same as personal-files -- raw paths are
   used directly in the AppArmor snippet.

3. **No instance-specific scoping**: Both instances get the same rules.

**Reasoning:** system-files grants access to fixed system paths. No snap-name-dependent
resources are involved. Two parallel instances can access the same system files without
conflict at the interface level (though they could conflict at the application level if
both write to the same file).

**Verification:** 
- **Result:** PASSED on noble. Parallel instance read/wrote same system files,
survived removal of original snap.


### hostname-control
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** System Control/Privileged Capability


**Code analysis:**
- D-Bus client to `org.freedesktop.hostname1` (send-only, `hostname_control.go:45-72`)
- Writes to `/etc/hostname`, `/etc/writable/hostname` (`hostname_control.go:35-38`)
- Has `sethostname` seccomp rule (`hostname_control.go:83-87`)
- System-provided implicit slot (`implicitOnCore: true`, `implicitOnClassic: true`)
- No `dbus (bind)`, no `DBusPermanentSlot`, no `SnapName()`/`InstanceName()` usage

**Reasoning:** Pure capability interface. All paths are global system config. No
snap-name-dependent resources. Parallel instances get identical permissions.

**Verification:** 
- **Results:** PASSED on noble.



### locale-control
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** System Control/Privileged Capability


**Code analysis:**
- D-Bus client to `org.freedesktop.locale1` (send-only, `locale_control.go:41-64`)
- Writes to `/etc/default/locale` (`locale_control.go:67`)
- No seccomp snippet
- System-provided implicit slot

**Reasoning:** Simplest of the six. Pure D-Bus client + one global config file. No
snap-name-dependent resources.

**Verification:** 

- **Results:** PASSED on noble.



### timezone-control
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** D-Bus/IPC Client


**Code analysis:**
- D-Bus client to `org.freedesktop.timedate1` (send-only, `timezone_control.go:49-83`)
- Reads `/usr/share/zoneinfo/**`, writes `/etc/timezone`, `/etc/localtime`
  (`timezone_control.go:41-45`)
- System-provided implicit slot

**Reasoning:** Global timezone configuration. No snap-name-dependent resources.

**Verification:** 

- **Results:** PASSED on noble.



### timeserver-control
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** System Control/Privileged Capability


**Code analysis:**
- D-Bus client to `org.freedesktop.timedate1`, `org.freedesktop.timesync1`,
  `org.freedesktop.network1` (send-only, `timeserver_control.go:51-106`)
- Writes to `/etc/systemd/timesyncd.conf` (`timeserver_control.go:47`)
- System-provided implicit slot

**Reasoning:** Global NTP configuration. No snap-name-dependent resources.

**Verification:** 

- **Results:** PASSED on noble.



### network-setup-control
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Network/Netlink Interface


**Code analysis:**
- D-Bus client to `io.netplan.Netplan` (send-only, `network_setup_control.go:74-87`)
- Writes to `/etc/netplan/{,**}`, `/etc/network/{,**}`, `/etc/systemd/network/{,**}`,
  `/run/systemd/network/*` (`network_setup_control.go:38-68`)
- Executes `/usr/sbin/netplan`
- System-provided implicit slot

**Reasoning:** Global network configuration. No snap-name-dependent resources. All
paths are global system directories.

**Verification:** 

- **Results:** PASSED on noble.



### account-control
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Identity/Credentials/Secrets


**Code analysis:**
- D-Bus client to `org.freedesktop.Accounts` (send-only, `account_control.go:44-73`)
- Writes to `/var/lib/extrausers/**`, `/var/log/faillog`, `/var/log/lastlog`
  (`account_control.go:75-109`)
- Executes `useradd`, `userdel`, `chpasswd` (`account_control.go:77-80`)
- Dynamic seccomp template resolves shadow file GID at runtime -- system-global
  constant, not snap-specific (`account_control.go:114-138`)
- System-provided implicit slot

**Reasoning:** Global user account management. No snap-name-dependent resources. The
dynamic seccomp GID resolution is deterministic regardless of instance.

**Verification:**

- **Results:** passed on core 18




### joystick
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Hardware Device Access


**Code analysis:**
- Access to `/dev/input/js*` and `/dev/input/event*` devices
- UDev tagging by input subsystem
- No D-Bus, no shared memory, no instance-specific paths
- Multiple processes accessing the same input device is normal (e.g., multiple game
  controllers)

**Verification:**
PASSED on noble.



### hardware-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Observability/Diagnostics


**Code analysis:**
- Read-only access to `/sys/`, `/proc/`, hardware information
- No writes, no D-Bus, no shared memory
- Multiple processes reading hardware info simultaneously is the normal case

**Verification:**
PASSED on noble.



### hardware-random-control
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** System Control/Privileged Capability


**Code analysis:**
- Read/write access to `/dev/hwrng` and sysfs hw_random paths
- Single hardware resource, but multiple readers don't conflict
- Writers could theoretically conflict (setting `rng_current`), but this is an
  operational concern, not an interface/AppArmor concern

**Verification:**
PASSED on noble.



### hardware-random-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Observability/Diagnostics


**Code analysis:**
- Read-only access to `/dev/hwrng` and sysfs hw_random paths
- Subset of hardware-random-control (read only)

**Verification:**
PASSED on noble.




### shared-memory (non-private/named mode)
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: NOT COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Filesystem/Mount Interface


**Code analysis:**
The shared-memory interface has two modes:

1. **Private mode** (`private: true` in plug attrs): Uses per-instance bind mounts.
   Fully isolated. See the "shared-memory (private mode)" section below.

2. **Named mode** (non-private): Uses specific named paths in `/dev/shm/`. The SHM
   object names come directly from the slot's `write` and `read` attributes (e.g.,
   `writable-bar`) and are used as-is in AppArmor rules (`shared_memory.go:209-232`):
   ```go
   fmt.Fprintf(w, "\"/{dev,run}/shm/%s\" mrwlk,\n", path)
   ```
   No instance name or prefix is added to the path. Both `shm-slot` and `shm-slot_foo`
   get AppArmor rules for the exact same `/dev/shm/writable-bar`.

**Reasoning:** In non-private mode, SHM names are kernel-global. When both the original
slot and a parallel slot write to the same named SHM path, they operate on the same
kernel object. The `_foo` slot's write clobbers the original's data. There is no
per-instance isolation of named SHM objects.

**Verification:**
Expected failure. The original plug reads `parallel data` instead of
  `original data`, because `shm-slot_foo` overwrote the same kernel SHM object at
  `/dev/shm/writable-bar`. The named SHM paths are not instance-scoped.



### shared-memory (private mode)
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Filesystem/Mount Interface


**Code analysis:**
The private mode of shared-memory gives each snap its own isolated `/dev/shm` namespace
via a bind mount. This is distinct from the named mode tested above.

1. **Per-instance bind mount** (`shared_memory.go:304-308`): The private mode UpdateNS
   rule uses `plug.Snap().InstanceName()`:
   ```go
   spec.AddUpdateNSf(`  # Private /dev/shm
     /dev/ r,
     /dev/shm/{,**} rw,
     mount options=(bind, rw) /dev/shm/snap.%s/ -> /dev/shm/,
     umount /dev/shm/,`, plug.Snap().InstanceName())
   ```
   For `snap_foo`, this creates a bind mount from `/dev/shm/snap.snap_foo/` to
   `/dev/shm/`, giving the instance its own private SHM directory.

2. **Instance isolation is guaranteed**: Each parallel instance gets its own
   `/dev/shm/snap.INSTANCE_NAME/` directory mounted over `/dev/shm/` in its namespace.
   The two instances cannot see each other's SHM files.

3. **No naming restrictions in private mode** (`shared_memory.go:293-296`): Unlike named
   mode, private SHM allows any name under `/dev/shm/` because the namespace is fully
   isolated.

**Reasoning:** Private shared-memory is designed for per-snap isolation. The
`InstanceName()` usage ensures parallel instances get separate namespaces. This is the
most isolation-friendly mode of shared-memory.

**Verification:** 
-Result: PASSED on noble. Parallel instance got its own `/dev/shm/snap.shm-private_foo/`
namespace, segments were isolated from original, survived removal of original snap.



### posix-mq
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: NOT COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Hardware Device Access


**Code analysis:**
The posix-mq interface manages POSIX message queue access between plug and slot snaps.

1. **Queue names from slot attributes** (`posix_mq.go:157-199`): Queue paths (e.g.,
   `/myqueue`) are declared in the slot's `path` attribute. They are POSIX mq names
   following the pattern `/name` (validated by regex at line 92:
   `^/[^/]{1,255}$`).

2. **AppArmor mqueue rules** (`posix_mq.go:272-282`): Rules are generated using the raw
   path string from the slot attribute:
   ```go
   snippet.WriteString(fmt.Sprintf("  mqueue %s %s,\n", aaPerms, path))
   ```
   No snap-name or instance-name is embedded in the queue path.

3. **Peer labels ARE instance-aware** (`posix_mq.go:287-302`): Connected plug/slot
   AppArmor rules use `LabelExpression()` for peer matching, which includes the
   instance name. So `plug_foo` can only talk to `slot_foo` (or whichever slot it's
   connected to).

4. **Queue names are NOT instance-scoped**: If both `slot` and `slot_foo` declare
   `path: [/test]`, both AppArmor profiles allow access to the same POSIX MQ
   `/test`. POSIX message queues are kernel-global resources (visible in
   `/dev/mqueue/`). Two parallel instances creating the same queue name share the
   same underlying kernel queue.

**Reasoning:** POSIX MQs are kernel-global -- there is no per-namespace isolation.
When two parallel instances both create queue `/test`, they operate on the same
kernel object. Messages sent by one instance can be received by the other. The
AppArmor peer labels don't help because the queue itself is the shared resource, not
the D-Bus-style peer communication.

**Verification:**
Expected failure. The `_foo` instance received `priority 7: Original message`
  instead of `priority 3: Parallel message`. Since POSIX MQs are priority-ordered and
  kernel-global, the read returns the highest-priority message from the shared queue --
  which was the original instance's message.



### mount-control
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: NOT COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Filesystem/Mount Interface


**Code analysis:**

This is a genuine incompatibility rooted in how `$SNAP_COMMON` is expanded:

1. **Path expansion uses `SnapName()`, not `InstanceName()`** (`snap/info.go:829`):
   ```go
   func (s *Info) ExpandSnapVariablesSetSnapMountDir(...) string {
       name := s.SnapName()  // <-- always base name, ignores instance key
       ...
       case "SNAP_COMMON":
           return CommonDataDir(name)  // -> /var/snap/<SnapName>/common
   ```
   For `test-snapd-mount-control_foo`, `$SNAP_COMMON` expands to
   `/var/snap/test-snapd-mount-control/common` (same as base instance), not
   `/var/snap/test-snapd-mount-control_foo/common`.

2. **AppArmor mount rules** (`mount_control.go:623-691`): The generated AppArmor mount
   rules use the expanded path (via SnapName), so the rule allows mounting to
   `/var/snap/test-snapd-mount-control/common/target1` regardless of instance.

3. **Permission check in `snapctl mount`** (`overlord/hookstate/ctlcmd/mount.go:62-72`):
   ```go
   func matchMountPathAttribute(path string, attribute any, snapInfo *snap.Info) bool {
       expandedPattern := snapInfo.ExpandSnapVariables(pattern)  // uses SnapName()
       pp, err := utils.NewPathPattern(expandedPattern, allowCommas)
       return err == nil && pp.Matches(path)
   }
   ```
   The pattern and the path are compared after expansion. If the snap passes the
   host-level instance path (`/var/snap/test-snapd-mount-control_foo/common/target1`),
   it won't match the expanded pattern
   (`/var/snap/test-snapd-mount-control/common/target1`).

4. **Mount namespace remapping**: Inside the snap's mount namespace, parallel instances
   see their instance-specific data at the same path as the base snap would (namespace
   remapping). So `$SNAP_COMMON` inside the namespace points to the right data. But
   `snapctl mount --persistent` creates a systemd mount unit on the HOST, where the
   actual directories are instance-specific.

**Reasoning:** The mount-control interface has a fundamental inconsistency: AppArmor rules
and permission checks use `SnapName()` (namespace-internal perspective), but the systemd
mount unit operates on host paths (which are instance-specific). A parallel instance
trying to use `mount` (direct syscall) is denied by AppArmor because the host path
(`/var/snap/..._foo/...`) doesn't match the AppArmor rule (which uses the base name). A
parallel instance using `snapctl mount` would create a unit pointing to the wrong
directory on the host.

**Verification (interfaces-mount-control):**
Expected failure. `mount: mount /var/tmp/test-snapd-mount-control on
  /var/snap/test-snapd-mount-control_foo/common/target1 failed: Permission denied`.
  AppArmor denies the mount because the rule uses `SnapName()` which only allows
  `/var/snap/test-snapd-mount-control/common/...`, not the instance-specific path.




### password-manager-service
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Identity/Credentials/Secrets


**Code analysis:**
- Session bus D-Bus access to `org.freedesktop.secrets` (gnome-keyring)
- The plug only sends/receives -- it does not own the keyring service name
- Multiple clients accessing the same keyring is the normal use case
- The `secret-tool` utility just performs operations on the user's keyring

**Reasoning:** gnome-keyring is a user-session service. Multiple snap instances are just
additional clients of the same session service, no different from multiple different
snaps accessing the keyring.

**Previous audit errors**:
- Classified as "NOT COMPATIBLE" -- INCORRECT. Test proves it works.

**Verification:**
PASSED on noble.



### calendar-service
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** D-Bus/IPC Client


**Code analysis:**
- Session bus D-Bus access to Evolution Data Server (calendar component)
- Same architecture as contacts-service (session bus, client-only)
- Multiple clients accessing the same EDS calendar is normal

**Previous audit errors**:
- Classified as "NOT COMPATIBLE" -- INCORRECT. Test proves it works.

**Verification:**
PASSED on noble.

### log-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Observability/Diagnostics


Read-only access to system logs (`/var/log/`, journal). No D-Bus, no snap-name paths.

**Verification:** Passed on noble. Test at `tests/main/interfaces-log-observe`.

### network-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Network/Netlink Interface


Read-only network status queries (D-Bus client to systemd-resolved, read /proc/sys).
No D-Bus ownership.

**Verification:** Passed on noble. Test at `tests/main/interfaces-network-observe`.

### mount-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Filesystem/Mount Interface


Read-only access to `/proc/<pid>/mounts` and mount propagation info. No D-Bus, no
snap-name paths.

**Verification:** Passed on noble. Test at `tests/main/interfaces-mount-observe`.

### system-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Observability/Diagnostics


Read-only access to system info (D-Bus client to hostnamed/systemd, read /proc, /boot).
No D-Bus ownership.

**Verification:** Passed on noble. Test at `tests/main/interfaces-system-observe`.

### process-control
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** System Control/Privileged Capability


Capability-based: `kill` syscall, signal sending, priority changes. No paths, no D-Bus.

**Verification:** Passed on noble. Test at `tests/main/interfaces-process-control`.

### gpg-keys
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Identity/Credentials/Secrets


Read/write access to `~/.gnupg/` (user file access). No D-Bus, no snap-name paths.

**Verification:** Passed on noble. Test at `tests/main/interfaces-gpg-keys`.

### gpg-public-keys
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Identity/Credentials/Secrets


Read-only access to `~/.gnupg/` public keys. No D-Bus, no snap-name paths.

**Verification:** Passed on noble. Test at `tests/main/interfaces-gpg-public-keys`.

### removable-media
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Filesystem/Mount Interface


Access to `/media/`, `/run/media/`, `/mnt/` mount points. No D-Bus, no snap-name paths.

**Verification:** Passed on noble. Test at `tests/main/interfaces-removable-media`.

### kvm
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE (no side-specific divergence documented in this entry).

**Type:** Container/Virtualization Support


Device access to `/dev/kvm`. No D-Bus, no snap-name paths.

**Verification:** Passed on noble. Test at `tests/main/interfaces-kvm`.

### raw-usb
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


Device access to `/dev/bus/usb/`, `/sys/bus/usb/`. No D-Bus, no snap-name paths.

**Verification:** Passed on noble. Test at `tests/main/interfaces-raw-usb`.

### cuda-driver-libs
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE.

**Type:** Hardware Device Access

**Code analysis:**
- The interface is mostly about publishing CUDA driver libraries and config metadata.
- `BeforePrepareSlot()` validates the compatibility expression and source directories (lines 61-77).
- `LdconfigConnectedPlug()` and `ConfigfilesConnectedPlug()` expose the slot's libraries/config through system helper paths (lines 79-103).
- The implementation is system-oriented and does not introduce snap-instance-specific paths.

**Reasoning:** This is a library exposure interface scoped by compatibility metadata and system paths. Parallel installs don’t create a snap instance naming issue in the code shown.

**Verification:** No verification has yet been done.

### packagekit-control
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE.

**Type:** Hardware Device Access

**Code analysis:**
- Slot is provided by core only (lines 30-35), with implicit slot on classic (line 107).
- AppArmor rules are D-Bus client-only and talk to the PackageKit daemon on the system bus (lines 44-100).
- The transaction object paths are random, numeric/hex identifiers under `/[0-9]*_[0-9a-f...]` (lines 74-100), not snap-name-derived.
- No snap-instance-specific paths, sockets, or mount operations are present.
- No D-Bus ownership is granted; this interface only sends and receives on the PackageKit endpoints.

**Reasoning:** PackageKit is a shared system service and the interface is just a D-Bus client. Parallel instances are ordinary concurrent clients talking to the same daemon, and the transaction object paths are generated by PackageKit itself rather than by snapd. No instance-naming issue is visible.

**Verification:** No verification has yet been done.

### polkit-agent
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE.

**Type:** Hardware Device Access

**Code analysis:**
- Slot is provided by core only when the helper exists, and the interface is implicitly on core/classic depending on helper availability (line 142).
- AppArmor rules allow registering with polkitd on the system bus and talking to accounts-daemon for UI prompts (lines 47-129).
- The helper subprofile uses `@{SNAP_INSTANCE_NAME}` in the signal peer label (line 114), which is instance-aware.
- The helper can read `/var/lib/extrausers/shadow` and `/var/lib/extrausers/gshadow`, but those are global system auth databases, not snap-scoped paths.
- Seccomp only adds audit-related socket/bind permissions (lines 132-136).

**Reasoning:** The interface is about acting as a polkit agent, which is a client role. The only snap-instance-specific element is the helper signal peer label, and that uses `SNAP_INSTANCE_NAME` correctly. The shared auth databases and D-Bus service are system-wide resources, so parallel instances do not create snap-instance collisions in the interface code.

**Verification:** No verification has yet been done.

### snap-refresh-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE.

**Type:** Hardware Device Access

**Code analysis:**
- Slot is provided by core only (lines 30-35), with implicit slots on core and classic (lines 42-43).
- The interface has no AppArmor, seccomp, mount, or udev snippets of its own.
- It is used as a marker interface in snapd's refresh/inhibit code paths.
- There are no snap-instance-specific paths or name-ownership rules in the interface definition itself.

**Reasoning:** This interface is essentially a marker/read-access capability used by snapd to gate refresh/inhibit behavior. Because the interface definition itself contributes no filesystem or D-Bus policy, there is no parallel-install collision surface in this code.

**Verification:** No verification has yet been done.

### classic-support
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Filesystem/Mount Interface


**Code analysis:**
- Plug-side policy is intentionally unrestricted and includes broad capabilities (`sys_admin`, `dac_override`, `mknod`, `chown`) plus mount/umount and `sudo`/`systemd-run` execution (`interfaces/builtin/classic_support.go:43-123`).
- AppArmor mount rules include both `@{SNAP_NAME}` and `@{SNAP_INSTANCE_NAME}` path variants for parallel-install remapping (`interfaces/builtin/classic_support.go:72-86`).
- Slot installation is restricted to core (`interfaces/builtin/classic_support.go:35-41`).

**Reasoning:** Even with instance-aware path allowances, this interface grants host-global classic-mode control and broad mount/system authority, so parallel instances are not isolated and can interfere heavily.

**Verification:** No verification has yet been done.

### snap-fde-control
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Snapd/Policy Management


**Code analysis:**
- Interface is a policy gate for access to the FDE subset of snapd's system-volumes API (`interfaces/builtin/snap_fde_control.go:22`).
- Definition is marker-like: no AppArmor/seccomp/mount snippets in the interface file; only base declarations and implicit core/classic behavior (`interfaces/builtin/snap_fde_control.go:24-46`).
- Slot side is core-only (`interfaces/builtin/snap_fde_control.go:30-35`).

**Reasoning:** No snap-instance-specific filesystem or D-Bus ownership surface is introduced by this interface definition; parallel plug instances are just additional authorized clients.

**Verification:** No verification has yet been done.

### snap-interfaces-requests-control
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Snapd/Policy Management


**Code analysis:**
- Plug-side AppArmor allows client communication with a fixed shell-integration D-Bus API (`com.canonical.Shell.PermissionPrompting`) and does not bind service names (`interfaces/builtin/snap_interfaces_requests_control.go:43-65`).
- Plug attribute validation for `handler-service` checks service existence and user-daemon scope; it does not introduce global naming ownership (`interfaces/builtin/snap_interfaces_requests_control.go:71-96`).
- Slot installation is core-only (`interfaces/builtin/snap_interfaces_requests_control.go:36-42`).

**Reasoning:** This interface is client/policy oriented. Parallel installs do not create instance-name collisions in the interface behavior.

**Verification:** No verification has yet been done.

### snap-refresh-control
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Snapd/Policy Management


**Code analysis:**
- Interface is explicitly marker-like and used by snapd refresh/inhibit logic to gate `snapctl refresh --proceed` behavior (`interfaces/builtin/snap_refresh_control.go:22-25`).
- No AppArmor/seccomp snippets are defined in this interface file (`interfaces/builtin/snap_refresh_control.go:42-50`).
- Slot installation is restricted to core (`interfaces/builtin/snap_refresh_control.go:34-39`).

**Reasoning:** There is no path/socket/name ownership policy in the interface definition itself, so no parallel-install naming collision surface is introduced.

**Verification:** No verification has yet been done.

### snap-themes-control
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Snapd/Policy Management


**Code analysis:**
- Interface is a policy gate for snapd's theme installation API (`interfaces/builtin/snap_themes_control.go:22`).
- It is defined as a common marker interface with no local AppArmor/seccomp policy snippets (`interfaces/builtin/snap_themes_control.go:38-46`).
- Slot side is core-only (`interfaces/builtin/snap_themes_control.go:30-35`).

**Reasoning:** Interface definition itself is parallel-safe, but operations target shared host theme state, so concurrent instances can contend at the shared-resource level.

**Verification:** No verification has yet been done.

### snapd-control
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Snapd/Policy Management


**Code analysis:**
- Plug-side AppArmor grants client access to the shared snapd Unix socket `/run/snapd.socket` (`interfaces/builtin/snapd_control.go:44-48`).
- Plug-side validation only checks optional `refresh-schedule` attribute values and does not introduce instance-specific naming (`interfaces/builtin/snapd_control.go:54-62`).
- Slot side is core-only (`interfaces/builtin/snapd_control.go:36-42`).

**Reasoning:** Multiple parallel instances can connect as concurrent snapd clients, but they operate against a single global daemon and shared system state.

**Verification:** No verification has yet been done.

### ubuntu-pro-control
**Status:** Plug-side: COMPATIBLE. Slot-side: NOT COMPATIBLE.

**Type:** Hardware Device Access

**Code analysis:**
- Slot is provided by core only (lines 30-35), with implicit slot on classic (line 128).
- AppArmor rules talk to `com.canonical.UbuntuAdvantage` on the system bus and query the object hierarchy with `ObjectManager`, properties, and introspection (lines 38-121).
- The interface is clearly designed around a single daemon service with a well-known bus name.
- No snap-instance-specific paths are used; the only filesystem access is `/etc/ubuntu-advantage/uaclient.conf` (line 43).
- No mount or shared-memory rules are present.

**Reasoning:** Ubuntu Pro control is a daemon-client interface on top of a singleton service. Parallel consumers are fine, but parallel providers would contend for the same well-known D-Bus name, so slot-side is not compatible.

**Verification:** No verification has yet been done.

### xdg-portal-permission-store
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE.

**Type:** Hardware Device Access

**Code analysis:**
- Slot is provided by core only (lines 30-35), with implicit slot on core and classic (lines 69-70).
- AppArmor rules grant session-bus access to the portal PermissionStore object at `/org/freedesktop/impl/portal/PermissionStore` (lines 38-63).
- The interface is client-only: it sends and receives on the portal object but does not own a bus name.
- No snap-instance-specific paths, sockets, or mount rules are present.

**Reasoning:** This is a shared portal service on the session bus. Multiple parallel instances can safely access the same PermissionStore as concurrent clients. No instance naming or global-file conflict is visible.

**Verification:** No verification has yet been done.

### kernel-firmware-control
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE.

**Type:** Hardware Device Access

**Code analysis:**
- Slot is provided by core only (lines 31-36), with implicit slots on core and classic (lines 48-49).
- AppArmor rules only grant write access to `/sys/module/firmware_class/parameters/path` (line 41).
- No D-Bus, sockets, mounts, or snap-instance-specific paths are involved.

**Reasoning:** The interface controls a global kernel firmware search path parameter. Multiple instances get the same permission, and the code does not include any snap-instance-dependent logic.

**Verification:** No verification has yet been done.

### ion-memory-control
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE.

**Type:** Hardware Device Access

**Code analysis:**
- Slot is provided by core only (lines 24-30), with an explicit plug-installation restriction (lines 32-36).
- AppArmor rules grant access to `/dev/ion` (lines 38-44).
- UDev tags the `ion` device (lines 46-48).
- No snap-instance-specific names, sockets, or mounts are involved.

**Reasoning:** The Android ION allocator is a global device interface. Multiple parallel instances can access the same device node without any snapd policy collision in the interface code.

**Verification:** No verification has yet been done.

### nvme-control
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE.

**Type:** Hardware Device Access

**Code analysis:**
- Slot is provided by core only (lines 40-45), with explicit plug-installation restriction (lines 34-38).
- AppArmor grants access to NVMe config files, sysfs, the fabrics character device, and NVMe controller/namespace nodes (lines 48-68).
- UDev tags NVMe and nvme-fabrics devices (lines 70-73).
- KMod module loading hints are declared for `nvme` and `nvme-tcp` (lines 79-82).
- No snap-instance-specific names are used.

**Reasoning:** NVMe is global storage hardware and the interface is device-path based. Parallel installs can access the same controllers/namespaces from separate snaps without snapd policy collision.

**Verification:** No verification has yet been done.

### sd-control
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE.

**Type:** Hardware Device Access

**Code analysis:**
- Slot is provided by core only (lines 30-35), with implicit slots on core and classic (lines 95-96).
- AppArmor/UDev permissions are conditionally added when the plug’s `flavor` is `dual-sd` (lines 60-86).
- Access is to `/dev/DualSD` and its corresponding udev tag; there are no snap-instance-specific paths.
- The interface uses plug attributes to control scope rather than snap naming.

**Reasoning:** The interface is hardware/flavor specific, not instance specific. Parallel installs just reuse the same hardware access if the plug flavor matches.

**Verification:** No verification has yet been done.

### kernel-module-control
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE.

**Type:** Hardware Device Access

**Code analysis:**
- Capability-based module management (insmod/rmmod/lsmod) and read access to `/sys/module/`.
- No D-Bus name ownership and no snap-instance-specific filesystem pathing.

**Reasoning:** This is a shared kernel capability surface rather than a snap-instance-named resource. Parallel instances can be granted the same capability without an instance-name collision in policy.

**Verification:** Passed on noble. Test at `tests/main/interfaces-kernel-module-control`.

### gpio-control
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access

**Code analysis:**
- This interface grants broad control of all GPIO pins and device nodes (`/sys/class/gpio`, `/sys/devices/platform/**/gpio`, `/dev/gpiochip[0-9]*`) (lines 43-57).
- The comments explicitly describe the interface as privileged and potentially impacting the system and other snaps (lines 25-27, 44-45).

**Reasoning:** Plug-side access is not parallel-safe in practice because it gives global write control over shared GPIO lines and gpiochip devices. Two instances can reconfigure pin direction/value/edge for the same hardware and interfere immediately. Slot-side is core-only and not an app-provider parallel-install scenario.

**Verification:** No verification has yet been done.
