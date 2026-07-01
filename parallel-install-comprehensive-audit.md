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

- **Overall pattern:** Most interfaces are plug-side usable under parallel installs. The most common slot result is `N/A` because many slots are restricted to system snaps (`core`/`gadget`/`os`/`snapd`), so parallel app-provided slots are out of scope by policy.
- **Type-level trend:**
  - **Hardware / privileged control interfaces:** Usually `Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE` + `Slot-side: N/A` (system-provided). These generally do not have snapd instance-key bugs; the limitation is shared host hardware/state.
  - **D-Bus provider interfaces:** Frequently `Slot-side: NOT COMPATIBLE` due to fixed well-known bus names (singleton identity), even when connected mediation labels are instance-aware.
  - **Client-style interfaces (network/socket/observe):** Typically `Plug-side: COMPATIBLE`, with caveats only when the app chooses host-global identities (fixed ports, fixed names).
  - **Path-driven service interfaces:** Compatible when paths are instance-aware; not compatible when provider paths are hardcoded to unkeyed snap names.
- **Important classification correction made in this audit:** Several interfaces previously treated as `NOT COMPATIBLE` were reclassified to `COMPATIBLE EXCEPT FOR SHARED RESOURCE` because the interface layer itself is parallel-safe and only the underlying host resource is shared.
- **COMPATIBLE-side re-verification (this revision):** Every interface previously marked plain `COMPATIBLE` was re-checked against current source, with special attention to `SNAP_NAME` vs `SNAP_INSTANCE_NAME` (`SnapName()`/`PerspectiveSelf` vs `InstanceName()`/`PerspectiveOther`) usage. Outcomes:
  - **No new `SNAP_NAME`-for-host-path bugs were found** among the COMPATIBLE interfaces. Interfaces that build host-side artifacts were confirmed to use the instance name correctly: `content` (source=`PerspectiveOther`/target=`PerspectiveSelf`), `gpio-chardev` (systemd export service, host symlink, AppArmor host device paths, and udev tag all use `InstanceName()`), `polkit`/`polkit-agent` (instance-aware file names / peer label), `x11`/`wayland`/`browser-support`/`pulseaudio`/`pipewire`/`desktop` (instance-keyed `/run/user/.../snap.<instance>/` paths), and the `cifs-mount`/`nfs-mount`/`fuse-support` mount rules (both `@{SNAP_NAME}` and `@{SNAP_INSTANCE_NAME}` variants, with `fuse-support` correctly using instance-only for the non-remapped `~/snap/` path).
  - **Single-pinned-device hardware interfaces** were reclassified from plain `COMPATIBLE` to `COMPATIBLE EXCEPT FOR SHARED RESOURCE` for consistency with `spi`/`pwm`: `serial-port`, `hidraw`, `i2c`, `iio`, `uio`, `gpio`, `gpio-memory-control`, `vcio`. (Device-*class* interfaces such as `tpm`, `joystick`, `raw-input`, `dvb`, `device-buttons`, `uhid`, `kvm`, `ptp`, `raw-usb`, `mediatek-accel` remain plain `COMPATIBLE`.)
  - **Shared per-user/system-file interfaces** were reclassified to `COMPATIBLE EXCEPT FOR SHARED RESOURCE`: `home`, `personal-files`, `system-files`, `removable-media`, `bool-file`, `browser-support`, and `gpg-keys` (writes the shared `~/.gnupg/random_seed`; `gpg-public-keys` stays `COMPATIBLE`).
  - **Slot-side corrections:** `pkcs11` slot-side changed from `COMPATIBLE` to `COMPATIBLE EXCEPT FOR SHARED RESOURCE` (the `pkcs11-socket` path is forced into shared `/run/p11-kit/` and is not instance-key disambiguated). `docker` and `custom-device` slot-side changed from `COMPATIBLE` to `N/A` (their slots are not app-providable by default — `deny-installation`/`allow-installation: false`). `avahi-control`/`avahi-observe` slot-side made explicit as `NOT COMPATIBLE` for app-provided slots (singleton `org.freedesktop.Avahi`).

### Bugs and code defects found

- **`desktop` session identity bug (visible UX failure):** Parallel GUI instances can show a generic icon / wrong dock matching (Firefox reproduction) because desktop session identity is not fully instance-aware. `StartupWMClass` is allowlisted but not rewritten per instance (`wrappers/desktop.go:99`).
- **`cups` slot-side path perspective bug:** Provider path handling uses the wrong perspective for host-side bind-mount source resolution; slot-side needs host-instance paths (`PerspectiveOther` style), otherwise parallel provider source paths do not resolve correctly.
- **`lxd`, `microceph`, `microovn` slot-side hardcoded socket bug:** Interface rules target fixed unkeyed paths (`/var/snap/lxd/...`, `/var/snap/microceph/...`, `/var/snap/microovn/...`), so parallel provider instances with keyed host paths cannot be addressed correctly.
- **`mount-control` namespace/host path bug:** Mount request processing mixes namespace-visible paths and host-level mount/systemd unit semantics; paths that are valid in snap namespace are not reliably valid for host-side execution.
- **`shared-memory` named mode bug:** Named mode uses declared names as-is under `/dev/shm` (kernel-global object namespace), with no automatic instance discriminator.
- **`posix-mq` bug-by-design in named queues:** Queue paths are used as declared (kernel-global namespace), so equal names across parallel instances collide on the same queue object.
- **`unity7` known mediation bug:** Existing code comment documents unintended D-Bus mediation overlap for keyed instances via `UNITY_SNAP_NAME` handling.
- **`dbus` activation/global-name bug:** Activation files are global and keyed by `busName + ".service"` while well-known name ownership is singleton; parallel providers contend/overwrite activation and routing.

### Interfaces that would otherwise be compatible

- **Would be compatible if fixed:** `cups` slot-side, `lxd` slot-side, `microceph` slot-side, `microovn` slot-side, and `mount-control` plug-side are primarily blocked by concrete code/path handling defects rather than an inherent parallel-install model limitation.
- **Conditionally compatible by app behavior:** `desktop` plug-side is interface-safe, but app/session identity surfaces (`desktop-file-ids`, `StartupWMClass`, launcher resolution) can still break parallel UX unless made instance-aware.

| Interface(s) | Current status impact | Root cause | Fix direction |
| --- | --- | --- | --- |
| `cups` (slot side) | `Slot-side: POTENTIALLY COMPATIBLE` | Provider-side host path resolution uses self perspective for a cross-snap/host bind source; keyed instance host path is not resolved correctly. | Use host/other-snap perspective (`InstanceName()` / `PerspectiveOther`) when constructing host-visible source paths. |
| `lxd`, `microceph`, `microovn` (slot side) | `Slot-side: POTENTIALLY COMPATIBLE` | Hardcoded unkeyed provider socket paths (`/var/snap/<name>/...`) do not map to keyed parallel provider paths on host. | Replace hardcoded provider paths with instance-aware provider path construction (keyed host path for provider snap). |
| `mount-control` (plug side) | `Plug-side: POTENTIALLY COMPATIBLE` | Path validation/execution crosses namespace and host semantics; namespace-valid paths are not consistently valid for host mount/systemd unit execution. | Normalize/translate request paths explicitly to host-visible paths before host-side checks/execution; keep namespace-vs-host boundary explicit. |
| `shared-memory` (named mode) | `Plug-side: NOT COMPATIBLE` in named mode | Named `/dev/shm` objects are kernel-global and used as declared, with no automatic instance discriminator. | Introduce instance-aware naming convention or enforce/require private mode for parallel-safe usage. |
| `posix-mq` (named queues) | `Plug-side: NOT COMPATIBLE` | Queue names are kernel-global and taken directly from slot attributes; same names collide across instances. | Introduce instance-aware queue naming guidance/mechanism or require unique names per instance by policy. |
| `dbus` (provider side broadly) | Many `Slot-side: NOT COMPATIBLE` provider cases | Well-known bus name is singleton and activation file namespace is global (`busName + ".service"`). | Require per-instance bus names for parallel providers, or explicitly keep provider side singleton and document this as design constraint. |
| `unity7` | `NOT COMPATIBLE` | Known mediation overlap for keyed instances (`UNITY_SNAP_NAME` handling). | Rework D-Bus mediation name derivation to remain isolated for keyed instances. |
| `desktop` (app/session behavior) | Plug side policy is compatible, UX may fail | Session identity surfaces (`StartupWMClass`, desktop IDs/lookup) are not consistently instance-aware end-to-end. | Ensure per-instance desktop/session identity (`StartupWMClass`, desktop ID resolution) and app runtime WMClass alignment. |


## App Feature Checklist

Use this checklist when auditing a snap for parallel-install issues that do not come from
interface policy itself. The recurring pattern is simple: if the app exposes or consumes
a host-global identity, path, socket, or bus name, then parallel instances may still
collide even when the interface layer is otherwise safe.

### 1. Desktop file IDs
**What to look for:** `desktop-file-ids` on the `desktop` plug, or app behavior that depends on a stable upstream desktop ID.

**Why it is risky:** desktop file IDs live in a global desktop namespace under snapd's desktop applications directory. If two instances want the same unmangled desktop ID, only one can own that file name.

**What snapd does today:** snapd preserves store-approved desktop file IDs as-is instead of mangling them per instance, and explicitly errors if the target file already belongs to another snap instance.

**Where:** `interfaces/builtin/desktop.go`, `snap/info.go`, `wrappers/desktop.go`

### 2. Common IDs
**What to look for:** `common-id` in app metadata, or any portal / desktop integration flow that resolves an app through `CommonID` rather than the instance-specific desktop prefix.

**Why it is risky:** `common-id` is intentionally a shared desktop identity. It is useful for portals and application matching, but parallel instances can still appear as the same logical app to components outside snapd.

**What snapd does today:** snapd validates uniqueness only within one snap's app set. It can prefer a `common-id` desktop file when resolving the app's desktop entry.

**Where:** `snap/validate.go`, `snap/info.go`, `cmd/snap/cmd_routine_portal_info.go`

### 3. Desktop launcher and desktop-entry lookup
**What to look for:** flows that launch apps by desktop file ID rather than by direct wrapper path, especially if the desktop ID is derived from a base snap name rather than the full instance name.

**Why it is risky:** desktop launchers and desktop-entry lookup operate in a shared desktop namespace. If the lookup format cannot represent the instance-specific desktop file name, parallel instances become unlaunchable or ambiguous.

**What snapd does today:** default desktop file generation is instance-aware, but some user-session desktop-launch paths still validate or resolve desktop IDs in ways that are not compatible with `+instance` desktop prefixes.

**Where:** `snap/info.go`, `usersession/userd/privileged_desktop_launcher.go`, `wrappers/desktop.go`

### 4. Autostart desktop files
**What to look for:** apps using `autostart`, especially if more than one instance could install equivalent desktop entries or if the app assumes a single session startup identity.

**Why it is risky:** autostart is a shared per-user desktop-session mechanism. Incorrect mapping between desktop file and wrapper can make the wrong instance start at login.

**What snapd does today:** snapd matches the autostart desktop file back to the app and then rewrites execution to the instance-specific wrapper path, which avoids many collisions but still depends on correct desktop file identity.

**Where:** `usersession/autostart/autostart.go`, `wrappers/desktop.go`

### 5. Well-known D-Bus names
**What to look for:** provider slots or daemons that bind a fixed session-bus or system-bus name, or app protocols built around a fixed D-Bus service identity.

**Why it is risky:** well-known D-Bus names are global singleton identities on a bus. Parallel providers cannot both own the same name, and consumers may be routed to the wrong instance if AppArmor expects a different peer label.

**What snapd does today:** connected plug/slot mediation is usually instance-aware, but the bus name itself is not rewritten per instance unless the interface or application explicitly does so.

**Where:** `interfaces/builtin/dbus.go`, interface-specific provider code such as `interfaces/builtin/network_manager.go`, `interfaces/builtin/bluez.go`, `interfaces/builtin/udisks2.go`, and activation handling in `wrappers/dbus.go`

### 6. D-Bus activation files
**What to look for:** services started through D-Bus activation where the activation file name is derived from the bus name.

**Why it is risky:** activation files are stored in a global `.service` namespace keyed by the bus name. Two parallel providers using the same D-Bus name overwrite or contend for the same activation entry.

**What snapd does today:** activation files are named `busName + ".service"`, while the internal metadata tracks the owning snap instance separately.

**Where:** `wrappers/dbus.go`

### 7. `daemon: dbus`, `bus-name`, and `activates-on`
**What to look for:** services using `daemon: dbus`, explicit `bus-name`, or `activates-on` links to D-Bus slots.

**Why it is risky:** these features wire the daemon lifecycle directly to global bus identity and activation semantics. They are safe only if the bus identity itself is instance-safe.

**What snapd does today:** validation checks daemon scope and interface consistency, but it does not invent a per-instance bus name.

**Where:** `snap/validate.go`, `wrappers/internal/service_unit_gen.go`

### 8. Abstract Unix socket names
**What to look for:** socket activation or app runtime code using abstract socket names such as `@snap.<name>...`.

**Why it is risky:** abstract socket names live in a global kernel namespace. If the app reuses the same suffix across instances, the sockets collide.

**What snapd does today:** validation requires the prefix to be based on the snap name, not the full instance name, so applications need their own extra discriminator if multiple instances must coexist.

**Where:** `snap/validate.go`

### 9. Fixed TCP/UDP listen ports
**What to look for:** daemons with fixed `listen-stream` network ports or app logic that assumes one exclusive port per machine.

**Why it is risky:** host ports are a global resource. Even if snapd policy allows both instances to run, the second bind fails if both want the same address and port.

**What snapd does today:** it validates the socket syntax, not whether the chosen port can be shared between parallel instances.

**Where:** `snap/validate.go`

### 10. Named shared memory objects
**What to look for:** `shared-memory` in named mode, or application code that creates fixed `/dev/shm` objects outside a private namespace.

**Why it is risky:** named SHM objects are kernel-global. Two instances using the same object name are reading and writing the same resource.

**What snapd does today:** named shared-memory paths are used as declared, without automatic instance prefixing. Only private mode gets per-instance namespace isolation.

**Where:** `interfaces/builtin/shared_memory.go`

### 11. POSIX message queue names
**What to look for:** `posix-mq` slots using fixed queue paths like `/queue-name`, or applications that assume one global MQ name.

**Why it is risky:** POSIX message queues are kernel-global objects. Matching queue names from parallel instances refer to the same queue.

**What snapd does today:** queue paths are taken directly from slot attributes, while peer-label mediation remains instance-aware. That means the queue resource itself, not the peer label, becomes the collision point.

**Where:** `interfaces/builtin/posix_mq.go`

### 12. Session service identity surfaces such as MPRIS and notifications
**What to look for:** app-visible names exposed to the desktop session, for example MPRIS service names or notification desktop-entry attribution.

**Why it is risky:** even when these do not hard-fail like D-Bus provider collisions, they can cause the desktop to group, route, or display multiple instances as though they were one app.

**What snapd does today:** some paths are explicitly instance-aware, such as MPRIS defaulting to `SNAP_INSTANCE_NAME`, while others depend on which desktop ID the caller supplies.

**Where:** `interfaces/builtin/mpris.go`, `desktop/notification/fdo.go`

### Quick audit rule of thumb

If the feature is built around a fixed external name, ask whether that name is:

- per instance
- per user session
- per host
- or truly global in the kernel / bus / filesystem namespace

If it is host-global or kernel-global and the application expects exclusive ownership,
parallel installs are usually either not compatible or only compatible with a shared
resource caveat.



---

## Additional Interface Analyses

### custom-device
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (gadget/snap-declaration-provided slot; `allow-installation: false`, so no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- The slot is gadget-driven and intentionally open-ended: the base declaration sets `allow-installation: false` (`interfaces/builtin/custom_device.go:43`), so a normal app snap cannot provide this slot on its own; only the gadget (or a snap with an explicit snap-declaration) can. Connection approval is keyed on the plug attribute matching the slot value: `custom-device: $SLOT(custom-device)` (`custom_device.go:44-46`).
- `BeforePrepareSlot()` defaults the `custom-device` slot attribute to the slot name if empty (`custom_device.go:256-259`), and `BeforePreparePlug()` defaults the plug attribute to the plug name (`custom_device.go:335-341`). Neither uses a snap or instance name.
- `AppArmorConnectedPlug()` (`custom_device.go:346-386`) emits rules entirely from the slot's `devices` (`rwk`), `read-devices` (`r`), and `files` read/write attributes — all gadget-authored absolute paths. No `SnapName()`, `InstanceName()`, `ExpandSnapVariables()`, or `LabelExpression()` is used anywhere in the file.
- `UDevConnectedPlug()` (`custom_device.go:406-516`) calls `spec.TagDevice()` (lines 477, 487, 495-496, 512) with `KERNEL==`/`SUBSYSTEM==`/`ENV`/`ATTR` rules derived from slot attributes. `TagDevice` attaches the consuming snap's security tag, which already includes the instance name, so udev tagging is instance-aware automatically.
- No hardcoded `/var/snap/<name>/` or `/snap/<name>/` paths, no D-Bus name ownership, no shared-memory/posix-mq/abstract-socket names.
- Attribute validation: `BeforePrepareSlot()` (`custom_device.go:246-326`) validates device paths (regexp `^/dev/[^"|{}\\]+$`), forbids a path in both `devices` and `read-devices`, validates `files` paths and `udev-tagging` rules.

**Reasoning:** The consuming-plug AppArmor/udev policy is built entirely from gadget-authored device/file paths and contains no per-snap-instance naming; udev tags are instance-aware via `TagDevice`. Multiple keyed instances connecting the same slot get identical, non-colliding rules, so the plug side is parallel-install compatible. Because the device/file set is whatever the gadget declares (a class of resources, not inherently one pinned device), this is plain COMPATIBLE rather than a forced shared-resource case. The slot side is out of scope for parallel app installs because `allow-installation: false` prevents app snaps from providing it.

**Verification:** No verification has yet been done.

### confdb
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Snapd/Policy Management


**Code analysis:**
- Auto-connection is driven by publisher account matching.
- The plug requires explicit `account` and `view` attributes.
- Plugs can read/write confdb data and may use the optional `custodian` role.
- No instance-name or snap-name scoping is used in the interface itself.

**Reasoning:** parallel instances of the same snap will generally behave like two clients using the same confdb view, so snapd does not introduce an instance collision. The remaining caveat is that they are still sharing the same confdb data for that view/account.

**Verification:** No verification has yet been done.

### raw-volume
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Filesystem/Mount Interface


**Code analysis:**
- The slot must point at a concrete disk partition.
- The accepted device paths are explicit partition nodes only.
- AppArmor and udev rules are generated from the slot path, not from instance naming.
- Auto-connect is allowed only for declarations, but the slot is still tied to the chosen partition.

**Reasoning:** The interface is path-based with no snap-instance-specific naming on either side. Parallel plug instances can connect to the same slot without snapd conflicts. Parallel slot instances can provide different partitions without conflicts. However, if multiple instances access the same partition (same slot), they share raw disk hardware and can interfere at the filesystem/data level - this is a shared resource concern, not a snapd incompatibility.

**Verification:** No verification has yet been done.

### opengl
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Desktop/Graphics/Media Integration


**Code analysis:**
- Access is to GPU driver stacks, DRM render nodes, and vendor libraries.
- The rules are broad and intentionally allow multiple GPUs / render nodes.
- The interface uses instance-agnostic paths and does not key access on snap instance identity.
- Some vendor-specific state is shared, but the code treats it as normal multi-client GPU access.

**Reasoning:** The interface is client/server model where the slot provides GPU access. No snap-instance-specific naming exists on either side. Parallel plug instances work as multiple GPU clients. Parallel slot instances (if app-provided) would provide access to different GPUs without conflicts at the snapd layer. All instances share the same GPU hardware resources and performance, which is the shared resource concern.

**Verification:** No verification has yet been done.

### jack1
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Daemon/Socket Client


**Code analysis:**
- Access is to JACK1 shared memory endpoints under `/dev/shm/jack-*`.
- The rules are based on JACK's server/client naming convention, not on snap instance names.
- There is no snap-specific namespace logic in the interface.

**Reasoning:** The JACK client/server model supports multiple clients. Parallel plug instances work as concurrent JACK clients. Parallel slot instances (if app-provided) could run different JACK servers on different shared memory segments. However, all instances sharing the same JACK session namespace and shared memory can interfere at the audio session level - this is a shared resource concern.

**Verification:** No verification has yet been done.

### pcscd
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Daemon/Socket Client


**Code analysis:**
- Client access is via `/run/pcscd/pcscd.comm`.
- The interface also grants read access to OpenSC config files.
- No singleton service ownership or instance-specific pathing is involved.

**Reasoning:** The interface is socket-based client/server model. Parallel plug instances work as concurrent PC/SC clients. Parallel slot instances (if app-provided) could provide different PC/SC daemons on different sockets. However, all instances accessing the same daemon and smart cards/readers contend for shared hardware resources.

**Verification:** No verification has yet been done.

### network
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (core-only slot; no parallel app slot providers possible).

**Type:** Network/Netlink Interface


**Code analysis:**
- Client-side network access only. The connected-plug AppArmor is a static snippet (`network.go:42-75`) containing only `dbus send` rules to `org.freedesktop.resolve1` (lines 51-56) and `org.freedesktop.systemd1` (lines 61-66), plus nameservice/ssl_certs abstractions and read-only `@{PROC}/sys/net/...` (lines 70-71). There is no `dbus (bind)` and no `DBusPermanentSlot`, so the interface owns no D-Bus name — it is purely a client.
- Seccomp snippet (`network.go:78-91`) is generic networking support: `bind`, `socket AF_NETLINK - NETLINK_ROUTE`, `socket AF_CONN`.
- No use of `SnapName()`, `InstanceName()`, `ExpandSnapVariables()`, or `LabelExpression()`; no hardcoded `/var/snap/<name>/` paths; no udev tagging; no shared kernel objects, abstract sockets, or fixed ports.
- Slot is restricted to core only (`network.go:24-29`: `slot-snap-type: [core]`); registered as a `commonInterface` with `implicitOnCore`/`implicitOnClassic` (lines 97-98).

**Reasoning:** This is a pure client interface for network access (send-only D-Bus to resolved/systemd1 plus a generic seccomp networking grant). Parallel plug instances work as independent network clients with no snapd-level (instance-name) collision. The slot side is core-only, so parallel app-provided slots are not possible.

**Verification:** No verification has yet been done.

### network-manager-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE.

**Type:** D-Bus/IPC Client


**Code analysis:**
- The slot is app-providable (`network_manager_observe.go:31-40`: `allow-installation: slot-snap-type: [app, core]`, `deny-auto-connection`, `deny-connection: on-classic: false`); `ImplicitOnClassic: true` (line 191).
- The interface only observes NetworkManager state and settings. The connected-plug AppArmor (`network_manager_observe.go:103-180`) is a **system-bus** D-Bus client: `dbus (send)` reads (Get/GetAll, GetDevices, ListConnections, GetSettings, GetManagedObjects, lines 106-135) and `dbus (receive)` of signals (PropertiesChanged, StateChanged, Device/Interfaces Added/Removed, lines 138-179), all with `peer=(label=###SLOT_SECURITY_TAGS###)`.
- **It does not own the NetworkManager bus name.** There is no `dbus (bind)` and no `DBusPermanentSlot` anywhere; `org.freedesktop.NetworkManager` appears only as a `send` peer destination (`name=...`), which is client addressing. Even the connected-**slot** snippet (`network_manager_observe.go:44-101`, applied when `!release.OnClassic`) is `dbus (receive)`/`dbus (send)` only — it never binds the name.
- `AppArmorConnectedPlug()` uses `slot.LabelExpression()` (line 204) and `AppArmorConnectedSlot()` uses `plug.LabelExpression()` (line 214); these build instance-aware peer labels. No `InstanceName()`/`SnapName()`/`ExpandSnapVariables()`, no hardcoded `/var/snap/<name>/` paths, no shared per-user state files, no seccomp/udev.

**Reasoning:** This is a read-only system-bus D-Bus client interface. Parallel plug instances work as multiple independent observers of NetworkManager with instance-aware peer labels and no name ownership. The slot side is also parallel-install safe: although an app snap may provide it, the slot never binds/owns `org.freedesktop.NetworkManager` (its rules are receive/send only), so it is not a singleton — hence Slot-side COMPATIBLE.

**Verification:** No verification has yet been done.

### openvswitch
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (core-only slot; no parallel app slot providers possible).

**Type:** Daemon/Socket Client


**Code analysis:**
- Path-based client access to Open vSwitch management sockets: `/run/openvswitch/db.sock rw` (`openvswitch.go:37`), `/run/openvswitch/*.mgmt rw` (line 38), `/run/openvswitch/ovs-vswitchd.*.ctl rw` (line 40), `/run/openvswitch/ovs-vswitchd.pid rw` (line 41). These are sockets owned by the host ovs daemon — client access, with no service definition.
- No D-Bus (no `dbus (bind)`/`DBusPermanentSlot`), no seccomp snippet, no udev tagging, and no use of `SnapName()`/`InstanceName()`/`ExpandSnapVariables()`/`LabelExpression()`. The `/run/openvswitch/` paths are host daemon paths, not snap-name paths.
- Slot is restricted to core only (`openvswitch.go:24-30`: `slot-snap-type: [core]`); note the interface sets `implicitOnClassic: true` but NOT `implicitOnCore` (`openvswitch.go:45-51`), so the slot type is core-only and the interface is implicitly available on classic only.

**Reasoning:** This is a client-side interface to the host's Open vSwitch management sockets. It defines no singleton service and bakes in no snap name, so parallel plug instances each connect to the same host ovs daemon as concurrent clients with no snapd-level collision. The slot side is core-only, so parallel app-provided slots are not possible.

**Verification:** No verification has yet been done.

### libvirt
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (core-only slot; no parallel app slot providers possible).

**Type:** Daemon/Socket Client


**Code analysis:**
- Path-based client access to libvirt sockets: `/run/libvirt/libvirt-sock-ro rw` (`libvirt.go:33`), `/run/libvirt/libvirt-sock rw` (line 34), plus read-only `/etc/libvirt/* r` (line 35) and `/var/lib/snapd/hostfs/var/lib/libvirt/dnsmasq/{,**} r` (line 36, a host path). These are sockets owned by the host libvirtd — client access, no service-name ownership.
- Seccomp (`libvirt.go:40-43`) allows `listen`, `accept`, `accept4`. No D-Bus (no `dbus (bind)`/`DBusPermanentSlot`), no udev tagging, and no use of `SnapName()`/`InstanceName()`/`ExpandSnapVariables()`/`LabelExpression()`.
- Slot is restricted to core only (`libvirt.go:24-30`: `slot-snap-type: [core]`); note `implicitOnClassic: true` is set but NOT `implicitOnCore` (`libvirt.go:46-53`), so the slot type is core-only and the interface is implicitly available on classic only.

**Reasoning:** This is a client-side interface to the host libvirtd sockets plus a few read-only config paths. It has no instance-name scoping and no service-name ownership, so parallel plug instances each connect to the same host libvirtd as concurrent clients with no snapd-level collision. The slot side is core-only, so parallel app-provided slots are not possible.

**Verification:** No verification has yet been done.

### docker
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (slot is denied to app snaps by default; only core/system can provide it).

**Type:** Daemon/Socket Client


**Code analysis:**
- The connected-plug AppArmor (`docker.go:37-43`) is socket-path based and client-only: it grants `/{,var/}run/docker.sock rw,` (line 42) to talk to the Docker daemon socket. No `dbus (bind)`, no `DBusPermanentSlot`, no name ownership.
- Connected-plug seccomp (`docker.go:45-51`) grants `bind` and `socket AF_NETLINK - NETLINK_GENERIC`.
- The base declaration lists `allow-installation: slot-snap-type: [app, core]` but immediately follows with `deny-installation: slot-snap-type: [app]` (`docker.go:26-32`), so an app snap cannot provide the docker slot by default — only `core` (or a store-granted snap-declaration override). There is no slot-side code at all (no `AppArmorConnectedSlot`/`AppArmorPermanentSlot`/`Mount*`); it is a plain `commonInterface` (`docker.go:53-61`).
- No use of `SnapName()`/`InstanceName()`/`ExpandSnapVariables()`/`LabelExpression()`; no hardcoded `/var/snap/<name>/` paths; no udev tagging. The only path is the fixed system daemon socket `/{,var/}run/docker.sock`.

**Reasoning:** This is a client interface to a fixed Docker daemon socket. Parallel plug instances work as concurrent Docker clients with no instance-specific naming and no snapd-level collision. The slot side is out of scope for parallel app installs because the base declaration denies app-snap installation of the slot by default (and the interface contributes no slot-side policy that could collide).

**Verification:** No verification has yet been done.

### podman
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (core-only slot; no parallel app slot providers possible).

**Type:** Daemon/Socket Client


**Code analysis:**
- The connected-plug AppArmor (`podman.go:33-41`) is socket-path based and client-only: the system Podman socket `/{,var/}run/podman/podman.sock rw,` (line 38) and the rootless/user socket `owner /{,var/}run/user/[0-9]*/podman/podman.sock rw,` (line 40, keyed on the UID via `[0-9]*`, not a snap instance). No `dbus (bind)`, no `DBusPermanentSlot`.
- Connected-plug seccomp (`podman.go:43-49`) grants `bind` and `socket AF_NETLINK - NETLINK_GENERIC`.
- No use of `SnapName()`/`InstanceName()`/`ExpandSnapVariables()`/`LabelExpression()`; no hardcoded `/var/snap/<name>/` paths; no udev tagging; no shared memory.
- Slot is restricted to core only (`podman.go:24-31`: `slot-snap-type: [core]`, plus `deny-connection`/`deny-auto-connection`).

**Reasoning:** This is a client interface to fixed Podman socket paths (system + per-UID rootless). Parallel plug instances work as concurrent Podman clients with no instance-scoped naming and no snapd-level collision. The slot side is core-only, so parallel app-provided slots are not possible.

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
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Network/Netlink Interface


**Code analysis:**
- The interface grants CAN network access and allows AF_CAN sockets.
- No instance-specific pathing or ownership is present.
- The kernel handles CAN bus concurrency; the interface is just a client to that medium.

**Reasoning:** The interface is network/protocol based with no snap-instance-specific naming on either side. Parallel plug instances work as concurrent CAN bus clients. Parallel slot instances (if app-provided) could provide access to different CAN interfaces without snapd conflicts. However, instances sharing the same bus can interfere at the CAN protocol/application level if they use overlapping identifiers - this is a shared resource concern.

**Verification:** No verification has yet been done.

### kernel-crypto-api
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (core-only slot; no parallel app slot providers possible).

**Type:** Hardware Device Access


**Code analysis:**
- Access is to the Linux kernel crypto API through `AF_ALG` and `NETLINK_CRYPTO`. AppArmor (`kernel_crypto_api.go:37-47`) grants `@{PROC}/crypto r,`, `network alg seqpacket,` (for `AF_ALG`, line 42), and `network netlink dgram,`/`network netlink raw,` (for `NETLINK_CRYPTO`, lines 45-46). Seccomp (`kernel_crypto_api.go:49-54`) grants `socket AF_NETLINK - NETLINK_CRYPTO` (line 51), `bind`, `accept`.
- Each process opens its own `AF_ALG` socket; there is no shared named object, path, or D-Bus name. No `dbus (bind)`/`DBusPermanentSlot`, no udev tagging, and no use of `SnapName()`/`InstanceName()`/`ExpandSnapVariables()`/`LabelExpression()`.
- Slot is restricted to core only (`kernel_crypto_api.go:29-35`: `slot-snap-type: [core]`).

**Reasoning:** This is a kernel-API client interface; each process opens its own `AF_ALG`/`NETLINK_CRYPTO` socket with no shared named object and no instance-specific path. Parallel plug instances are fully independent clients of the kernel crypto subsystem with no snapd-level collision. The slot side is core-only, so parallel app-provided slots are not possible.

**Verification:** No verification has yet been done.

### avahi-control
**Status:** Plug-side: COMPATIBLE. Slot-side: NOT COMPATIBLE for app-provided slots (owns the singleton `org.freedesktop.Avahi` name); N/A for the implicit system slot.

**Type:** D-Bus Service/Provider


**Code analysis:**
- The slot is app-providable (`avahi_control.go:31-40`: `allow-installation: slot-snap-type: [app, core]`, `deny-auto-connection`, `deny-connection: on-classic: false`); `ImplicitOnClassic: true` (line 113).
- The interface imports and extends `avahi-observe` behavior. `AppArmorConnectedPlug()` (`avahi_control.go:118-137`) adds both the observe and control plug snippets. The control plug snippet (`avahi_control.go:60-102`) is `dbus (send)` to the Avahi server / entry groups (Set*, EntryGroupNew, Free/Commit/Reset, GetState/IsEmpty/UpdateServiceTxt, Add*) with `peer=(name=org.freedesktop.Avahi, label=###SLOT_SECURITY_TAGS###)`, plus one `dbus (receive)`. Sending to `name=org.freedesktop.Avahi` is client addressing, not ownership.
- **Plug side owns no D-Bus name.** The only name ownership lives in the slot-only material inherited from avahi-observe: `dbus (bind) bus=system name="org.freedesktop.Avahi"` (`avahi_observe.go:77-79`) and `<allow own="org.freedesktop.Avahi"/>` in the D-Bus policy (`avahi_observe.go:213`). avahi-control reaches these only via `AppArmorPermanentSlot()` (line 145) and `DBusPermanentSlot()` (line 171), each guarded by `!implicitSystemPermanentSlot(slot)` (lines 142, 168) — i.e. applied only when an app snap provides the slot.
- `AppArmorConnectedPlug()` uses `slot.LabelExpression()` (line 129) and `AppArmorConnectedSlot()` uses `plug.LabelExpression()` (line 155), both instance-aware. No `InstanceName()`/`SnapName()`/`ExpandSnapVariables()`, no hardcoded `/var/snap/<name>/` paths, no seccomp/udev.

**Reasoning:** A parallel client snap using `avahi-control` behaves like any other client: it only sends to / receives from the Avahi system service (no `dbus (bind)`, no `<allow own>`) with instance-aware peer labels, so the plug side is COMPATIBLE. A parallel *provider* snap is constrained by the singleton Avahi service name: when an app snap provides the slot, it binds/owns the well-known `org.freedesktop.Avahi` name (`avahi_observe.go:77-79`, `:213`), and two parallel provider instances cannot both own it — so the slot side is NOT COMPATIBLE for app providers (and N/A for the implicit system slot, which is handled outside snap confinement).

**Verification:** No verification has yet been done.

### fwupd
**Status:** Plug-side: COMPATIBLE. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
- The connected-plug AppArmor (`fwupd.go:262-334`) is a **system-bus** D-Bus client: `dbus (receive, send)` to the fwupd service at `path=/ interface=org.freedesktop.fwupd` and `org.freedesktop.DBus.Properties` (lines 293-303), plus send-only Introspect (lines 307-312) and read-only queries to `org.freedesktop.systemd1` (lines 314-333). The peer is `###SLOT_SECURITY_TAGS###` for the fwupd service and `unconfined` for systemd1.
- **The plug owns no D-Bus name.** The only `dbus (bind) bus=system name="org.freedesktop.fwupd"` (line 197-199) and `<allow own="org.freedesktop.fwupd"/>` (`fwupd.go:369`) live in `fwupdPermanentSlotAppArmor`/`fwupdPermanentSlotDBus`, applied only to the slot provider and guarded by `!implicitSystemPermanentSlot(slot)` (`AppArmorPermanentSlot()` line 453, `DBusPermanentSlot()` line 431).
- `AppArmorConnectedPlug()` substitutes `###SLOT_SECURITY_TAGS###` with `slot.LabelExpression()` on Core / `unconfined` for the implicit system slot (`fwupd.go:437-448`), so the peer label is instance-aware. Connected seccomp is just `bind` (`fwupd.go:388-392`). No `SnapName()`/`InstanceName()`/`ExpandSnapVariables()` and no hardcoded `/var/snap/<name>/` paths on the plug side.

**Reasoning:** As a client interface, fwupd behaves like other system-bus D-Bus consumers (`avahi-observe`, `network-manager` plug side): the plug owns no well-known name, uses instance-aware peer labels, and just sends to / receives from the fwupd service, so parallel plug instances have no snapd-level collision — plug side is COMPATIBLE. The slot side remains a hard singleton: a provider snap binds/owns `org.freedesktop.fwupd` (`fwupd.go:197-199`, `:369`), which two parallel provider instances cannot both hold, so slot side is NOT COMPATIBLE (and N/A for the implicit system slot).

**Verification:** No verification has yet been done.

### maliit
**Status:** Plug-side: COMPATIBLE. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
- The slot is app-only (`maliit.go:33-40`: `allow-installation: slot-snap-type: [app]`, `deny-connection`, `deny-auto-connection`).
- The connected-plug AppArmor (`maliit.go:97-119`) is a **session-bus** client: `dbus (send)` to the address service `org.maliit.Server.Address` at `/org/maliit/server/address` (lines 105-115), plus a peer-to-peer `unix (send, receive, connect)` to the per-client socket `@/tmp/maliit-server/dbus-*` (line 118). Both use `peer=(label=###SLOT_SECURITY_TAGS###)`.
- **The plug owns no D-Bus name.** The only `dbus (bind) bus=session name="org.maliit.server"` (`maliit.go:64-66`) and the `unix (bind, listen, accept)` for the peer-to-peer socket (line 75) live in `maliitPermanentSlotAppArmor`, applied to the slot provider via `AppArmorPermanentSlot()` (line 153).
- `AppArmorConnectedPlug()` substitutes `###SLOT_SECURITY_TAGS###` with `slot.LabelExpression()` (`maliit.go:140-145`), which is instance-aware. The per-client peer-to-peer socket (`@/tmp/maliit-server/dbus-*`) is negotiated at runtime and matched by peer label, not by snap name. No `InstanceName()`/`SnapName()` and no hardcoded `/var/snap/<name>/` paths on the plug side.

**Reasoning:** The Maliit design brokers each client onto its own private peer-to-peer socket, so on the plug side a client just talks to the address service and then to its own socket with instance-aware peer labels, owning no name — parallel plug (consumer) instances do not collide, so plug side is COMPATIBLE. The slot side binds the singleton well-known name `org.maliit.server` (`maliit.go:64-66`); two parallel provider instances cannot both own it, so slot side is NOT COMPATIBLE.

**Verification:** No verification has yet been done.

### mpris
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
- The slot binds `org.mpris.MediaPlayer2.<name>` based on a `name` attribute, defaulting to `SNAP_INSTANCE_NAME`.
- The code explicitly warns that snaps using this interface must adjust themselves for parallel installs.
- The plug side discovers and talks to the player over the session bus.
- The implementation is careful about per-snap naming, but the well-known bus name still represents a provider identity.

**Reasoning:** Parallel plug instances work as independent MPRIS clients. Parallel slot instances work correctly because the D-Bus well-known name uses `SNAP_INSTANCE_NAME` by default (e.g., `org.mpris.MediaPlayer2.snap_foo` vs `org.mpris.MediaPlayer2.snap`). The interface code explicitly supports per-instance naming, preventing D-Bus name collisions between parallel provider instances.

**App-level caveat:** Applications that override the default `name` attribute with a fixed value (instead of accepting the instance-aware default) will create D-Bus name collisions between parallel instances. Apps should either use the default or incorporate instance-specific identifiers if parallel instances are intended.

**Verification:** No verification has yet been done.

### pipewire
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE (permanent-slot socket names `pipewire-[0-9]`/`pipewire-[0-9]-manager` are fixed per user session, not instance-keyed, so two parallel providers in the same session contend over the same runtime socket name).

**Type:** Daemon/Socket Client


**Code analysis:**
- The slot is app-providable (`pipewire.go:33-42`: `allow-installation: slot-snap-type: [app, core]`, `deny-auto-connection: true`); `implicitOnClassic: true`, `implicitOnCore: false` (`pipewire.go:117-118`).
- The base connected-plug AppArmor (`pipewire.go:44-47`) grants `owner /run/user/[0-9]*/pipewire-[0-9] rw,` for classic/system slots.
- For app-provided slots, `AppArmorConnectedPlug()` (`pipewire.go:89-101`, gated by `!implicitSystemConnectedSlot(slot)` at line 91) uses instance-aware paths:
  - `###SLOT_SECURITY_TAGS###` is replaced with `"snap." + slot.Snap().InstanceName()` (line 93), producing `/run/user/[0-9]*/snap.<SLOT_INSTANCE_NAME>/pipewire-[0-9]` (template line 50).
  - `###SLOT_INSTANCE_NAME###` is replaced with `slot.Snap().InstanceName()` (line 96), producing `/var/snap/<SLOT_INSTANCE_NAME>/common/pipewire-[0-9]` for system mode (template line 52).
- The slot provider creates sockets at `/run/user/[0-9]*/pipewire-[0-9]` and `/run/user/[0-9]*/pipewire-[0-9]-manager` (`pipewirePermanentSlotAppArmor`, lines 68-69).
- No D-Bus name ownership (no `dbus (bind)`/`DBusPermanentSlot`). Shared memory is handled via the `shmctl` seccomp syscall (plug line 56; permanent slot line 80), not a `/dev/shm` path rule.
**Reasoning:** The plug-side correctly uses `slot.Snap().InstanceName()` (lines 93, 96) for instance-aware path resolution when connecting to an app-provided slot, so there is no base-snap-name hardcoding and no snapd-level collision. Multiple parallel plug instances connecting to the same PipeWire server (system or snap-provided) is the normal multi-client audio pattern, so the plug side is COMPATIBLE.

The slot side is parallel-safe at the snapd policy layer — there is no `SNAP_NAME`-vs-`INSTANCE_NAME` bug and no D-Bus name ownership — but the permanent-slot socket names (`pipewire-0`, etc., lines 68-69) are fixed and not instance-keyed, so two parallel slot providers in the same user session would contend over the same runtime socket name. That is a session/host shared-resource contention rather than a snapd identifier collision, so the slot side is COMPATIBLE EXCEPT FOR SHARED RESOURCE.

**Verification:** No verification has yet been done.

### cups
**Status:** Plug-side: COMPATIBLE. Slot-side: POTENTIALLY COMPATIBLE.

**Type:** Daemon/Socket Client


**Code analysis:**
The `cups` interface (distinct from `cups-control`) lets a provider snap expose a CUPS socket to consumers via bind-mount and path-based mediation. The slot is app-only (`cups.go:48-55`: `allow-installation: slot-snap-type: [app]`, `deny-connection`/`deny-auto-connection`; `implicitOnCore: false`, `implicitOnClassic: false`), so slot-side parallel-install correctness is directly in scope.

**Plug side (the consumer):** `cupsConnectedPlugAppArmor` (`cups.go:57-78`) grants the consumer access to the CUPS socket at the fixed in-its-own-namespace path `/var/cups/cups.sock` (line 77). `MountConnectedPlug()` (`cups.go:188-206`) bind-mounts the provider's socket directory onto the plug's own `/var/cups/` (target `Dir: "/var/cups/"`, lines 201-205). Because the mount **target** is the plug's own fixed namespace path, multiple keyed consumer instances each get an identical, self-namespace target with no instance collision — the plug side is COMPATIBLE.

**Slot side (the provider) — the bug:**

1. **Socket path resolution uses `PerspectiveSelf`** (`cups.go:130`):
   `validateCupsSocketDirSlotAttr()` returns `snapInfo.ExpandSnapVariables(cupsdSocketSourceDir)`, and `ExpandSnapVariables()` defaults to `PerspectiveSelf` (`snap/info.go:809`), which resolves `$SNAP_COMMON`/`$SNAP_DATA` via the base `SnapName()` (`snap/info.go:829`) to `/var/snap/cups-provider/common/...` — NOT `InstanceName()`.

2. **The provider snap sees namespace-remapped paths**: Inside the provider snap's mount namespace, `/var/snap/cups-provider/` is bind-mounted from the host path `/var/snap/cups-provider_foo/`. When the provider creates its socket at what it sees as `/var/snap/cups-provider/common/...`, the socket is actually created at the host path `/var/snap/cups-provider_foo/common/...`.

3. **The base-name path is used as a host bind-mount source and in mount profiles** (`cups.go:188-206`, and `cups.go:179,182`):
   `MountConnectedPlug()` creates a `MountEntry` whose **source** (`Name`) is the base-name-resolved `cupsdSocketSourceDir` (`cups.go:201-205`). `AppArmorConnectedPlug()` additionally emits this base-name path into the snap-update-ns mount profile via `emit("mount options=(rw bind) \"%s/\" -> /var/cups/,", ...)` (`cups.go:179`) and `GenWritableProfile(emit, cupsdSocketSourceDir, 1)` (`cups.go:182`). None of these resolve to the keyed host path `/var/snap/cups-provider_foo/common/...`, so the source does not exist on the host for a keyed provider.

4. **AppArmor accessor rule has the same mismatch** (`cups.go:170`):
   Permissions are granted for `"%s/**" mrwklix,` using the base-name dir (`/var/snap/cups-provider/common/**`) instead of `/var/snap/cups-provider_foo/common/**`.

5. **Contrast with `content` interface**: `content` uses `PerspectiveOther` for provider path expansion (`content.go:234`), which calls `InstanceName()` and produces the correct host path `/var/snap/cups-provider_foo/...`.

**Reasoning:** The plug/consumer side is parallel-install safe because the bind-mount target is the consumer's own fixed namespace path `/var/cups/`. The current slot/provider implementation is incompatible due to a concrete path-resolution bug: it needs to bind-mount from the **host filesystem path** where the provider's socket actually exists, but it resolves that path with `PerspectiveSelf` (base `SnapName()`), so for a keyed provider instance the source path, AppArmor rule, and snap-update-ns profile all point at the unkeyed `/var/snap/cups-provider/...` which does not exist on the host. Because this is a fixable implementation defect (use `PerspectiveOther`/`InstanceName()` as in `content.go:234`), slot-side is POTENTIALLY COMPATIBLE.

**Verification:**
- Plug-side: passed on noble (`test-snapd-cups-consumer_foo` connected and communicated through provider socket; remained functional after removing original consumer).
- Slot-side parallel provider: expected to fail because bind mount source path doesn't exist on host.

### serial-port
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Slots are provided by core or gadget snaps only (`serial_port.go:40-43`: `slot-snap-type: [core, gadget]`), not by application snaps. The interface summary is literally "allows accessing a specific serial port" (`serial_port.go:36`).
- The slot requires a `path` attribute pointing to a specific device node (e.g., `/dev/ttyUSB0`) or a udev symlink (`/dev/serial-port-*`) with USB vendor/product attributes (`BeforePrepareSlot()`, `serial_port.go:90-138`).
- `AppArmorConnectedPlug()` (`serial_port.go:164-181`): with USB attrs it emits a broad approximation `/dev/tty[A-Z]*[0-9] rwk,` (line 169) that is then narrowed by udev/cgroup tagging; otherwise it emits the fixed device node from the slot's `path` via `cleanedPath := filepath.Clean(path)` (line 178) and `spec.AddSnippet(fmt.Sprintf("%s rwk,", cleanedPath))` (line 179). The path is core/gadget-authored, never snap-name-derived.
- `UDevConnectedPlug()` (`serial_port.go:183-212`) tags the specific device via `spec.TagDevice()` at line 200 (path-only `SUBSYSTEM=="tty", KERNEL=="<dev>"`) and lines 204/207 (USB vendor/product, optional interface number). `UDevPermanentSlot()` (`serial_port.go:140-162`) emits `SYMLINK+=` rules for the slot device.
- No use of `SnapName()`, `InstanceName()`, `ExpandSnapVariables()`, or `LabelExpression()`; no hardcoded `/var/snap/<name>/` paths; no D-Bus name ownership, shared memory, or sockets.

**Reasoning:** The plug policy is device-node/USB-id based with no per-instance naming, and udev tags are instance-aware via `TagDevice`, so there is no snapd-level collision between parallel keyed instances. However, a serial-port slot pins one specific serial device (a single `path`, or one USB serial device); two parallel instances connecting the same slot contend over that one physical port. This is a shared-hardware concern at the application/protocol level, not a snapd incompatibility, so the plug side is policy-compatible but shares a single physical resource.

**Verification:** No verification has yet been done.

### hidraw
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Slots are provided by core or gadget snaps only (`hidraw.go:38-41`: `slot-snap-type: [core, gadget]`), not by application snaps.
- The slot requires a `path` attribute pointing to a specific hidraw device node or a udev symlink with USB vendor/product attributes (`BeforePrepareSlot()`, `hidraw.go:74-117`).
- Device node pattern: `^/dev/hidraw[0-9]{1,3}$` (`hidraw.go:66`). Udev symlink pattern: `^/dev/hidraw-[a-z0-9]+$` (`hidraw.go:71`).
- `AppArmorConnectedPlug()` (`hidraw.go:139-156`): with USB attrs it emits the broad pattern `/dev/hidraw[0-9]{,[0-9],[0-9][0-9]} rw,` (line 143); otherwise the fixed node from the slot `path` via `cleanedPath := filepath.Clean(path)` (line 152) and `spec.AddSnippet(fmt.Sprintf("%s rw,", cleanedPath))` (line 153).
- `UDevConnectedPlug()` (`hidraw.go:158-189`) tags the device via `spec.TagDevice()` at line 183 (path-only `SUBSYSTEM=="hidraw", KERNEL=="<dev>"`) and line 185 (USB vendor/product). `UDevPermanentSlot()` (`hidraw.go:119-137`) emits a `SYMLINK+=` rule.
- No use of `SnapName()`, `InstanceName()`, `ExpandSnapVariables()`, or `LabelExpression()`; no hardcoded `/var/snap/<name>/` paths; no D-Bus, shared memory, or sockets.

**Reasoning:** Like serial-port, the policy is device-node/USB-id based with no per-instance naming, and udev tags are instance-aware via `TagDevice`, so there is no snapd-level collision between parallel instances. But the slot pins one specific hidraw device (a single `path`, or one USB HID device); two parallel instances connecting the same slot share that single physical device and would interfere at the HID protocol level. That is an application/hardware concern, so the plug side is policy-compatible but shares a single physical resource.

**Verification:** No verification has yet been done.

### i2c
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (gadget/core-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Slots are provided by gadget or core snaps only (`i2c.go:38-41`: `slot-snap-type: [gadget, core]`), not by application snaps. The interface summary is "allows access to specific I2C controller" (`i2c.go:34`).
- The slot can specify either a `path` attribute (e.g., `/dev/i2c-0`) or a `sysfs-name` attribute, but not both (`BeforePrepareSlot()`, `i2c.go:85-113`; mutual exclusion at lines 91-93).
- Device node pattern: `^/dev/i2c-[0-9]+$` (`i2c.go:79`). Sysfs name pattern: `^[a-zA-Z0-9_-]+$` (`i2c.go:82`).
- `AppArmorConnectedPlug()` (`i2c.go:115-137`): for `sysfs-name`, emits `/sys/bus/i2c/devices/<name>/** rw,` (line 120); for `path`, emits `<cleanedPath> rw,` (line 131) plus a parametric snippet for `/sys/devices/platform/{*,**.i2c}/i2c-<N>/** rw,` (lines 133-135, where `<N>` is `strings.TrimPrefix(path, "/dev/i2c-")`). All values come from slot attributes, never from a snap/instance name.
- `UDevConnectedPlug()` (`i2c.go:139-146`) tags the device via `spec.TagDevice(KERNEL=="<dev>")` at line 144 (path-only; if only `sysfs-name` is set, it returns early and emits no udev rule).
- No use of `SnapName()`, `InstanceName()`, `ExpandSnapVariables()`, or `LabelExpression()`; no hardcoded `/var/snap/<name>/` paths (the sysfs paths are hardware paths); no D-Bus, shared memory, or sockets.

**Reasoning:** Rules are derived purely from the slot's `path`/`sysfs-name` with no per-instance naming, and udev tags are instance-aware via `TagDevice`, so there is no snapd-level collision between parallel instances. However, the slot pins a single I2C controller (one `/dev/i2c-N` node or one sysfs device), so two parallel instances connecting the same slot contend over that one shared controller. Whether concurrent access is safe depends on the bus devices and application protocol; the kernel arbitrates bus access but not higher-level conflicts. So the plug side is policy-compatible but shares a single physical controller.

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
**Status:** Plug-side: COMPATIBLE. Slot-side: POTENTIALLY COMPATIBLE.

**Type:** Daemon/Socket Client


**Code analysis:**
- Slot installation is denied by default, requires snap-declaration (lines 26-28).
- AppArmor rules grant access to the LXD socket at `/var/snap/lxd/common/lxd/unix.socket` (line 35).
- Seccomp rules allow `AF_NETLINK` socket creation (line 42).
- The socket path is **hardcoded** to the `lxd` snap's location, not parameterized by instance name.
- No D-Bus, no shared memory.
- This is a client interface to the LXD daemon.

**Reasoning:** Parallel plug instances work as concurrent LXD clients. The current slot-side incompatibility comes from a concrete, fixable code defect: the provider socket path is hardcoded to `/var/snap/lxd/...` instead of being instance-aware. A parallel instance like `lxd_test` has its socket at `/var/snap/lxd_test/common/lxd/unix.socket`, but current policy still targets `/var/snap/lxd/...`. If the path construction is made instance-aware, slot-side would be compatible, so it is POTENTIALLY COMPATIBLE.

**Verification:** No verification has yet been done.

### microceph
**Status:** Plug-side: COMPATIBLE. Slot-side: POTENTIALLY COMPATIBLE.

**Type:** Daemon/Socket Client


**Code analysis:**
- Slot installation is denied by default, requires snap-declaration (lines 25-28).
- AppArmor rules grant access to the MicroCeph socket at `/var/snap/microceph/common/state/control.socket` (line 34).
- Seccomp rules allow `AF_NETLINK` socket creation (line 40).
- The socket path is **hardcoded** to the `microceph` snap's location, not parameterized by instance name.
- No D-Bus, no shared memory.

**Reasoning:** Parallel plug instances work as concurrent MicroCeph clients. The current slot-side incompatibility comes from a concrete, fixable code defect: the provider socket path is hardcoded to `/var/snap/microceph/...` instead of being instance-aware. A parallel instance like `microceph_test` has its socket at `/var/snap/microceph_test/common/state/control.socket`, but current policy still targets `/var/snap/microceph/...`. If the path construction is made instance-aware, slot-side would be compatible, so it is POTENTIALLY COMPATIBLE.

**Verification:** No verification has yet been done.

### microovn
**Status:** Plug-side: COMPATIBLE. Slot-side: POTENTIALLY COMPATIBLE.

**Type:** Daemon/Socket Client


**Code analysis:**
- Slot installation is denied by default, requires snap-declaration (lines 25-28).
- AppArmor rules grant access to the MicroOVN socket at `/var/snap/microovn/common/state/control.socket` (line 34).
- Seccomp rules allow `AF_NETLINK` socket creation (line 40).
- The socket path is **hardcoded** to the `microovn` snap's location, not parameterized by instance name.
- No D-Bus, no shared memory.
- This is a client interface to the MicroOVN daemon.

**Reasoning:** Parallel plug instances work as concurrent MicroOVN clients. The current slot-side incompatibility comes from a concrete, fixable code defect: the provider socket path is hardcoded to `/var/snap/microovn/...` instead of being instance-aware. A parallel instance like `microovn_test` has its socket at `/var/snap/microovn_test/common/state/control.socket`, but current policy still targets `/var/snap/microovn/...`. If the path construction is made instance-aware, slot-side would be compatible, so it is POTENTIALLY COMPATIBLE.

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
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Filesystem/Mount Interface


**Code analysis:**
- Slots are provided by core or gadget snaps only (`bool_file.go:34-41`: `slot-snap-type: [core, gadget]`).
- Slot validation accepts only LED brightness and GPIO value sysfs paths (regexes at `bool_file.go:63-72`, validated in `BeforePrepareSlot()` `bool_file.go:76-92`).
- `AppArmorConnectedPlug()` (`bool_file.go:106-125`) is built from the **dereferenced slot sysfs path** (`dereferencedPath`, lines 127-137), so the connected plug mediates the exact file the slot identifies; for GPIO slots, the permanent-slot rules expose export/unexport and direction handling (`bool_file.go:94-103`).
- **SNAP_NAME vs INSTANCE_NAME:** the interface is gadget/sysfs-path based, not snap-name based — no `@{SNAP_NAME}`/`@{SNAP_INSTANCE_NAME}`/`SnapName()`/`InstanceName()` anywhere. No bug (no snap-name path concept here).
- No D-Bus, no shared kernel named objects, no udev.

**Reasoning:** This is a specific-file interface with path validation and no snap-instance naming, so it is parallel-safe at the policy layer. However, the slot pins a single physical GPIO/LED sysfs file; two parallel plug instances connecting the same slot would each get access to that one hardware-backed file and contend over it — compatible at the snapd layer but sharing a single hardware resource.

**Verification:** No verification has yet been done.

### cifs-mount
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Filesystem/Mount Interface


**Code analysis:**
- Slot is provided by core only (`cifs_mount.go:24-30`: `slot-snap-type: [core]`), with implicit slots on core and classic (lines 71-72).
- AppArmor and seccomp permissions are for mount/umount of CIFS filesystems (seccomp `mount`/`umount`/`umount2` at `cifs_mount.go:32-37`; `capability sys_admin` at line 43).
- **SNAP_NAME vs INSTANCE_NAME (correct both-variant pattern):** the mount targets (`cifs_mount.go:48-49`) and umount targets (lines 55-56) use the alternation `/var/snap/{@{SNAP_NAME},@{SNAP_INSTANCE_NAME}}/...` for both `$SNAP_DATA` (`@{SNAP_REVISION}`) and `$SNAP_COMMON`. As the comments explain (lines 46-47, 53-54), `$SNAP_{DATA,COMMON}` are remapped, so `@{SNAP_NAME}` covers the in-namespace view and `@{SNAP_INSTANCE_NAME}` is allowed "for completeness" to cover the real keyed host path. Including both variants is the correct parallel-safe pattern; no bug.
- No D-Bus or shared kernel named objects (mounts land in the snap's own writable dirs).

**Reasoning:** The interface is already written to handle parallel-instance mount targets explicitly. The mount/umount rules include both the base (`@{SNAP_NAME}`) and instance (`@{SNAP_INSTANCE_NAME}`) variants for the snap's own `/var/snap/...` dirs, so there is no instance collision and parallel instances each mount into their own directories.

**Verification:** No verification has yet been done.

### empty
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE.

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
- Slot is provided by core only (`fuse_support.go:28-34`: `slot-snap-type: [core]`), with implicit slots on core and classic except old Ubuntu 14.04 (`fuse_support.go:101`).
- AppArmor grants `/dev/fuse rw,` (line 49), `capability sys_admin` (line 52), and `mount` seccomp (lines 36-41).
- **SNAP_NAME vs INSTANCE_NAME (correctly differentiated):**
  - Per-user `~/snap/...` (home) mount targets (`fuse_support.go:68-71`) use `@{SNAP_INSTANCE_NAME}` **only** (`/home/*/snap/@{SNAP_INSTANCE_NAME}/...`). The comment (line 67) explains `$SNAP_USER_{DATA,COMMON}` are **not** remapped, so the instance name is required for this host path. Using base here would be a bug; it correctly does not. ✓
  - System `/var/snap/...` mount targets (`fuse_support.go:74-77`) use **both** `{@{SNAP_NAME},@{SNAP_INSTANCE_NAME}}` because `$SNAP_{DATA,COMMON}` are remapped (comment lines 72-73). ✓
- UDev tags the `fuse` device (`KERNEL=="fuse"`, `fuse_support.go:94`). No D-Bus, no hardcoded base-name host path.

**Reasoning:** FUSE support is deliberately instance-aware in the mount rules, and crucially differentiates the two cases correctly: the non-remapped per-user `~/snap/<instance>/` path uses `@{SNAP_INSTANCE_NAME}` only, while the remapped system `/var/snap/...` path allows both variants. Each instance therefore mounts into its own directories with no `SNAP_NAME`-vs-`INSTANCE_NAME` bug.

**Verification:** No verification has yet been done.

### nfs-mount
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Filesystem/Mount Interface


**Code analysis:**
- Slot is provided by core only (`nfs_mount.go:24-30`: `slot-snap-type: [core]`), with implicit slots on core and classic (lines 85-86).
- AppArmor and seccomp permissions are for NFS mount/umount operations (seccomp `mount`/`umount`/`umount2` at `nfs_mount.go:32-37`; `capability sys_admin` at line 42; `/etc/rpc` read at line 78).
- **SNAP_NAME vs INSTANCE_NAME (correct both-variant pattern):** the mount targets (`nfs_mount.go:50-51`) and umount targets (lines 60-61) use `/var/snap/{@{SNAP_NAME},@{SNAP_INSTANCE_NAME}}/...` for both `$SNAP_DATA` (`@{SNAP_REVISION}`) and `$SNAP_COMMON`, with comments (lines 45-46, 55-56) giving the same rationale as cifs-mount (remapped paths → base variant, instance variant allowed for completeness). Both variants present; no bug.
- No D-Bus or shared kernel named objects.

**Reasoning:** Like cifs-mount, this interface is already instance-aware in its mount target rules: both the base (`@{SNAP_NAME}`) and instance (`@{SNAP_INSTANCE_NAME}`) variants are allowed for the snap's own `/var/snap/...` dirs, so parallel instances do not create a mount-path collision.

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
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE (the `pkcs11-socket` path is forced into the shared host `/run/p11-kit/` and is not instance-key disambiguated, so parallel slot providers collide unless the operator sets distinct socket paths).

**Type:** Identity/Credentials/Secrets


**Code analysis:**
- **Slot provider restriction:** the base declaration has only plug rules — `allow-installation: false`, `deny-auto-connection: true` (`pkcs11.go:35-39`). There is NO `slot-snap-type: core`, so the slot is **app-providable** (subject to a snap-declaration, since plug install is denied by default). `AutoConnect()` returns true (`pkcs11.go:157-160`). This makes slot-side parallel safety relevant.
- The slot provides a `pkcs11-socket` string attribute. `getSocketPath()` (`pkcs11.go:71-93`) requires it to be a string, cleans it, and enforces `filepath.Dir(socketPath) == "/run/p11-kit"` (lines 88-90) — i.e. every slot's socket must live directly in the shared host dir `/run/p11-kit`. `BeforePrepareSlot()` (`pkcs11.go:95-105`) additionally rejects AppArmor-regex metacharacters (`ValidateNoAppArmorRegexp`, line 101).
- The slot operates as a **server**: `pkcs11PermanentSlotSecComp` grants `bind`/`listen`/`accept`/`accept4` (`pkcs11.go:59-69`, applied at 107-110), and `AppArmorPermanentSlot()` grants `/{,var/}run/p11-kit/ rw` plus the socket `rwk` (`pkcs11.go:134-155`). `AppArmorConnectedPlug()` (`pkcs11.go:112-132`) grants the plug `rw` on the slot-specified socket plus fixed `/etc/pkcs11` and p11 tools.
- **SNAP_NAME vs INSTANCE_NAME:** there is no `@{SNAP_NAME}`/`@{SNAP_INSTANCE_NAME}`/`SnapName()`/`InstanceName()`/`LabelExpression()` anywhere — the socket path is taken verbatim from the slot attribute. Crucially, it is **not** auto-decorated with the instance key, so two parallel instances of the same slot snap carry the same `pkcs11-socket` value from their identical snap.yaml. There is no D-Bus name ownership (it is a unix-socket server).

**Reasoning:** Plug-side is a path-based client capability: each plug instance gets `rw` to the slot-specified socket under `/run/p11-kit`, with no snap-name derivation, so parallel plug instances are COMPATIBLE. Slot-side, however, is only parallel-safe if the `pkcs11-socket` attribute differs per instance: because the path is forced into the shared host directory `/run/p11-kit` and is not instance-key disambiguated, two parallel instances of the same slot snap default to the same `/run/p11-kit/<name>` socket and both try to bind it — a real collision over a shared host resource. Hence slot-side is COMPATIBLE EXCEPT FOR SHARED RESOURCE (it is not a D-Bus-name-ownership case).

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
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

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
- Slot is provided by core only (`login_session_control.go:24-30`: `slot-snap-type: [core]`), with implicit slots on core and classic (lines 68-69).
- The connected-plug AppArmor (`login_session_control.go:32-62`) is a **system-bus** D-Bus client to systemd-logind, all with `peer=(label=unconfined)`:
  - Properties on `/org/freedesktop/login1/{seat,session}/**` (lines 37-42)
  - Full access to `org.freedesktop.login1.Seat` (lines 44-48) and `org.freedesktop.login1.Session` (lines 50-54)
  - Manager methods: ActivateSession, GetSession, GetSeat, KillSession, ListSessions, LockSession, TerminateSession, UnlockSession (lines 56-61)
- **It owns no D-Bus name** — there is no `dbus (bind)`/`DBusPermanentSlot`/`<allow own>`; it is purely a client of systemd-logind. No `@{SNAP_NAME}`/`@{SNAP_INSTANCE_NAME}`/`SnapName()`/`InstanceName()`/`LabelExpression()`, no hardcoded `/var/snap/<name>/` paths, no mounts/seccomp/udev.

**Reasoning:** The login-session-control interface grants D-Bus client access to systemd-logind for managing login sessions. Multiple parallel instances all interact with the same logind service as concurrent clients with instance-aware AppArmor labels; the interface owns no bus name, so there is no snapd-level (instance-name) collision. Like other system-control interfaces (e.g. `time-control`, `hostname-control`), the resource it operates on — logind sessions/seats — is a system-wide singleton whose concurrent access is serialized by logind itself; this is the intended single-system-state model rather than a parallel-install incompatibility, so the plug side is COMPATIBLE.

**Verification:** No verification has yet been done.

### login-session-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** D-Bus/IPC Client


**Code analysis:**
- Slot is provided by core only (`login_session_observe.go:24-30`: `slot-snap-type: [core]`), with implicit slots on core and classic (lines 123-124).
- AppArmor rules grant:
  - Read access to login tracking files: `/var/log/wtmp` (line 36), `/{,var/}run/utmp` (line 37), `/var/log/lastlog` (line 40), `/var/log/faillog` (line 43)
  - Read access to systemd session files at `/run/systemd/sessions/` (lines 46-47)
  - Execute `who` (via `@{SNAP_COREUTIL_DIRS}who`, line 35), `lastlog`, `faillog`, `loginctl` (lines 39, 42, 57)
  - **System-bus** D-Bus **read-only** client access to systemd-logind for introspection, property queries, and signal receipt (`login_session_observe.go:62-112`); no `dbus (bind)`/`<allow own>`.
- **SNAP_NAME vs INSTANCE_NAME:** the one snap variable is `@{SNAP_COREUTIL_DIRS}who` (line 35); `@{SNAP_COREUTIL_DIRS}` expands to the snap's OWN in-namespace coreutils binary directories (a self/in-namespace path used to exec the bundled `who`), so the base/self view is correct — not a host artifact and not instance-keyed. No `@{SNAP_NAME}`/`@{SNAP_INSTANCE_NAME}`/`LabelExpression()`. No bug.

**Reasoning:** The login-session-observe interface grants read-only access to system login/session information (login records plus read-only logind D-Bus queries). Multiple parallel instances read the same system-wide login state; the interface owns no D-Bus name and the one snap variable (`@{SNAP_COREUTIL_DIRS}`) is a correct self/in-namespace path, so there is no instance-name collision.

**Verification:** No verification has yet been done.

### screen-inhibit-control
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE.

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
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (core-only slot; no parallel app slot providers possible).

**Type:** Hardware Device Access


**Code analysis:**
- AppArmor rules grant access to `/dev/snd/` and `/dev/snd/*` (read/write)
- UDev rules match sound devices by kernel name patterns (`c116:[0-9]*`, `+sound:card[0-9]*`)
- No D-Bus usage, no shared memory, no instance-specific paths
- Multiple instances access the same physical devices, which is the intended behavior for
  audio (the kernel/ALSA manages concurrent access)
- Slot is restricted to core only (slot-snap-type: [core]).

**Reasoning:** This is a hardware device access interface. Parallel plug instances work as concurrent ALSA clients accessing the same audio devices. The slot side is core-only, so parallel app-provided slots are not possible.

**Verification:**
PASSED on noble.

### pulseaudio
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE (the permanent slot's native socket `/{,var/}run/pulse/native` and the `pulse-shm-*` shared-memory name are fixed, not instance-keyed, so two parallel PA-server providers contend over the same session/host resources).

**Type:** Daemon/Socket Client


**Code analysis:**
- The slot is app-providable (`pulseaudio.go:35-44`: `allow-installation: slot-snap-type: [app, core]`, `deny-auto-connection: true`); `ImplicitOnClassic: true` (line 152).
- Shared memory: `/{run,dev}/shm/pulse-shm-* mrwk,` (`pulseaudio.go:49`, also `:118`)
  grants access to PulseAudio shared memory segments. These are NOT namespaced per snap
  instance. However, this is intentional -- all PulseAudio clients share the same SHM
  segments with the server. Multiple clients is the normal operating mode.
- **No D-Bus usage**: The pulseaudio interface does NOT use D-Bus at all (confirmed: zero `dbus (` rules in the file). Communication
  is exclusively via UNIX sockets (`/{,var/}run/pulse/native`, `pulseaudio.go:52`; `/run/user/[0-9]*/pulse/`) and POSIX shared memory.
  The previous audit incorrectly claimed "Global D-Bus name binding".
- Instance-aware runtime paths: for app-provided slots, `AppArmorConnectedPlug()` (`pulseaudio.go:157-169`, gated by `!implicitSystemConnectedSlot(slot)` at line 162) substitutes `###SLOT_SECURITY_TAGS###` with `"snap." + slot.Snap().InstanceName()` (`pulseaudio.go:164`), scoping the runtime socket directory to `/run/user/[0-9]*/snap.<SLOT_INSTANCE_NAME>/pulse/...`. Each app slot provider therefore gets its own instance-scoped socket path.
- No use of `SnapName()`/`ExpandSnapVariables()`/`LabelExpression()`; no hardcoded `/var/snap/<name>/` paths. `UDevPermanentSlot()` tags ALSA devices (`controlC[0-9]*`, `pcmC*`, `timer`, lines 171-176).

**Reasoning:** PulseAudio is designed for multiple simultaneous clients. The shared
memory segments (`pulse-shm-*`) are created by the PA server and shared with all
connected clients -- having two snap instances connect as clients is no different from
having two different snaps connect. The plug-side uses `slot.Snap().InstanceName()` (line 164) for app-provided slots, so there is no base-snap-name hardcoding and no snapd-level collision; the plug side is COMPATIBLE. Slot-side (running multiple PA servers) is parallel-safe at the snapd policy layer, but the permanent slot's native socket `/{,var/}run/pulse/native` (`pulseaudio.go:114-115`) and the shared-memory name `pulse-shm-*` (line 118) are fixed and not instance-keyed, so two parallel PA-server providers would contend over the same session/host resources. That is shared-session/host contention, not a parallel-install identifier bug, so the slot side is COMPATIBLE EXCEPT FOR SHARED RESOURCE.

**Previous audit errors**:
- Claimed "Global D-Bus name binding" -- INCORRECT. No D-Bus is used.
- Claimed "NOT COMPATIBLE" -- INCORRECT. Plug-side works fine.

**Verification:**
PASSED on noble.


### x11
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE (the permanent-slot X socket `@/tmp/.X11-unix/X[0-9]*` is keyed by display number in a global abstract-socket namespace, not by snap instance, so parallel X-server providers must coordinate distinct display numbers).

**Type:** Desktop/Graphics/Media Integration


**Code analysis:**
- Slot-side creates sockets at `/tmp/.X11-unix/X[0-9]*` (abstract socket `@/tmp/.X11-unix/X[0-9]*`, `x11.go:72,108`). Multiple X servers on
  different display numbers (X0, X1) can coexist.
- **SNAP_NAME vs INSTANCE_NAME (correct):** when the plug connects to an app-provided slot, the plug's private-tmp bind mount source uses the **instance** name: `MountConnectedPlug()` builds `Name: "/var/lib/snapd/hostfs/tmp/snap-private-tmp/snap.%s/tmp/.X11-unix"` with `slotSnapName := slot.Snap().InstanceName()` (`x11.go:194-197`), and the matching update-ns/AppArmor rules use the same instance-keyed path (`x11.go:220-224`). This is a HOST-side path referring to the slot snap's private tmp, so using `InstanceName()` is correct. There is no `@{SNAP_NAME}`/base-name path used for any host artifact.
- An early `if plug.Snap().InstanceName() == slot.Snap().InstanceName()` check (`x11.go:191,217`) skips the private-tmp bind when plug and slot are the same snap. For the implicit system slot, the bind source is the host `/var/lib/snapd/hostfs/tmp/.X11-unix` (`x11.go:178-179`).
- `AppArmorConnectedPlug()` substitutes `###PLUG_SECURITY_TAGS###` with `plug.LabelExpression()` (`x11.go:234-235`), which uses `InstanceName()`, so cross-instance peer matching is correct.

**Reasoning:** When a plug connects to a specific slot, the mount namespace setup
correctly isolates the socket sharing using the slot's **instance** name for the host-side private-tmp source (`x11.go:194-197`), and peer labels via `LabelExpression()` are instance-aware. Parallel instances of a client snap each get their own mount namespace entry, so the plug side is COMPATIBLE with no `SNAP_NAME`-vs-`INSTANCE_NAME` bug.

The slot side is parallel-safe at the snapd policy layer (the permanent-slot rule and the connected-slot peer label are identical for each keyed instance and match by display-number pattern + `plug.LabelExpression()`), but the X server socket `@/tmp/.X11-unix/X[0-9]*` (`x11.go:70-72`) is bound by **display number** in the global abstract-socket namespace, not by snap instance. Two parallel X-server providers must therefore use different display numbers (X0, X1) to coexist — a shared X11 session-namespace resource that must be coordinated, not a snapd identifier collision. So the slot side is COMPATIBLE EXCEPT FOR SHARED RESOURCE.

**Verification:**
PASSED on noble (parallel instances communicate correctly via
  instance-scoped private tmp).



### wayland
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE (the permanent-slot compositor socket `/run/user/[0-9]*/wayland-[0-9]*` is keyed by display number per user session, not by snap instance, so parallel compositor providers must coordinate distinct `WAYLAND_DISPLAY` numbers).

**Type:** Desktop/Graphics/Media Integration


**Code analysis:**
- Plug-side accesses `/run/user/[0-9]*/wayland-[0-9]*` sockets provided by the
  compositor (slot) (`wayland.go:56,116`). Multiple client snaps connecting to the same Wayland compositor is the normal use case.
- **SNAP_NAME vs INSTANCE_NAME (correct):** in `AppArmorConnectedSlot()` (`wayland.go:153-159`), `###PLUG_SECURITY_TAGS###` is replaced with `"snap." + plug.Snap().InstanceName()` (`wayland.go:154`) — with an explicit code comment that this "forms the snap-instance-specific subdirectory name of /run/user/*/ used for XDG_RUNTIME_DIR". This feeds the host-side per-instance paths `/run/user/[0-9]*/snap.<instance>/...-shared-*` (`wayland.go:102`) and the shared-memory path `/{dev,run}/shm/snap.<instance>.wayland.mozilla.ipc.[0-9]*` (`wayland.go:106`). Because `/run/user/.../snap.<instance>/` and these `/dev/shm` objects are HOST artifacts, using `InstanceName()` is correct. A second `###PLUG_SECURITY_TAGS###` substitution at `wayland.go:158-159` uses `plug.LabelExpression()` for the peer label (also instance-aware).
- On the plug side, `AppArmorConnectedPlug()` substitutes `###SLOT_SECURITY_TAGS###` with `slot.LabelExpression()` (`wayland.go:144-145`). No `@{SNAP_NAME}`/base-name path is used for any host artifact.

**Reasoning:** Wayland is inherently multi-client. Multiple snap instances connecting as
clients to the same compositor is functionally identical to having multiple different
snaps as clients. The connected-slot rules key the per-instance XDG_RUNTIME_DIR subdir and `/dev/shm` IPC objects by `plug.Snap().InstanceName()` (`wayland.go:154`), so parallel client instances are correctly isolated — the plug side is COMPATIBLE with no `SNAP_NAME`-vs-`INSTANCE_NAME` bug.

The slot side is parallel-safe at the snapd policy layer, but the compositor's own socket `/run/user/[0-9]*/wayland-[0-9]*` (`wayland.go:56`) is created by **display number** per user session, not by snap instance. Two parallel compositor providers must therefore use different `WAYLAND_DISPLAY` numbers (`wayland-0`, `wayland-1`) to coexist — a shared per-session namespace resource that must be coordinated, not a snapd identifier collision. So the slot side is COMPATIBLE EXCEPT FOR SHARED RESOURCE.

**Previous audit errors**:
- Claimed "NOT COMPATIBLE" due to "Shared memory" and "Global socket paths" -- INCORRECT
  for plug-side usage (the SHM objects are instance-keyed via the security tag).

**Verification:**
PASSED on ubuntu-22.04-64 (noble is disabled for this test).




### network-control
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Network/Netlink Interface


**Code analysis:**
- The connected-plug AppArmor D-Bus rules (`network_control.go:81-165`) are client-only: `dbus send` to `org.freedesktop.resolve1` (e.g. lines 81-129, 140-145), `dbus (receive)` of `PropertiesChanged` (lines 132-137, 148-153), and `dbus (receive, send)` to wpa_supplicant (lines 156-165). The interface acts purely as a **D-Bus client**; there is NO `dbus (bind)` and NO `DBusPermanentSlot`, so it does not own/bind any D-Bus name.
- The interface grants broad network capabilities (`net_admin`, `net_raw`, `net_broadcast`, `setuid` at lines 169-172; `sys_admin` at line 324; raw/netlink rules; `/dev/net/tun`, `/dev/rfkill`, `/run/netns/*`), and a dynamic `network xdp,` snippet added in `AppArmorConnectedPlug()` when the parser supports it (`network_control.go:40-58`). These are all global system resources that multiple consumers can use simultaneously.
- udev tagging is present: `KERNEL=="rfkill"` and `KERNEL=="tun"` (`network_control.go:397-400`); udev tags are instance-aware via the security tag and do not collide across instances.
- Seccomp permits many `AF_NETLINK` families plus `bind`, `mount`, `unshare`, `setns - CLONE_NEWNET`, `bpf` (`network_control.go:357-389`).
- No `SnapName()` or `SNAP_INSTANCE_NAME` is used in the AppArmor rules -- they are purely capability/host-resource based. Host-path mount/update-ns rules use `/var/lib/snapd/hostfs/var/lib/dhcp` and `/var/lib/dhcp` (lines 402-449), not snap-name paths.

**Reasoning:** network-control grants system-level network manipulation capabilities.
Multiple instances with network-control all get the same privileges, just like multiple
different snaps with network-control. They can all modify routing tables, ARP entries,
etc. without conflicting at the interface/AppArmor level (though they could conflict at
the operational level if they set contradictory routes).

**Previous audit errors**:
- Claimed "Global D-Bus names: Lines 88-153 bind to org.freedesktop.resolve1" --
  INCORRECT. The interface only SENDS to / RECEIVES from resolved (and wpa_supplicant); it never binds/owns a name.
- Claimed test "failed on noble, as expected" -- INCORRECT. Test passed.

**Verification:**
PASSED on noble.



### network-bind
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (core-only slot; no parallel app slot providers possible).

**Type:** Network/Netlink Interface


**Code analysis:**
- Grants the capability to bind to network ports and accept connections. The connected-plug AppArmor (`network_bind.go:42-75`) is client-only: a single `dbus send` to `org.freedesktop.resolve1` (lines 50-55) plus read-only `/etc/hosts.{deny,allow}` and `@{PROC}/sys/net/...` and `@{PROC}/@{pid}/net/...`. No `dbus (bind)`, no `DBusPermanentSlot`.
- Seccomp (`network_bind.go:78-95`) grants `accept`, `accept4`, `bind`, `listen`, and `socket AF_NETLINK - NETLINK_ROUTE`.
- No D-Bus name ownership, no shared memory, no udev tagging, and no use of `SnapName()`/`InstanceName()`/`ExpandSnapVariables()`/`LabelExpression()`. The interface grants only the capability to bind ports; specific ports are an app-YAML concern, not encoded here.
- Multiple instances can each bind to different ports without conflict.
- Slot is restricted to core only (`network_bind.go:24-29`: `slot-snap-type: [core]`).

**Reasoning:** This is a network capability interface. Parallel plug instances can each bind different ports without conflicts. The slot side is core-only, so parallel app-provided slots are not possible.

**App-level caveat:** Applications that declare fixed `listen-stream` ports in snap.yaml or hardcode specific TCP/UDP ports in their code will encounter port conflicts if parallel instances try to bind the same port. Apps should use dynamic port allocation or configuration-based ports if parallel instances are intended.

**Verification:**
PASSED on noble.



### network-status
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Network/Netlink Interface


**Code analysis:**
- The connected-plug AppArmor (`network_status.go:37-41`) is a single `dbus (send, receive)` rule on the session bus to `org.freedesktop.portal.NetworkMonitor` at `/org/freedesktop/portal/desktop`, `peer=(label=unconfined)`. This is the xdg-desktop-portal client pattern (send method calls + receive replies), NOT D-Bus name ownership: there is no `dbus (bind)` and no `DBusPermanentSlot`.
- No writes, no shared writable state, no seccomp snippet, no udev tagging, and no use of `SnapName()`/`InstanceName()`/`ExpandSnapVariables()`/`LabelExpression()`.
- Slot is restricted to core only (`network_status.go:24-29`: `slot-snap-type: [core]`).

**Reasoning:** This is an observer/client interface to the desktop-portal NetworkMonitor. Multiple parallel instances are just additional portal clients; the interface owns no bus name and holds no instance-specific state, so there is no snapd-level collision.

**Verification:**
PASSED on noble.



### network-setup-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Network/Netlink Interface


**Code analysis:**
- Read-only file access to netplan configuration: `/etc/netplan/{,**} r`, `/etc/network/{,**} r`, `/etc/systemd/network/{,**} r` (`network_setup_observe.go:56-58`) plus read-only `/run/systemd/network/...`, `/run/NetworkManager/conf.d/...`, `/run/udev/rules.d/...` (lines 60-63).
- A single client-only `dbus (send)` to `io.netplan.Netplan` member `Info`, `peer=(label=unconfined)` (`network_setup_observe.go:69-74`). No `dbus (bind)`, no `DBusPermanentSlot`. (A busctl abstract-socket `unix (bind)` at line 54 is address-pattern based, not a snap-name resource.)
- No write operations, no shared writable resources, no udev tagging, and no use of `SnapName()`/`InstanceName()`/`ExpandSnapVariables()`/`LabelExpression()`.
- Slot is restricted to core only (`network_setup_observe.go:24-30`: `slot-snap-type: [core]` plus `deny-auto-connection: true`).

**Verification:**
PASSED on noble.



### network-manager
**Status:** Plug-side: COMPATIBLE. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
The plug side is a system-bus D-Bus **client** and is parallel-safe; the slot side is a system singleton service with multiple fatal conflicts for parallel installs.

**Plug side (COMPATIBLE):**
- The connected-plug AppArmor (`network_manager.go:311-340`) is `dbus (receive, send)` to `/org/freedesktop/NetworkManager{,/**}` and `org.freedesktop.DBus.ObjectManager`, with `peer=(label=###SLOT_SECURITY_TAGS###)`. There is no `dbus (bind)` on the plug side — it owns no name.
- `AppArmorConnectedPlug()` substitutes `###SLOT_SECURITY_TAGS###` with `slot.LabelExpression()` on Core / `unconfined` on classic (`network_manager.go:543-560`), so the peer label is instance-aware. This is the same pure-client pattern as `avahi-observe`/`network-manager-observe`, so parallel plug instances have no snapd-level collision.

**Slot side (NOT COMPATIBLE):**

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
**Status:** Plug-side: COMPATIBLE. Slot-side: NOT COMPATIBLE for app-provided slots (owns the singleton `org.freedesktop.Avahi` name); N/A for the implicit system slot.

**Type:** D-Bus/IPC Client


**Code analysis:**
- The slot is app-providable (`avahi_observe.go:33-42`: `allow-installation: slot-snap-type: [app, core]`, `deny-auto-connection`, `deny-connection: on-classic: false`); `ImplicitOnClassic: true` (line 424).
- The `dbus (bind) bus=system name="org.freedesktop.Avahi"` rule exists ONLY in
  `avahiObservePermanentSlotAppArmor` (`avahi_observe.go:77-79`), and `<allow own="org.freedesktop.Avahi"/>` only in `avahiObservePermanentSlotDBus` (`avahi_observe.go:213`) — both applied to the **slot-providing snap** (a snap running the Avahi daemon).
- `AppArmorPermanentSlot()` at `avahi_observe.go:447` and `DBusPermanentSlot()` at `avahi_observe.go:468` explicitly check
  `implicitSystemPermanentSlot(slot)` (guards at lines 450, 471) -- when the slot is the system (core/snapd), the
  bind/own rules are NOT applied (the system's own avahi-daemon handles this outside of snap
  confinement).
- The connected PLUG rules (`avahiObserveConnectedPlugAppArmor`, `avahi_observe.go:234-413`) only use `dbus (send)`
  and `dbus (receive)` to communicate with `org.freedesktop.Avahi`, plus socket access to `/{,var/}run/avahi-daemon/socket` (line 238). This is read-only
  consumption of the Avahi service. `AppArmorConnectedPlug()` uses `slot.LabelExpression()` (line 440) and the connected-slot path uses `plug.LabelExpression()` (line 461), both instance-aware.
- No `InstanceName()`/`SnapName()`/`ExpandSnapVariables()`, no hardcoded `/var/snap/<name>/` paths, no seccomp/udev.

**Reasoning:** avahi-observe is a consumer interface on the plug side. The relevant question for parallel installs is "can two
instances of my snap both query Avahi?" -- and the answer is yes (the plug rules are send/receive only, with instance-aware peer labels, and own no name), so the plug side is COMPATIBLE. The slot side is a different matter: when an app snap provides the slot it binds/owns the singleton `org.freedesktop.Avahi` name (`avahi_observe.go:77-79`, `:213`), which two parallel provider instances cannot share — so the slot side is NOT COMPATIBLE for app providers (and N/A for the implicit system slot).

**Previous audit errors**:
- Claimed "NOT COMPATIBLE" due to "Global D-Bus name: binds to org.freedesktop.Avahi" --
  MISLEADING. The bind rule is only for the slot provider, not the plug consumer.

**Verification:**
PASSED on noble.



### contacts-service
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** D-Bus/IPC Client


**Code analysis:**
- The connected-plug AppArmor (`contacts_service.go:36-150`) is a **session-bus** D-Bus client: `#include <abstractions/dbus-session-strict>` (line 39) and `dbus (receive, send)` to Evolution Data Server AddressBook objects, all `bus=session`, `peer=(label=unconfined)` (lines 42-146). The session bus supports many simultaneous clients.
- **It owns no D-Bus name.** No `dbus (bind)`, no `DBusPermanentSlot`, no `<allow own>`; this is a `commonInterface` with only `connectedPlugAppArmor` set (`contacts_service.go:152-159`), so there is no slot-side code at all.
- The only filesystem rule is a read-only avatar cache: `owner @{HOME}/.cache/evolution/addressbook/[0-9a-f]*/*.jpeg r,` (line 149) — read-only and EDS-managed, not a per-instance writable DB.
- No `InstanceName()`/`SnapName()`/`ExpandSnapVariables()`/`LabelExpression()`, no hardcoded `/var/snap/<name>/` paths, no seccomp/udev.
- Slot is restricted to core only (`contacts_service.go:28-34`: `slot-snap-type: [core]`).

**Reasoning:** This is a session-bus client to Evolution Data Server; the plug owns no bus name and the only file rule is a read-only avatar cache, so parallel instances are independent clients with no snapd-level collision. The slot side is core-only, so parallel app-provided slots are not possible.

**Verification:**
PASSED on noble.



### accounts-service
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** D-Bus/IPC Client


**Code analysis:**
- The connected-plug AppArmor (`accounts_service.go:32-70`) is a **session-bus** D-Bus client: `#include <abstractions/dbus-session-strict>` (line 35) and `dbus (receive, send)` to `/org/gnome/OnlineAccounts` via ObjectManager/Properties/`org.gnome.OnlineAccounts.*`, all `bus=session`, `peer=(label=unconfined)` (lines 38-69).
- **It owns no D-Bus name.** No `dbus (bind)`, no `DBusPermanentSlot`, no `<allow own>`; this is a `commonInterface` with only `connectedPlugAppArmor` set (`accounts_service.go:72-79`), so there is no slot-side code.
- There is **no** direct file-path AppArmor rule in this interface. The `~/.config/goa-1.0/accounts.conf` account state is GNOME Online Accounts daemon state, accessed over D-Bus through the GOA service — it is not granted as a path by this interface, so parallel instances do not independently write a shared file via this interface.
- No `InstanceName()`/`SnapName()`/`ExpandSnapVariables()`/`LabelExpression()`, no hardcoded `/var/snap/<name>/` paths, no seccomp/udev.
- Slot is restricted to core only (`accounts_service.go:24-30`: `slot-snap-type: [core]`).

**Reasoning:** GNOME Online Accounts is a per-user session service. Multiple snap
instances are just additional session-bus D-Bus clients that read/modify the shared account list through the GOA daemon — the normal multi-client pattern. The plug owns no bus name and writes no per-instance file directly, so there is no snapd-level collision. The slot side is core-only, so parallel app-provided slots are not possible.

**Verification:**
PASSED on noble.



### location-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: NOT COMPATIBLE (app-only slot that owns singleton D-Bus names).

**Type:** D-Bus/IPC Client


**Code analysis:**
- The slot is app-only (`location_observe.go:35-37`: `allow-installation: slot-snap-type: [app]`, `deny-connection`, `deny-auto-connection`).
- Plug side is a **system-bus** D-Bus client: `dbus (send)` for Get/CreateSessionForCriteria/Start/Stop updates and `dbus (receive)` for Update*/PropertiesChanged (`location_observe.go:143-235`), with `peer=(label=###SLOT_SECURITY_TAGS###)`.
- **The plug owns no D-Bus name** — the connected-plug D-Bus policy explicitly `<deny own="com.ubuntu.location.Service"/>` (line 251). `AppArmorConnectedPlug()` substitutes the peer with `slot.LabelExpression()` (line 284), which is instance-aware. No `InstanceName()`/`SnapName()`/`ExpandSnapVariables()` and no hardcoded `/var/snap/<name>/` paths on the plug side.
- Slot side binds singleton names: `dbus (bind) bus=system name="com.ubuntu.location.Service"` (`location_observe.go:63-65`) and, on the connected slot, additionally `com.ubuntu.location.Service.Session` (`location_observe.go:78-80`); `DBusPermanentSlot` grants `<allow own>` for both (lines 240-241).

**Reasoning:** Same architecture as `location-control` on the plug side: a consumer observing location data from the single service is a pure system-bus client that owns no name and uses instance-aware peer labels, so parallel plug instances do not conflict — plug side is COMPATIBLE. The slot side is NOT COMPATIBLE because it is app-providable and owns the singleton `com.ubuntu.location.Service` (and `...Session`) names, which two parallel providers cannot share.

**Verification:** Not separately tested, but same reasoning as avahi-observe applies.



### online-accounts-service
**Status:** Plug-side: COMPATIBLE. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
- The slot is app-only (`online_accounts_service.go:35-37`: `allow-installation: slot-snap-type: [app]`, `deny-connection`).
- Plug side is a **session-bus** D-Bus client: `dbus (receive, send)` to `com.ubuntu.OnlineAccounts.Manager` at `/com/ubuntu/OnlineAccounts{,/**}` plus `dbus (send)` Introspect (`online_accounts_service.go:77-89`), with `peer=(label=###SLOT_SECURITY_TAGS###)`. `AppArmorConnectedPlug()` substitutes the peer with `slot.LabelExpression()` (line 115), which is instance-aware. **The plug owns no D-Bus name** (no `dbus (bind)` on the plug side); no `InstanceName()`/`SnapName()` and no hardcoded `/var/snap/<name>/` paths.
- Slot side binds the singleton `dbus (bind) bus=session name="com.ubuntu.OnlineAccounts.Manager"` (`online_accounts_service.go:55-57`). There is no `DBusPermanentSlot` (session-bus slots get no D-Bus policy file), consistent with the `dbus` interface only emitting D-Bus policy for the system bus.

**Reasoning:** Plug-side parallel consumers work as multiple session-bus clients of the online accounts service: the plug owns no bus name and uses instance-aware peer labels, so there is no snapd-level collision. Slot-side parallel providers cannot both own the well-known session-bus name `com.ubuntu.OnlineAccounts.Manager`, so the slot side is NOT COMPATIBLE.

**Verification:** No verification has yet been done.



### autopilot-introspection
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (core-only slot; no parallel app slot providers possible).

**Type:** D-Bus/IPC Client


**Code analysis:**
- Slot is provided by core only (`autopilot.go:26-28`: `slot-snap-type: [core]`), with implicit slots on core and classic (`autopilot.go:69-70`).
- AppArmor rules (the static `connectedPlugAppArmor`) are session-bus only and **receive**-oriented:
  - `dbus (receive)` Introspection of `/com/canonical/Autopilot/**` (`autopilot.go:38-43`)
  - `dbus (receive)` `GetVersion` and `GetState` on `/com/canonical/Autopilot/Introspection` (`autopilot.go:44-55`)
  - The peer is the static literal `peer=(label=unconfined)` (lines 43, 49, 55), not a `LabelExpression()` substitution.
- Seccomp allows only message-passing syscalls (`recvmsg`, `sendmsg`, `sendto`) (`autopilot.go:57-63`).
- **No name ownership or bind rules** — there is no `dbus (bind)` anywhere on the plug side (the app is introspected by an unconfined peer; a `dbus (receive)` rule does not constitute name ownership). This is a `commonInterface` with only static `connectedPlugAppArmor`/`connectedPlugSecComp` and no per-connection substitution; no `InstanceName()`/`SnapName()`/`LabelExpression()`, no `/var/snap/<name>/` paths.

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
**Status:** Plug-side: COMPATIBLE. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
- The slot is app-providable (`media_hub.go:33-41`: `allow-installation: slot-snap-type: [app, core]`, `deny-connection: on-classic: false`).
- The connected-plug AppArmor (`media_hub.go:126-152`) is a **session-bus** client to `/core/ubuntu/media/Service{,/**}`: `dbus (receive, send)` for Properties, send-only Introspect, and `dbus (send)` to `core.ubuntu.media.Service{,.*}` for managing Player sessions. All use `peer=(label=###SLOT_SECURITY_TAGS###)`.
- **The plug owns no D-Bus name.** The `dbus (bind) bus=session name="core.ubuntu.media.Service"` (`media_hub.go:65-67`) lives only in `mediaHubPermanentSlotAppArmor`, applied to the slot provider via `AppArmorPermanentSlot()` (line 180).
- `AppArmorConnectedPlug()` substitutes `###SLOT_SECURITY_TAGS###` with `slot.LabelExpression()` (`media_hub.go:173-177`), which is instance-aware. No `InstanceName()`/`SnapName()` and no hardcoded `/var/snap/<name>/` paths on the plug side. The permanent slot binds the well-known session-bus name `core.ubuntu.media.Service` (lines 64-68).

**Reasoning:** Media Hub is a D-Bus service provider interface. On the plug side it is a pure session-bus client that owns no name and uses instance-aware peer labels, so parallel consumers each talk to the media service independently with no snapd-level collision — plug side is COMPATIBLE. Parallel providers cannot both own the well-known session-bus name `core.ubuntu.media.Service`, so the slot side is a singleton conflict (NOT COMPATIBLE).

**Verification:** No verification has yet been done.

### mir
**Status:** Plug-side: COMPATIBLE. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
- The permanent slot owns the Mir server runtime resources, including `/run/mir_socket`, `/run/user/[0-9]*/mir_socket`, `/dev/tty[0-9]*`, and `/dev/input/*` (lines 42-71).
- The slot AppArmor also includes `/dev/shm/\#[0-9]*` shared-memory objects and `sys_admin` / `sys_tty_config` capabilities (lines 42-71).
- The Seccomp profile permits server-side socket/listen/accept and netlink uevent handling (lines 73-85).
- The connected plug only gets client access to Mir sockets and shared-memory objects (lines 87-100).

**Reasoning:** Mir is a display-server service interface. Parallel clients are fine, but parallel service providers would compete for the same Mir server runtime paths and privileged system resources, making the slot side a singleton.

**Verification:** No verification has yet been done.

### storage-framework-service
**Status:** Plug-side: COMPATIBLE. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
- The slot is app-only (`storage_framework_service.go:33-40`: `allow-installation: slot-snap-type: [app]`, `deny-connection`, `deny-auto-connection`).
- The connected-plug AppArmor (`storage_framework_service.go:93-109`) is a **session-bus** client: `dbus (receive, send)` to `com.canonical.StorageFramework.Registry` at `/com/canonical/StorageFramework/Registry` and to `com.canonical.StorageFramework.Provider.*` at `/provider/*`, both with `peer=(label=###SLOT_SECURITY_TAGS###)`.
- **The plug owns no D-Bus name.** The `dbus (bind)` for `com.canonical.StorageFramework.Registry` and `com.canonical.StorageFramework.Provider.*` (`storage_framework_service.go:66-72`), and the privileged AppArmor-introspection paths (`/sys/kernel/security/apparmor/.access` etc., lines 51-53), live only in `storageFrameworkServicePermanentSlotAppArmor`, applied to the slot provider via `AppArmorPermanentSlot()` (line 137).
- `AppArmorConnectedPlug()` substitutes `###SLOT_SECURITY_TAGS###` with `slot.LabelExpression()` (`storage_framework_service.go:128-134`), which is instance-aware. No `InstanceName()`/`SnapName()` and no hardcoded `/var/snap/<name>/` paths on the plug side. The service names are the actual singleton resources; the path patterns are not instance-scoped.

**Reasoning:** This is a D-Bus service provider interface. On the plug side it is a pure session-bus client that owns no name and uses instance-aware peer labels, so parallel consumers are independent clients with no snapd-level collision — plug side is COMPATIBLE. Parallel providers cannot both own the registry/provider bus names, so the slot side is NOT COMPATIBLE.

**Verification:** No verification has yet been done.

### unity8
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (the interface contributes no slot-side policy and binds no well-known name of its own; a provider's actual name ownership would come from other interfaces).

**Type:** D-Bus Service/Provider


**Code analysis:**
- The connected plug talks to Unity 8 session services over the **session bus**: `dbus (send)` to `com.canonical.URLDispatcher` `DispatchURL` at `/com/canonical/URLDispatcher` (`unity8.go:67-72`) and `dbus (send)`/`dbus (receive)` to `com.ubuntu.content.dbus.Service` at `/` (`unity8.go:77-88`), each with `peer=(name=<service>, label=###SLOT_SECURITY_TAGS###)`. It also reads host-global font/schema dirs (`/var/cache/fontconfig/`, `/usr/share/.../schemas/`, lines 51-59).
- **The plug owns no D-Bus name** — there is no `dbus (bind)` anywhere in this file; naming a `peer=(name=...)` destination is client addressing, not ownership. `AppArmorConnectedPlug()` substitutes `###SLOT_SECURITY_TAGS###` with `slot.LabelExpression()` (`unity8.go:111`), which is instance-aware.
- This interface defines ONLY `AppArmorConnectedPlug` — there is no `AppArmorPermanentSlot`/`DBusPermanentSlot`/`AppArmorConnectedSlot`, so it emits no slot-side policy and owns no well-known name itself (a provider's actual name ownership would come from other interfaces). The plug base declaration is `allow-installation: false` (`unity8.go:32-35`), so plug install needs a snap-declaration.
- No `InstanceName()`/`SnapName()`/`ExpandSnapVariables()`, no hardcoded `/var/snap/<name>/` or `/snap/<name>/` paths (only host-global font/schema reads), no shared memory or sockets.

**Reasoning:** Unity 8 is a desktop service interface built around well-known D-Bus services. On the plug side it is a pure session-bus client that owns no name and uses instance-aware peer labels, so parallel plug instances each talk to the Unity8 services independently with no snapd-level collision. The slot side is N/A: this interface defines only `AppArmorConnectedPlug` (no `AppArmorPermanentSlot`/`DBusPermanentSlot`/`AppArmorConnectedSlot`), so it emits no slot-side policy and binds no well-known name of its own — there is no app-provided slot behavior in this interface to be compatible or not (a provider's actual name ownership would come from other interfaces).

**Verification:** No verification has yet been done.

### unity8-calendar
**Status:** Plug-side: COMPATIBLE. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
- The slot is app-only (`unity8_calendar.go:24-31`: `allow-installation: slot-snap-type: [app]`, `deny-auto-connection`, `deny-connection`); the interface is built on the shared `unity8PimCommonInterface`.
- The connected-plug AppArmor (`unity8_calendar.go:111-146` plus the common `unity8_pim_common.go:75-94`) is a **session-bus** client to the Evolution Data Server calendar objects (`/org/gnome/evolution/dataserver/Calendar*`, `/com/canonical/SyncMonitor`, `SourceManager`), all with `peer=(label=###SLOT_SECURITY_TAGS###)`.
- **The plug owns no D-Bus name.** All `dbus (bind)` rules (`org.gnome.evolution.dataserver.Calendar7`, `...Subprocess.Backend.Calendar*`, `com.canonical.SyncMonitor` at `unity8_calendar.go:38-46`, and `...Sources5` at `unity8_pim_common.go:58-60`) live in the permanent-slot snippets, applied to the slot provider via `AppArmorPermanentSlot()` (`unity8_pim_common.go:147`).
- `AppArmorConnectedPlug()` substitutes `###SLOT_SECURITY_TAGS###` with `slot.LabelExpression()` (`unity8_pim_common.go:131-136`), which is instance-aware, and additionally allows `unconfined` on classic (line 141) since the real EDS runs unconfined on the host. No `InstanceName()`/`SnapName()` and no hardcoded `/var/snap/<name>/` paths on the plug side. The service paths are fixed names/object paths, not snap-instance-scoped.

**Reasoning:** This is a calendar service provider interface. On the plug side it is a pure session-bus client (owns no name, instance-aware peer labels, `unconfined` fallback for the host EDS on classic), so parallel consumers are independent clients with no snapd-level collision — plug side is COMPATIBLE. Parallel providers would contend for the same well-known calendar and sync-monitor bus names, so the slot side is NOT COMPATIBLE.

**Verification:** No verification has yet been done.

### unity8-contacts
**Status:** Plug-side: COMPATIBLE. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
- The slot is app-only (`unity8_contacts.go:24-31`: `allow-installation: slot-snap-type: [app]`, `deny-auto-connection`, `deny-connection`); the interface is built on the shared `unity8PimCommonInterface`.
- The connected-plug AppArmor (`unity8_contacts.go:140-183` plus the common `unity8_pim_common.go:75-94`) is a **session-bus** client to the Evolution Data Server address-book objects (`/org/gnome/evolution/dataserver/AddressBook*`, `/com/canonical/pim/AddressBook*`, `/synchronizer{,/**}`, `SourceManager`), all with `peer=(label=###SLOT_SECURITY_TAGS###)`.
- **The plug owns no D-Bus name.** All `dbus (bind)` rules (`org.gnome.evolution.dataserver.AddressBook9`, `...Subprocess.Backend.AddressBook*`, `com.canonical.pim`, `com.meego.msyncd` at `unity8_contacts.go:38-53`, and `...Sources5` at `unity8_pim_common.go:58-60`) live in the permanent-slot snippets, applied to the slot provider via `AppArmorPermanentSlot()` (`unity8_pim_common.go:147`).
- `AppArmorConnectedPlug()` substitutes `###SLOT_SECURITY_TAGS###` with `slot.LabelExpression()` (`unity8_pim_common.go:131-136`), which is instance-aware, and additionally allows `unconfined` on classic (line 141) since the real EDS runs unconfined on the host. No `InstanceName()`/`SnapName()` and no hardcoded `/var/snap/<name>/` paths on the plug side.

**Reasoning:** Unity 8 Contacts is another D-Bus service provider interface. On the plug side it is a pure session-bus client (owns no name, instance-aware peer labels, `unconfined` fallback for the host EDS on classic), so parallel consumers are independent clients with no snapd-level collision — plug side is COMPATIBLE. Parallel providers would collide on the same well-known bus names, so the slot side is NOT COMPATIBLE.

**Verification:** No verification has yet been done.

### screencast-legacy
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** D-Bus/IPC Client


**Code analysis:**
- The plug talks to gnome-shell screenshot/screencast interfaces on the session bus (lines 32-53).
- The API allows absolute file names as method arguments, so the caller can direct output to arbitrary paths permitted by the user.
- The interface does not own a bus name itself, but the permissions are explicitly tied to the desktop session service.
- No snap-instance-specific pathing is used by snapd.

**Reasoning:** The interface is privileged and can affect shared user-visible outputs (screen/audio capture and file destinations), but it is still a client-side D-Bus interface with no instance-name collision in policy.

**Verification:** No verification has yet been done.

### ros-opt-data
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Filesystem/Mount Interface


**Code analysis:**
- The plug gets read-only access to `/var/lib/snapd/hostfs/opt/ros/**` and common ROS file extensions under that tree (lines 31-49).
- The interface is implicit on classic and not on core, which matches a host filesystem read-only pattern.
- No sockets, mounts, or D-Bus names are involved.
- No snap-instance-specific names are used.

**Reasoning:** ROS static data is read-only host content. Parallel instances can all read the same files without snapd-level collisions.

**Verification:** No verification has yet been done.

### system-backup
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Observability/Diagnostics


**Code analysis:**
- The plug gets read-only access across the host filesystem through `/var/lib/snapd/hostfs/` exclusions and `dac_read_search` (lines 32-47).
- The policy explicitly excludes `/dev`, `/sys`, and `/proc` from the broad read rule and then re-adds narrow cases as needed.
- No D-Bus, sockets, or instance-specific mount paths are present.

**Reasoning:** This is a broad read-only backup interface. Parallel instances are just concurrent readers of the same host data, and the policy does not encode snap-instance-specific paths.

**Verification:** No verification has yet been done.

### system-source-code
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Observability/Diagnostics


**Code analysis:**
- The plug gets read-only access to `/usr/src/{,**}` (line 38).
- The interface is implicit on core and classic and otherwise just exposes source trees/headers.
- No sockets, mounts, or snap-instance-specific names are involved.

**Reasoning:** `/usr/src` is a shared system source tree. Multiple instances can read it concurrently without any instance-name collision.

**Verification:** No verification has yet been done.

### juju-client-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Observability/Diagnostics


**Code analysis:**
- The plug gets read access to `~/.local/share/juju/{,**}` using `owner` file rules (lines 32-35).
- The interface is classic-only and reads the user’s Juju client state; it does not own a bus name.
- No sockets, mounts, or snap-instance-specific names are used.

**Reasoning:** Juju client state is per-user data. Parallel instances under the same user will read the same Juju config/state, which is normal shared-user behavior and not an instance collision.

**Verification:** No verification has yet been done.

### netlink-driver
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A for parallel app instances (slot is declarable only by core or gadget snaps, which cannot be parallel-installed; identity is protocol-family based, not snap-name based).

**Type:** Network/Netlink Interface


**Code analysis:**
- The slot is declarable by core or gadget snaps only (`netlink_driver.go:33-40`: `slot-snap-type: [core, gadget]`, `deny-auto-connection: true`). It is registered as a plain interface WITHOUT `implicitOnCore`/`implicitOnClassic` (`netlink_driver.go:143-151`), so the slot is explicitly declared (by core/gadget), not implicit.
- The slot is keyed by a numeric `family` (protocol number) attribute and a validated `family-name` (`BeforePrepareSlot()`, `netlink_driver.go:67-81`; `validateFamilyNameAttr()` with regexp `^[a-z]+[a-z0-9-]*[^\-]$` at lines 64, 83-102). The plug must present a matching `family-name` (`BeforePreparePlug()`, lines 104-107).
- The connected-plug AppArmor is a static capability grant: `network netlink,` and `capability net_admin,` (`netlink_driver.go:47-56`). The connected-plug seccomp filter is scoped to the slot's numeric `family`: `socket AF_NETLINK - <family>` plus `bind` (`netlink_driver.go:109-125`).
- `AutoConnect()` (`netlink_driver.go:127-141`) matches purely on `family-name` equality between plug and slot — it does not use snap identity.
- No use of `SnapName()`, `InstanceName()`, `ExpandSnapVariables()`, or `LabelExpression()`; no hardcoded `/var/snap/<name>/` paths; no D-Bus; no udev tagging. The only shared kernel object is the netlink protocol family number itself, which is global per kernel.

**Reasoning:** Identity in this interface is the kernel netlink protocol family (the `family` number / `family-name`), not the snap name, so parallel plug instances connecting to the same family slot do not collide at the snapd level — the plug side is COMPATIBLE. The slot side cannot be provided by parallel app instances because only core or gadget snaps may declare it, and those are singletons per device (a gadget/core snap cannot be parallel-installed). The relevant contention surface — two providers declaring the same `family` number for the same global kernel protocol — is therefore not a snapd parallel-instance scenario.

**Verification:** No verification has yet been done.

### core-support
**Status:** Plug-side: N/A (core-only plug; parallel app plugs out of scope). Slot-side: N/A (core-only slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- This interface is explicitly hollow and grants no permissions (lines 39-41).
- It only exists so callers can test for its presence; `commonInterface` is registered with no AppArmor/seccomp/udev policy.
- No paths, sockets, mounts, or snap-instance-specific logic are present.

**Reasoning:** The interface has no confinement effect at all. Parallel instances cannot collide because there is no policy to collide over.

**Verification:** No verification has yet been done.

### accel
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (core-only slot; no parallel app slot providers possible).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants access to `/dev/accel/accel*` (lines 4560-4566 in the bucket summary).
- The access is device-node based and tied to global accelerator hardware.
- No instance-specific pathing or name expansion exists in the interface model.
- Slot is restricted to core only (implicitOnCore/implicitOnClassic).

**Reasoning:** The interface is device-path-based with no snap-instance-specific naming. Parallel plug instances can access the accelerator devices without snapd-level conflicts. However, they share the same physical accelerator hardware, which is the shared resource concern.

**Verification:** No verification has yet been done.

### acrn-support
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (core-only slot; no parallel app slot providers possible).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants access to `/dev/acrn_hsm` (lines 4572-4579 in the bucket summary).
- ACRN management is a single hypervisor control device node.
- No snap-instance-specific logic is involved.
- Slot is restricted to core only (implicitOnCore/implicitOnClassic).

**Reasoning:** The interface is device-path-based with no snap-instance-specific naming. Parallel plug instances can access the ACRN hypervisor device without snapd-level conflicts. However, they share the same global hypervisor control device, which is the shared resource concern.

**Verification:** No verification has yet been done.

### allegro-vcu
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (core-only slot; no parallel app slot providers possible).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants access to `/dev/allegroDecodeIP`, `/dev/allegroIP`, and `/dev/dmaproxy` (lines 4583-4590 in the bucket summary).
- These are hardware codec device nodes, not per-instance resources.
- Slot is restricted to core only (implicitOnCore/implicitOnClassic).

**Reasoning:** The interface is device-path-based with no snap-instance-specific naming. Parallel plug instances can access the codec devices without snapd-level conflicts. However, they share the same hardware codec devices, which is the shared resource concern.

**Verification:** No verification has yet been done.

### broadcom-asic-control
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (core-only slot; no parallel app slot providers possible).

**Type:** System Control/Privileged Capability


**Code analysis:**
- The interface grants access to `/dev/linux-user-bde`, `/dev/linux-kernel-bde`, and `/dev/linux-bcm-knet` (lines 4594-4601 in the bucket summary).
- These are ASIC kernel module/device interfaces for a specific hardware platform.
- Slot is restricted to core only (implicitOnCore/implicitOnClassic).

**Reasoning:** The interface is device-path-based with no snap-instance-specific naming. Parallel plug instances can access the ASIC control devices without snapd-level conflicts. However, they share the same hardware ASIC resource, which is the shared resource concern.

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
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (core-only slot; no parallel app slot providers possible).

**Type:** System Control/Privileged Capability


**Code analysis:**
- The interface targets `/sys/devices/system/cpu/**` (lines 4628-4635 in the bucket summary).
- It controls governor, scaling, and hotplug settings for the whole system.
- No snap-instance-specific logic is involved.
- Slot is restricted to core only (implicitOnCore/implicitOnClassic).

**Reasoning:** The interface is sysfs-path-based with no snap-instance-specific naming. Parallel plug instances can access CPU control without snapd-level conflicts. However, they share the same global CPU policy settings, which is the shared resource concern.

**Verification:** No verification has yet been done.

### dcdbas-control
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (core-only slot; no parallel app slot providers possible).

**Type:** System Control/Privileged Capability


**Code analysis:**
- The interface targets `/sys/devices/platform/dcdbas/*` (lines 4639-4646 in the bucket summary).
- It exposes the Dell Systems Management Base Driver, which is a single system resource.
- Slot is restricted to core only (implicitOnCore/implicitOnClassic).

**Reasoning:** The interface is sysfs-path-based with no snap-instance-specific naming. Parallel plug instances can access the dcdbas interface without snapd-level conflicts. However, they share the same system-management resource, which is the shared resource concern.

**Verification:** No verification has yet been done.

### dsp
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (core-only slot; no parallel app slot providers possible).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants access to `/dev/ucode` and `/dev/iav*` (lines 4650-4657 in the bucket summary).
- These are hardware DSP device nodes.
- Slot is restricted to core only (implicitOnCore/implicitOnClassic).

**Reasoning:** The interface is device-path-based with no snap-instance-specific naming. Parallel plug instances can access the DSP devices without snapd-level conflicts. However, they share the same hardware DSP resource, which is the shared resource concern.

**Verification:** No verification has yet been done.

### fpga
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (core-only slot; no parallel app slot providers possible).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants access to `/dev/fpga[0-9]*` (lines 4661-4668 in the bucket summary).
- These are numbered FPGA device nodes with shared hardware state.
- Slot is restricted to core only (implicitOnCore/implicitOnClassic).

**Reasoning:** The interface is device-path-based with no snap-instance-specific naming. Parallel plug instances can access the FPGA devices without snapd-level conflicts. However, they share the same hardware FPGA resource, which is the shared resource concern.

**Verification:** No verification has yet been done.

### framebuffer
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (core-only slot; no parallel app slot providers possible).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants access to `/dev/fb[0-9]*` (lines 4672-4679 in the bucket summary).
- Framebuffer devices are global display hardware.
- Slot is restricted to core only (implicitOnCore/implicitOnClassic).

**Reasoning:** The interface is device-path-based with no snap-instance-specific naming. Parallel plug instances can access the framebuffer devices without snapd-level conflicts. However, they share the same display hardware, which is the shared resource concern.

**Verification:** No verification has yet been done.

### gpio
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Slots are provided by core or gadget snaps only (`gpio.go:38-41`: `slot-snap-type: [core, gadget]`), not by app snaps.
- The slot is keyed by a `number` attribute (validated as `int64` in `BeforePrepareSlot()`, `gpio.go:67-81`). `AppArmorConnectedPlug()` (`gpio.go:83-106`) builds the sysfs path `path := fmt.Sprint("/sys/class/gpio/gpio", number)` (line 88), resolves it via `evalSymlinks(path)` (line 93), and emits `spec.AddSnippet(fmt.Sprintf("%s/* rwk,", dereferencedPath))` (line 104). If the GPIO does not exist it logs and returns nil without failing (lines 94-100).
- The interface sets up a per-slot systemd service via `SystemdConnectedSlot()` (`gpio.go:108-122`) with suffix `gpio-%d` keyed on the GPIO number (line 114) to export/unexport the line (lines 118-119). The suffix is keyed on the GPIO number, not the snap/instance; the slot is core/gadget-provided so this is not an app-instance collision.
- No udev tagging in this file. No use of `SnapName()`, `InstanceName()`, `ExpandSnapVariables()`, or `LabelExpression()`; no hardcoded `/var/snap/<name>/` paths (the `/sys/class/gpio/gpioN` path is a hardware sysfs path); no D-Bus, shared memory, or sockets.

**Reasoning:** The plug AppArmor rule is derived from the slot's GPIO number (resolved through sysfs) with no per-instance naming, so there is no snapd-level collision between parallel instances. However, the slot grants control of one specific GPIO line (a single hardware pin), and the slot-side systemd service exports/unexports that one line; two parallel instances connecting the same slot contend over that single shared pin. So the plug side is policy-compatible but shares a single physical GPIO line.

**Verification:** No verification has yet been done.

### gpio-memory-control
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (core-only slot; no parallel app slot providers possible).

**Type:** System Control/Privileged Capability


**Code analysis:**
- Slot is provided by core only (`gpio_memory_control.go:27-29`: `slot-snap-type: [core]`), with implicit slots on core and classic (`gpio_memory_control.go:47-48`).
- This is a `commonInterface` registration with a single static AppArmor rule `/dev/gpiomem rw,` (`gpio_memory_control.go:38`, wired via `connectedPlugAppArmor` at line 50). No attributes, no snap name.
- Static udev rule `KERNEL=="gpiomem"` (`gpio_memory_control.go:41`, wired via `connectedPlugUDev` at line 51); the udev backend attaches the instance-aware security tag.
- No `BeforePreparePlug()`/`BeforePrepareSlot()` sanitizers. No use of `SnapName()`, `InstanceName()`, `ExpandSnapVariables()`, or `LabelExpression()`; no hardcoded `/var/snap/<name>/` paths; no D-Bus, no mounts, no sockets.

**Reasoning:** The single hardcoded rule `/dev/gpiomem rw,` contains no per-instance naming, so multiple keyed instances get identical, non-colliding rules and instance-aware udev tags — there is no snapd-level collision. But the interface grants access to one fixed global device (`/dev/gpiomem`, the GPIO physical memory), which is a single shared hardware resource all instances would contend over. So the plug side is policy-compatible but shares a single global device.

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
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (gadget/core-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Slots are provided by gadget or core snaps only (`iio.go:38-41`: `slot-snap-type: [gadget, core]`).
- Slot validation requires a device node path under `/dev/iio:deviceN` (`BeforePrepareSlot()`, `iio.go:78-96`; regexp `^/dev/iio:device[0-9]+$` at `iio.go:75`).
- `AppArmorConnectedPlug()` (`iio.go:98-133`) builds rules from the slot `path`: `cleanedPath := filepath.Clean(path)` (line 104) fills `###IIO_DEVICE_PATH###` (line 105), and `deviceName := strings.TrimPrefix(path, "/dev/")` (lines 111-112) fills `###IIO_DEVICE_NAME###`. Note this "device name" is the kernel device name `iio:deviceN` from the slot path, **not** a snap name. Parametric snippets for `/sys/devices/**/iio:device<num>/** rwk,` use `deviceNum := strings.TrimPrefix(deviceName, "iio:device")` (lines 121-130).
- `UDevConnectedPlug()` (`iio.go:135-142`) tags the device via `spec.TagDevice(KERNEL=="<dev>")` at line 140 (the exact `/dev/iio:deviceN` node).
- No use of `SnapName()`, `InstanceName()`, `ExpandSnapVariables()`, or `LabelExpression()`; no hardcoded `/var/snap/<name>/` paths (sysfs paths are hardware paths); no D-Bus, shared memory, or sockets.

**Reasoning:** The `###IIO_DEVICE_NAME###` token is the kernel device name (`iio:deviceN`) derived from the slot path, not a snap/instance name, and udev tags are instance-aware via `TagDevice`, so there is no snapd-level collision between parallel instances. The slot pins one specific IIO device node, so two parallel instances connecting the same slot share that single device. So the plug side is policy-compatible but shares a single physical device.

**Verification:** No verification has yet been done.

### intel-mei
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (core-only slot; no parallel app slot providers possible).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants access to `/dev/mei[0-9]*` (lines 4727-4734 in the bucket summary).
- Intel MEI is a system-management bus exposed as hardware device nodes.
- Slot is restricted to core only (implicitOnCore/implicitOnClassic).

**Reasoning:** The interface is device-path-based with no snap-instance-specific naming. Parallel plug instances can access the MEI devices without snapd-level conflicts. However, they share the same hardware management channel, which is the shared resource concern.

**Verification:** No verification has yet been done.

### intel-qat
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (core-only slot; no parallel app slot providers possible).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants access to `/dev/vfio/*` and IOMMU sysfs (lines 4738-4745 in the bucket summary).
- It targets Intel QuickAssist Technology accelerator hardware.

**Reasoning:** QAT is a shared PCIe accelerator. Parallel instances can’t be treated as isolated consumers in the interface code.

**Verification:** No verification has yet been done.

### io-ports-control
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** System Control/Privileged Capability


**Code analysis:**
- Slot is provided by core only (`io_ports_control.go:24-30`), with implicit slots on core and classic (`io_ports_control.go:57-58`).
- AppArmor grants access to `/dev/port` and `capability sys_rawio` (`io_ports_control.go:32-39`).
- Seccomp allows `ioperm` and `iopl` (`io_ports_control.go:41-49`).
- UDev tags the `port` device (`io_ports_control.go:51`).
- This is full I/O port access for the system.

**Reasoning:** The interface is device-path-based with no snap-instance-specific naming. Parallel plug instances can access I/O ports without snapd-level conflicts. However, they share the same global machine I/O port space, which is the shared resource concern.

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
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (core-only slot; no parallel app slot providers possible).

**Type:** System Control/Privileged Capability


**Code analysis:**
- The interface grants read/write access to `/dev/mem` (lines 4805-4813 in the bucket summary).
- This is full physical memory access.
- Slot is restricted to core only (implicitOnCore/implicitOnClassic).

**Reasoning:** The interface is device-path-based with no snap-instance-specific naming. Parallel plug instances can access physical memory without snapd-level conflicts. However, they share the same system memory resource, which is the shared resource concern.

**Verification:** No verification has yet been done.

### power-control
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (core-only slot; no parallel app slot providers possible).

**Type:** System Control/Privileged Capability


**Code analysis:**
- The interface targets `/sys/devices/**/power/*` and power-supply knobs (implementation section for `power-control`).
- It controls wakeup, runtime power management, and battery threshold settings for the whole system.
- Slot is restricted to core only (implicitOnCore/implicitOnClassic).

**Reasoning:** The interface is sysfs-path-based with no snap-instance-specific naming. Parallel plug instances can access power controls without snapd-level conflicts. However, they share the same global power policy settings, which is the shared resource concern.

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
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Identity/Credentials/Secrets


**Code analysis:**
- The interface grants access to `/dev/hidraw*` and related udev/sysfs metadata (`u2f_devices.go:227-243`).
- UDev matching is vendor/product based for known U2F/FIDO tokens (`u2f_devices.go:249-252`).
- It is a physical token interface with device matching rather than instance naming.

**Reasoning:** The interface is policy-safe, but the underlying token is a shared physical device. Parallel instances can contend for the same security key at the application level.

**Verification:** No verification has yet been done.

### uio
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Slots are provided by core or gadget snaps only (`uio.go:40-45`: `slot-snap-type: [core, gadget]`).
- Slot path validation requires `/dev/uioN` via `verifySlotPathAttribute()` with `uioPattern = ^/dev/uio[0-9]+$` (`uio.go:61`, used at `BeforePrepareSlot()` `uio.go:69-72`).
- `AppArmorConnectedPlug()` (`uio.go:74-120`) emits `<path> rw,` for the device node (line 79), a broad read rule `/sys/devices/platform/**/uio/uio[0-9]** r,` (line 105), and a per-device config rule resolved from `/sys/class/uio/<dev>/device/config` via `evalSymlinks` (lines 108-118). All path-driven.
- `UDevConnectedPlug()` (`uio.go:122-129`) tags the device via `spec.TagDevice(SUBSYSTEM=="uio", KERNEL=="<dev>")` at line 127.
- Note: `slot.Snap.InstanceName()` IS referenced at `uio.go:70`, but only to build the `SlotRef` used in slot-side validation error messages — it does not enter any AppArmor/udev rule and has no effect on parallel-install compatibility. No `SnapName()`/`ExpandSnapVariables()`/`LabelExpression()` is used; no hardcoded `/var/snap/<name>/` paths; no D-Bus, shared memory, or sockets.

**Reasoning:** Plug AppArmor/udev rules are derived purely from the slot's `/dev/uioN` path with no per-instance naming (the lone `InstanceName()` call at `uio.go:70` is for slot-side error text only), and udev tags are instance-aware via `TagDevice`, so there is no snapd-level collision between parallel instances. But the slot pins one specific UIO device node, so two parallel instances connecting the same slot share that single userspace-mapped device. So the plug side is policy-compatible but shares a single physical device.

**Verification:** No verification has yet been done.

### usb-gadget
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (core-only slot; no parallel app slot providers possible).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants broad access to USB gadget configfs (`usb_gadget.go:168-179`).
- FunctionFS mount targets are expanded from the plug snap identity via `expandMountWhereVariable()` (`usb_gadget.go:205`).
- The interface validates persistent mount targets and rejects persistent mounts under `$SNAP_DATA` and `$SNAP_USER_DATA` (`usb_gadget.go:74-81`).
- Configfs remains the system-wide USB peripheral configuration plane.
- Slot is restricted to core only (implicitOnCore/implicitOnClassic).

**Reasoning:** The interface is configfs-path-based with no snap-instance-specific naming in the configfs plane itself. Parallel plug instances can access USB gadget configuration without snapd-level conflicts. However, they share the same system-wide USB peripheral control plane, which is the shared resource concern.

**Verification:** No verification has yet been done.

### vcio
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (core-only slot; no parallel app slot providers possible).

**Type:** Hardware Device Access


**Code analysis:**
- Slot is provided by core only (`vcio.go:29-35`: `slot-snap-type: [core]`), implicit on core and classic (`vcio.go:59-60`).
- AppArmor grants access to a **single fixed device node** `/dev/vcio rw,` (`vcio.go:41`), plus read-only `/sys/devices/virtual/bcm2708_vcio/vcio/**` (line 42) and udev metadata (lines 46-48). The driver is privileged and "assumes trusted input" (comment lines 26-28).
- UDev tags `SUBSYSTEM=="bcm2708_vcio", KERNEL=="vcio"` (`vcio.go:51-53`), instance-aware via the security tag.
- **SNAP_NAME vs INSTANCE_NAME:** no snap-name interpolation (static `commonInterface` const); no `@{SNAP_NAME}`/`@{SNAP_INSTANCE_NAME}`/`SnapName()`/`InstanceName()`. No D-Bus, no sockets, no mounts. No bug.

**Reasoning:** The interface is device-path based with no snap-instance naming, so it is parallel-safe at the policy layer. However, `/dev/vcio` is a single fixed VideoCore GPU mailbox device (not a device class) — two parallel plug instances both get access to that one privileged hardware mailbox and contend over it. This is the same single-pinned-device situation as `gpio-memory-control` (`/dev/gpiomem`), so it is compatible at the snapd layer but shares a single hardware resource.

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
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants access to `/dev/input/*` and input-device sysfs/udev metadata (lines 44-57 in the implementation).
- UDev tagging is based on input device subsystems, not snap names.
- No snap-instance-specific paths are used.

**Reasoning:** Raw input devices are shared hardware resources. Parallel instances can be granted the same access; the interface does not encode any snap-instance collision point.

**Verification:** Passed on noble. Test at `tests/main/interfaces-raw-input`.

### dvb
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants access to `/dev/dvb/adapter[0-9]*/*` and DVB udev metadata (lines 32-39 in the implementation).
- The interface is device-path based and uses subsystem tagging, not snap naming.

**Reasoning:** DVB adapters are shared hardware devices. Parallel instances can access the same device nodes without snapd-level collision.

**Verification:** Passed on noble. Test at `tests/main/interfaces-dvb`.

### device-buttons
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants access to `/dev/input/event[0-9]*` and supporting input capability files (lines 37-59 in the implementation).
- The interface is backed by udev filtering for GPIO-key events, not by snap-instance-specific paths.

**Reasoning:** Device buttons are input-event hardware. Multiple parallel instances can share the same access; the policy does not key off snap instance names.

**Verification:** Passed on noble. Test at `tests/main/interfaces-device-buttons`.

### uhid
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants write access to `/dev/uhid` (lines 32-38 in the implementation).
- There is no udev tagging because UHID is not represented in sysfs.
- No snap-instance-specific logic is involved.

**Reasoning:** UHID is a shared kernel interface for creating HID devices from userspace. Parallel instances can access the same kernel interface without snapd path collisions.

**Verification:** Passed on noble. Test at `tests/main/interfaces-uhid`.

### block-devices
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- The interface grants broad access to raw disk block devices, controller character devices, and block-related sysfs/udev metadata (lines 58-132 in the implementation).
- It explicitly avoids partitions in the default policy and only adds partitions when requested.
- No snap-instance-specific names are used.
- The verified test installs a `_foo` instance, connects it independently, verifies it can read the same disk, and confirms it still works after the original snap is removed.

**Reasoning:** Raw block devices are accessible independently to parallel instances at the snapd policy level, which is what the verified test demonstrates. However, the underlying device is still shared hardware, so two snaps can absolutely interfere with each other if they read/write, repartition, mount, format, or otherwise manipulate the same disk at the application level.

**Verification:** Passed on noble. Test at `tests/main/interfaces-block-devices`.

### daemon-notify
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Snapd/Policy Management


**Code analysis:**
- The interface resolves `NOTIFY_SOCKET` from the environment or defaults to `/run/systemd/notify` (lines 56-88 in the implementation).
- It validates the socket path and emits an AppArmor rule for the resolved socket.
- No snap-instance-specific paths are introduced by snapd.

**Reasoning:** This is a client-side notify socket interface. Parallel instances are just concurrent clients talking to systemd’s notify socket; the code does not encode a snap-instance collision.

**Verification:** Passed on noble. Test at `tests/main/interfaces-daemon-notify`.

### browser-support
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Desktop/Graphics/Media Integration


**Code analysis:**
- **SNAP_NAME vs INSTANCE_NAME (correct):** the interface uses `@{SNAP_INSTANCE_NAME}` for the host-side `$XDG_RUNTIME_DIR` socket paths `/run/user/[0-9]*/snap.@{SNAP_INSTANCE_NAME}/...` (`browser_support.go:73-75`), with an explicit comment that "`$XDG_RUNTIME_DIR` is not remapped, need to use `SNAP_INSTANCE_NAME`" (`browser_support.go:72`). It also uses `@{SNAP_INSTANCE_NAME}` for peer security tags (`ptrace`/`unix peer=(label=snap.@{SNAP_INSTANCE_NAME}.**)`, `browser_support.go:230-231`). These are all HOST-side artifacts, so using the instance name is correct. The only `@{SNAP_NAME}` occurrences are inside commented-out illustrative rules (`browser_support.go:237,241`), not enforced. No bug.
- The interface also grants `owner` rules for per-user shared memory and browser-specific state, and a **send-only** session D-Bus to RealtimeKit (`org.freedesktop.RealtimeKit1`, `browser_support.go:281-292`) — no `dbus (bind)`, so no D-Bus name ownership.
- **Shared `/dev/shm` fixed-prefix names** (`browser_support.go:64-67,264,267`): `org.chromium.*`, `com.google.Chrome.*`, `com.microsoft.Edge.*`, `WK2SharedMemory.*`, `shmfd-*` are `owner`-matched but **not** snap-name-scoped, so two instances of the same browser snap can contend over the same `/dev/shm` object names.
- Slot is restricted to core only (`browser_support.go:35-46`: `slot-snap-type: [core]`), implicit on core and classic.

**Reasoning:** The snap-name/instance-name usage is correct (the `/run/user/.../snap.<instance>/` host paths and peer tags use `@{SNAP_INSTANCE_NAME}`), so there is no `SNAP_NAME`-vs-`INSTANCE_NAME` bug and the policy layer is parallel-safe. However, the fixed-name `/dev/shm/{org.chromium,com.google.Chrome,...}.*` segments are shared across instances (the IPC objects are not instance-keyed), so parallel instances of the same browser are not cleanly isolated — compatible at the snapd layer but sharing those user/SHM resources.

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
**Status:** Plug-side: POTENTIALLY COMPATIBLE. Slot-side: NOT COMPATIBLE.

**Type:** Desktop/Graphics/Media Integration


**Code analysis:**
- Plug-side uses instance-aware paths for document portal mounts via `plug.Snap().InstanceName()` (`interfaces/builtin/desktop.go:737`, `interfaces/builtin/desktop.go:760`).
- Connected plug/slot policy uses label expressions so mediation is per-connection (`interfaces/builtin/desktop.go:724-727`, `interfaces/builtin/desktop.go:813-816`).
- Slot-side permanent policy includes binding well-known desktop service names such as `org.gnome.Shell{,.*}` and `org.gnome.SettingsDaemon{,.*}` (`interfaces/builtin/desktop.go:567-580`).
- Document portal behavior is instance-scoped (`$XDG_RUNTIME_DIR/doc/by-app/snap.<instance>`) and mounted into each snap namespace, which isolates parallel instances at the portal mount layer (`interfaces/builtin/desktop.go:737`, `interfaces/builtin/desktop.go:760-765`).

**Reasoning:** Consumer snaps are parallel-install safe at the interface layer, including the document-portal mount path that is keyed by instance name. Provider snaps attempting to act as a full desktop session service hit singleton D-Bus ownership constraints.

**App-level caveat (desktop file IDs):** Applications using the `desktop-file-ids` attribute to register specific desktop file IDs may encounter collisions. Snapd preserves store-approved desktop file IDs as-is instead of mangling them per instance (`MangleDesktopFileName()` is skipped for store-approved IDs around `wrappers/desktop.go:281`/`:381`), and explicitly errors if the target file already belongs to another snap instance: `cannot install %q: %q already exists for another snap` when `instanceName != info.InstanceName()` (`wrappers/desktop.go:378-379`). Apps should avoid requesting fixed desktop IDs if parallel instances are intended.

**App-level caveat (desktop session integration — icon/window matching):** Even when the interface layer and desktop file generation work correctly, parallel instances can still be misrendered by the desktop shell. This is a known, observable bug.

*Reproduction (Firefox):*
```
snap set system experimental.parallel-instances=true
snap install firefox
snap install firefox firefox_beta
snap refresh firefox_beta --beta
snap run firefox        # dock button shows correct firefox icon, matches window
snap run firefox_beta   # dock button shows a GENERIC COG icon, does not match correctly
```

*Background — two distinct instance-naming schemes are involved.* `Info.DesktopPrefix()` (`snap/info.go:975-982`) deliberately substitutes `_` with `+` because the desktop file name already uses `_` to separate `<prefix>_<appname>`:
```go
// snap/info.go:975-982
func (s *Info) DesktopPrefix() string {
    if s.InstanceKey == "" {
        return s.SnapName()
    }
    return fmt.Sprintf("%s+%s", s.SnapName(), s.InstanceKey)
}
```
This is why the installed files are named:
- `/var/lib/snapd/desktop/applications/firefox_firefox.desktop` (instance `firefox`)
- `/var/lib/snapd/desktop/applications/firefox+beta_firefox.desktop` (instance `firefox_beta`)

The desktop file *names* are therefore instance-safe and do not collide. The breakage is in the desktop-entry *contents* that the shell relies on for window/icon association.

*Root cause — `StartupWMClass` is not rewritten per instance.* Inspecting Firefox's installed base-instance file shows:
```
X-SnapInstanceName=firefox
Icon=/snap/firefox/current/default256.png
StartupWMClass=firefox_firefox
```
The `StartupWMClass` value (`firefox_firefox`) comes verbatim from the snap's own source desktop file (`/snap/firefox/current/meta/gui/firefox.desktop`). `StartupWMClass=` is in the allowlist of permitted desktop-file lines (`wrappers/desktop.go:99`) but is **passed through completely unrewritten** — there is no per-instance handling for it anywhere in `wrappers/desktop.go` or `snap/info.go`. Consequently the `firefox+beta_firefox.desktop` entry carries the **same** `StartupWMClass=firefox_firefox` as the base instance. When the `firefox_beta` window appears, the shell uses `StartupWMClass` to associate the window with a desktop entry, but the value is ambiguous (shared with the base instance), so the shell cannot bind the window to the `firefox_beta` entry. The result is a dock button that fails to resolve the correct entry/icon and falls back to a generic icon.

*Icon path note.* The `Icon=${SNAP}/default256.png` source line is expanded using the instance-specific mount dir (`wrappers/desktop.go:229-232`, where `${SNAP}` becomes `s.MountDir()/../current`), so `firefox_beta` correctly gets `Icon=/snap/firefox_beta/current/default256.png`. The icon *path* is therefore correct; the visible generic-icon symptom is downstream of the failed window-to-entry association via `StartupWMClass`, not a wrong icon path. (Note: `rewriteIconLine()` at `wrappers/desktop.go:157-185` only rewrites themed `Icon=snap.<snapname>.*` references to the instance name; absolute `${SNAP}/...` paths are handled by the `${SNAP}` substitution above instead.)

*Net effect:* desktop-file naming is instance-safe, but the **session-level identity** the shell uses for window matching (`StartupWMClass`) is not instance-aware, so parallel GUI instances can be visually indistinguishable or mis-iconed. This is a session-integration limitation, not an interface-policy incompatibility, which is why the plug-side status remains COMPATIBLE while this visual/UX bug is called out separately. A complete fix would require snapd (and/or the app) to emit a per-instance `StartupWMClass` and for the app's runtime WM class to match it.

*Relevant code:* `snap/info.go:975-982` (DesktopPrefix `+` mangling), `wrappers/desktop.go:99` (StartupWMClass allowlisted but not rewritten), `wrappers/desktop.go:229-232` (`${SNAP}` expansion uses instance mount dir), `wrappers/desktop.go:157-185` (themed icon rewriting), `wrappers/icons.go:68-92` (themed icon file install/rename with `_`).

**Verification:** Passed on noble for document-portal mount behavior. Desktop session icon/window matching for parallel instances is a known failing case (see Firefox reproduction above); not yet covered by an automated test.

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
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

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
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- The interface tags USB devices by vendor ID and emits udev rules for matching devices (lines 129-190 in the implementation).
- The generated udev rules are keyed by the snap security tag, which is instance-aware.
- AppArmor grants access to `/dev/bus/usb/...`, udev metadata, and USB serial number sysfs files.
- No snap-instance-specific paths are involved.

**Reasoning:** ADB support is device- and vendor-based, and the udev mediation uses the snap security tag so parallel instances stay separated at the policy layer. Parallel instances can share the same USB debugging access without snapd-level collision.

**Verification:** Passed on noble. Test at `tests/main/interfaces-adb-support`.

### netlink-audit
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Network/Netlink Interface


**Code analysis:**
- Pure capability/syscall grant. Seccomp (`netlink_audit.go:42-43`) allows `bind` and `socket AF_NETLINK - NETLINK_AUDIT`; AppArmor (`netlink_audit.go:46-60`) grants `network netlink,`, `capability net_admin,`, `capability audit_read,`, `capability audit_write,`.
- `BeforeConnectPlug()` (`netlink_audit.go:66-83`) probes the host AppArmor `ParserFeatures()` for `cap-audit-read` and refuses connection on systems lacking it. It performs no plug/slot attribute checks.
- No D-Bus (no `dbus (bind)`/`DBusPermanentSlot`), no udev tagging, no hardcoded `/var/snap/<name>/` paths, and no use of `SnapName()`/`InstanceName()`/`ExpandSnapVariables()`/`LabelExpression()`. The kernel audit netlink socket is a global facility, not a snap-name-keyed resource.
- Slot is restricted to core only (`netlink_audit.go:32-38`: `slot-snap-type: [core]`).

**Reasoning:** This is a kernel-facility capability grant (NETLINK_AUDIT + CAP_NET_ADMIN/AUDIT_READ/AUDIT_WRITE). Multiple instances can use it concurrently as clients of the kernel audit subsystem; there is no snap-instance-specific resource and thus no snapd-level collision.

**Verification:** Passed on noble. Test at `tests/main/interfaces-netlink-audit`.

### netlink-connector
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Network/Netlink Interface


**Code analysis:**
- Pure capability/syscall grant. Seccomp (`netlink_connector.go:37-38`) allows `bind` and `socket AF_NETLINK - NETLINK_CONNECTOR`; AppArmor (`netlink_connector.go:41-49`) grants `network netlink,` and `capability net_admin,`. The policy intentionally allows communication via all netlink connectors (comments at lines 33-36, 42-45).
- No D-Bus, no udev tagging, no hardcoded `/var/snap/<name>/` paths, and no use of `SnapName()`/`InstanceName()`/`ExpandSnapVariables()`/`LabelExpression()`. NETLINK_CONNECTOR is a global kernel facility, not snap-name-keyed.
- Slot is restricted to core only (`netlink_connector.go:24-30`: `slot-snap-type: [core]`).

**Reasoning:** The connector is a shared kernel messaging facility exposed as a capability grant. Parallel instances can use it concurrently; there is no snap-instance-specific resource and thus no snapd-level collision.

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

2. **D-Bus bus policy** (`bluez.go:213-243`): `DBusPermanentSlot` (method at line 259, guarded by `if !release.OnClassic` at lines 259-263) emits
   `<allow own="org.bluez"/>` etc. (the `<allow own>` literals are at lines 215-217). File names are per-instance (security tag), but
   content grants the same name ownership to all instances. Note the entire slot side
   (permanent AppArmor/SecComp/DBus and connected-slot) is suppressed on classic via
   `!release.OnClassic` (lines 260, 295, 302), where bluez is the host's unconfined service.

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
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (gadget-provided slot; no parallel app slot providers in scope).

**Type:** Hardware Device Access


**Code analysis:**
- Slots are provided by gadget snaps only (`gpio_chardev.go:53-54`: `slot-snap-type: [gadget]`); the interface uses instance-aware names throughout the setup.
- **SNAP_NAME vs INSTANCE_NAME (every host-side artifact correctly uses `InstanceName()`):**
  - The slot's systemd export service uses `snapName := slot.Snap().InstanceName()` as the `<gadget>` arg to `export-chardev`/`unexport-chardev` (`gpio_chardev.go:136`, used at 145-149).
  - `SystemdConnectedPlug()` builds the host symlink: `target := gpio.SnapChardevPath(slot.Snap().InstanceName(), slotName)` and `symlink := gpio.SnapChardevPath(plug.Snap().InstanceName(), plugName)` (`gpio_chardev.go:160-165`), i.e. `/dev/snap/gpio-chardev/<slot-instance>/<slot-name>` and `/dev/snap/gpio-chardev/<plug-instance>/<plug-name>`. (`SnapChardevPath` joins `dirs.SnapGpioChardevDir/<instanceName>/<name>`, `gpio_chardev.go:38-40`.) These are host artifacts created outside the snap namespace, so `InstanceName()` is correct.
  - `AppArmorConnectedPlug()` emits `/dev/snap/gpio-chardev/%s/%s rwk,` with `slot.Snap().InstanceName(), slot.Name()` (line 185) and `/dev/snap/gpio-chardev/%s/{,*} r,` with `plug.Snap().InstanceName()` (line 187).
  - `UDevConnectedPlug()` tags with an instance-aware tag `snap_<slot-instance>_interface_gpio_chardev_<slot>` using `slot.Snap().InstanceName()` (`gpio_chardev.go:195`).
  - There is **no `@{SNAP_NAME}`/base-name/`SnapName()` anywhere** — no bug.
- KMod permanent slot loads `gpio-aggregator` (`gpio_chardev.go:58-60`). A conflict with `gpio` is explicitly declared via `conflictingConnectedInterfaces: []string{"gpio"}` (`gpio_chardev.go:207-210`) because both export the same kernel GPIO lines through different APIs.

**Reasoning:** The interface is carefully namespaced by snap **instance** for every host-side artifact — the export systemd service, the host symlink target and symlink, the AppArmor host device paths, and the udev tag all use `InstanceName()`. Parallel plug instances therefore each get their own `/dev/snap/gpio-chardev/<plug-instance>/<plug-name>` symlink and instance-distinct services, with no base-name bug and no snapd-level collision. (The underlying physical GPIO lines are a finite slot/gadget-pinned resource, but that contention is governed by the gadget side, not a plug-instance collision.) The only declared conflict is with the legacy `gpio` interface, which is intentional and unrelated to parallel naming.

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
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** Network/Netlink Interface


**Code analysis:**
- Slot is provided by core only (lines 24-29), with implicit slots on core and classic (lines 70-71).
- AppArmor grants access to `/usr/sbin/pppd`, `/etc/ppp/**`, `/dev/ppp`, tty devices, lock files, and log directories (lines 32-52).
- KMod and UDev support are declared for `ppp_generic` and the relevant devices (lines 54-64).
- No snap-instance-specific paths are used.

**Reasoning:** PPP control is a shared host service/device surface (`pppd`, `/etc/ppp/**`, `/dev/ppp`). There is no instance-name collision in policy, but parallel instances can interfere through shared PPP runtime/config state.

**Verification:** No verification has yet been done.

### qualcomm-ipc-router
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE.

**Type:** Hardware Device Access


**Code analysis:**
- The slot is app-providable as well as system-provided (`qualcomm_ipc_router.go:47-49`: `slot-snap-type: [app, core]`; `ImplicitOnCore`/`ImplicitOnClassic` true). There are two slot modes: a system slot (TypeOS/TypeSnapd, detected via `isConnectedSlotSystem`/`isSlotInfoSystem`, lines 160-172) and an app slot.
- The interface is socket-based (`AF_QIPCRTR`/seqpacket `network qipcrtr`), not D-Bus. For the system slot, the connected plug gets raw `network qipcrtr` + `capability net_admin` (compat, lines 69-76). For an app slot, the connected plug gets a scoped `unix (connect,send,receive) type=seqpacket addr="<address>" peer=(label=<slot label>)` (lines 78-84).
- **SNAP_NAME vs INSTANCE_NAME (peer labels correct):** `AppArmorConnectedPlug()` substitutes `###SLOT_SECURITY_TAGS###` with `slot.LabelExpression()` (`qualcomm_ipc_router.go:217`) and `AppArmorConnectedSlot()` substitutes `###PLUG_SECURITY_TAGS###` with `plug.LabelExpression()` (line 234); both resolve through `labelExpr` → `appSet.InstanceName()`, so peer mediation is instance-aware. The socket `address` is injected from the slot's `address` attribute (`fillSnippetSocketAddress`, lines 147-154; validated by `validateAddress`, lines 184-193) — a slot-author string, not derived from a snap name. No `@{SNAP_NAME}`/`SnapName()` misuse; no base-name bug.
- The app slot binds its address via `unix (bind, listen) type=seqpacket addr="<address>"` in the permanent slot (`qualcomm_ipc_router.go:86-96`, 244-256). Seccomp permanent slot grants `bind`/`accept`/`accept4`/`listen` (lines 110-119, 258-264). `BeforePrepareSlot()` validates `qcipc`/`address` and requires the `qipcrtr-socket` parser feature (lines 274-319).

**Reasoning:** The interface is socket-address based and already uses the snap labels correctly where needed (`LabelExpression()` for both peer directions), so there is no parallel-install instance-name collision at the snapd policy layer — plug and slot are both COMPATIBLE on that basis.

**App-level caveat (socket address):** The app slot binds the literal `address` attribute, which is **not** instance-keyed. If two parallel instances of the same slot-providing snap are installed, both would bind the same `AF_QIPCRTR` address and clash at the kernel-socket layer. This is a shared-resource caveat governed by the slot author's `address` value (akin to a fixed port), not a snapd-level instance-name bug; apps intending parallel slot providers must use distinct addresses.

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

2. **D-Bus bus policy** (`udisks2.go:239-247`): `DBusPermanentSlot` (method at line 420,
   guarded by `if !implicitSystemPermanentSlot(slot)` at lines 420-425) emits
   `<allow own="org.freedesktop.UDisks2"/>` (the `<allow own>` literal is at line 241).

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

3. **Connected plug is system-aware** (`upower_observe.go:233-243`): default peer is
   `slot.LabelExpression()` (line 235); when `implicitSystemConnectedSlot(slot)` is true
   (the system slot, e.g. on classic), the peer is overridden to
   `peer=(label=unconfined)` (lines 236-239). Instance-aware when connecting to an app slot.

4. **Connected slot is instance-aware** (`upower_observe.go:266-272`): uses
   `plug.LabelExpression()` (line 268) on Core.

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
**Status:** Plug-side: COMPATIBLE. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
The ofono interface provides telephony services via the ofono daemon. The plug side is a system-bus D-Bus **client** and is parallel-safe; the slot side is a system singleton.

**Plug side (COMPATIBLE):**
- The connected-plug AppArmor (`ofono.go:148-169`) is `dbus (receive, send)` to `org.ofono.*` and send-only Introspect, with `peer=(label=###SLOT_SECURITY_TAGS###)`. There is no `dbus (bind)` on the plug side — it owns no name.
- `AppArmorConnectedPlug()` substitutes `###SLOT_SECURITY_TAGS###` with `slot.LabelExpression()` (`ofono.go:306-309`), which is instance-aware, and additionally allows `unconfined` on classic (`ofono.go:310-313`, snippet `ofono.go:171-187`) since ofono runs unconfined on the host there. No `SnapName()`/`InstanceName()` and no hardcoded `/var/snap/<name>/` paths on the plug side. This is the same pure-client pattern as `network-manager`/`modem-manager` plug sides, so parallel plug instances have no snapd-level collision.

**Slot side (NOT COMPATIBLE):**

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
**Status:** Plug-side: COMPATIBLE. Slot-side: NOT COMPATIBLE.

**Type:** D-Bus Service/Provider


**Code analysis:**
The modem-manager interface provides cellular modem management via ModemManager. The plug side is a system-bus D-Bus **client** and is parallel-safe; the slot side is a system singleton.

**Plug side (COMPATIBLE):**
- The connected-plug AppArmor (`modem_manager.go:184-205`) is `dbus (receive, send)` to `/org/freedesktop/ModemManager1{,/**}` and `org.freedesktop.DBus.ObjectManager`, with `peer=(label=###SLOT_SECURITY_TAGS###)`. There is no `dbus (bind)` on the plug side — it owns no name.
- `AppArmorConnectedPlug()` substitutes `###SLOT_SECURITY_TAGS###` with `slot.LabelExpression()` (`modem_manager.go:1353-1356`), which is instance-aware, and additionally allows `unconfined` on classic (lines 1357-1360) since ModemManager runs unconfined on the host there. No `SnapName()`/`InstanceName()` and no hardcoded `/var/snap/<name>/` paths on the plug side. Same pure-client pattern as `network-manager`/`ofono` plug sides, so parallel plug instances have no snapd-level collision.

**Slot side (NOT COMPATIBLE):**

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
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core-provided slot).

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
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE.

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
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Filesystem/Mount Interface


**Code analysis:**
- The connected-plug AppArmor (`home.go:42-110`) is built entirely from `@{HOME}` (the user's real home directory, not the snap's home — see comment at `home.go:53`); rules at lines 56, 63-76, 80-81, 85-86.
- **SNAP_NAME vs INSTANCE_NAME:** there is no snap-name path interpolated into any enforced rule. The only occurrence of `@{SNAP_INSTANCE_NAME}` is inside a comment (`home.go:73`) explaining the `owner @{HOME}/snap/ r,` rule (line 76); the enforced rule itself has no snap name. No `SnapName()`/`InstanceName()` calls — `AppArmorConnectedPlug()` (`home.go:118-130`) just adds static snippets. No bug.
- The `@{HOME}/snap[^/]**` exclusion (`home.go:67`) plus the dotfile exclusion chain block access to other snaps' `~/snap/` data and hidden files. No D-Bus, no shared kernel objects, no udev.
- Slot is restricted to core only (`home.go:32-36`: `slot-snap-type: [core]`), implicit on core and classic (lines 136-137).

**Reasoning:** There is no `SNAP_NAME`/`INSTANCE_NAME` path issue, so the policy layer is parallel-safe. However, both instances of the same snap (like all snaps with `home`) access the same user `$HOME` files — a shared per-user resource by design. Parallel instances can read/overwrite each other's effects on the same home files, so this is compatible at the snapd layer but shares the home directory.

**Verification:**
PASSED on noble.



### desktop-launch
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

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
**Status:** Plug-side: COMPATIBLE. Slot-side: COMPATIBLE.

**Type:** Daemon/Socket Client


**Code analysis:**
- The slot is app-providable (`cups_control.go:52-61`: `allow-installation: slot-snap-type: [app, core]`, `deny-auto-connection: true`); `implicitOnClassic: true`, `implicitOnCore: false`.
- Plug-side AppArmor (`cups_control.go:106-119`) is a client: `#include <abstractions/cups-client>`, read-only `/{,var/}run/cups/printcap`, and `dbus (receive)` of `org.cups.cupsd.Notifier` signals with `peer=(label=###SLOT_SECURITY_TAGS###)`. It does NOT own a D-Bus name. `AppArmorConnectedPlug()` (`cups_control.go:150-173`) substitutes `###SLOT_SECURITY_TAGS###` with `slot.LabelExpression()` for app slots (line 163) or `{unconfined,/usr/sbin/cupsd,cupsd}` for the implicit system cupsd (line 161); `LabelExpression()` is instance-aware.
- Slot-side (`AppArmorPermanentSlot()`, `cups_control.go:129-136`, applied only when `!implicitSystemPermanentSlot(slot)`) grants the fixed system CUPS dir `/{,var/}run/cups/ rw,` + `/{,var/}run/cups/** rwk,` and D-Bus rules that are **send/receive only**: `dbus (receive, send)` to `org.freedesktop.ColorManager` (a client of ColorManager) and `dbus (send)` of its own `org.cups.cupsd.Notifier` (`cups_control.go:77-88`). **There is no `dbus (bind)` and no `DBusPermanentSlot`/`<allow own=...>`**, so the slot does not own a well-known D-Bus name. `AppArmorConnectedSlot()` (`cups_control.go:138-148`) sends the Notifier signal to the connected plug via `plug.LabelExpression()` (instance-aware).
- No use of `SnapName()`/`InstanceName()`/`ExpandSnapVariables()`; no hardcoded `/var/snap/<name>/` paths (the CUPS dir `/{,var/}run/cups/` is a fixed system path, not per-snap). Slot-side seccomp adds only `lsm_get_self_attr` (`cups_control.go:121-123`).

**Reasoning:** Plug-side parallel instances can submit print jobs simultaneously and only **receive** Notifier signals, with instance-aware peer labels via `LabelExpression()` — no snapd-level collision. The slot side is also parallel-install safe at the policy layer because it owns no well-known D-Bus name and constructs no base-snap-name host path; its D-Bus rules are send/receive only. The only shared resource is the singular host CUPS control socket directory `/{,var/}run/cups/`, which reflects the normal single print-service model rather than a parallel-install instance bug.

**Verification:**
FAILED -- pre-existing environment issue (no CUPS printer configured).
  Failure occurs at `lpr: Error - No default destination` in the original test code
  before any parallel-instance section. Unrelated to parallel installs. Needs a test
  environment with a configured CUPS printer.



### polkit
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Identity/Credentials/Secrets


**Code analysis:**
The polkit interface installs policy files (`.policy`) and rule files (`.rules`) for
polkit authorization.

1. **File names ARE instance-aware** (`polkit/backend.go:133,151`): Both policy and rule
   file names are built with `appSet.InstanceName()` — `polkitPolicyName(appSet.InstanceName(), nameSuffix)` (`backend.go:133`) and `polkitRuleName(appSet.InstanceName(), nameSuffix)` (`backend.go:151`). `appSet.InstanceName()` resolves to the instance-key-decorated name, so the templates (`backend.go:42-49`) produce:
   - Policy: `snap.<instance_name>.interface.<suffix>.policy`
   - Rules: `70-snap.<instance_name>.<suffix>.rules`
   Parallel instances (`foo` vs `foo_bar`) therefore get DISTINCT file names in the shared
   `dirs.SnapPolkitPolicyDir` / `dirs.SnapPolkitRuleDir`, so they do NOT collide. The per-snap `Setup()` sync glob is also instance-scoped (`backend.go:81,97`), so one instance's sync does not delete another's files.

2. **Source file reads are instance-aware** (`polkit.go:134`): Files are read from
   `plug.Snap().MountDir()` which is instance-specific (`/snap/<instance_name>/<rev>/`), via the glob `meta/polkit/<plug.Name()>.*.{policy,rules}`.

3. **D-Bus usage is client-only** (`polkit.go:61-89`, gated at `288-299`): The interface grants permission
   to call `{,Cancel}CheckAuthorization`/`RegisterAuthenticationAgentWithOptions` on `org.freedesktop.PolicyKit1.Authority` (the system
   polkitd), `peer=(label=unconfined)`. It does NOT own any D-Bus name (no `dbus (bind)`/`<allow own>`).

4. **Minor caveat -- action IDs in XML are not instance-scoped**: The `action-prefix`
   attribute (e.g., `org.example.foo`) is shared across all instances. Both `foo` and
   `foo_bar` would install policy files containing actions under the same prefix. Polkitd
   could see duplicate action definitions, though this is typically harmless (last file
   wins in polkitd's evaluation). This is a polkit content overlap, not a snapd-level file collision.

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
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

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
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Identity/Credentials/Secrets


**Code analysis:**
- Read access to `~/.ssh/` files
- No shared memory, no D-Bus, no instance-specific paths
- Multiple instances reading SSH keys is the same as having SSH read access

**Verification:**
PASSED on noble.



### ssh-public-keys
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Identity/Credentials/Secrets


**Code analysis:**
- Read access to SSH public keys (`~/.ssh/*.pub`, `/etc/ssh/ssh_host_*_key.pub`)
- No shared memory, no D-Bus, no writes to global resources

**Verification:**
PASSED on noble.



### personal-files
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Filesystem/Mount Interface


**Code analysis:**
The personal-files interface grants access to user-specific file paths declared in plug
attributes. The implementation is in `common_files.go` (shared with `system-files`).

1. **Paths are from plug attributes** (`personal_files.go`): the `read` and
   `write` attributes are lists of absolute paths under `$HOME/` (validated by `validateSinglePathHome`, `personal_files.go:58-66`).

2. **Path expansion** (`common_files.go:formatPath`, `common_files.go:60-77`): the ONLY
   substitution is `$HOME` → `@{HOME}` with an `owner` prefix (`common_files.go:69-71`); then `{,/,/**}` is appended (line 74). **No snap-name token (`@{SNAP_NAME}`/`@{SNAP_INSTANCE_NAME}`) and no `SnapName()`/`InstanceName()` call anywhere.**

3. **SNAP_NAME vs INSTANCE_NAME:** the generated AppArmor rules are snap-name-agnostic; the snap-update-ns ensure-dir machinery is keyed by the interface name (`"personal-files"`), not by snap name, and operates inside the user's own per-instance namespace. Both a base snap and its parallel instance get **identical** rules. No bug.

4. The plug base declaration is `allow-installation: false` (`personal_files.go:34-38`, super-privileged), and the slot is core-only (`personal_files.go:40-46`).

**Reasoning:** personal-files grants access to user-owned paths declared in attributes, completely
outside the snap's own data directories. There is no `SNAP_NAME`/`INSTANCE_NAME` issue, so the policy layer is parallel-safe. However, two parallel instances accessing the same declared `$HOME/...` files is contention over shared per-user files (they can overwrite each other), so this is compatible at the snapd layer but shares those user files.

**Verification:**
-Result: PASSED on noble. Parallel instance read/wrote same personal files,
survived removal of original snap.



### system-files
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Filesystem/Mount Interface


**Code analysis:**
Same implementation as personal-files (both embed `commonFilesInterface` in
`common_files.go`).

1. **Paths are absolute system paths** from plug attributes (e.g., `/etc/foo`,
   `/var/lib/bar`); `$HOME` is forbidden (`validateSinglePathSystem`, `system_files.go:52-61`).

2. **Path expansion** (`common_files.go:formatPath`): because `$HOME` is forbidden, the `$HOME`→`@{HOME}` branch never fires, so paths are emitted verbatim as absolute system paths. **No snap-name interpolation whatsoever** — no `@{SNAP_NAME}`/`@{SNAP_INSTANCE_NAME}`/`SnapName()`/`InstanceName()`.

3. **SNAP_NAME vs INSTANCE_NAME:** rules are snap-name-agnostic; both a base snap and its parallel instance get identical rules. No bug.

4. The plug base declaration is `allow-installation: false` (`system_files.go:29-33`, super-privileged), and the slot is core-only (`system_files.go:35-41`).

**Reasoning:** system-files grants access to fixed system paths declared in attributes. There is no `SNAP_NAME`/`INSTANCE_NAME` issue, so the policy layer is parallel-safe. However, two parallel instances accessing the same absolute system files is contention over a shared system resource (they can conflict if both write the same file), so this is compatible at the snapd layer but shares those system files.

**Verification:** 
- **Result:** PASSED on noble. Parallel instance read/wrote same system files,
survived removal of original snap.


### hostname-control
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

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
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

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
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

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
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

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
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Network/Netlink Interface


**Code analysis:**
- D-Bus client (send-only) to `io.netplan.Netplan` (`/io/netplan/Netplan`, members Generate/Apply/Info/Config — `network_setup_control.go:74-79`) and `io.netplan.Netplan.Config` (`/io/netplan/Netplan/config/*` — lines 82-87), both `peer=(label=unconfined)`. No `dbus (bind)`, no `DBusPermanentSlot` — owns no name.
- Writes to global host network-config paths: `/etc/netplan/{,**} rw`, `/etc/network/{,**} rw`, `/etc/systemd/network/{,**} rw` (`network_setup_control.go:55-57`), `/run/systemd/network/*-netplan-* w` (line 62; note `/run/systemd/network/{,**}` itself is read-only at line 61), `/run/NetworkManager/conf.d/*netplan*.conf* w` (line 64), and `/run/udev/rules.d/...` rw (lines 67-68). Executes `/usr/sbin/netplan` (lines 38-40) and `/usr/libexec/netplan/configure` (line 65).
- No seccomp snippet, no udev tagging, and no use of `SnapName()`/`InstanceName()`/`ExpandSnapVariables()`/`LabelExpression()`. All write paths are global system directories, not snap-name-dependent.
- System-provided implicit slot, core-only (`network_setup_control.go:24-30`: `slot-snap-type: [core]`).

**Reasoning:** Global network configuration via a send-only D-Bus client that owns no name. No snap-name-dependent resources; all paths are global system directories. Two parallel instances writing the same global netplan config is shared-host contention at the operational level, not a snapd instance-name collision, so the plug side is parallel-install compatible.

**Verification:** 

- **Results:** PASSED on noble.



### account-control
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Identity/Credentials/Secrets


**Code analysis:**
- D-Bus client to `org.freedesktop.Accounts`: `dbus (send)` Introspect/Accounts/Accounts.User/Properties (`account_control.go:44-66`) plus `dbus (receive)` PropertiesChanged (lines 68-73). No `dbus (bind)`/`DBusPermanentSlot`/`<allow own>` — owns no name.
- Writes to `/var/lib/extrausers/**` (`account_control.go:81-82`, `rwkl` incl. lock+link), plus `/var/log/{faillog,lastlog,tallylog}` (lines 107-109)
- Executes `useradd`, `userdel`, `chpasswd` (`account_control.go:75-76`)
- Dynamic seccomp template (`account_control.go:114-122`) substitutes `{{group}}` with the runtime-resolved GID owning `/etc/shadow` (`makeAccountControlSecCompSnippet`, lines 129-138) -- a system-global numeric GID, not snap-specific; the substituted snippet is cached and applied via `SecCompConnectedPlug()` (lines 141-152).
- **SNAP_NAME vs INSTANCE_NAME:** no snap-name interpolation -- all paths are fixed host paths and the seccomp GID is numeric. `network netlink raw` (line 95); capabilities `audit_write`/`chown`/`fsetid` (lines 98-100). No bug.
- System-provided implicit slot, core-only (`account_control.go:33-39`: `slot-snap-type: [core]`).

**Reasoning:** Global user account management via a D-Bus client (no name ownership) plus writes to the shared `/var/lib/extrausers/` user database. No snap-name-dependent resources, and the dynamic seccomp GID resolution is deterministic regardless of instance. The extrausers DB is shared host state, but useradd/userdel use lock files (`rwkl`) and the system serializes access, so this remains compatible at the snapd layer (the same single-system-state model as the other system-control interfaces).

**Verification:**

- **Results:** passed on core 18




### joystick
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

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
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Observability/Diagnostics


**Code analysis:**
- Slot is provided by core only (`hardware_observe.go:24-30`: `slot-snap-type: [core]`), implicit on core and classic (lines 162-163).
- The connected-plug AppArmor (`hardware_observe.go:32-138`) is read-only access to hardware info: `@{PROC}/...`, `/sys/...`, `/dev/...`, `/run/udev/data/...`, plus `ixr` exec of helpers (`lsblk`, `lscpu`, `lsmem`, `lsusb`, `systemd-detect-virt`). Capabilities `sys_rawio`/`sys_admin`; `network netlink raw` (line 71). Seccomp (`hardware_observe.go:140-156`) adds `iopl`, `riscv_hwprobe`, `socket AF_NETLINK - NETLINK_GENERIC`/`NETLINK_KOBJECT_UEVENT` + `bind`.
- **SNAP_NAME vs INSTANCE_NAME:** no snap-name interpolation; all paths are fixed host/kernel paths and the netlink sockets are unnamed/per-process. No D-Bus, no mounts, no udev tagging, no bug.

**Reasoning:** Read-only hardware observer. There is no snap-name path and no shared mutable named resource (netlink sockets are per-process), so multiple parallel instances read the same hardware info with no snapd-level collision.

**Verification:**
PASSED on noble.



### hardware-random-control
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** System Control/Privileged Capability


**Code analysis:**
- Read/write access to `/dev/hwrng` and sysfs hw_random paths
- Single hardware resource, but multiple readers don't conflict
- Writers could theoretically conflict (setting `rng_current`), but this is an
  operational concern, not an interface/AppArmor concern

**Verification:**
PASSED on noble.



### hardware-random-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Observability/Diagnostics


**Code analysis:**
- Slot is provided by core only (`hardware_random_observe.go:24-30`: `slot-snap-type: [core]`), implicit on core and classic (lines 49-50).
- The connected-plug AppArmor (`hardware_random_observe.go:32-41`) grants read-only `/dev/hwrng` (line 37), `/run/udev/data/c10:183` (line 38), and `/sys/devices/virtual/misc/.../hw_random/rng_{available,current}` (lines 39-40). UDev tags `KERNEL=="hw_random"` (line 43).
- **SNAP_NAME vs INSTANCE_NAME:** no snap-name interpolation; fixed device/sysfs paths only. No D-Bus, no sockets, no mounts, no bug. This is the read-only subset of `hardware-random-control`.

**Reasoning:** Read-only access to the hardware RNG device and its sysfs state. Reading `/dev/hwrng` is non-exclusive and there is no snap-name path or owned resource, so parallel instances do not collide at the snapd layer.

**Verification:**
PASSED on noble.




### shared-memory
**Status:** non-private/named mode Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core-provided slot).
private mode Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot).

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

**Reasoning:** In non-private mode, SHM names are kernel-global. When both the original
slot and a parallel slot write to the same named SHM path, they operate on the same
kernel object. The `_foo` slot's write clobbers the original's data. There is no
per-instance isolation of named SHM objects.

Private shared-memory is designed for per-snap isolation. The
`InstanceName()` usage ensures parallel instances get separate namespaces. This is the
most isolation-friendly mode of shared-memory.

**Verification:**
Expected failure for non-private mode. The original plug reads `parallel data` instead of
  `original data`, because `shm-slot_foo` overwrote the same kernel SHM object at
  `/dev/shm/writable-bar`. The named SHM paths are not instance-scoped.

PASSED on noble for private mode. Parallel instance got its own `/dev/shm/snap.shm-private_foo/`
namespace, segments were isolated from original, survived removal of original snap.

### posix-mq
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: NOT COMPATIBLE.

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
**Status:** Plug-side: POTENTIALLY COMPATIBLE. Slot-side: N/A (system/core-provided slot)

**Type:** Filesystem/Mount Interface


**Code analysis:**

1. **Path expansion uses `SnapName()` for namespace paths** (`snap/info.go:829`):
   `$SNAP_COMMON` expands to `/var/snap/<snap>/common` using the base snap name, which is correct for paths inside the snap's mount namespace where `/var/snap/<snap_instance>/` is remapped to `/var/snap/<snap>/`.

2. **AppArmor mount rules use namespace paths** (`mount_control.go:623-691`): 
   The generated AppArmor mount rules use the expanded path (via `SnapName()`), allowing mounting to `/var/snap/test-snapd-mount-control/common/target1`. When a parallel instance tries to use the `mount` syscall directly with a host path like `/var/snap/test-snapd-mount-control_foo/common/target1`, AppArmor denies it because the rule only allows the base-name path.

3. **Permission check in `snapctl mount` uses namespace paths** (`overlord/hookstate/ctlcmd/mount.go:62-72`):
   ```go
   func matchMountPathAttribute(path string, attribute any, snapInfo *snap.Info) bool {
       expandedPattern := snapInfo.ExpandSnapVariables(pattern)  // uses SnapName()
       pp, err := utils.NewPathPattern(expandedPattern, allowCommas)
       return err == nil && pp.Matches(path)
   }
   ```
   The pattern is expanded using the base snap name. When the snap provides a path argument to `snapctl mount`, that path is what the snap sees in its namespace (e.g., `/var/snap/test-snapd-mount-control/common/target1`), which matches the pattern. However, `snapctl mount --persistent` creates a systemd mount unit on the host.

4. **Systemd mount units operate on host paths**: The systemd mount unit created by `snapctl mount --persistent` must use the actual host filesystem path, which for a parallel instance would be `/var/snap/test-snapd-mount-control_foo/common/target1`. But the current implementation doesn't translate from namespace paths to host paths.

**Reasoning:** The mount-control interface currently has a namespace-vs-host path mismatch: it uses namespace-internal paths (via `SnapName()`) for AppArmor rules and permission checks, but direct `mount` syscalls and systemd mount units operate on host paths (which include the instance key). Parallel instances are therefore blocked today by AppArmor when using host paths, and `snapctl mount --persistent` can point systemd units at incorrect host paths. Because this is an implementation/translation bug rather than an inherent model limit, plug-side is POTENTIALLY COMPATIBLE if path normalization/translation is fixed.

**Verification (interfaces-mount-control):**
Expected failure. `mount: mount /var/tmp/test-snapd-mount-control on
  /var/snap/test-snapd-mount-control_foo/common/target1 failed: Permission denied`.
  AppArmor denies the mount because the rule uses `SnapName()` which only allows
  `/var/snap/test-snapd-mount-control/common/...`, not the instance-specific path.




### password-manager-service
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Identity/Credentials/Secrets


**Code analysis:**
- The connected-plug AppArmor (`password_manager_service.go:32-82`) is a **session-bus** D-Bus client: `#include <abstractions/dbus-session-strict>` (line 37) and `dbus (receive, send)` to `/org/freedesktop/secrets` (`org.freedesktop.Secret.*`) and KWallet `/modules/kwalletd` (`org.kde.KWallet`), all `bus=session`, `peer=(label=unconfined)` (lines 54-81).
- **It owns no D-Bus name.** No `dbus (bind)`, no `DBusPermanentSlot`, no `<allow own>`; it talks to `org.freedesktop.secrets`/KWallet as a client (addressed by object path, peer label unconfined). This is a `commonInterface` with only `connectedPlugAppArmor` set (`password_manager_service.go:85-91`), so there is no slot-side code.
- The in-code comment (lines 42-52, 66-69) explicitly notes the secret-service/KWallet APIs do not allow AppArmor application isolation — i.e. all clients (including parallel instances) share the same secrets store at the service level. The keyring DB itself is owned/mediated by the gnome-keyring/KWallet daemon, not granted as a file path here.
- No `InstanceName()`/`SnapName()`/`ExpandSnapVariables()`/`LabelExpression()`, no hardcoded `/var/snap/<name>/` paths, no seccomp/udev.
- Slot is restricted to core only (`password_manager_service.go:24-30`: `slot-snap-type: [core]`).

**Reasoning:** gnome-keyring / KWallet is a user-session service. Multiple snap instances are just
additional session-bus clients of the same keyring; the plug owns no name and writes no per-instance file directly, so there is no snapd-level collision. (By design all clients share one secrets store — a confidentiality property of secret-service, not a parallel-install break.) The slot side is core-only, so parallel app-provided slots are not possible.

**Previous audit errors**:
- Classified as "NOT COMPATIBLE" -- INCORRECT. The interface is a session-bus client that owns no keyring service name.

**Verification:**
PASSED on noble.



### calendar-service
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** D-Bus/IPC Client


**Code analysis:**
- The connected-plug AppArmor (`calendar_service.go:36-131`) is a **session-bus** D-Bus client: `#include <abstractions/dbus-session-strict>` (line 39) and `dbus (receive, send)` to Evolution Data Server Calendar objects, all `bus=session`, `peer=(label=unconfined)` (lines 42-130).
- **It owns no D-Bus name.** No `dbus (bind)`, no `DBusPermanentSlot`, no `<allow own>`; this is a `commonInterface` with only `connectedPlugAppArmor` set (`calendar_service.go:133-140`), so there is no slot-side code. Unlike contacts-service, there is no avatar-cache file rule (no `@{HOME}` rules at all).
- No `InstanceName()`/`SnapName()`/`ExpandSnapVariables()`/`LabelExpression()`, no hardcoded `/var/snap/<name>/` paths, no seccomp/udev.
- Slot is restricted to core only (`calendar_service.go:28-34`: `slot-snap-type: [core]`).

**Reasoning:** Evolution Data Server calendar access is client-side session D-Bus use, the same architecture as contacts-service. Parallel instances are additional clients to shared user-session calendar data, with no bus-name ownership and no snap-instance naming collision in interface policy. The slot side is core-only, so parallel app-provided slots are not possible.

**Previous audit errors**:
- Classified as "NOT COMPATIBLE" -- INCORRECT. There is no D-Bus name ownership in code; the interface is a session-bus client.

**Verification:**
PASSED on noble.

### log-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Observability/Diagnostics


**Code analysis:**
- Slot is provided by core only (`log_observe.go:24-30`: `slot-snap-type: [core]`), implicit on core and classic (lines 90-91).
- The connected-plug AppArmor (`log_observe.go:33-80`) is read access to system logs: `/var/log/**` (lines 36-37), `/dev/kmsg` (line 39), `/run/log/journal/**` (lines 42-43), host `journalctl` + systemd libs (lines 47-48). It additionally has a couple of `rw` rules on global kernel/apparmor tunables (`@{PROC}/sys/kernel/printk_ratelimit` line 56, `/sys/module/apparmor/parameters/audit` line 67) and capabilities `dac_override`/`dac_read_search` — these are system-global knobs, not per-snap resources. UDev tags `KERNEL=="kmsg"` (lines 82-84).
- **SNAP_NAME vs INSTANCE_NAME:** no snap-name interpolation anywhere; all paths are fixed host/kernel paths (`@{PROC}` is the proc mount, not a snap-name variable). No D-Bus, no mounts, no bug.

**Reasoning:** Read-only system-log observer (the handful of `rw` items are global kernel/apparmor tunables, not snap-instance resources). There is no snap-name path and no owned resource, so parallel instances do not collide at the snapd layer.

**Verification:** Passed on noble. Test at `tests/main/interfaces-log-observe`.

### network-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Network/Netlink Interface


**Code analysis:**
- Privileged read-only/observer network status. Connected-plug AppArmor (`network_observe.go`) is a D-Bus client: `dbus send` to `org.freedesktop.resolve1` (lines 58-63), `dbus receive` of `PropertiesChanged` from systemd-networkd (lines 74-86), and `dbus send` to `org.freedesktop.network1` Get/All and Manager list/describe methods (lines 89-102). No `dbus (bind)`, no `DBusPermanentSlot` — owns no name.
- Capabilities are limited to `net_raw`+`setuid` for ping (lines 149-152); a comment at lines 38-41 explicitly refuses `net_admin` to avoid becoming network-control. Read-only `@{PROC}/sys/net/...` and `/sys/devices/**/net/** rk`.
- Seccomp grants `bind` plus several `AF_NETLINK` families (`NETLINK_INET_DIAG`, `NETLINK_ROUTE`, `NETLINK_GENERIC`, `NETLINK_KOBJECT_UEVENT`) (`network_observe.go:177-189`).
- No use of `SnapName()`/`InstanceName()`/`ExpandSnapVariables()`/`LabelExpression()`; no hardcoded `/var/snap/<name>/` paths; no udev tagging; no shared kernel objects.

**Reasoning:** Read-only/observer network status queries (D-Bus client to systemd-resolved and systemd-networkd, read-only proc/sys, NET_RAW for ping). The interface owns no D-Bus name and has no instance-specific paths, so parallel instances are independent observers with no snapd-level collision.

**Verification:** Passed on noble. Test at `tests/main/interfaces-network-observe`.

### mount-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Filesystem/Mount Interface


**Code analysis:**
- The connected-plug AppArmor (`mount_observe.go:42-76`) is read-only `@{PROC}`/`/proc`, `/sys`, `/etc/mtab`, `/etc/fstab`, `/run/mount/utab` introspection using AppArmor macros `@{PROC}`/`@{pid}`/`@{tid}`. `mountInfoSnippet` (`mount_observe.go:82-85`) adds `owner @{PROC}/@{pid}/mountinfo` and `@{PROC}/self/mountinfo`, added via `AddPrioritizedSnippet(..., MountInfoKey, ...)` (line 119).
- **SNAP_NAME vs INSTANCE_NAME:** there is no `@{SNAP_NAME}`/`@{SNAP_INSTANCE_NAME}`/`SnapName()`/`InstanceName()`. The one snapd path variable that appears is `@{SNAP_COREUTIL_DIRS}df ixr,` (`mount_observe.go:48`), which expands to the coreutils binary dirs **inside the snap's own runtime** (a self/in-namespace path used to execute the bundled `df`), so the base/self view is correct here. No bug.
- Seccomp adds `quotactl`, `listmount`, `statmount` (`mount_observe.go:87-100`). No D-Bus, no shared kernel named objects.
- Slot is restricted to core only (`mount_observe.go:33-39`: `slot-snap-type: [core]`), implicit on core and classic (lines 107-108).

**Reasoning:** This is read-only introspection of the calling process's own mount/quota info; there is no snap-name host path and no shared writable/singular resource, so parallel instances are independent readers with no snapd-level collision.

**Verification:** Passed on noble. Test at `tests/main/interfaces-mount-observe`.

### system-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Observability/Diagnostics


**Code analysis:**
- Slot is provided by core only (`system_observe.go:36-42`: `slot-snap-type: [core]`), implicit on core and classic (lines 264-265).
- The connected-plug AppArmor (`system_observe.go:44-204`, added via `AppArmorConnectedPlug()` at 225-239) is broad **read-only** system/process observation: `ptrace (read)`, `@{PROC}/**`, `/sys/fs/cgroup/...`, `/var/lib/snapd/hostfs/{etc/os-release,usr/lib/os-release}`, `/boot/config*`.
- **D-Bus is client-only:** `dbus (send)` to `org.freedesktop.hostname1` (lines 149-161), DBus daemon ListNames/GetMachineId (164-177), and systemd1 manager property/unit queries (181-196), all `peer=(label=unconfined)`. No `dbus (bind)`/`DBusPermanentSlot`/`<allow own>` — owns no name.
- **Read-only `/boot` bind mount:** `MountPermanentPlug()` (`system_observe.go:241-257`) and the matching update-ns rules in `AppArmorConnectedPlug()` (lines 228-237) bind the host `/var/lib/snapd/hostfs/boot` onto `/boot` read-only.
- **SNAP_NAME vs INSTANCE_NAME:** the mount source/target are fixed host paths (`/var/lib/snapd/hostfs/boot` → `/boot`), identical for every instance; no `@{SNAP_NAME}`/`@{SNAP_INSTANCE_NAME}`/`SnapName()`/`InstanceName()`/`ExpandSnapVariables()`. No bug. Seccomp adds `lsm_get_self_attr` (line 211).

**Reasoning:** Read-only system/process observation. The D-Bus access is client-side only (no name ownership), and the `/boot` bind mount uses a fixed host path identical for every instance (mounted into each snap's own private namespace), so there is no instance-name collision and no shared mutable named resource.

**Verification:** Passed on noble. Test at `tests/main/interfaces-system-observe`.

### process-control
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** System Control/Privileged Capability


Capability-based: `kill` syscall, signal sending, priority changes. No paths, no D-Bus.

**Verification:** Passed on noble. Test at `tests/main/interfaces-process-control`.

### gpg-keys
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Identity/Credentials/Secrets


**Code analysis:**
- The connected-plug AppArmor (`gpg_keys.go:32-56`) allows running `gpg` (line 37), reading `owner @{HOME}/.gnupg/{,**}` (line 44), `rw` on the per-uid gpg-agent socket `owner /run/user/[0-9]*/gnupg/S.*` (line 42), and **writing** `owner @{HOME}/.gnupg/random_seed wk,` (line 55). It denies `~/.gnupg/trustdb.gpg w` (line 47).
- **SNAP_NAME vs INSTANCE_NAME:** no snap-name interpolation — `@{HOME}` and `/run/user/[0-9]*` are per-user/per-uid paths resolved at runtime, not snap-name tokens. No D-Bus, seccomp, or udev. No bug.
- Slot is restricted to core only (`gpg_keys.go:24-30`: `slot-snap-type: [core]`).

**Reasoning:** There is no snap-name path, so the policy layer is parallel-safe. However, the interface writes the shared per-user `~/.gnupg/random_seed` (`wk`, line 55) and uses the shared per-uid gpg-agent socket (line 42); two parallel instances run by the same user both mutate that single user file. So this is compatible at the snapd layer but shares per-user GnuPG state (unlike `gpg-public-keys`, which only takes transient gpg lock files).

**Verification:** Passed on noble. Test at `tests/main/interfaces-gpg-keys`.

### gpg-public-keys
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Identity/Credentials/Secrets


Read access to public-key and config files, plus limited lock-file writes required by some gpg operations. No D-Bus, no snap-name paths.

**Verification:** Passed on noble. Test at `tests/main/interfaces-gpg-public-keys`.

### removable-media
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Filesystem/Mount Interface


**Code analysis:**
- The connected-plug AppArmor (`removable_media.go:32-50`) is fixed host mount-point paths only: `/run/`, `/{,run/}media/`, `/{,run/}media/*/`, `/{,run/}media/*/**`, `/mnt/`, `/mnt/**`. The `*` is a user-name wildcard (comment at `removable_media.go:42`), not a snap name.
- **SNAP_NAME vs INSTANCE_NAME:** there is no `@{SNAP_NAME}`/`@{SNAP_INSTANCE_NAME}`/`SnapName()`/`InstanceName()` anywhere; it is a plain `commonInterface` (`removable_media.go:52-60`). No bug.
- No D-Bus, no shared kernel objects, no udev.
- Slot is restricted to core only (`removable_media.go:24-30`: `slot-snap-type: [core]`), implicit on core and classic (lines 56-57).

**Reasoning:** No snap-name path is involved, so the policy is identical for all instances and parallel-safe at the snapd layer. The `/media`, `/run/media`, `/mnt` mount points are shared host locations, so parallel instances reading/writing the same removable media contend over that shared resource — compatible at the snapd layer but sharing the host mount points.

**Verification:** Passed on noble. Test at `tests/main/interfaces-removable-media`.

### kvm
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Container/Virtualization Support


Device access to `/dev/kvm`. No D-Bus, no snap-name paths.

**Verification:** Passed on noble. Test at `tests/main/interfaces-kvm`.

### raw-usb
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (core-only slot; no parallel app slot providers possible).

**Type:** Hardware Device Access


Device access to a generic class of USB devices: `/dev/bus/usb/[0-9][0-9][0-9]/[0-9][0-9][0-9]` (`raw_usb.go:35`), `/dev/tty{USB,ACM}[0-9]*`, `/dev/usb/lp[0-9]*`, plus USB sysfs and `/run/udev/data/...`. UDev tags `SUBSYSTEM=="usb"`/`usbmisc`/`tty ID_BUS==usb` (`raw_usb.go:68-72`, instance-aware via security tag); seccomp adds `socket AF_NETLINK - NETLINK_KOBJECT_UEVENT` (lines 60-66). No D-Bus, no snap-name paths. Slot is core only (`raw_usb.go:27-28`: `slot-snap-type: [core]`; the doc previously said core/gadget — gadget is NOT permitted).

**Verification:** Passed on noble. Test at `tests/main/interfaces-raw-usb`.

### cuda-driver-libs
**Status:** Plug-side: N/A (system/core plug only on classic; parallel app plugs out of scope). Slot-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE.

**Type:** Desktop/Graphics/Media Integration

**Code analysis:**
- The interface is mostly about publishing CUDA driver libraries and config metadata.
- `BeforePrepareSlot()` validates the compatibility expression and source directories (lines 61-77).
- `LdconfigConnectedPlug()` and `ConfigfilesConnectedPlug()` expose the slot's libraries/config through system helper paths (lines 79-103).
- The implementation is system-oriented and does not introduce snap-instance-specific paths.

**Reasoning:** This is a library exposure interface scoped by compatibility metadata and system paths. Parallel installs don’t create a snap instance naming issue in the code shown.

**Verification:** No verification has yet been done.

### packagekit-control
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** System Control/Privileged Capability

**Code analysis:**
- Slot is provided by core only (`packagekit_control.go:30-36`: `slot-snap-type: [core]`), with implicit slot on classic (line 107). The plug base declaration sets `allow-installation: false` (`packagekit_control.go:24-28`), so this is super-privileged and plug installation needs a snap-declaration.
- The connected-plug AppArmor (`packagekit_control.go:38-101`) is a **system-bus** D-Bus client (`#include <abstractions/dbus-strict>`, line 42): `dbus (receive, send)` to `/org/freedesktop/PackageKit` (PackageKit, PackageKit.Offline, DBus.Properties, Introspectable) at lines 45-72, and to transaction object paths at lines 78-100, `peer=(label=unconfined)`.
- The transaction object paths are random, numeric/hex identifiers (`/[0-9]*_[0-9a-f]{8}`, lines 80/85/91/97), not snap-name-derived.
- **It owns no D-Bus name.** No `dbus (bind)`, no `DBusPermanentSlot`, no `<allow own>` (and no `peer=(name=...)` — purely label-based client access). This is a `commonInterface` with only `connectedPlugAppArmor` set (`packagekit_control.go:104-111`), so there is no slot-side code.
- No `InstanceName()`/`SnapName()`/`ExpandSnapVariables()`/`LabelExpression()`, no hardcoded `/var/snap/<name>/` paths, no mount/seccomp/udev.

**Reasoning:** PackageKit is a shared system service and the interface is just a system-bus D-Bus client. Parallel instances are ordinary concurrent clients talking to the same daemon; the transaction object paths are generated by PackageKit itself (not snapd), and the interface owns no bus name, so there is no snapd-level collision. The slot side is core-only, so parallel app-provided slots are not possible.

**Verification:** No verification has yet been done.

### polkit-agent
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Identity/Credentials/Secrets

**Code analysis:**
- Slot is provided by core only, plug install denied: plug base declaration `allow-installation: false` (`polkit_agent.go:28-32`), slot `slot-snap-type: core` (`polkit_agent.go:34-40`). `implicitOnCore` is set only when the polkit-agent helper binary exists (`polkit_agent.go:142`); there is no `implicitOnClassic` field.
- The connected-plug AppArmor (`polkit_agent.go:47-129`) registers with polkitd on the system bus (`dbus (receive, send)` to `org.freedesktop.PolicyKit1.Authority`, lines 48-63), receives from `org.freedesktop.PolicyKit1.AuthenticationAgent` (lines 66-69), and talks to `org.freedesktop.Accounts` for UI prompts (lines 74-93). It is a **client** — there is no `dbus (bind)`/`<allow own>`, so it owns no bus name (it registers as an agent via a method call).
- **SNAP_NAME vs INSTANCE_NAME (correct):** the helper subprofile (`polkit_agent.go:98-129`) uses `@{SNAP_INSTANCE_NAME}` in its signal peer label — `signal (receive) set=(term) peer=snap.@{SNAP_INSTANCE_NAME}.*,` (`polkit_agent.go:114`). This allows the setuid `polkit-agent-helper-1` to receive SIGTERM from the agent process whose AppArmor label is `snap.<instance>.<app>`. Because AppArmor labels are instance-decorated, using `@{SNAP_INSTANCE_NAME}` here is correct and required (base `@{SNAP_NAME}` would not match a keyed instance's label). No bug.
- The helper can read `/var/lib/extrausers/shadow` and `/var/lib/extrausers/gshadow` (`polkit_agent.go:106-107`), but those are global system auth databases read-only, not snap-scoped paths.
- Seccomp adds `bind` and `socket AF_NETLINK - NETLINK_AUDIT` (`polkit_agent.go:132-136`).

**Reasoning:** The interface is about acting as a polkit agent, which is a client role with no bus-name ownership. The only snap-instance-specific element is the helper signal peer label, which correctly uses `@{SNAP_INSTANCE_NAME}`. The shared auth databases and polkitd are system-wide resources, so parallel instances do not create snap-instance collisions in the interface code (polkit honoring one registered agent per session at runtime is an operational concern, not a snapd-level one).

**Verification:** No verification has yet been done.

### snap-refresh-observe
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Observability/Diagnostics

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
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Snapd/Policy Management

**Code analysis:**
- Slot is provided by core only (`ubuntu_pro_control.go:30-36`: `slot-snap-type: [core]`), with implicit slot on classic (line 128). The plug base declaration sets `allow-installation: false` (`ubuntu_pro_control.go:24-28`).
- The connected-plug AppArmor (`ubuntu_pro_control.go:38-122`) is a **system-bus** D-Bus client (`#include <abstractions/dbus-strict>`, line 41): `dbus (send)` for ObjectManager.GetManagedObjects, Manager Attach/Detach, Services Enable/Disable, and Introspectable (all with `peer=(name=com.canonical.UbuntuAdvantage)`), plus `dbus (receive)` of PropertiesChanged/InterfacesAdded/Removed with `peer=(label=unconfined)`.
- **It owns no D-Bus name.** No `dbus (bind)`, no `DBusPermanentSlot`, no `<allow own>`; `com.canonical.UbuntuAdvantage` appears only as a `send` peer destination (`name=...`), which is client addressing. This is a `commonInterface` with only `connectedPlugAppArmor` set (`ubuntu_pro_control.go:124-132`), so there is no slot-side code.
- The only filesystem access is `/etc/ubuntu-advantage/uaclient.conf r,` (line 43) — a fixed system path, read-only, not snap-name-derived. No mount or shared-memory rules; no `InstanceName()`/`SnapName()`/`ExpandSnapVariables()`/`LabelExpression()`.

**Reasoning:** Ubuntu Pro control is a system-bus client interface to a single shared system daemon. Parallel instances are independent clients; the interface owns no bus name and the one file rule is a read-only system path, so there is no snapd-level collision. The slot side is core-only, so parallel app-provided slots are not possible.

**Verification:** No verification has yet been done.

### xdg-portal-permission-store
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** Desktop/Graphics/Media Integration

**Code analysis:**
- Slot is provided by core only (`xdg_portal_permission_store.go:30-36`: `slot-snap-type: [core]`), with implicit slot on core and classic (lines 69-70). The plug base declaration sets `allow-installation: false` (`xdg_portal_permission_store.go:24-28`).
- The connected-plug AppArmor (`xdg_portal_permission_store.go:38-63`) is a **session-bus** D-Bus client (`#include <abstractions/dbus-session-strict>`, line 41): `dbus (receive, send)` to the fixed object path `/org/freedesktop/impl/portal/PermissionStore` via `org.freedesktop.impl.portal.PermissionStore`, `DBus.Properties`, `DBus.Peer`, `DBus.Introspectable`, all `bus=session`, `peer=(label=unconfined)`.
- **It owns no D-Bus name.** No `dbus (bind)`, no `DBusPermanentSlot`, no `<allow own>`; access is by object path with `peer=(label=unconfined)`, no `name=` ownership. This is a `commonInterface` with only `connectedPlugAppArmor` set (`xdg_portal_permission_store.go:65-74`), so there is no slot-side code.
- No `InstanceName()`/`SnapName()`/`ExpandSnapVariables()`/`LabelExpression()`, no hardcoded `/var/snap/<name>/` paths, no mount/seccomp/udev.

**Reasoning:** This is a shared portal service on the session bus. Multiple parallel instances can safely access the same PermissionStore at a fixed object path as concurrent clients; the permission data is held by the xdg-desktop-portal daemon, and the interface owns no bus name, so there is no snapd-level collision. The slot side is core-only, so parallel app-provided slots are not possible.

**Verification:** No verification has yet been done.

### kernel-firmware-control
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** System Control/Privileged Capability

**Code analysis:**
- Slot is provided by core only (lines 31-36), with implicit slots on core and classic (lines 48-49).
- AppArmor rules only grant write access to `/sys/module/firmware_class/parameters/path` (line 41).
- No D-Bus, sockets, mounts, or snap-instance-specific paths are involved.

**Reasoning:** The interface controls a global kernel firmware search path parameter. Multiple instances get the same permission, and the code does not include any snap-instance-dependent logic.

**Verification:** No verification has yet been done.

### ion-memory-control
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** System Control/Privileged Capability

**Code analysis:**
- Slot is provided by core only (lines 24-30), with an explicit plug-installation restriction (lines 32-36).
- AppArmor rules grant access to `/dev/ion` (lines 38-44).
- UDev tags the `ion` device (lines 46-48).
- No snap-instance-specific names, sockets, or mounts are involved.

**Reasoning:** The Android ION allocator is a global device interface. Multiple parallel instances can access the same device node without any snapd policy collision in the interface code.

**Verification:** No verification has yet been done.

### nvme-control
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** System Control/Privileged Capability

**Code analysis:**
- Slot is provided by core only (`nvme_control.go:40-46`: `slot-snap-type: [core]`), with an explicit plug-installation restriction `allow-installation: false` (`nvme_control.go:34-38`). Note the interface sets `implicitOnClassic: true` (`nvme_control.go:88`) but has NO `implicitOnCore`, so the slot is not implicitly present on Ubuntu Core.
- AppArmor grants access to NVMe config files `/etc/nvme/*` (lines 50-52), sysfs (lines 55-58), the fabrics character device `/dev/nvme-fabrics` (line 63), and NVMe controller/namespace nodes `/dev/nvme[0-9]*`/`/dev/nvme[0-9]*n[0-9]*` (lines 66-67).
- UDev tags NVMe and nvme-fabrics devices (`nvme_control.go:70-73`).
- KMod module loading hints are declared for `nvme` and `nvme-tcp` (`nvme_control.go:79-82`).
- **SNAP_NAME vs INSTANCE_NAME:** no snap-name interpolation — all paths are fixed device/sysfs/config paths. No D-Bus. No bug.

**Reasoning:** NVMe is global storage hardware and the interface is device-path based with no snap-instance naming. Parallel installs can access the same controllers/namespaces from separate snaps without snapd policy collision; the shared devices are mediated by the kernel.

**Verification:** No verification has yet been done.

### sd-control
**Status:** Plug-side: COMPATIBLE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** System Control/Privileged Capability

**Code analysis:**
- Slot is provided by core only (lines 30-35), with implicit slots on core and classic (lines 95-96).
- AppArmor/UDev permissions are conditionally added when the plug’s `flavor` is `dual-sd` (lines 60-86).
- Access is to `/dev/DualSD` and its corresponding udev tag; there are no snap-instance-specific paths.
- The interface uses plug attributes to control scope rather than snap naming.

**Reasoning:** The interface is hardware/flavor specific, not instance specific. Parallel installs just reuse the same hardware access if the plug flavor matches.

**Verification:** No verification has yet been done.

### kernel-module-control
**Status:** Plug-side: COMPATIBLE EXCEPT FOR SHARED RESOURCE. Slot-side: N/A (system/core-provided slot; no parallel app slot providers in scope).

**Type:** System Control/Privileged Capability

**Code analysis:**
- Capability-based module management (insmod/rmmod/lsmod) and read access to `/sys/module/`.
- No D-Bus name ownership and no snap-instance-specific filesystem pathing.

**Reasoning:** This grants shared kernel module management authority (`sys_module`). There is no snap-instance naming collision in policy, but parallel instances can interfere by loading/unloading shared kernel modules.

**Verification:** Passed on noble. Test at `tests/main/interfaces-kernel-module-control`.

### gpio-control
**Status:** Plug-side: NOT COMPATIBLE. Slot-side: N/A (system/core/gadget-provided slot; no parallel app slot providers in scope).

**Type:** System Control/Privileged Capability

**Code analysis:**
- This interface grants broad control of all GPIO pins and device nodes (`/sys/class/gpio`, `/sys/devices/platform/**/gpio`, `/dev/gpiochip[0-9]*`) (lines 43-57).
- The comments explicitly describe the interface as privileged and potentially impacting the system and other snaps (lines 25-27, 44-45).

**Reasoning:** Plug-side access is not parallel-safe in practice because it gives global write control over shared GPIO lines and gpiochip devices. Two instances can reconfigure pin direction/value/edge for the same hardware and interfere immediately. Slot-side is core-only and not an app-provider parallel-install scenario.

**Verification:** No verification has yet been done.
