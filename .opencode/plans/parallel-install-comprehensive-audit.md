# Snapd Parallel Install Compatibility: Comprehensive Audit

**Date**: June 2026  
**Status**: Consolidated from interface audit + runtime verification  
**Last revised**: June 23, 2026 (corrected after spread verification)

---

## Framework: Plug-side vs Slot-side Compatibility

A critical distinction that must be made for every interface:

- **Plug-side (consumer)**: A snap that uses a resource provided by another snap or the
  system. Example: a snap reading audio via pulseaudio, or reading from Avahi.
- **Slot-side (provider)**: A snap that provides a resource to other snaps. Example: a
  snap running a PulseAudio server, or providing a D-Bus service.

For parallel installs, the relevant question is almost always about **plug-side**
compatibility -- can two instances of the same snap simultaneously consume a resource?
Slot-side conflicts (two instances trying to own the same D-Bus name) are real but
rarely the use case for parallel installs.

### Classification Key

- **COMPATIBLE**: Parallel instances work correctly for plug-side usage. Verified by test.
- **COMPATIBLE (plug-side only)**: Plug-side works; slot-side has conflicts (e.g., D-Bus
  name ownership). Most snaps only use the plug side.
- **POTENTIALLY COMPATIBLE**: Should work but has minor caveats or was not fully verified.
- **NOT COMPATIBLE**: Fundamental issue that prevents parallel instances from working
  correctly even for plug-side usage.

---

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

---

## Additional Interface Analyses

### custom-device
**Status: POTENTIALLY COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- The slot definition is gadget-driven and intentionally open-ended.
- `custom-device` defaults the slot attribute to the slot name if unspecified.
- Connection approval is keyed on the plug attribute matching the slot value.
- The interface validates paths and udev rules carefully, but it does not inject snap-instance-specific naming.

**Reasoning**: there is no generic snap-instance collision visible in the interface code itself, but the effective behavior is entirely gadget-defined.

**Verification:** No verification has yet been done.

### confdb
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Auto-connection is driven by publisher account matching.
- The plug requires explicit `account` and `view` attributes.
- Plugs can read/write confdb data and may use the optional `custodian` role.
- No instance-name or snap-name scoping is used in the interface itself.

**Reasoning**: parallel instances of the same snap will generally behave like two clients using the same confdb view, so this is reasonable for parallel installs.

**Verification:** No verification has yet been done.

### raw-volume
**Status: POTENTIALLY COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- The slot must point at a concrete disk partition.
- The accepted device paths are explicit partition nodes only.
- AppArmor and udev rules are generated from the slot path, not from instance naming.
- Auto-connect is allowed only for declarations, but the slot is still tied to the chosen partition.

**Reasoning**: this is not a snap-instance collision problem so much as a device-selection problem. Parallel instances are only safe if they intentionally bind to different partitions.

**Verification:** No verification has yet been done.

### opengl
**Status: POTENTIALLY COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Access is to GPU driver stacks, DRM render nodes, and vendor libraries.
- The rules are broad and intentionally allow multiple GPUs / render nodes.
- The interface uses instance-agnostic paths and does not key access on snap instance identity.
- Some vendor-specific state is shared, but the code treats it as normal multi-client GPU access.

**Reasoning**: the interface reads like a shared-client GPU interface rather than a per-snap singleton.

**Verification:** No verification has yet been done.

### jack1
**Status: POTENTIALLY COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Access is to JACK1 shared memory endpoints under `/dev/shm/jack-*`.
- The rules are based on JACK's server/client naming convention, not on snap instance names.
- There is no snap-specific namespace logic in the interface.

**Reasoning**: two instances behave like two JACK clients on the same user session. That is usually fine, but the interface shares the same JACK namespace and therefore is not isolated by snap instance.

**Verification:** No verification has yet been done.

### pcscd
**Status: POTENTIALLY COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Client access is via `/run/pcscd/pcscd.comm`.
- The interface also grants read access to OpenSC config files.
- No singleton service ownership or instance-specific pathing is involved.

**Reasoning**: this is a straightforward daemon client interface. Parallel installs should behave like concurrent clients of the same PC/SC daemon.

**Verification:** No verification has yet been done.

### network
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Client-side network access only.
- Uses `systemd-resolved` and `systemd` D-Bus APIs as a client.
- No snap-instance-specific pathing or service ownership.
- The seccomp snippet is generic networking support, not a singleton resource.

**Reasoning**: this is the canonical shared-client networking case.

**Verification:** No verification has yet been done.

### network-manager-observe
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- The interface only observes NetworkManager state and settings.
- It uses D-Bus as a client and subscribes to signals; it does not own the NetworkManager bus name.
- The code adjusts the peer label depending on classic vs confined NetworkManager, but not on snap instance identity.

**Reasoning**: multiple instances are just multiple observers of the same NetworkManager service.

**Verification:** No verification has yet been done.

### openvswitch
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Access is to Open vSwitch management sockets such as `/run/openvswitch/db.sock` and `*.mgmt`.
- The interface is client-side and does not define a singleton service.
- The rules are broad enough to cover per-bridge sockets and runtime control sockets.

**Reasoning**: this is a socket client interface. Parallel instances should be able to talk to the same OVS daemon concurrently.

**Verification:** No verification has yet been done.

### libvirt
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Access is to libvirt sockets (`/run/libvirt/libvirt-sock*`) plus a few config paths.
- The seccomp rules allow socket operations needed by libvirt clients.
- There is no instance-name scoping or service-name ownership.

**Reasoning**: parallel instances should behave like ordinary libvirt clients, sharing the daemon socket.

**Verification:** No verification has yet been done.

### docker
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Access is to the Docker daemon socket (`/run/docker.sock` or `/var/run/docker.sock`).
- The interface is explicit about privileged socket access, but it is still client-side.
- No snap-instance-specific naming is involved.

**Reasoning**: multiple instances can act as concurrent Docker clients. The risk is operational privilege, not snap-instance collision.

**Verification:** No verification has yet been done.

### podman
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Access is to both the system Podman socket and the rootless user socket.
- The AppArmor rules are socket-path based and not instance-scoped.
- The interface is client-side; it does not own a service name.

**Reasoning**: parallel instances should work as concurrent Podman clients.

**Verification:** No verification has yet been done.

### can-bus
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- The interface grants CAN network access and allows AF_CAN sockets.
- No instance-specific pathing or ownership is present.
- The kernel handles CAN bus concurrency; the interface is just a client to that medium.

**Reasoning**: parallel instances can use the CAN bus at the same time, but they share the same underlying hardware bus.

**Verification:** No verification has yet been done.

### kernel-crypto-api
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Access is to the Linux kernel crypto API through AF_ALG and NETLINK_CRYPTO.
- The implementation explicitly notes the API is intended for any process and requires no special privileges.
- No instance-specific paths or service names are involved.

**Reasoning**: this is a shared kernel service interface. Multiple instances should behave like concurrent clients of the same kernel crypto subsystem.

**Verification:** No verification has yet been done.

### avahi-control
**Status: COMPATIBLE (plug-side only; code analysis -- not yet verified)**

**Code analysis:**
- The interface explicitly imports and extends `avahi-observe` behavior.
- Plug-side rules only send to the Avahi server and manage entry groups; they do not own the Avahi bus name.
- Slot-side rules are only applied when running as an application snap, and the code handles the system-vs-snap Avahi distinction.
- D-Bus ownership is only relevant for a snap acting as the Avahi service.

**Reasoning**: a parallel client snap using `avahi-control` should behave like any other client. A parallel provider snap would still be constrained by the singleton Avahi service name.

**Verification:** No verification has yet been done.

### fwupd
**Status: NOT COMPATIBLE (slot-side singleton; code analysis -- not yet verified)**

**Code analysis:**
- Permanent slot rules bind `org.freedesktop.fwupd` on the system bus.
- The slot side carries extensive privileged access to firmware, EFI variables, TPM, MEI, NVMe, USB, and systemd D-Bus control paths.
- The plug side uses D-Bus as a client to query/stop fwupd and inspect systemd state.
- The interface is explicitly a service interface with privileged system access.

**Reasoning**: parallel instances cannot both act as the fwupd service. As a client interface, multiple instances should be fine, but the service-provider side is a hard singleton.

**Verification:** No verification has yet been done.

### maliit
**Status: NOT COMPATIBLE (slot-side singleton; code analysis -- not yet verified)**

**Code analysis:**
- The slot binds the well-known session-bus name `org.maliit.server`.
- After address negotiation, communication moves to a private per-client Unix socket under `@/tmp/maliit-server/dbus-*`.
- The plug and slot both use D-Bus and per-client socket rules, but the address service itself is the singleton.
- The code is explicitly structured around one server brokering individual client channels.

**Reasoning**: parallel consumers are fine, but parallel providers cannot both own the Maliit server name.

**Verification:** No verification has yet been done.

### mpris
**Status: POTENTIALLY COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- The slot binds `org.mpris.MediaPlayer2.<name>` based on a `name` attribute, defaulting to `SNAP_INSTANCE_NAME`.
- The code explicitly warns that snaps using this interface must adjust themselves for parallel installs.
- The plug side discovers and talks to the player over the session bus.
- The implementation is careful about per-snap naming, but the well-known bus name still represents a provider identity.

**Reasoning**: parallel clients are fine, but parallel providers can collide unless the instance-aware naming is handled correctly.

**Verification:** No verification has yet been done.

### pipewire
**Status: COMPATIBLE (plug-side only; code analysis -- not yet verified)**

**Code analysis:**
- The plug accesses PipeWire sockets at `/run/user/[0-9]*/pipewire-[0-9]` for classic/system slots.
- For app-provided slots, the plug uses instance-aware paths:
  - `/run/user/[0-9]*/snap.<SLOT_INSTANCE_NAME>/pipewire-[0-9]` (line 50, 93: uses `slot.Snap().InstanceName()`)
  - `/var/snap/<SLOT_INSTANCE_NAME>/common/pipewire-[0-9]` for system mode (line 52, 96: uses `slot.Snap().InstanceName()`)
- The slot provider creates sockets at `/run/user/[0-9]*/pipewire-[0-9]` and `/run/user/[0-9]*/pipewire-[0-9]-manager` (lines 68-69).
- No D-Bus name ownership in this interface.
- Shared memory via `shmctl` syscall (line 56, 80) is used for audio IPC, same pattern as pulseaudio.

**Reasoning**: The plug-side correctly uses `slot.Snap().InstanceName()` for instance-aware path resolution when connecting to an app-provided slot. Multiple parallel plug instances connecting to the same PipeWire server (system or snap-provided) is the normal multi-client audio pattern. The slot-side would conflict if two parallel instances tried to create sockets at the same runtime path, but that's the expected slot-side singleton pattern.

**Verification:** No verification has yet been done.

### cups (provider/slot-side issue)
**Status: NOT COMPATIBLE (slot-side); COMPATIBLE (plug-side)**

**Code analysis:**
- The plug accesses a fixed socket at `/var/cups/cups.sock` (line 77).
- The slot declares a `cups-socket-directory` attribute that must be under `$SNAP_COMMON` or `$SNAP_DATA` (lines 115-116).
- **BUG IDENTIFIED** at line 130: `validateCupsSocketDirSlotAttr` calls `snapInfo.ExpandSnapVariables(cupsdSocketSourceDir)` where `snapInfo` is `slot.Snap()`. This uses `ExpandSnapVariables` which, for `$SNAP_COMMON`, expands using `SnapName()` not `InstanceName()` when using `PerspectiveSelf` (the default).
- This means if a slot snap `cups-provider_foo` declares `cups-socket-directory: $SNAP_COMMON/cups`, it expands to `/var/snap/cups-provider/common/cups` instead of `/var/snap/cups-provider_foo/common/cups`.
- The mount entry (lines 201-205) uses this incorrectly-expanded path, causing the bind mount to point to the wrong directory for parallel instances.
- The AppArmor rules at line 170 also use this path, so the plug gets rules for the wrong location.

**Reasoning**: The slot-side path expansion bug means parallel instances of a cups provider snap will all try to use the same socket directory (the base snap name's directory), not their instance-specific directories. The plug-side is fine since it just accesses `/var/cups/cups.sock` which is bind-mounted.

**Verification:** No verification has yet been done. This bug was previously identified in the audit and is awaiting a code fix.

### serial-port
**Status: COMPATIBLE (device-specific; code analysis -- not yet verified)**

**Code analysis:**
- Slots are provided by core or gadget snaps only (lines 41-43), not by application snaps.
- The slot requires a `path` attribute pointing to a specific device node (e.g., `/dev/ttyUSB0`) or a udev symlink with USB vendor/product attributes.
- AppArmor rules grant access to the specific device path from the slot (line 179: `cleanedPath`), not based on snap instance names.
- UDev rules tag the specific device by kernel name or USB vendor/product (lines 200-210).
- No snap-instance-specific paths are involved; the interface is purely device-path-based.
- No D-Bus, no shared memory, no sockets that could conflict.

**Reasoning**: The serial-port interface grants access to a specific physical device declared in the slot. Parallel instances of a plug snap can all connect to the same serial-port slot and access the same device. Whether this is safe depends on the application: two processes reading/writing the same serial port would interfere at the protocol level, but that's an application concern, not a snapd interface conflict. The interface itself has no instance-naming issues.

**Verification:** No verification has yet been done.

### hidraw
**Status: COMPATIBLE (device-specific; code analysis -- not yet verified)**

**Code analysis:**
- Slots are provided by core or gadget snaps only (lines 39-41), not by application snaps.
- The slot requires a `path` attribute pointing to a specific hidraw device node (e.g., `/dev/hidraw0`) or a udev symlink with USB vendor/product attributes.
- Device node pattern: `/dev/hidraw[0-9]{1,3}` (line 66).
- Udev symlink pattern: `/dev/hidraw-[a-z0-9]+` (line 71).
- AppArmor rules grant access to the specific device path from the slot (line 153: `cleanedPath`), or a broad pattern `/dev/hidraw[0-9]{,[0-9],[0-9][0-9]}` when using USB attributes (line 143).
- UDev rules tag the specific device by kernel name or USB vendor/product (lines 182-187).
- No snap-instance-specific paths are involved; the interface is purely device-path-based.
- No D-Bus, no shared memory, no sockets.

**Reasoning**: Like serial-port, the hidraw interface grants access to a specific physical HID device declared in the slot. The interface is device-path-based with no instance-naming involved. Parallel instances of a plug snap can all connect to the same hidraw slot and access the same device. Two processes accessing the same hidraw device would interfere at the HID protocol level, but that's an application concern, not a snapd interface conflict.

**Verification:** No verification has yet been done.

### i2c
**Status: COMPATIBLE (device-specific; code analysis -- not yet verified)**

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

**Reasoning**: The i2c interface grants access to a specific I2C bus controller declared in the slot. The interface is device-path-based with no instance-naming involved. Parallel instances of a plug snap can all connect to the same i2c slot and access the same bus. Whether concurrent access is safe depends on the I2C devices on the bus and the application protocol; the kernel's I2C subsystem handles bus arbitration but not higher-level conflicts. The interface itself has no instance-naming issues.

**Verification:** No verification has yet been done.

### media-control
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 32-33), with implicit slots on core and classic (lines 55-56).
- AppArmor rules grant access to `/dev/media[0-9]*` and `/dev/v4l-subdev[0-9]*` (lines 39-43).
- UDev rules tag media and v4l-subdev devices by subsystem and kernel name (lines 46-49).
- No snap-instance-specific paths are involved; the interface is purely device-path-based.
- No D-Bus, no shared memory, no sockets.

**Reasoning**: The media-control interface grants access to kernel media controller devices for configuring media hardware subsystems. These are numbered global hardware resources. Multiple parallel instances accessing the same media devices would share the hardware, similar to the camera interface. The interface has no instance-naming issues.

**Verification:** No verification has yet been done.

### gsettings
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 27-28), with implicit slot on classic (line 53).
- AppArmor rules grant access to the user's dconf database:
  - `/{,var/}run/user/*/dconf/user` (line 41)
  - `@{HOME}/.config/dconf/user` (line 42)
- D-Bus rules allow send/receive to `ca.desrt.dconf.Writer` on the session bus (lines 43-46).
- The interface uses `#include <abstractions/dconf>` for standard dconf access patterns.
- No snap-instance-specific paths; all paths are user-session-scoped, not snap-scoped.
- No D-Bus name ownership (client only).

**Reasoning**: The gsettings interface grants access to the user's global dconf/gsettings database. This is explicitly a shared per-user resource, not per-snap. Multiple parallel instances accessing the same gsettings database is the intended behavior (same as multiple different snaps). The interface has no instance-naming issues since it's designed for shared access to user settings.

**Verification:** No verification has yet been done.

### lxd
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot installation is denied by default, requires snap-declaration (lines 26-28).
- AppArmor rules grant access to the LXD socket at `/var/snap/lxd/common/lxd/unix.socket` (line 35).
- Seccomp rules allow `AF_NETLINK` socket creation (line 42).
- The socket path is hardcoded to the `lxd` snap's location, not parameterized by instance name.
- No D-Bus, no shared memory.
- This is a client interface to the LXD daemon.

**Reasoning**: The lxd interface grants client access to the LXD daemon's Unix socket. Multiple parallel instances of a plugging snap would all connect to the same LXD daemon as concurrent clients, which is normal socket-client behavior. The LXD daemon manages concurrent connections. No instance-naming issues exist since this is purely client access to a fixed socket path.

**Verification:** No verification has yet been done.

### microceph
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot installation is denied by default, requires snap-declaration (lines 25-28).
- AppArmor rules grant access to the MicroCeph socket at `/var/snap/microceph/common/state/control.socket` (line 34).
- Seccomp rules allow `AF_NETLINK` socket creation (line 40).
- The socket path is hardcoded to the `microceph` snap's location, not parameterized by instance name.
- No D-Bus, no shared memory.
- This is a client interface to the MicroCeph daemon.

**Reasoning**: The microceph interface grants client access to the MicroCeph control socket. Multiple parallel instances of a plugging snap would all connect to the same MicroCeph daemon as concurrent clients. The daemon manages concurrent connections. No instance-naming issues since this is client access to a fixed socket path.

**Verification:** No verification has yet been done.

### microovn
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot installation is denied by default, requires snap-declaration (lines 25-28).
- AppArmor rules grant access to the MicroOVN socket at `/var/snap/microovn/common/state/control.socket` (line 34).
- Seccomp rules allow `AF_NETLINK` socket creation (line 40).
- The socket path is hardcoded to the `microovn` snap's location, not parameterized by instance name.
- No D-Bus, no shared memory.
- This is a client interface to the MicroOVN daemon.

**Reasoning**: The microovn interface grants client access to the MicroOVN control socket. Multiple parallel instances of a plugging snap would all connect to the same MicroOVN daemon as concurrent clients. The daemon manages concurrent connections. No instance-naming issues since this is client access to a fixed socket path.

**Verification:** No verification has yet been done.

### appstream-metadata
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 35-40), with implicit slot on classic (line 126).
- AppArmor rules grant read access to AppStream metadata under `/usr/share/{metainfo,appdata,app-info,swcatalog}` and apt list metadata (lines 47-61).
- Mount rules bind host metadata directories into the snap namespace, and those paths are based on host filesystem locations rather than snap names (lines 79-120).
- No snap-instance-specific names are used.

**Reasoning**: AppStream metadata is host-wide read-only documentation and metadata. Parallel instances just read the same data and the mount logic is based on host paths, not instance-specific paths.

**Verification:** No verification has yet been done.

### bool-file
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slots are provided by core or gadget snaps only (lines 34-40).
- Slot validation accepts only LED brightness and GPIO value paths (lines 76-92).
- AppArmor rules are built from the dereferenced slot path, so the connected plug mediates the exact file the slot identifies (lines 106-125).
- For GPIO slots, the permanent-slot rules expose export/unexport and direction handling (lines 94-103).
- No snap-instance-specific paths are involved.

**Reasoning**: This is a specific-file interface with path validation. Parallel installs can use the same or different hardware-backed paths based on the slot; the code doesn’t key anything off snap instance names.

**Verification:** No verification has yet been done.

### cifs-mount
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 24-29), with implicit slots on core and classic (lines 71-72).
- AppArmor and seccomp permissions are for mount/umount of CIFS filesystems (lines 32-65).
- The policy explicitly uses both `SNAP_NAME` and `SNAP_INSTANCE_NAME` for writable mount targets, to cover parallel installs (lines 45-56).
- No D-Bus or sockets are involved.

**Reasoning**: The interface is already written to handle parallel-instance mount targets explicitly. The mount rules include both base and instance names, so there is no obvious instance collision in the code.

**Verification:** No verification has yet been done.

### empty
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- This interface intentionally contributes no permissions.
- `BeforeConnectPlug()` and `BeforeConnectSlot()` only mutate plug/slot attributes (lines 65-85).
- AppArmor connection handlers are no-ops (lines 87-93).
- `AutoConnect()` always returns true (lines 95-97).
- No snap-instance-specific paths are used.

**Reasoning**: The interface is a no-op sandbox for testing. It doesn’t introduce any resource conflicts or instance-scoped policy.

**Verification:** No verification has yet been done.

### fuse-support
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 28-33), with implicit slots on core and classic except old Ubuntu 14.04 (lines 100-101).
- AppArmor grants access to `/dev/fuse`, `sys_admin`, and mount targets under snap-specific writable directories (lines 43-92).
- The mount rules explicitly use `SNAP_INSTANCE_NAME` for per-user home snap directories, and `SNAP_NAME`/`SNAP_INSTANCE_NAME` for system snap directories (lines 67-77).
- UDev tags the `fuse` device (line 94).
- No hardcoded snap-instance path conflicts are visible.

**Reasoning**: FUSE support is deliberately instance-aware in the mount rules. The interface is one of the examples that already accounts for parallel instances via `SNAP_INSTANCE_NAME` and `SNAP_NAME`.

**Verification:** No verification has yet been done.

### nfs-mount
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 24-29), with implicit slots on core and classic (lines 85-86).
- AppArmor and seccomp permissions are for NFS mount/umount operations (lines 32-79).
- The policy explicitly uses both `SNAP_NAME` and `SNAP_INSTANCE_NAME` for writable mount targets, covering parallel installs (lines 45-61).
- No D-Bus or sockets are involved.

**Reasoning**: Like cifs-mount, this interface is already instance-aware in its mount target rules. Parallel instances do not create a mount-path collision in the code.

**Verification:** No verification has yet been done.

### optical-drive
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 32-43), with implicit slot on classic only (line 107).
- AppArmor grants read access to optical drive device nodes and supporting SCSI/udev files; optional write access is gated by a plug attribute (lines 45-54, 85-99).
- UDev rules tag the relevant SCSI device types (lines 56-63).
- No snap-instance-specific paths are used.

**Reasoning**: Optical drives are global hardware devices. The interface is attribute/device based, not instance-name based.

**Verification:** No verification has yet been done.

### physical-memory-observe
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 24-29), with implicit slots on core and classic (lines 49-50).
- AppArmor grants read-only `/dev/mem` and `/proc/*/pagemap` access (lines 32-41).
- UDev tags the `mem` device (line 43).
- No snap-instance-specific paths are involved.

**Reasoning**: Read-only physical memory observation is global system state, not snap-instance state. The interface code does not introduce any parallel-install collision point.

**Verification:** No verification has yet been done.

### pkcs11
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- The slot provides a `pkcs11-socket` attribute and must live under `/run/p11-kit` (lines 71-93).
- `BeforePrepareSlot()` validates the path and disallows AppArmor-regex characters (lines 95-105).
- AppArmor and Seccomp rules use the socket path as supplied by the slot (lines 107-155).
- The interface is path-driven by the slot, not by snap instance names.

**Reasoning**: This is a named socket interface whose path is set by the slot, not by the snap instance. Parallel instances talk to the same p11-kit service or different sockets as declared by the slot, so there is no snap-instance collision in the code.

**Verification:** No verification has yet been done.

### system-packages-doc
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 31-36), with implicit slot on classic (line 204-205).
- AppArmor grants read access to documentation directories under `/usr/share`, `/usr/local/share`, and `/var/lib/snapd/hostfs`-backed locations (lines 39-53).
- Mount rules bind host documentation into the snap namespace (lines 59-196).
- The code uses host paths and generic doc paths; there are no snap-instance-specific names.

**Reasoning**: Documentation files are shared read-only host resources. Parallel instances can all mount/read them, and the policy is path-based rather than instance-name-based.

**Verification:** No verification has yet been done.

### display-control
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 34-39), with implicit slot on classic (line 137).
- AppArmor rules cover backlight and keyboard backlight sysfs nodes plus UPower and GNOME Settings Daemon D-Bus APIs (lines 46-91).
- The interface discovers backlight paths dynamically via sysfs symlinks (lines 97-127).
- No snap-instance-specific paths are involved.

**Reasoning**: Display/backlight control is global device state. Parallel instances can adjust the same display settings, and the policy code does not key anything off snap instance names.

**Verification:** No verification has yet been done.

### desktop-legacy
**Status: COMPATIBLE (code analysis -- not yet verified)**

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

**Reasoning**: The desktop-legacy interface grants access to shared desktop services (accessibility, input methods, notifications, etc.). These are per-user-session resources designed for concurrent access by multiple applications. Multiple parallel instances accessing the same desktop services is the intended behavior. The `getDesktopFileRules()` call correctly uses the snap's identity. No instance-naming issues.

**Verification:** No verification has yet been done.

### gconf
**Status: COMPATIBLE (code analysis -- not yet verified)**

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

**Reasoning**: The gconf interface grants access to the user's global GConf database. This is explicitly documented as "a global database for GNOME desktop and application settings" with "no application isolation." Multiple parallel instances accessing the same GConf database is the intended behavior (same as multiple different snaps). No instance-naming issues.

**Verification:** No verification has yet been done.

### login-session-control
**Status: COMPATIBLE (code analysis -- not yet verified)**

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

**Reasoning**: The login-session-control interface grants D-Bus client access to systemd-logind for managing login sessions. Multiple parallel instances would all interact with the same logind service as concurrent D-Bus clients. The logind service manages concurrent access. No instance-naming issues since this is client access to system services.

**Verification:** No verification has yet been done.

### login-session-observe
**Status: COMPATIBLE (code analysis -- not yet verified)**

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

**Reasoning**: The login-session-observe interface grants read-only access to system login/session information. Multiple parallel instances would read the same system-wide login state, which is the intended behavior. No instance-naming issues since this is purely observational access to system state.

**Verification:** No verification has yet been done.

### screen-inhibit-control
**Status: COMPATIBLE (code analysis -- not yet verified)**

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

**Reasoning**: The screen-inhibit-control interface allows snaps to inhibit screen savers. The D-Bus rules use `LabelExpression()` which correctly identifies snap instances. Multiple parallel instances can independently inhibit/uninhibit screen savers through separate D-Bus calls. No instance-naming issues.

**Verification:** No verification has yet been done.

### time-control
**Status: COMPATIBLE (code analysis -- not yet verified)**

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

**Reasoning**: The time-control interface grants access to system time control via D-Bus, syscalls, and device nodes. Multiple parallel instances would all have the same capability to modify system time, which is inherently a system-wide singleton resource. The kernel and systemd manage concurrent access. No instance-naming issues since this is access to global system state.

**Verification:** No verification has yet been done.

---

## Audio Interfaces

### alsa
**Status: COMPATIBLE**

**Code analysis:**
- AppArmor rules grant access to `/dev/snd/` and `/dev/snd/*` (read/write)
- UDev rules match sound devices by kernel name patterns (`c116:[0-9]*`, `+sound:card[0-9]*`)
- No D-Bus usage, no shared memory, no instance-specific paths
- Multiple instances access the same physical devices, which is the intended behavior for
  audio (the kernel/ALSA manages concurrent access)

**Reasoning**: Audio devices are global hardware resources. Multiple snaps (parallel or
not) accessing `/dev/snd/*` is already the normal case. The AppArmor rules are purely
device-path-based and don't reference snap names at all.

**Verification:**
```diff
diff --git a/tests/main/interfaces-alsa/task.yaml b/tests/main/interfaces-alsa/task.yaml
index a1f206c1c0..0655c1adc7 100644
--- a/tests/main/interfaces-alsa/task.yaml
+++ b/tests/main/interfaces-alsa/task.yaml
@@ -20,12 +20,18 @@ prepare: |
     echo "Given a snap declaring a plug on the alsa interface is installed"
     #shellcheck source=tests/lib/snaps.sh
     . "$TESTSLIB"/snaps.sh
+    snap set system experimental.parallel-instances=true
     install_generic_consumer alsa

 restore: |
+    snap remove --purge generic-consumer_foo || true
+    snap set system experimental.parallel-instances=null
     rm -f /dev/snd/mysnd-dev

 execute: |
+    #shellcheck source=tests/lib/snaps.sh
+    . "$TESTSLIB"/snaps.sh
+
     echo "When the plug is connected"
     snap connect generic-consumer:alsa

@@ -91,5 +97,23 @@ execute: |
         rm /run/udev/data/c116:0
     fi

+    echo "When a parallel install of the snap is installed"
+    install_generic_consumer_as alsa generic-consumer_foo
+    snap connect generic-consumer_foo:alsa
+
+    echo "Then the parallel snap is able to access snd devices"
+    mkdir -p /dev/snd
+    generic-consumer_foo.cmd touch /dev/snd/mysnd-dev
+    echo "mysnd-dev-content" | tee /dev/snd/mysnd-dev
+    generic-consumer_foo.cmd cat /dev/snd/mysnd-dev | MATCH mysnd-dev-content
+    generic-consumer_foo.cmd rm /dev/snd/mysnd-dev
+
+    echo "When the original snap is removed"
+    snap remove --purge generic-consumer
+
+    echo "Then the parallel snap can still access snd devices"
+    generic-consumer_foo.cmd touch /dev/snd/mysnd-dev
+    generic-consumer_foo.cmd rm /dev/snd/mysnd-dev
+
     # TODO: extend test to check /var/lib/alsa with plug disconnected when
     # https://bugs.launchpad.net/snapd/+bug/1694281 is fixed
```
- **Result**: PASSED on noble.

---

### pulseaudio
**Status: COMPATIBLE (plug-side only)**

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

**Reasoning**: PulseAudio is designed for multiple simultaneous clients. The shared
memory segments (`pulse-shm-*`) are created by the PA server and shared with all
connected clients -- having two snap instances connect as clients is no different from
having two different snaps connect. Slot-side (running multiple PA servers) would
conflict, but that's not a parallel-install concern.

**Previous audit errors**:
- Claimed "Global D-Bus name binding" -- INCORRECT. No D-Bus is used.
- Claimed "NOT COMPATIBLE" -- INCORRECT. Plug-side works fine.

**Verification:**
```diff
diff --git a/tests/main/interfaces-pulseaudio/task.yaml b/tests/main/interfaces-pulseaudio/task.yaml
@@ -15,6 +15,7 @@ environment:
     PLAY_FILE: "/snap/test-snapd-pulseaudio/current/usr/share/sounds/alsa/Noise.wav"

 prepare: |
+    snap set system experimental.parallel-instances=true
     # Install pulseaudio.
     apt-get update
@@ -37,6 +38,8 @@ prepare: |
     # Install a snap that uses the pulseaudio interface.
     snap install --edge test-snapd-pulseaudio
     tests.cleanup defer snap remove --purge test-snapd-pulseaudio
+    tests.cleanup defer snap remove --purge test-snapd-pulseaudio_foo
+    tests.cleanup defer snap set system experimental.parallel-instances=null
@@ -132,3 +135,15 @@ execute: |
+    echo "When a parallel install of the snap is installed"
+    snap install --edge test-snapd-pulseaudio_foo
+    snap connect test-snapd-pulseaudio_foo:pulseaudio
+    tests.session -u test exec test-snapd-pulseaudio_foo.play "/snap/test-snapd-pulseaudio_foo/current/usr/share/sounds/alsa/Noise.wav"
+    tests.session -u test exec test-snapd-pulseaudio_foo.recsimple
+
+    echo "When the original snap is removed"
+    snap remove --purge test-snapd-pulseaudio
+
+    echo "Then the parallel snap can still play audio"
+    tests.session -u test exec test-snapd-pulseaudio_foo.play "/snap/test-snapd-pulseaudio_foo/current/usr/share/sounds/alsa/Noise.wav"
```
- **Result**: PASSED on noble.

---

### pipewire
**Status: COMPATIBLE (plug-side only) -- NOT VERIFIED**

**Code analysis**: Similar architecture to pulseaudio (shared memory IPC between server
and clients). Multiple clients connecting to the same PipeWire server is the normal use
case. Slot-side (running multiple PW servers) would conflict.

**Reasoning**: Same as pulseaudio -- plug-side consumers don't conflict.

**Verification**: No spread test run. Needs verification.

---

## Display Interfaces

### x11
**Status: COMPATIBLE (plug-side only)**

**Code analysis:**
- Slot-side creates sockets at `/tmp/.X11-unix/X[0-9]*`. Multiple X servers on
  different display numbers (X0, X1) can coexist.
- Plug-side accesses the slot's private tmp via bind mount. The mount path uses
  instance-aware naming: `/tmp/snap-private-tmp/snap.INSTANCE_NAME/tmp/.X11-unix/`
- Instance name comparison at the interface code uses `plug.Snap().InstanceName()` and
  `slot.Snap().InstanceName()` for correct scoping.
- `LabelExpression()` used for AppArmor peer matching uses `InstanceName()`, so
  cross-instance connections work correctly.

**Reasoning**: When a plug connects to a specific slot, the mount namespace setup
correctly isolates the socket sharing. Parallel instances of a client snap each get their
own mount namespace entry. Parallel instances of a server snap would use different
display numbers.

**Verification:**
```diff
diff --git a/tests/main/interfaces-x11-unix-socket/task.yaml b/tests/main/interfaces-x11-unix-socket/task.yaml
index cf76bae729..bf4b133140 100644
--- a/tests/main/interfaces-x11-unix-socket/task.yaml
+++ b/tests/main/interfaces-x11-unix-socket/task.yaml
@@ -10,7 +10,13 @@ details: |
     system:x11 slot, or an application snap's private /tmp if it is a
     regular slot.
 
+prepare: |
+    snap set system experimental.parallel-instances=true
+
 restore: |
+    snap remove --purge x11-client_foo || true
+    snap remove --purge x11-server_foo || true
+    snap set system experimental.parallel-instances=null
     rm -f /tmp/.X11-unix/X0
 
 execute: |
@@ -50,3 +56,23 @@ execute: |
 
     echo "The client cannot remove host system sockets either"
     not x11-client.rm -f /tmp/.X11-unix/X0
+
+    echo "When parallel installs are installed"
+    "$TESTSTOOLS"/snaps-state install-local-as x11-client x11-client_foo
+    "$TESTSTOOLS"/snaps-state install-local-as x11-server x11-server_foo
+    snap connect x11-client_foo:x11 x11-server_foo:x11
+
+    echo "The parallel snaps can communicate via the unix domain socket in /tmp"
+    x11-server_foo &
+    retry -n 4 --wait 0.5 test -e /tmp/snap-private-tmp/snap.x11-server_foo/tmp/.X11-unix/X0
+    x11-client_foo | MATCH "Hello from xserver"
+
+    echo "When the original snaps are removed"
+    snap remove --purge x11-client
+    snap remove --purge x11-server
+
+    echo "Then the parallel client can still communicate via /tmp"
+    # Restart the server (it's a one-shot nc process that exited after the first connection)
+    x11-server_foo &
+    retry -n 4 --wait 0.5 test -e /tmp/snap-private-tmp/snap.x11-server_foo/tmp/.X11-unix/X0
+    x11-client_foo | MATCH "Hello from xserver"
```
- **Result**: PASSED on noble (parallel instances communicate correctly via
  instance-scoped private tmp).

---

### wayland
**Status: COMPATIBLE (plug-side only)**

**Code analysis:**
- Plug-side accesses `/run/user/[0-9]*/wayland-[0-9]*` sockets provided by the
  compositor (slot). Multiple client snaps connecting to the same Wayland compositor is
  the normal use case.
- `plug.Snap().InstanceName()` at the interface code is used for instance-specific mount
  namespace setup.
- Shared memory paths in the connected slot use instance-aware naming via
  `###PLUG_SECURITY_TAGS###` substitution.

**Reasoning**: Wayland is inherently multi-client. Multiple snap instances connecting as
clients to the same compositor is functionally identical to having multiple different
snaps as clients. Slot-side (running multiple compositors) would require coordination
over socket naming but is out of scope for parallel installs of a client snap.

**Previous audit errors**:
- Claimed "NOT COMPATIBLE" due to "Shared memory" and "Global socket paths" -- INCORRECT
  for plug-side usage.

**Verification:**
```diff
diff --git a/tests/main/interfaces-wayland/task.yaml b/tests/main/interfaces-wayland/task.yaml
@@ -19,6 +19,7 @@ systems:

 prepare: |
+    snap set system experimental.parallel-instances=true
     snap install --edge test-snapd-wayland
@@ -26,6 +27,8 @@ prepare: |

 restore: |
     snap remove test-snapd-wayland
+    snap remove test-snapd-wayland_foo || true
+    snap set system experimental.parallel-instances=null
@@ -51,3 +54,14 @@ execute: |
+    echo "When a parallel install of the snap is installed"
+    snap install --edge test-snapd-wayland_foo
+    snap connect test-snapd-wayland_foo:wayland
+    tests.session -u test exec test-snapd-wayland_foo | MATCH wl_compositor
+
+    echo "When the original snap is removed"
+    snap remove test-snapd-wayland
+
+    echo "Then the parallel snap can still connect to the wayland socket"
+    tests.session -u test exec test-snapd-wayland_foo | MATCH wl_compositor
```
- **Result**: PASSED on ubuntu-22.04-64 (noble is disabled for this test).

---

## Network Interfaces

### network-control
**Status: COMPATIBLE (plug-side only)**

**Code analysis:**
- The connected plug AppArmor rules at `network_control.go:81-151` only use `dbus send`
  (sending messages to `org.freedesktop.resolve1`). The interface acts as a **D-Bus
  client**, it does NOT own/bind any D-Bus name.
- The interface grants broad network capabilities (raw sockets, netlink, WPA supplicant
  access, network namespace management), but these are all global system resources that
  multiple consumers can use simultaneously.
- No `SNAP_NAME` or `SNAP_INSTANCE_NAME` is used in the AppArmor rules -- they are
  purely capability-based.

**Reasoning**: network-control grants system-level network manipulation capabilities.
Multiple instances with network-control all get the same privileges, just like multiple
different snaps with network-control. They can all modify routing tables, ARP entries,
etc. without conflicting at the interface/AppArmor level (though they could conflict at
the operational level if they set contradictory routes).

**Previous audit errors**:
- Claimed "Global D-Bus names: Lines 88-153 bind to org.freedesktop.resolve1" --
  INCORRECT. The interface only SENDS to resolved, it never binds/owns.
- Claimed test "failed on noble, as expected" -- INCORRECT. Test passed.

**Verification:**
```diff
diff --git a/tests/main/interfaces-network-control/task.yaml b/tests/main/interfaces-network-control/task.yaml
@@ -21,9 +21,11 @@ environment:
     PORT: 8081
     SERVICE_NAME: "test-service"
     ARP_ENTRY_ADDR: "30.30.30.30"
+    ARP_ENTRY_ADDR_FOO: "30.30.30.31"

 prepare: |
+    snap set system experimental.parallel-instances=true
     "$TESTSTOOLS"/snaps-state install-local network-control-consumer
@@ -40,6 +42,8 @@ restore: |
+    snap remove --purge network-control-consumer_foo || true
+    snap set system experimental.parallel-instances=null
@@ -165,3 +169,20 @@ execute: |
+    echo "When a parallel install of the snap is installed"
+    "$TESTSTOOLS"/snaps-state install-local-as network-control-consumer network-control-consumer_foo
+    snap connect network-control-consumer_foo:network-control
+
+    echo "Then the parallel snap command can query network status information"
+    network-control-consumer_foo.cmd ss -lnt | MATCH "LISTEN.*:$PORT"
+
+    echo "And the parallel snap can modify the network configuration"
+    network-control-consumer_foo.cmd ip neigh add "$ARP_ENTRY_ADDR_FOO" lladdr aa:aa:aa:aa:aa:aa dev veth0
+    ip neigh show dev veth0 | MATCH "$ARP_ENTRY_ADDR_FOO"
+
+    echo "When the original snap is removed"
+    snap remove --purge network-control-consumer
+
+    echo "Then the parallel snap still works"
+    network-control-consumer_foo.cmd ss -lnt | MATCH "LISTEN.*:$PORT"
```
- **Result**: PASSED on noble.

---

### network-bind
**Status: COMPATIBLE**

**Code analysis:**
- Grants capability to bind to network ports and accept connections.
- No D-Bus name ownership, no shared memory, no instance-specific paths.
- Multiple instances can each bind to different ports without conflict.

**Reasoning**: Pure network capability. Same as two different snaps each binding a port.

**Verification:**
```diff
diff --git a/tests/main/interfaces-network-bind/task.yaml b/tests/main/interfaces-network-bind/task.yaml
@@ -18,6 +18,7 @@ environment:

 prepare: |
+    snap set system experimental.parallel-instances=true
     "$TESTSTOOLS"/snaps-state install-local "$SNAP_NAME"
@@ -36,6 +37,8 @@ restore: |
     snap remove --purge network-bind-consumer
+    snap remove --purge network-bind-consumer_foo || true
+    snap set system experimental.parallel-instances=null
@@ -57,3 +60,15 @@ execute: |
+    echo "When a parallel install of the snap is installed"
+    "$TESTSTOOLS"/snaps-state install-local-as "$SNAP_NAME" "${SNAP_NAME}_foo"
+
+    echo "Then the parallel service is accessible by a client"
+    nc -w 1 localhost "$PORT" < "$REQUEST_FILE" | grep -Pqz 'ok\n'
+
+    echo "When the original snap is removed"
+    snap remove --purge "$SNAP_NAME"
+
+    echo "Then the parallel service is still accessible by a client"
+    nc -w 1 localhost "$PORT" < "$REQUEST_FILE" | grep -Pqz 'ok\n'
```
- **Result**: PASSED on noble.

---

### network-status
**Status: COMPATIBLE**

**Code analysis:**
- Read-only D-Bus access to the `org.freedesktop.portal.NetworkMonitor` portal.
- No D-Bus ownership, no writes, no shared state.
- Multiple consumers reading network status simultaneously is the normal case.

**Verification:**
```diff
diff --git a/tests/main/interfaces-network-status-classic/task.yaml b/tests/main/interfaces-network-status-classic/task.yaml
@@ -25,12 +25,15 @@ prepare: |
+    snap set system experimental.parallel-instances=true
@@ restore: |
+    snap remove --purge test-snapd-network-status-client_foo || true
+    snap set system experimental.parallel-instances=null
@@ execute: |
+    echo "When a parallel install of the snap is installed"
+    "$TESTSTOOLS"/snaps-state install-local-as test-snapd-network-status-client test-snapd-network-status-client_foo
+
+    echo "The parallel snap can access connectivity status"
+    tests.session -u test exec test-snapd-network-status-client_foo.connectivity | MATCH "uint32 4"
+
+    echo "When the original snap is removed"
+    snap remove --purge test-snapd-network-status-client
+
+    echo "Then the parallel snap can still access connectivity status"
+    tests.session -u test exec test-snapd-network-status-client_foo.connectivity | MATCH "uint32 4"
```
- **Result**: PASSED on noble.

---

### network-setup-observe
**Status: COMPATIBLE**

**Code analysis:**
- Read-only file access to netplan configuration (`/etc/netplan/`, `/etc/network/`)
- Read-only D-Bus access to Netplan Info API
- No write operations, no shared resources, no instance-specific paths

**Verification:**
```diff
diff --git a/tests/main/interfaces-network-setup-observe/task.yaml b/tests/main/interfaces-network-setup-observe/task.yaml
@@ prepare: |
+    snap set system experimental.parallel-instances=true
@@ execute: |
+    echo "When a parallel install of the snap is installed"
+    "$TESTSTOOLS"/snaps-state install-local-as test-snapd-sh test-snapd-sh_foo
+    snap connect test-snapd-sh_foo:network-setup-observe
+
+    echo "Then the parallel snap is able to read the network and netplan directories"
+    for dir in $dirs; do
+        if [ -d "$dir" ]; then
+            test-snapd-sh_foo.with-network-setup-observe-plug -c "ls $dir"
+        fi
+    done
+
+    echo "When the original snap is removed"
+    snap remove --purge test-snapd-sh
+
+    echo "Then the parallel snap can still read the network and netplan directories"
+    for dir in $dirs; do
+        if [ -d "$dir" ]; then
+            test-snapd-sh_foo.with-network-setup-observe-plug -c "ls $dir"
+        fi
+    done
```
- **Result**: PASSED on noble.

---

### network-manager
**Status: NOT COMPATIBLE (slot-side system singleton)**

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

**Reasoning**: NetworkManager is architecturally a system-wide singleton. The D-Bus
well-known name `org.freedesktop.NetworkManager` is defined by the upstream
freedesktop.org specification and cannot be per-instance. The shared runtime state paths
reflect that NM manages global system network configuration.

**Verification:**
```diff
diff --git a/tests/main/interfaces-network-manager/task.yaml b/tests/main/interfaces-network-manager/task.yaml
index 6f88ddc0ad..5a4a39a901 100644
--- a/tests/main/interfaces-network-manager/task.yaml
+++ b/tests/main/interfaces-network-manager/task.yaml
@@ -20,6 +20,7 @@ systems:
 
 prepare: |
     echo "Given a network-manager snap is installed"
+    snap set system experimental.parallel-instances=true
     if os.query is-core16; then
         snap install --channel=latest network-manager
     elif os.query is-core18; then
@@ -34,6 +35,10 @@ prepare: |
 
     rm -f /etc/netplan/00-default-nm-renderer.yaml
 
+restore: |
+    snap remove --purge network-manager_foo || true
+    snap set system experimental.parallel-instances=null
+
 execute: |
     # using wait_for_service is not enough, systemd considers the service
     # active even when it is not (yet) listening to dbus
@@ -67,3 +72,37 @@ execute: |
         exit 1
     fi
     MATCH "Permission denied" < call.error
+
+    echo "Reconnect the plug for the parallel instance test"
+    snap connect network-manager:nmcli
+
+    echo "When a parallel install of the snap is installed"
+    if os.query is-core16; then
+        snap install --channel=latest network-manager_foo
+    elif os.query is-core18; then
+        snap install --channel=1.10 network-manager_foo
+    elif os.query is-core20; then
+        snap install --channel=20 network-manager_foo
+    elif os.query is-core22; then
+        snap install --channel=22 network-manager_foo
+    else
+        snap install --channel=24 network-manager_foo
+    fi
+
+    echo "Wait for the parallel instance service to be ready"
+    for _ in $(seq 300); do
+        if network-manager_foo.nmcli general; then
+            break
+        fi
+        sleep 1
+    done
+
+    echo "Then the parallel snap can add a new connection"
+    network-manager_foo.nmcli con add type ethernet con-name nmtest-foo ifname eth0 | MATCH "successfully added"
+
+    echo "When the original snap is removed"
+    snap remove --purge network-manager
+
+    echo "Then the parallel snap can still manage connections"
+    network-manager_foo.nmcli c | MATCH "^nmtest-foo .+ethernet +"
+    network-manager_foo.nmcli connection delete id nmtest-foo | MATCH "successfully deleted"
```
- **Result**: Expected failure on Ubuntu Core 18. The `_foo` nmcli initially works
  while the original is present (both instances share the original's NM service via
  D-Bus). After `snap remove --purge network-manager`, snapd disconnects
  `network-manager_foo:nmcli` from the removed `network-manager:service` slot. The
  `_foo` nmcli then gets `Error: Could not create NMClient object: Could not connect:
  Permission denied` because it can no longer reach the system D-Bus socket
  (`apparmor="DENIED" operation="connect" profile="snap.network-manager_foo.nmcli"
  name="/run/dbus/system_bus_socket"`).

---

## D-Bus Service Interfaces

### location-control
**Status: NOT COMPATIBLE (slot-side); COMPATIBLE (plug-side consumer only)**

**Code analysis:**
- The SLOT permanently binds `dbus (bind) bus=system name="com.ubuntu.location.Service"`
- The PLUG only sends/receives on that bus name
- When a parallel instance provides the slot, it tries to own the same D-Bus name. Only
  one process can own a well-known D-Bus name at a time.
- AppArmor peer labels are instance-specific (`snap.INSTANCE_NAME.app`), so consumer_foo
  is only allowed to talk to provider_foo, but D-Bus routing sends to whoever currently
  owns the name (the original provider).

**Reasoning**: The fundamental issue is D-Bus well-known name uniqueness. Two instances
of the same provider snap cannot both own `com.ubuntu.location.Service`. A parallel
consumer connecting to the system's location service (not a parallel slot) would work
fine.

**Verification:**
```diff
diff --git a/tests/main/interfaces-location-control/task.yaml b/tests/main/interfaces-location-control/task.yaml
index caf48fd812..d266c96c5e 100644
--- a/tests/main/interfaces-location-control/task.yaml
+++ b/tests/main/interfaces-location-control/task.yaml
@@ -20,6 +20,7 @@ systems:
 
 prepare: |
     echo "Given a snap declaring a plug on the location-control interface is installed"
+    snap set system experimental.parallel-instances=true
     snap install test-snapd-location-control-provider
 
     echo "And the provider dbus loop is started"
@@ -37,6 +38,8 @@ restore: |
     # scope, thus it is no longer part of the unit's cgroup
     pkill -f provider.py || true
     tests.session -u test restore
+    snap remove --purge test-snapd-location-control-provider_foo || true
+    snap set system experimental.parallel-instances=null
 
 execute: |
     echo "The interface is not connected by default"
@@ -67,3 +70,11 @@ execute: |
 
     echo "And the plug can be re-connected"
     snap connect test-snapd-location-control-provider:location-control test-snapd-location-control-provider:location-control-test
+
+    echo "When a parallel install of the snap is installed"
+    snap install test-snapd-location-control-provider_foo
+    systemd-run --unit test-snapd-location-control-provider_foo.service test-snapd-location-control-provider_foo.provider
+    snap connect test-snapd-location-control-provider_foo:location-control test-snapd-location-control-provider_foo:location-control-test
+
+    echo "Then the parallel consumer can access its own provider"
+    tests.session -u test exec test-snapd-location-control-provider_foo.consumer Get | MATCH "location-provider-added"
```
- **Result**: Expected failure. `org.freedesktop.DBus.Error.AccessDenied: An AppArmor
  policy prevents this sender from sending this message to this recipient;
  label="snap.test-snapd-location-control-provider_foo.consumer (enforce)"
  destination=... label="snap.test-snapd-location-control-provider.provider (enforce)"`.
  The parallel consumer_foo tries to reach its own provider_foo, but D-Bus routes to the
  original provider (which owns the well-known name), and AppArmor denies the mismatch.

---

### avahi-observe
**Status: COMPATIBLE (plug-side)**

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

**Reasoning**: avahi-observe is a consumer interface. The "NOT COMPATIBLE" label in the
previous audit confused the slot-side (a snap trying to run Avahi) with the plug-side
(a snap querying Avahi). For parallel installs, the relevant question is "can two
instances of my snap both query Avahi?" -- and the answer is yes.

**Previous audit errors**:
- Claimed "NOT COMPATIBLE" due to "Global D-Bus name: binds to org.freedesktop.Avahi" --
  MISLEADING. The bind rule is only for the slot provider, not the plug consumer.

**Verification:**
```diff
diff --git a/tests/main/interfaces-avahi-observe/task.yaml b/tests/main/interfaces-avahi-observe/task.yaml
@@ prepare: |
+    snap set system experimental.parallel-instances=true
     install_generic_consumer avahi-observe,unity7
@@ execute: |
+    echo "When a parallel install of the snap is installed"
+    install_generic_consumer_as avahi-observe,unity7 generic-consumer_foo
+    snap connect generic-consumer_foo:avahi-observe
+
+    echo "Then the parallel snap is able to access avahi provided info"
+    parallel_avahi_dbus_call | MATCH "$hostname"
+
+    echo "When the original snap is removed"
+    snap remove --purge generic-consumer
+
+    echo "Then the parallel snap can still access avahi provided info"
+    parallel_avahi_dbus_call | MATCH "$hostname"
```
- **Result**: PASSED on noble.

---

### contacts-service
**Status: COMPATIBLE**

**Code analysis:**
- Session bus D-Bus access to Evolution Data Server
- Session bus allows multiple simultaneous clients
- No ownership of bus names by the plug-side snap

**Verification:**
```diff
diff --git a/tests/main/interfaces-contacts-service/task.yaml b/tests/main/interfaces-contacts-service/task.yaml
@@ prepare: |
+    snap set system experimental.parallel-instances=true
@@ restore: |
+    snap remove --purge test-snapd-eds_foo || true
+    snap set system experimental.parallel-instances=null
@@ execute: |
+    echo "When a parallel install of the snap is installed"
+    snap install --edge test-snapd-eds_foo
+    snap connect test-snapd-eds_foo:contacts-service
+    tests.session -u test exec test-snapd-eds_foo.contacts list test-address-book
+
+    echo "When the original snap is removed"
+    snap remove --purge test-snapd-eds
+
+    echo "Then the parallel snap can still retrieve contacts"
+    tests.session -u test exec test-snapd-eds_foo.contacts list test-address-book
```
- **Result**: PASSED on noble.

---

### accounts-service
**Status: COMPATIBLE**

**Code analysis:**
- Session bus D-Bus access to `org.gnome.OnlineAccounts` (GNOME Online Accounts)
- The plug only sends/receives on the session bus -- it does not own any bus name
- Multiple instances reading the same per-user account data is the normal use case
- Account state lives in `~/.config/goa-1.0/accounts.conf`, shared across all instances

**Reasoning**: GNOME Online Accounts is a per-user session service. Multiple snap
instances are just additional D-Bus clients reading the same account list.

**Verification:**
```diff
diff --git a/tests/main/interfaces-accounts-service/task.yaml b/tests/main/interfaces-accounts-service/task.yaml
index 49ecb99277..d7f2543bf4 100644
--- a/tests/main/interfaces-accounts-service/task.yaml
+++ b/tests/main/interfaces-accounts-service/task.yaml
@@ -17,6 +17,7 @@ prepare: |
     # Not all the images have the same packages pre-installed.
     apt-get install -y --no-install-recommends gnome-online-accounts
 
+    snap set system experimental.parallel-instances=true
     snap install --edge test-snapd-accounts-service
     tests.session -u test prepare
 
@@ -37,6 +38,8 @@ prepare: |
 
 restore: |
     tests.session -u test restore
+    snap remove --purge test-snapd-accounts-service_foo || true
+    snap set system experimental.parallel-instances=null
 
     # Ensure the file we are expecting to remove is there. This ought to catch
     # future format changes.
@@ -51,3 +54,16 @@ execute: |
     echo "When the plug is connected we can get the data"
     snap connect test-snapd-accounts-service:accounts-service
     tests.session -u test exec test-snapd-accounts-service.list-accounts | MATCH "Display Name at IMAP and SMTP"
+
+    echo "When a parallel install of the snap is installed"
+    snap install --edge test-snapd-accounts-service_foo
+    snap connect test-snapd-accounts-service_foo:accounts-service
+
+    echo "Then the parallel snap can list the accounts"
+    tests.session -u test exec test-snapd-accounts-service_foo.list-accounts | MATCH "Display Name at IMAP and SMTP"
+
+    echo "When the original snap is removed"
+    snap remove --purge test-snapd-accounts-service
+
+    echo "Then the parallel snap can still list the accounts"
+    tests.session -u test exec test-snapd-accounts-service_foo.list-accounts | MATCH "Display Name at IMAP and SMTP"
```
- **Result**: PASSED on noble.

---

### system-dbus (generic `dbus` interface)
**Status: NOT COMPATIBLE (slot-side)**

**Code analysis:**
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

**Reasoning**: This is a fundamental architectural limitation. The D-Bus name model
(globally unique names) is incompatible with having multiple instances of the same
service snap.

**Verification:**
```diff
diff --git a/tests/main/interfaces-system-dbus/task.yaml b/tests/main/interfaces-system-dbus/task.yaml
index ea86b101ba..50898532d7 100644
--- a/tests/main/interfaces-system-dbus/task.yaml
+++ b/tests/main/interfaces-system-dbus/task.yaml
@@ -7,6 +7,7 @@ details: |
 
 prepare: |
     echo "Install dbus system test snaps"
+    snap set system experimental.parallel-instances=true
     snap install --edge test-snapd-dbus-provider
     snap install --edge test-snapd-dbus-consumer
     # we can only talk from an unconfied dbus-send to the service on classic,
@@ -19,6 +20,9 @@ prepare: |
 restore: |
     snap remove --purge test-snapd-dbus-consumer || true
     snap remove --purge test-snapd-dbus-provider || true
+    snap remove --purge test-snapd-dbus-consumer_foo || true
+    snap remove --purge test-snapd-dbus-provider_foo || true
+    snap set system experimental.parallel-instances=null
 
 execute: |
     echo "The dbus consumer plug is disconnected by default"
@@ -54,3 +58,20 @@ execute: |
     echo "And the provider is not able to access the provided method (same snap)"
     not test-snapd-dbus-provider.system-consumer 2> call.error
     MATCH "Permission denied" < call.error
+
+    echo "When parallel installs of the snaps are installed"
+    snap install --edge test-snapd-dbus-provider_foo
+    snap install --edge test-snapd-dbus-consumer_foo
+
+    echo "When the parallel plug is connected"
+    snap connect test-snapd-dbus-consumer_foo:dbus-system-test test-snapd-dbus-provider_foo:dbus-system-test
+
+    echo "Then the parallel consumer is able to call the provided method"
+    test-snapd-dbus-consumer_foo.dbus-system-consumer | MATCH "hello world"
+
+    echo "When the original snaps are removed"
+    snap remove --purge test-snapd-dbus-consumer
+    snap remove --purge test-snapd-dbus-provider
+
+    echo "Then the parallel consumer still works"
+    test-snapd-dbus-consumer_foo.dbus-system-consumer | MATCH "hello world"
```
- **Result**: Expected failure. `org.freedesktop.DBus.Error.AccessDenied: An AppArmor
  policy prevents this sender from sending this message to this recipient;
  label="snap.test-snapd-dbus-consumer_foo.dbus-system-consumer (enforce)"
  destination=... label="snap.test-snapd-dbus-provider.system-provider (enforce)"`.
  Both providers compete for `com.dbustest.HelloWorld`; consumer_foo's AppArmor profile
  expects peer `snap.test-snapd-dbus-provider_foo.*` but D-Bus routes to the original.

---

### location-observe
**Status: COMPATIBLE (plug-side only)**

Same architecture as `location-control` plug-side. A consumer observing location data
from the system service does not conflict with other instances doing the same.

**Verification**: Not separately tested, but same reasoning as avahi-observe applies.

---

### online-accounts-service
**Status: NOT COMPATIBLE (slot-side); COMPATIBLE (plug-side)**

**Code analysis:**
- Slot binds `dbus (bind) bus=session name="com.ubuntu.OnlineAccounts.Manager"`
- Same D-Bus name uniqueness issue as location-control slot-side

---

### autopilot-introspection
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 24-29), with implicit slots on core and classic (lines 69-70).
- AppArmor rules are session-bus only and read-oriented:
  - Introspection of `/com/canonical/Autopilot/**` (lines 38-43)
  - `GetVersion` and `GetState` on `/com/canonical/Autopilot/Introspection` (lines 44-55)
- Seccomp allows only message-passing syscalls (`recvmsg`, `sendmsg`, `sendto`) (lines 57-63).
- No snap-instance-specific paths are involved.
- No name ownership or bind rules; this is a client-only interface.

**Reasoning**: This interface is for inspecting an application's UI status over D-Bus. Multiple parallel instances are just multiple session-bus clients talking to the same service, and the policy does not depend on snap instance naming. No instance collision points are visible in the code.

**Verification:** No verification has yet been done.

### dbus
**Status: NOT COMPATIBLE (slot-side singleton); COMPATIBLE (plug-side)**

**Code analysis:**
- This interface is explicitly built around a well-known D-Bus name provided by the slot snap.
- Permanent slot policy binds the requested bus name with `dbus (bind)` and grants ownership in the generated D-Bus policy (lines 49-150).
- `getAttribs()` validates the `bus` and `name` attributes and rejects names ending in `-NUMBER` to avoid overlap with parallel-install instance naming (lines 240-265).
- `AppArmorConnectedPlug()` and `AppArmorConnectedSlot()` both compare plug/slot attributes and only emit policy when the names match (lines 316-350, 402-429).
- The generated AppArmor peer labels use `slot.LabelExpression()` and `plug.LabelExpression()`, so the security labels are instance-aware, but the D-Bus well-known name itself is a singleton resource.
- `DBusPermanentSlot()` only emits bus policy for system services, but a parallel app slot still cannot have two instances both binding the same bus name.

**Reasoning**: The `dbus` interface is the canonical singleton-service case. Parallel instances of a provider snap cannot both own the same well-known D-Bus name, so slot-side is not compatible. Plug-side use is fine because multiple consumers can talk to the same service if the connection is set up correctly.

**Verification:** No verification has yet been done.

### ubuntu-download-manager
**Status: NOT COMPATIBLE (slot-side singleton); COMPATIBLE (plug-side)**

**Code analysis:**
- The permanent slot binds the well-known session-bus name `com.canonical.applications.Downloader` (lines 127-130).
- The permanent slot also grants D-Bus ownership and listen/accept permissions for that daemon role (lines 131-151).
- Connected plug rules are client-only and use `slot.LabelExpression()` for the security peer label (lines 215-221).
- Connected slot rules use `plug.LabelExpression()` and substitute `###PLUG_NAME###` with `plug.Snap().InstanceName()` (lines 228-236), which is instance-aware.
- The download directories under `~/snap/<plug-instance>/common/Downloads/` are instance-specific because the plug name substitution uses `InstanceName()`.

**Reasoning**: Plug-side consumer access is fine: each parallel instance gets its own download directory and talks to the same download service as a client. Slot-side is a singleton service because the session bus name is globally unique, so two parallel provider instances cannot both own `com.canonical.applications.Downloader`.

**Verification:** No verification has yet been done.

### system-trace
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 24-29), with implicit slots on core and classic (lines 71-72).
- AppArmor rules grant access to kernel tracing files under `/sys/kernel/debug/{kprobes,tracing}` and `/sys/kernel/tracing` plus `/usr/src` headers (lines 32-56).
- Seccomp permits `bpf` and `perf_event_open` (lines 58-65).
- No snap-instance-specific paths are used.
- No D-Bus, sockets, or mounts are involved.

**Reasoning**: Kernel tracing is a global system facility. Multiple parallel instances would simply be concurrent consumers of the same tracing APIs. The interface code does not introduce any snap-instance scoping that could conflict.

**Verification:** No verification has yet been done.

### media-hub
**Status: NOT COMPATIBLE (slot-side singleton; code analysis -- not yet verified)**

**Code analysis:**
- The permanent slot binds the well-known session-bus name `core.ubuntu.media.Service` (lines 64-68).
- The slot AppArmor rules also allow request/release-name operations on the session bus and talk to unconfined clients for the service path (lines 49-99).
- The connected slot and plug rules both key access on the security label of the opposite side, but the actual service name remains a singleton resource (lines 102-152).
- The interface exposes session management and MPRIS-like APIs over the same well-known bus object paths.
- No snap-instance-specific filesystem paths are used.

**Reasoning**: Media Hub is a D-Bus service provider interface. Parallel consumers are fine, but parallel providers cannot both own the same well-known service name, so the slot side is a singleton conflict.

**Verification:** No verification has yet been done.

### mir
**Status: NOT COMPATIBLE (slot-side singleton; code analysis -- not yet verified)**

**Code analysis:**
- The permanent slot owns the Mir server runtime resources, including `/run/mir_socket`, `/run/user/[0-9]*/mir_socket`, `/dev/tty[0-9]*`, and `/dev/input/*` (lines 42-71).
- The slot AppArmor also includes `/dev/shm/\#[0-9]*` shared-memory objects and `sys_admin` / `sys_tty_config` capabilities (lines 42-71).
- The Seccomp profile permits server-side socket/listen/accept and netlink uevent handling (lines 73-85).
- The connected plug only gets client access to Mir sockets and shared-memory objects (lines 87-100).

**Reasoning**: Mir is a display-server service interface. Parallel clients are fine, but parallel service providers would compete for the same Mir server runtime paths and privileged system resources, making the slot side a singleton.

**Verification:** No verification has yet been done.

### storage-framework-service
**Status: NOT COMPATIBLE (slot-side singleton; code analysis -- not yet verified)**

**Code analysis:**
- The permanent slot binds `com.canonical.StorageFramework.Registry` and `com.canonical.StorageFramework.Provider.*` on the session bus (lines 55-73).
- The slot AppArmor also writes to `/sys/kernel/security/apparmor/.access` and reads `/sys/module/apparmor/parameters/enabled` and `/proc/*/mounts` as part of policy introspection (lines 42-54).
- Connected slot and plug rules are client-only and use label expressions for peer mediation (lines 75-109).
- The service name is the actual singleton resource; the path patterns are not instance-scoped.

**Reasoning**: This is a D-Bus service provider interface. Parallel consumers are fine, but parallel providers cannot both own the registry/provider bus names.

**Verification:** No verification has yet been done.

### unity8
**Status: NOT COMPATIBLE (slot-side singleton; code analysis -- not yet verified)**

**Code analysis:**
- The connected plug talks to Unity 8 session services over the session bus, including `com.canonical.URLDispatcher` and `com.ubuntu.content.dbus.Service` (lines 45-89).
- The URL dispatcher peer is a well-known bus name, and the content-hub-style interface is presented as a shared session service.
- The slot side is intended to represent the desktop service provider; multiple providers would contend for the same session-bus identities.
- No snap-instance-specific filesystem paths are involved.

**Reasoning**: Unity 8 is a desktop service interface built around well-known D-Bus services. Parallel clients are fine, but parallel service providers would collide on the same bus names.

**Verification:** No verification has yet been done.

### unity8-calendar
**Status: NOT COMPATIBLE (slot-side singleton; code analysis -- not yet verified)**

**Code analysis:**
- The permanent slot binds `org.gnome.evolution.dataserver.Calendar7`, `org.gnome.evolution.dataserver.Subprocess.Backend.Calendar*`, and `com.canonical.SyncMonitor` on the session bus (lines 33-47).
- The slot AppArmor exposes the calendar factory/view/subprocess paths and sync-monitor endpoints to unconfined clients (lines 48-75).
- The connected plug is client-only to the same calendar service paths (lines 77-109).
- The service paths are fixed names and object paths, not snap-instance-scoped resources.

**Reasoning**: This is a calendar service provider interface. Parallel clients are fine, but parallel providers would contend for the same well-known calendar and sync-monitor bus names.

**Verification:** No verification has yet been done.

### unity8-contacts
**Status: NOT COMPATIBLE (slot-side singleton; code analysis -- not yet verified)**

**Code analysis:**
- The permanent slot binds `org.gnome.evolution.dataserver.AddressBook9`, `org.gnome.evolution.dataserver.Subprocess.Backend.AddressBook*`, `com.canonical.pim`, and `com.meego.msyncd` on the session bus (lines 33-54).
- The slot AppArmor exposes address book factory/view/subprocess paths and Canonical PIM paths to unconfined clients (lines 55-93).
- The connected plug is client-only to the same address book service paths (lines 95-183).
- No snap-instance-specific filesystem paths are used.

**Reasoning**: Unity 8 Contacts is another D-Bus service provider interface. Parallel consumers are fine, but parallel providers would collide on the same well-known bus names.

**Verification:** No verification has yet been done.

### screencast-legacy
**Status: NOT COMPATIBLE (plug-side only; code analysis -- not yet verified)**

**Code analysis:**
- The plug talks to gnome-shell screenshot/screencast interfaces on the session bus (lines 32-53).
- The API allows absolute file names as method arguments, so the caller can direct output to arbitrary paths permitted by the user.
- The interface does not own a bus name itself, but the permissions are explicitly tied to the desktop session service.
- No snap-instance-specific pathing is used by snapd.

**Reasoning**: The interface is intentionally powerful and can write arbitrary files via gnome-shell. That is not a snap-instance collision per se, but it is not a safe parallel-install interface to analyze as compatible; it is a privileged client-side desktop capability.

**Verification:** No verification has yet been done.

### ros-opt-data
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- The plug gets read-only access to `/var/lib/snapd/hostfs/opt/ros/**` and common ROS file extensions under that tree (lines 31-49).
- The interface is implicit on classic and not on core, which matches a host filesystem read-only pattern.
- No sockets, mounts, or D-Bus names are involved.
- No snap-instance-specific names are used.

**Reasoning**: ROS static data is read-only host content. Parallel instances can all read the same files without snapd-level collisions.

**Verification:** No verification has yet been done.

### system-backup
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- The plug gets read-only access across the host filesystem through `/var/lib/snapd/hostfs/` exclusions and `dac_read_search` (lines 32-47).
- The policy explicitly excludes `/dev`, `/sys`, and `/proc` from the broad read rule and then re-adds narrow cases as needed.
- No D-Bus, sockets, or instance-specific mount paths are present.

**Reasoning**: This is a broad read-only backup interface. Parallel instances are just concurrent readers of the same host data, and the policy does not encode snap-instance-specific paths.

**Verification:** No verification has yet been done.

### system-source-code
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- The plug gets read-only access to `/usr/src/{,**}` (line 38).
- The interface is implicit on core and classic and otherwise just exposes source trees/headers.
- No sockets, mounts, or snap-instance-specific names are involved.

**Reasoning**: `/usr/src` is a shared system source tree. Multiple instances can read it concurrently without any instance-name collision.

**Verification:** No verification has yet been done.

### juju-client-observe
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- The plug gets read access to `~/.local/share/juju/{,**}` using `owner` file rules (lines 32-35).
- The interface is classic-only and reads the user’s Juju client state; it does not own a bus name.
- No sockets, mounts, or snap-instance-specific names are used.

**Reasoning**: Juju client state is per-user data. Parallel instances under the same user will read the same Juju config/state, which is normal shared-user behavior and not an instance collision.

**Verification:** No verification has yet been done.

### netlink-driver
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- The slot is keyed by a numeric `family` attribute and a validated `family-name` (lines 66-100).
- The plug must present a matching `family-name` (lines 104-107, 127-140).
- The connected plug seccomp snippet allows `AF_NETLINK` for the declared family and `bind` (lines 109-124).
- No snap-instance-specific paths are used; the identity is based on the protocol family name, not snap name.

**Reasoning**: Netlink-driver is scoped to a kernel protocol family rather than to snap identity. Parallel instances are safe when they connect to the same declared family or to different families; the interface code does not create a snap-instance collision.

**Verification:** No verification has yet been done.

### core-support
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- This interface is explicitly hollow and grants no permissions (lines 39-41).
- It only exists so callers can test for its presence; `commonInterface` is registered with no AppArmor/seccomp/udev policy.
- No paths, sockets, mounts, or snap-instance-specific logic are present.

**Reasoning**: The interface has no confinement effect at all. Parallel instances cannot collide because there is no policy to collide over.

**Verification:** No verification has yet been done.

### accel
**Status: NOT COMPATIBLE (exclusive hardware; code analysis -- not yet verified)**

**Code analysis:**
- The interface grants access to `/dev/accel/accel*` (lines 4560-4566 in the bucket summary).
- The access is device-node based and tied to global accelerator hardware.
- No instance-specific pathing or name expansion exists in the interface model.

**Reasoning**: Accelerator device nodes are exclusive physical hardware resources. Two parallel instances would contend for the same accelerator device, so this is not a good parallel-install fit.

**Verification:** No verification has yet been done.

### acrn-support
**Status: NOT COMPATIBLE (exclusive hardware; code analysis -- not yet verified)**

**Code analysis:**
- The interface grants access to `/dev/acrn_hsm` (lines 4572-4579 in the bucket summary).
- ACRN management is a single hypervisor control device node.
- No snap-instance-specific logic is involved.

**Reasoning**: This is a single global hypervisor-management device. Parallel instances would compete for the same control node.

**Verification:** No verification has yet been done.

### allegro-vcu
**Status: NOT COMPATIBLE (exclusive hardware; code analysis -- not yet verified)**

**Code analysis:**
- The interface grants access to `/dev/allegroDecodeIP`, `/dev/allegroIP`, and `/dev/dmaproxy` (lines 4583-4590 in the bucket summary).
- These are hardware codec device nodes, not per-instance resources.

**Reasoning**: The codec hardware is shared and effectively exclusive. Parallel instances would contend for the same devices.

**Verification:** No verification has yet been done.

### broadcom-asic-control
**Status: NOT COMPATIBLE (exclusive hardware; code analysis -- not yet verified)**

**Code analysis:**
- The interface grants access to `/dev/linux-user-bde`, `/dev/linux-kernel-bde`, and `/dev/linux-bcm-knet` (lines 4594-4601 in the bucket summary).
- These are ASIC kernel module/device interfaces for a specific hardware platform.

**Reasoning**: Broadcom ASIC control is tied to a single hardware resource and is not instance-isolated.

**Verification:** No verification has yet been done.

### camera
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 28-33), with implicit slots on core and classic (lines 80-81).
- AppArmor rules are device-path based and intentionally broad: `/dev/video[0-9]*`, `/dev/vchiq`, and supporting sysfs/udev paths (lines 36-57).
- UDev rules tag video devices (lines 71-74).
- No snap-instance-specific paths are used.
- The interface explicitly notes it allows access to all cameras until better device assignment exists (line 37).

**Reasoning**: Camera devices are shared hardware resources. Parallel instances accessing the same global camera nodes is expected; the interface code is not instance-scoped and does not create a collision surface.

**Verification:** No verification has yet been done.

### can-bus
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- The interface grants CAN network access and allows AF_CAN sockets (lines 4617-4624 in the bucket summary).
- No instance-specific pathing or ownership is present.
- The kernel handles CAN concurrency; the interface is just a client to that medium.

**Reasoning**: Parallel instances can use the CAN bus at the same time, but they share the same underlying hardware bus.

**Verification:** No verification has yet been done.

### cpu-control
**Status: NOT COMPATIBLE (system-global control; code analysis -- not yet verified)**

**Code analysis:**
- The interface targets `/sys/devices/system/cpu/**` (lines 4628-4635 in the bucket summary).
- It controls governor, scaling, and hotplug settings for the whole system.
- No snap-instance-specific logic is involved.

**Reasoning**: CPU policy is a system-global control surface. Parallel instances changing settings would conflict.

**Verification:** No verification has yet been done.

### dcdbas-control
**Status: NOT COMPATIBLE (system-global control; code analysis -- not yet verified)**

**Code analysis:**
- The interface targets `/sys/devices/platform/dcdbas/*` (lines 4639-4646 in the bucket summary).
- It exposes the Dell Systems Management Base Driver, which is a single system resource.

**Reasoning**: This is a single system-management interface. Parallel instances would contend for the same sysfs knobs.

**Verification:** No verification has yet been done.

### dsp
**Status: NOT COMPATIBLE (exclusive hardware; code analysis -- not yet verified)**

**Code analysis:**
- The interface grants access to `/dev/ucode` and `/dev/iav*` (lines 4650-4657 in the bucket summary).
- These are hardware DSP device nodes.

**Reasoning**: DSP hardware is a single-instance resource. Parallel instances would share/contend for the same device.

**Verification:** No verification has yet been done.

### fpga
**Status: NOT COMPATIBLE (exclusive hardware; code analysis -- not yet verified)**

**Code analysis:**
- The interface grants access to `/dev/fpga[0-9]*` (lines 4661-4668 in the bucket summary).
- These are numbered FPGA device nodes with shared hardware state.

**Reasoning**: FPGA programming/control is hardware-exclusive. Parallel instances programming the same FPGA would conflict.

**Verification:** No verification has yet been done.

### framebuffer
**Status: NOT COMPATIBLE (exclusive hardware; code analysis -- not yet verified)**

**Code analysis:**
- The interface grants access to `/dev/fb[0-9]*` (lines 4672-4679 in the bucket summary).
- Framebuffer devices are global display hardware.

**Reasoning**: Two instances writing the same framebuffer would conflict on the same display device.

**Verification:** No verification has yet been done.

### gpio
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slots are provided by core or gadget snaps only (lines 35-41), not by app snaps.
- The slot is keyed by a GPIO number attribute and the code resolves the sysfs path via `evalSymlinks()` before emitting rules (lines 83-105).
- The interface also sets up a per-slot systemd service to export/unexport the GPIO line (lines 108-122).
- No snap-instance-specific names are used beyond the slot-supplied GPIO number.

**Reasoning**: GPIO access is tied to a physical pin, not a snap instance. Parallel installs can connect to the same pin or different pins as declared by the slot; there is no instance-name collision in the interface code.

**Verification:** No verification has yet been done.

### gpio-memory-control
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 25-30), with implicit slots on core and classic (lines 47-48).
- AppArmor rules grant access to `/dev/gpiomem` (line 38).
- UDev tags the `gpiomem` device (line 41).
- No instance-specific names, sockets, or mounts are used.

**Reasoning**: This is a global GPIO memory device and the interface is just device-path based. Multiple instances can share the same access without snap-instance collisions in snapd policy.

**Verification:** No verification has yet been done.

### hugepages-control
**Status: NOT COMPATIBLE (system-global control; code analysis -- not yet verified)**

**Code analysis:**
- The interface controls system hugepage sysfs and `/proc/sys/vm/*` plus `/{dev,run}/hugepages/` (lines 4705-4713 in the bucket summary).
- The runtime directory uses `owner`, but that is user ownership, not snap-instance scoping.
- A mount rule permits `/dev/hugepages`.

**Reasoning**: Hugepages are a global kernel memory facility. Parallel instances would contend for the same system controls.

**Verification:** No verification has yet been done.

### iio
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slots are provided by core or gadget snaps only (lines 36-42).
- Slot validation requires a device node path under `/dev/iio:deviceN` (lines 77-95).
- AppArmor rules are generated from the specific slot path and derived device name (lines 98-133).
- UDev tags the device by the exact `/dev/iio:deviceN` node (lines 135-141).
- No snap-instance-specific names are used.

**Reasoning**: The interface targets a specific IIO hardware device, not an instance-scoped resource. Parallel installs can connect to the same device or different devices without snapd-level collision.

**Verification:** No verification has yet been done.

### intel-mei
**Status: NOT COMPATIBLE (exclusive hardware; code analysis -- not yet verified)**

**Code analysis:**
- The interface grants access to `/dev/mei[0-9]*` (lines 4727-4734 in the bucket summary).
- Intel MEI is a system-management bus exposed as hardware device nodes.

**Reasoning**: This is a single hardware-management channel. Parallel instances would contend for the same device resource.

**Verification:** No verification has yet been done.

### intel-qat
**Status: NOT COMPATIBLE (shared accelerator hardware; code analysis -- not yet verified)**

**Code analysis:**
- The interface grants access to `/dev/vfio/*` and IOMMU sysfs (lines 4738-4745 in the bucket summary).
- It targets Intel QuickAssist Technology accelerator hardware.

**Reasoning**: QAT is a shared PCIe accelerator. Parallel instances can’t be treated as isolated consumers in the interface code.

**Verification:** No verification has yet been done.

### io-ports-control
**Status: NOT COMPATIBLE (system-global control; code analysis -- not yet verified)**

**Code analysis:**
- The interface grants access to `/dev/port` and the `sys_rawio` capability, plus `ioperm`/`iopl` syscalls (lines 4749-4757 in the bucket summary).
- This is full I/O port access for the system.

**Reasoning**: I/O port access is a global machine capability and is inherently not instance-isolated.

**Verification:** No verification has yet been done.

### kernel-crypto-api
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- The interface grants `AF_ALG` access to the kernel crypto API (lines 4761-4768 in the bucket summary).
- It is a shared kernel subsystem and does not own a singleton name or path.

**Reasoning**: Multiple instances can use the kernel crypto API simultaneously. This is a shared subsystem, not an exclusive snap-scoped resource.

**Verification:** No verification has yet been done.

### mediatek-accel
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 33-38), with plug-side `units` selection validated in `BeforePreparePlug()` (lines 94-122).
- The selected units (`apu`, `vcu`) drive AppArmor and udev snippets (lines 71-88, 124-147).
- No snap-instance-specific paths are involved; access is keyed by device type and slot attributes.

**Reasoning**: The interface is device-selector based and not instance-name based. Parallel installs can use the same hardware accelerator devices as long as the declared units match.

**Verification:** No verification has yet been done.

### opengl
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- The interface grants access to GPU device nodes / DRM render nodes (lines 4783-4790 in the bucket summary).
- It is a shared-client GPU interface and does not encode snap-instance scoping.

**Reasoning**: Multiple processes using the same GPU is normal. Parallel instances can share the GPU, so this is compatible for plug-side usage.

**Verification:** No verification has yet been done.

### optical-drive
**Status: NOT COMPATIBLE (exclusive hardware; code analysis -- not yet verified)**

**Code analysis:**
- The interface grants access to `/dev/sr[0-9]*` and `/dev/scd[0-9]*` (lines 4794-4801 in the bucket summary).
- These are physical optical drives, which are exclusive devices.

**Reasoning**: Optical drives are exclusive-access hardware. Two instances trying to use the same drive are not a parallel-install-safe pattern.

**Verification:** No verification has yet been done.

### physical-memory-control
**Status: NOT COMPATIBLE (extreme privilege; code analysis -- not yet verified)**

**Code analysis:**
- The interface grants read/write access to `/dev/mem` (lines 4805-4813 in the bucket summary).
- This is full physical memory access.

**Reasoning**: This is an extreme system-global privilege and is not a sensible parallel-install target.

**Verification:** No verification has yet been done.

### physical-memory-observe
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- The interface grants read-only `/dev/mem` access (lines 4816-4823 in the bucket summary).
- It is read-only physical memory inspection with no snap-instance-specific logic.

**Reasoning**: Read-only access means parallel instances can coexist reading the same data, though this remains an extreme privilege.

**Verification:** No verification has yet been done.

### power-control
**Status: NOT COMPATIBLE (system-global control; code analysis -- not yet verified)**

**Code analysis:**
- The interface targets `/sys/devices/**/power/*` (lines 4827-4835 in the bucket summary).
- It controls power-management settings for the whole system.

**Reasoning**: Power policy is system-global, so parallel instances would contend for the same controls.

**Verification:** No verification has yet been done.

### ptp
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- The interface grants access to `/dev/ptp[0-9]*` and related sysfs knobs (lines 4838-4845 in the bucket summary).
- It is a hardware clock device interface.

**Reasoning**: PTP hardware clocks are shared devices. Parallel instances can access the same underlying clock hardware from separate snaps without snapd-level collision.

**Verification:** No verification has yet been done.

### pwm
**Status: NOT COMPATIBLE (exclusive hardware; code analysis -- not yet verified)**

**Code analysis:**
- The interface targets `/sys/class/pwm/pwmchipN` and specific channels (lines 4849-4856 in the bucket summary).
- It is tied to numbered PWM outputs.

**Reasoning**: PWM channels are physical hardware outputs. Two instances claiming the same channel would conflict.

**Verification:** No verification has yet been done.

### spi
**Status: NOT COMPATIBLE (exclusive hardware; code analysis -- not yet verified)**

**Code analysis:**
- The interface grants access to `/dev/spidev<N>.<M>` (lines 4860-4867 in the bucket summary).
- It is tied to a numbered SPI bus and chip select.

**Reasoning**: SPI buses are physical hardware. Two instances accessing the same SPI bus simultaneously would cause bus contention.

**Verification:** No verification has yet been done.

### u2f-devices
**Status: NOT COMPATIBLE (exclusive hardware; code analysis -- not yet verified)**

**Code analysis:**
- The interface matches USB vendor/product patterns for U2F/FIDO tokens (lines 4871-4878 in the bucket summary).
- It is a physical token interface.

**Reasoning**: A specific hardware token is an exclusive interactive resource. Parallel instances using the same token would contend for it.

**Verification:** No verification has yet been done.

### uio
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- The interface grants access to `/dev/uio[0-9]*` (lines 4882-4889 in the bucket summary).
- UIO devices are userspace-mapped hardware devices.

**Reasoning**: The interface is device-based. Multiple instances can share the same access path without snapd-level collision, though the hardware itself may still be shared.

**Verification:** No verification has yet been done.

### usb-gadget
**Status: NOT COMPATIBLE (system-global control; code analysis -- not yet verified)**

**Code analysis:**
- The interface grants access to USB gadget configfs (lines 4893-4900 in the bucket summary).
- Configfs is used to configure the system-wide USB peripheral mode gadget.

**Reasoning**: USB gadget configuration is a single system-wide control plane. Parallel instances cannot both safely manage it.

**Verification:** No verification has yet been done.

### vcio
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- The interface grants access to `/dev/vcio` (lines 4904-4911 in the bucket summary).
- It is a single hardware mailbox interface for the VideoCore GPU.

**Reasoning**: This is a shared hardware mailbox rather than a snap-scoped resource. Parallel instances can access it as concurrent clients.

**Verification:** No verification has yet been done.

### raw-volume
**Status: POTENTIALLY COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- The interface is tied to a specific disk partition via a slot-declared device node (lines 4915-4924 in the bucket summary).
- AppArmor and udev rules are derived from the slot path attribute.
- There is no snap-instance-specific naming in the interface logic.

**Reasoning**: This is not instance-scoped; it is device-scoped. Parallel instances are only safe when they are deliberately connected to different partitions.

**Verification:** No verification has yet been done.

### bluez
**Status: NOT COMPATIBLE (slot-side system singleton); COMPATIBLE (plug-side)**

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

**Reasoning**: Like network-manager, bluez is architecturally a system singleton. The
D-Bus names (`org.bluez`, etc.) are defined by the upstream BlueZ specification. For
plug-side usage (a snap consuming Bluetooth services from the system), parallel
instances work fine since they're just D-Bus clients. For slot-side (providing the
bluez service), only one instance can operate.

**Verification**: 
```diff
diff --git a/tests/main/interfaces-bluez/task.yaml b/tests/main/interfaces-bluez/task.yaml
index 1f53397d94..0a2341fc35 100644
--- a/tests/main/interfaces-bluez/task.yaml
+++ b/tests/main/interfaces-bluez/task.yaml
@@ -7,9 +7,31 @@ details: |
     This test verifies that the bluez snap from the store installs and
     we can connect its slot and plug.
 
+prepare: |
+    snap set system experimental.parallel-instances=true
+
+restore: |
+    snap remove --purge bluez_foo || true
+    snap set system experimental.parallel-instances=null
+
 execute: |
     echo "Installing bluez snap from the store ..."
     snap install --channel=latest/stable bluez
 
     echo "Connecting bluez snap plugs/slots ..."
     snap connect bluez:client bluez:service
+
+    echo "When a parallel install of the snap is installed"
+    snap install --channel=latest/stable bluez_foo
+
+    echo "Connect the parallel client plug to the original service slot"
+    # NOTE: The slot is a D-Bus singleton (org.bluez). Only one instance can
+    # provide the service. We test plug-side only by connecting the parallel
+    # client to the original's service slot.
+    snap connect bluez_foo:client bluez:service
+
+    echo "When the original snap is removed"
+    snap remove --purge bluez
+
+    echo "Then the parallel snap can provide its own service and connect to it"
+    snap connect bluez_foo:client bluez_foo:service
```

- **Result:** PASSED on noble (plug-side). Parallel `bluez_foo` client connected to
original service slot; after original removed, `_foo` self-connected its own service
slot (no D-Bus name conflict with only one instance running).

---

### camera
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 28-33), with implicit slots on core and classic (lines 80-81).
- AppArmor rules are device-path based and intentionally broad: `/dev/video[0-9]*`, `/dev/vchiq`, and supporting sysfs/udev paths (lines 36-57).
- UDev rules tag video devices (lines 71-74).
- No snap-instance-specific paths are used.
- The interface explicitly notes it allows access to all cameras until better device assignment exists (line 37).

**Reasoning**: Camera devices are shared hardware resources. Parallel instances accessing the same global camera nodes is expected; the interface code is not instance-scoped and does not create a collision surface.

**Verification:** No verification has yet been done.

### bluetooth-control
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 24-29), with implicit slots on core and classic (lines 70-71).
- AppArmor rules grant access to Bluetooth kernel interfaces and device nodes (`/sys/devices/**/bluetooth/**`, `/dev/vhci`, `/dev/stpbt`) (lines 32-56).
- Seccomp only adds `bind` (lines 58-62).
- UDev rules match Bluetooth-related subsystems (line 64).
- No snap-instance-specific paths, D-Bus names, or sockets are involved.

**Reasoning**: This interface controls the system Bluetooth stack, which is a global kernel/service resource. Multiple parallel instances can be granted the same access; the code does not create snap-instance collisions.

**Verification:** No verification has yet been done.

### gpio
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slots are provided by core or gadget snaps only (lines 35-41), not by app snaps.
- The slot is keyed by a GPIO number attribute and the code resolves the sysfs path via `evalSymlinks()` before emitting rules (lines 83-105).
- The interface also sets up a per-slot systemd service to export/unexport the GPIO line (lines 108-122).
- No snap-instance-specific names are used beyond the slot-supplied GPIO number.

**Reasoning**: GPIO access is tied to a physical pin, not a snap instance. Parallel installs can connect to the same pin or different pins as declared by the slot; there is no instance-name collision in the interface code.

**Verification:** No verification has yet been done.

### gpio-chardev
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slots are provided by gadget snaps (lines 50-55), and the interface uses instance-aware names throughout the setup.
- `slot.Snap().InstanceName()` and `plug.Snap().InstanceName()` are used to build `/dev/snap/gpio-chardev/<instance>/<name>` paths (lines 136-187).
- The systemd service for the slot exports the virtual device using the slot instance name and slot name (lines 127-156).
- UDev tagging uses an instance-aware tag (`snap_<instance>_interface_gpio_chardev_<slot>`) (lines 193-196).
- A conflict with `gpio` is explicitly declared via `conflictingConnectedInterfaces: []string{"gpio"}` (lines 207-210).

**Reasoning**: The interface is carefully namespaced by snap instance for both slot and plug paths, so parallel installs do not collide. The only conflict is with the legacy `gpio` interface, which is intentional and unrelated to parallel naming.

**Verification:** No verification has yet been done.

### gpio-memory-control
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 25-30), with implicit slots on core and classic (lines 47-48).
- AppArmor rules grant access to `/dev/gpiomem` (line 38).
- UDev tags the `gpiomem` device (line 41).
- No instance-specific names, sockets, or mounts are used.

**Reasoning**: This is a global GPIO memory device and the interface is just device-path based. Multiple instances can share the same access without snap-instance collisions in snapd policy.

**Verification:** No verification has yet been done.

### hugepages-control
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 29-34), with implicit slots on core and classic (noted in the interface registration).
- AppArmor rules cover system hugepage sysfs, `/proc/sys/vm/*`, and `/{dev,run}/hugepages/` (lines 37-68).
- The rules use `owner` for the hugepages runtime directory (line 54), but that is user/file ownership, not snap instance naming.
- A mount rule permits `/dev/hugepages` (line 67).
- No snap-instance-specific paths are involved.

**Reasoning**: Hugepages are a global kernel memory facility. Parallel instances can all manipulate the same system hugepage controls; the interface code does not introduce any snap-instance-specific pathing.

**Verification:** No verification has yet been done.

### iio
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slots are provided by core or gadget snaps only (lines 36-42).
- Slot validation requires a device node path under `/dev/iio:deviceN` (lines 77-95).
- AppArmor rules are generated from the specific slot path and derived device name (lines 98-133).
- UDev tags the device by the exact `/dev/iio:deviceN` node (lines 135-141).
- No snap-instance-specific names are used.

**Reasoning**: The interface targets a specific IIO hardware device, not an instance-scoped resource. Parallel installs can connect to the same device or different devices without snapd-level collision.

**Verification:** No verification has yet been done.

### io-ports-control
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 24-29), with implicit slots on core and classic (lines 57-58).
- AppArmor grants access to `/dev/port` and the `sys_rawio` capability (lines 32-39).
- Seccomp allows `ioperm` and `iopl` (lines 41-49).
- UDev tags the `port` device (line 51).
- No snap-instance-specific paths or D-Bus names are involved.

**Reasoning**: I/O port access is a global hardware capability. The interface is pure capability/device access and does not depend on instance naming.

**Verification:** No verification has yet been done.

### kernel-module-observe
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 24-29), with implicit slots on core and classic (lines 54-55).
- AppArmor grants read access to `/proc/modules`, `/sys/module/**`, and modprobe config directories (lines 32-48).
- The interface notes that `kmod` is used only for querying and seccomp/no-SYS_MODULE prevent loading/removal (line 34).
- No snap-instance-specific paths are used.

**Reasoning**: This is read-only kernel module observation. Parallel instances can all read the same global module state without colliding at the interface level.

**Verification:** No verification has yet been done.

### mediatek-accel
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 33-38), with plug-side `units` selection validated in `BeforePreparePlug()` (lines 94-122).
- The selected units (`apu`, `vcu`) drive AppArmor and udev snippets (lines 71-88, 124-147).
- No snap-instance-specific paths are involved; access is keyed by device type and slot attributes.

**Reasoning**: The interface is device-selector based and not instance-name based. Parallel installs can use the same hardware accelerator devices as long as the declared units match.

**Verification:** No verification has yet been done.

### ppp
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 24-29), with implicit slots on core and classic (lines 70-71).
- AppArmor grants access to `/usr/sbin/pppd`, `/etc/ppp/**`, `/dev/ppp`, tty devices, lock files, and log directories (lines 32-52).
- KMod and UDev support are declared for `ppp_generic` and the relevant devices (lines 54-64).
- No snap-instance-specific paths are used.

**Reasoning**: PPP is a global daemon/device interface. Parallel instances behave as ordinary clients of the same system PPP stack; the policy does not encode any instance-specific paths.

**Verification:** No verification has yet been done.

### ptp
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 24-29), with implicit slots on core and classic (lines 49-50).
- AppArmor grants access to `/dev/ptp[0-9]*` and related sysfs knobs under `/sys/class/ptp/` (lines 32-39).
- UDev tags PTP devices by subsystem and kernel name (lines 41-43).
- No snap-instance-specific paths are used.

**Reasoning**: PTP hardware clocks are global devices. The interface is purely device-based and does not create any snap-instance collision point.

**Verification:** No verification has yet been done.

### pwm
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slots are provided by core or gadget snaps only (lines 36-42).
- The interface validates slot attributes `channel` and `chip-number` and resolves `/sys/class/pwm/pwmchipN` with `evalSymlinks()` (lines 52-107).
- A systemd service exports/unexports the PWM channel using the slot-supplied chip/channel values (lines 110-129).
- No snap-instance-specific names are used beyond slot attributes.

**Reasoning**: PWM access is tied to a specific hardware chip/channel. Parallel installs do not collide at the interface layer because the slot defines the hardware target.

**Verification:** No verification has yet been done.

### qualcomm-ipc-router
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- The interface supports both system and app slots, and the app-slot path is fully instance-aware via `slot.LabelExpression()` and `plug.LabelExpression()` (lines 195-241).
- Slot attributes `qcipc` and `address` are validated, and the socket address is injected directly into AppArmor/Seccomp snippets (lines 174-192, 244-263).
- The code explicitly avoids instance-unsafe matching by separating system-slot compatibility and app-slot handling.
- No snap-instance-specific paths are hardcoded; paths are derived from slot attributes.

**Reasoning**: The interface is socket-address based and already uses the snap labels correctly where needed. The code does not show a parallel-install collision surface.

**Verification:** No verification has yet been done.

### spi
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slots are provided by core or gadget snaps only (lines 36-42).
- Slot path validation ensures the path is a concrete `/dev/spidevN.M` node (lines 60-79).
- AppArmor and udev rules are generated from the slot path, and the interface uses `slot.Ref()` / `slot.Snap()` in a way that is instance-aware for slot identity (lines 81-101).
- No snap-instance-specific mounts or D-Bus rules are present.

**Reasoning**: SPI access is tied to a concrete bus/device node. Parallel instances do not collide at the interface layer because the slot defines the hardware target.

**Verification:** No verification has yet been done.

### tpm
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 24-29), with implicit slots on core and classic (lines 49-50).
- AppArmor grants access to `/dev/tpm[0-9]*` and `/dev/tpmrm[0-9]*` (lines 32-38).
- UDev tags TPM devices (lines 40-43).
- No snap-instance-specific names, sockets, or mounts are involved.

**Reasoning**: TPM is a global hardware device. The interface is pure device access and does not encode any snap-instance-specific scoping.

**Verification:** No verification has yet been done.

### uio
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slots are provided by core or gadget snaps only (lines 39-45).
- Slot path validation uses `verifySlotPathAttribute()` and requires `/dev/uioN` (lines 65-72).
- AppArmor rules are derived from the slot path and a shared deduplicated sysfs rule is used for all connections (lines 74-119).
- UDev tags the exact UIO device (lines 122-129).
- No snap-instance-specific names are involved.

**Reasoning**: UIO access is tied to the declared hardware node. Parallel instances are just concurrent consumers of the same or different UIO devices, with no snapd instance collision.

**Verification:** No verification has yet been done.

### usb-gadget
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- This interface is mount-heavy and uses `plug.Snap()` to expand `where` paths for FunctionFS mounts (lines 160-225).
- `expandMountWhereVariable()` is used to resolve mount targets from the plug snap's identity (line 205), keeping paths instance-aware where needed.
- The interface validates persistent mount targets so they cannot be under `$SNAP_DATA` or `$SNAP_USER_DATA` (lines 74-81).
- The code is careful to use the slot/plug attributes rather than hardcoded snap names.

**Reasoning**: USB gadget setup is based on the configured function mounts and device controller, not on snap instance naming. The path expansion and mount generation appear to be driven by snap identity in the intended direction.

**Verification:** No verification has yet been done.

### vcio
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 29-34), with implicit slots on core and classic (lines 59-60).
- AppArmor grants access to `/dev/vcio` and related sysfs/udev data (lines 37-49).
- UDev tags the `vcio` device (lines 51-53).
- No snap-instance-specific names or paths are used.

**Reasoning**: VideoCore I/O is a global device interface. Parallel instances can share the same hardware access without instance-scoped conflicts in the policy code.

**Verification:** No verification has yet been done.

### udisks2
**Status: NOT COMPATIBLE (slot-side system singleton); COMPATIBLE (plug-side)**

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

**Reasoning**: Same as bluez/network-manager. The D-Bus name
`org.freedesktop.UDisks2` is a freedesktop.org specification singleton. The shared
`/run/udisks2/` runtime directory would cause data corruption between parallel
instances. Plug-side (querying disk info) works fine since it's just a D-Bus client.

**Verification**:
```diff
diff --git a/tests/main/interfaces-udisks2/task.yaml b/tests/main/interfaces-udisks2/task.yaml
index 64fbaee8ab..b748bbe1af 100644
--- a/tests/main/interfaces-udisks2/task.yaml
+++ b/tests/main/interfaces-udisks2/task.yaml
@@ -10,6 +10,7 @@ environment:
     FS_PATH: "$(pwd)/dev0-fake0"
 
 prepare: |
+    snap set system experimental.parallel-instances=true
     snap install test-snapd-udisks2
 
 restore: |
@@ -17,6 +18,8 @@ restore: |
     if [ -n "$device" ]; then
         udisksctl loop-delete -b "$device"
     fi
+    snap remove --purge test-snapd-udisks2_foo || true
+    snap set system experimental.parallel-instances=null
 
 execute: |
     echo "The interface is not connected by default"
@@ -58,3 +61,22 @@ execute: |
         exit 1
     fi
     MATCH "Permission denied" < call.error
+
+    echo "When a parallel install of the snap is installed"
+    # NOTE: The udisks2 slot is provided by the system (implicit slot).
+    # We test plug-side only -- the parallel snap is just another D-Bus client.
+    snap install test-snapd-udisks2_foo
+    snap connect test-snapd-udisks2_foo:udisks2
+
+    echo "Then the parallel snap can check udisks2 status"
+    test-snapd-udisks2_foo.udisksctl status | MATCH "MODEL"
+
+    echo "And the parallel snap can dump udisks objects"
+    test-snapd-udisks2_foo.udisksctl dump | MATCH "org.freedesktop.UDisks2.Manager"
+
+    echo "When the original snap is removed"
+    snap remove --purge test-snapd-udisks2
+
+    echo "Then the parallel snap can still check udisks2 status"
+    test-snapd-udisks2_foo.udisksctl status | MATCH "MODEL"
+    test-snapd-udisks2_foo.udisksctl dump | MATCH "org.freedesktop.UDisks2.Manager"
```
- **Results:** PASSED on noble (plug-side). Parallel `test-snapd-udisks2_foo`
queried disk status and objects via the system's UDisks2 service; survived removal
of original snap.

---

### upower-observe
**Status: NOT COMPATIBLE (slot-side D-Bus singleton); COMPATIBLE (plug-side)**

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

**Reasoning**: Same singleton pattern as bluez/udisks2/network-manager. The `org.freedesktop.UPower`
D-Bus name is defined by the freedesktop spec. For plug-side (reading battery/power
info from the system), parallel instances work fine since they're just D-Bus clients.
For slot-side (providing the UPower service), only one instance can operate.

**Verification**:
```diff
diff --git a/tests/main/interfaces-upower-observe/task.yaml b/tests/main/interfaces-upower-observe/task.yaml
index d551054fd4..11b7f229bc 100644
--- a/tests/main/interfaces-upower-observe/task.yaml
+++ b/tests/main/interfaces-upower-observe/task.yaml
@@ -22,6 +22,7 @@ systems:
 
 prepare: |
     echo "Given a snap declaring a plug on the upower-observe interface is installed"
+    snap set system experimental.parallel-instances=true
     snap install --edge test-snapd-upower-observe-consumer
 
     if os.query is-core; then
@@ -29,6 +30,10 @@ prepare: |
         snap install test-snapd-upower --edge
     fi
 
+restore: |
+    snap remove --purge test-snapd-upower-observe-consumer_foo || true
+    snap set system experimental.parallel-instances=null
+
 execute: |
     SLOT_PROVIDER=
     SLOT_NAME=upower-observe
@@ -57,3 +62,18 @@ execute: |
         exit 1
     fi
     MATCH "Permission denied" < upower.error
+
+    echo "When a parallel install of the snap is installed"
+    # NOTE: The upower-observe slot is provided by the system on classic (implicit
+    # slot). We test plug-side only -- the parallel snap is another D-Bus client.
+    snap install --edge test-snapd-upower-observe-consumer_foo
+
+    echo "Then the parallel snap can dump info about the upower devices"
+    expected="/org/freedesktop/UPower/devices/DisplayDevice.*"
+    retry -n 20 --wait 1 sh -c "test-snapd-upower-observe-consumer_foo.upower --dump | MATCH \"$expected\""
+
+    echo "When the original snap is removed"
+    snap remove --purge test-snapd-upower-observe-consumer
+
+    echo "Then the parallel snap can still dump upower info"
+    test-snapd-upower-observe-consumer_foo.upower --dump | MATCH "$expected"
```
- **Results:** PASSED on noble.

---

### ofono
**Status: NOT COMPATIBLE (slot-side D-Bus singleton)**

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

**Reasoning**: System singleton. The D-Bus name `org.ofono` plus shared `/run/ofono/`
runtime state make this fundamentally single-instance. Additionally, the hardware
device paths (`/dev/tty*`, `/dev/modem*`) are global physical resources.

**Verification**: No spread test exists for this interface. Cannot write a parallel
instance test because there is no test snap or hardware emulation available. The
incompatibility is confirmed by code analysis only (D-Bus singleton `org.ofono` at
`ofono.go:123-125`).

---

### modem-manager
**Status: NOT COMPATIBLE (slot-side D-Bus singleton)**

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

**Reasoning**: Same as ofono -- system singleton. The D-Bus name
`org.freedesktop.ModemManager1` is a freedesktop.org specification singleton. Shared
device and runtime paths make parallel slot providers impossible.

**Verification**: No spread test exists for this interface. Cannot write a parallel
instance test because there is no test snap or modem hardware emulation available. The
incompatibility is confirmed by code analysis only (D-Bus singleton
`org.freedesktop.ModemManager1` at `modem_manager.go:106-108`).

---

### unity7
**Status: NOT COMPATIBLE (known documented D-Bus path leakage between instances)**

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

**Reasoning**: This is a known, documented code issue. The D-Bus path pattern
`/com/canonical/indicator/messages/###UNITY_SNAP_NAME###_*_desktop` uses
`DesktopPrefix()` which for the base instance produces `snapname`, and the `_*_`
wildcard inadvertently matches parallel instances' indicator paths. This breaks D-Bus
path isolation between parallel instances -- the base snap can receive D-Bus messages
intended for `snap_foo`'s indicator.

**Verification**: No dedicated spread test exists for this interface's parallel-install
issue. The bug is a D-Bus path wildcard leakage (information leak, not a hard failure),
which would require a custom test with two snap instances and D-Bus introspection to
demonstrate. The incompatibility is confirmed by the explicit code comment at
`unity7.go:679-681` acknowledging the issue.

---

## Content Interface

### content
**Status: COMPATIBLE**

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

**Reasoning**: The content interface deliberately uses `PerspectiveOther` when referring
to another snap's paths and `PerspectiveSelf` when referring to the consumer's own mount
target. This means:
- `plug_foo` connecting to `slot_foo` works -- source uses `slot_foo` instance paths
- `plug_foo` connecting to `slot` (non-parallel) also works -- source uses `slot` paths
- Mount paths don't collide between `plug` and `plug_foo` because each has its own
  mount namespace

**Verification**: 
```diff
diff --git a/tests/main/interfaces-content/task.yaml b/tests/main/interfaces-content/task.yaml
index 517d7ce143..8fe3971d04 100644
--- a/tests/main/interfaces-content/task.yaml
+++ b/tests/main/interfaces-content/task.yaml
@@ -15,6 +15,8 @@ backends: [-autopkgtest]
 systems: [-ubuntu-core-16-*]
 
 execute: |
+    snap set system experimental.parallel-instances=true
+
     echo "When a snap declaring a content sharing plug is installed"
     snap install --edge test-snapd-content-plug
 
@@ -46,3 +48,21 @@ execute: |
 
     echo "Then the fstab files are recreated"
     [ "$(find /var/lib/snapd/mount -type f -name "*.fstab" | wc -l)" -gt 0 ]
+
+    echo "When a parallel install of the plug snap is installed"
+    snap install --edge test-snapd-content-plug_foo
+
+    echo "Then the parallel snap can also use the shared content"
+    test-snapd-content-plug_foo.content-plug | grep "Some shared content"
+
+    echo "When the original plug snap is removed"
+    snap remove --purge test-snapd-content-plug
+
+    echo "Then the parallel snap can still access shared content"
+    test-snapd-content-plug_foo.content-plug | grep "Some shared content"
+
+restore: |
+    snap remove --purge test-snapd-content-plug_foo || true
+    snap remove --purge test-snapd-content-plug || true
+    snap remove --purge test-snapd-content-slot || true
+    snap set system experimental.parallel-instances=null
```
- Result: PASSED on noble. Parallel plug `_foo` connected to same slot provider,
read shared content, survived removal of original plug snap.

---

## File System Interfaces

### home
**Status: COMPATIBLE**

**Code analysis:**
- AppArmor rules use `owner @{HOME}/` patterns that don't distinguish instances
- Both instances access the same home directory files, which is the intended behavior
- The `@{HOME}/snap/` exclusion pattern prevents access to other snaps' data, but
  parallel instances of the same snap share data directories (by design of the parallel
  install feature)

**Verification:**
```diff
diff --git a/tests/main/interfaces-home/task.yaml b/tests/main/interfaces-home/task.yaml
@@ prepare: |
+    snap set system experimental.parallel-instances=true
@@ restore: |
+    snap remove --purge home-consumer_foo || true
+    snap set system experimental.parallel-instances=null
@@ execute: |
+    echo "When a parallel install of the snap is installed"
+    "$TESTSTOOLS"/snaps-state install-local-as home-consumer home-consumer_foo
+
+    echo "The parallel snap can read home files"
+    home-consumer_foo.reader "$READABLE_FILE" | grep -Pqz ok
+
+    echo "When the original snap is removed"
+    snap remove --purge home-consumer
+
+    echo "Then the parallel snap can still read home files"
+    home-consumer_foo.reader "$READABLE_FILE" | grep -Pqz ok
```
- **Result**: PASSED on noble.

---

### desktop-launch
**Status: PARTIALLY COMPATIBLE (API access works; desktop file launching does NOT)**

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

**Reasoning**: This is a design tension: `_` separates snap name from desktop file name,
so a parallel instance `snap_key` can't use `_` again for the instance key without
ambiguity. The `+` workaround allows file creation but breaks the userd lookup.

**Verification:**
```diff
diff --git a/tests/main/interfaces-desktop-launch/task.yaml b/tests/main/interfaces-desktop-launch/task.yaml
index 11928e63e5..dd0aef0df8 100644
--- a/tests/main/interfaces-desktop-launch/task.yaml
+++ b/tests/main/interfaces-desktop-launch/task.yaml
@@ -13,6 +13,7 @@ skip:
 
 prepare: |
     snap remove --purge api-client || true
+    snap set system experimental.parallel-instances=true
     tests.session -u test prepare
     tests.session -u test exec systemctl --user \
       set-environment XDG_DATA_DIRS=/usr/share:/var/lib/snapd/desktop
@@ -20,6 +21,10 @@ prepare: |
 restore: |
     tests.session -u test restore
     rm -f ~test/snap/test-app/current/launch-data.txt
+    snap remove --purge api-client_foo || true
+    snap remove --purge test-app_foo || true
+    snap remove --purge test-launcher_foo || true
+    snap set system experimental.parallel-instances=null
 
 execute: |
     "$TESTSTOOLS"/snaps-state install-local api-client
@@ -67,3 +72,28 @@ execute: |
 
     echo "Check that snap can access /v2/snaps"
     api-client --socket /run/snapd-snap.socket "/v2/snaps" | gojq '."status-code"' | MATCH '^200$'
+
+    echo "Install parallel instances"
+    "$TESTSTOOLS"/snaps-state install-local-as api-client api-client_foo
+    "$TESTSTOOLS"/snaps-state install-local-as test-app test-app_foo
+    "$TESTSTOOLS"/snaps-state install-local-as test-launcher test-launcher_foo
+
+    echo "Connect the parallel api-client desktop-launch plug"
+    snap connect api-client_foo:desktop-launch
+
+    echo "The parallel snap can access /v2/snaps/{name}"
+    api-client_foo --socket /run/snapd-snap.socket "/v2/snaps/snapd" | gojq '."status-code"' | MATCH '^200$'
+
+    echo "The parallel snap can access /v2/snaps"
+    api-client_foo --socket /run/snapd-snap.socket "/v2/snaps" | gojq '."status-code"' | MATCH '^200$'
+
+    echo "When the original api-client is removed"
+    snap remove --purge api-client
+
+    echo "Then the parallel snap can still access the API"
+    api-client_foo --socket /run/snapd-snap.socket "/v2/snaps/snapd" | gojq '."status-code"' | MATCH '^200$'
+
+    echo "The parallel launcher snap can launch the parallel application snap"
+    snap connect test-launcher_foo:desktop-launch
+    tests.session -u test exec test-launcher_foo \
+        test-app_foo_test-app.desktop
```
- **Result**: Expected failure -- desktop file launching is incompatible with parallel
  instances. The error is: `Error org.freedesktop.DBus.Error.Failed: cannot find desktop
  file for "test-app_foo_test-app.desktop"`. API access (tested above the launch
  attempt) works correctly.

---

### desktop-document-portal
**Status: COMPATIBLE**

**Code analysis:**
- The document portal mounts a per-snap subtree of the xdg-desktop-portal FUSE
  filesystem over `$XDG_RUNTIME_DIR/doc` inside the snap's sandbox
- The per-snap directory uses instance-aware naming:
  `by-app/snap.INSTANCE_NAME` -- snapd's mount namespace setup correctly scopes
  this to the instance name
- The snap sees only its own confined directory, not the unconfined parent

**Reasoning**: The document portal is inherently per-snap-instance. Each instance
gets its own `by-app/snap.INSTANCE_NAME` directory mounted, providing proper
isolation. A parallel instance gets its own portal mount.

**Verification:**
```diff
diff --git a/tests/main/interfaces-desktop-document-portal/task.yaml b/tests/main/interfaces-desktop-document-portal/task.yaml
index b0b79d30b6..5c0364ea10 100644
--- a/tests/main/interfaces-desktop-document-portal/task.yaml
+++ b/tests/main/interfaces-desktop-document-portal/task.yaml
@@ -10,6 +10,7 @@ details: |
 systems: [-ubuntu-core-*,-ubuntu-14.04*]
 
 prepare: |
+    snap set system experimental.parallel-instances=true
     "$TESTSTOOLS"/snaps-state install-local test-snapd-desktop
     snap disconnect test-snapd-desktop:desktop
 
@@ -17,7 +18,9 @@ prepare: |
     tests.cleanup defer tests.session -u test restore
 
 restore: |
-    rm -f /tmp/check-doc-portal.sh
+    rm -f /tmp/check-doc-portal.sh /tmp/check-doc-portal-foo.sh
+    snap remove --purge test-snapd-desktop_foo || true
+    snap set system experimental.parallel-instances=null
 
 execute: |
     cat << EOF > /tmp/check-doc-portal.sh
@@ -55,3 +58,29 @@ execute: |
       exit 1
     fi
     MATCH "No such file or directory" < check.error
+
+    echo "When a parallel install of the snap is installed"
+    "$TESTSTOOLS"/snaps-state install-local-as test-snapd-desktop test-snapd-desktop_foo
+    snap disconnect test-snapd-desktop_foo:desktop
+
+    cat << 'EOF' > /tmp/check-doc-portal-foo.sh
+    set -eu
+    mkdir -p /run/user/12345/doc/by-app/snap.test-snapd-desktop_foo
+    touch /run/user/12345/doc/is-unconfined
+    touch /run/user/12345/doc/by-app/snap.test-snapd-desktop_foo/is-confined
+    test-snapd-desktop_foo.check-dirs /run/user/12345/doc
+    EOF
+    chown test:test /tmp/check-doc-portal-foo.sh
+
+    snapd.tool exec snap-discard-ns test-snapd-desktop_foo
+
+    echo "With desktop connected on the parallel instance, we see confined version"
+    snap connect test-snapd-desktop_foo:desktop
+    tests.session -u test exec sh /tmp/check-doc-portal-foo.sh | MATCH is-confined
+
+    echo "When the original snap is removed"
+    snap remove --purge test-snapd-desktop
+
+    echo "Then the parallel snap still sees the confined version"
+    snapd.tool exec snap-discard-ns test-snapd-desktop_foo
+    tests.session -u test exec sh /tmp/check-doc-portal-foo.sh | MATCH is-confined
```
- **Result**: PASSED on noble.

---

### cups-control
**Status: COMPATIBLE (not verified)**

**Code analysis:**
- Access to CUPS socket and D-Bus for printing
- Multiple instances can submit print jobs simultaneously
- No global resource contention from plug side

**Verification:**
- **Result**: FAILED -- pre-existing environment issue (no CUPS printer configured).
  Failure occurs at `lpr: Error - No default destination` in the original test code
  before any parallel-instance section. Unrelated to parallel installs. Needs a test
  environment with a configured CUPS printer.

---

### cups (provider/consumer interface)
**Status: NOT COMPATIBLE (slot-side path expansion bug) COMPATIBLE (plug-side)**

**Code analysis:**
The `cups` interface (distinct from `cups-control`) allows a snap to provide CUPS print
services to consuming snaps via a socket bind-mount.

1. **Socket path resolution uses wrong perspective** (`cups.go:130`): The slot's
   `cups-socket-directory` attribute is expanded via `ExpandSnapVariables()` which uses
   `PerspectiveSelf` (calls `SnapName()`, not `InstanceName()`):
   ```go
   return snapInfo.ExpandSnapVariables(cupsdSocketSourceDir), nil
   ```
   For a parallel slot provider `cups-provider_foo` with `cups-socket-directory:
   $SNAP_COMMON/cups-socket`, this expands to `/var/snap/cups-provider/common/cups-socket`
   instead of `/var/snap/cups-provider_foo/common/cups-socket`.

2. **Mount entry uses the wrong source path** (`cups.go:188-206`): `MountConnectedPlug`
   creates a bind mount from the (incorrectly expanded) source path to `/var/cups/` in
   the plug's namespace. A parallel slot provider's socket directory would be at the
   instance-specific host path, but the mount entry points to the base snap name path.

3. **No D-Bus usage**: The cups interface has zero D-Bus rules. It communicates
   exclusively via UNIX sockets.

4. **No LabelExpression usage**: Unlike most slot/plug interfaces, `cups` doesn't use
   `LabelExpression()` or `###SLOT_SECURITY_TAGS###` for peer matching. Access is
   purely path-based.

5. **Contrast with content interface**: The `content` interface correctly uses
   `PerspectiveOther` when resolving the slot provider's paths (`content.go:234`). The
   `cups` interface does not -- this is likely a bug.

**Reasoning**: The socket path expansion bug means a parallel-installed CUPS provider's
actual socket directory (at the instance-specific host path) doesn't match what the
plug's AppArmor rules and mount entries reference. The plug would try to bind-mount
from a non-existent or wrong directory.

**Verification**: 
```diff
diff --git a/tests/main/interfaces-cups/task.yaml b/tests/main/interfaces-cups/task.yaml
index 127e63400b..82cdb013ef 100644
--- a/tests/main/interfaces-cups/task.yaml
+++ b/tests/main/interfaces-cups/task.yaml
@@ -19,6 +19,7 @@ systems:
 
 prepare: |
     # install the test snaps
+    snap set system experimental.parallel-instances=true
 
     # source for this snap:
     # https://github.com/anonymouse64/test-snapd-cups-consumer
@@ -45,6 +46,8 @@ restore: |
     if [ -e /run/cups.orig ]; then
         mv /run/cups.orig /run/cups
     fi
+    snap remove --purge test-snapd-cups-consumer_foo || true
+    snap set system experimental.parallel-instances=null
 
 execute: |
     echo "The provider can create the socket and any other files"
@@ -115,3 +118,24 @@ execute: |
     echo "And the environment variable is not set"
     #shellcheck disable=SC2016
     test-snapd-cups-consumer.bin -c 'echo $CUPS_SERVER' | NOMATCH /var/cups/cups.sock
+
+    echo "When a parallel install of the consumer snap is installed"
+    snap install --edge test-snapd-cups-consumer_foo
+
+    echo "Connect the parallel consumer's cups interface to the provider"
+    snap connect test-snapd-cups-consumer_foo:cups test-snapd-cups-provider:cups
+
+    echo "The parallel consumer can write to the cups socket"
+    #shellcheck disable=SC2016
+    echo hello-foo | test-snapd-cups-consumer_foo.cups -c 'nc -q 1 -U $CUPS_SERVER' > cups-foo-response.txt
+
+    echo "And the cups server sends a response"
+    MATCH hello-foo < cups-foo-response.txt
+
+    echo "When the original consumer snap is removed"
+    snap remove --purge test-snapd-cups-consumer
+
+    echo "Then the parallel consumer can still communicate via the cups socket"
+    #shellcheck disable=SC2016
+    echo still-works | test-snapd-cups-consumer_foo.cups -c 'nc -q 1 -U $CUPS_SERVER' > cups-foo-response2.txt
+    MATCH still-works < cups-foo-response2.txt
```
- **Results:** PASSED on noble (plug-side consumer). Parallel `test-snapd-cups-consumer_foo`
connected to the provider's cups socket via `$CUPS_SERVER` and communicated successfully;
survived removal of original consumer snap. Note: parallel *provider* not tested -- the
`cups.go:130` bug would only manifest with a parallel provider snap.

---

### polkit
**Status: COMPATIBLE**

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

**Reasoning**: The interface is structurally compatible -- file names don't collide, D-Bus
access is client-only, and the backend correctly uses `InstanceName()`. The action ID
duplication caveat is minor and unlikely to cause functional failures.

**Verification**:
```diff
diff --git a/tests/main/interfaces-polkit/task.yaml b/tests/main/interfaces-polkit/task.yaml
index c560bfb31e..fdb668719c 100644
--- a/tests/main/interfaces-polkit/task.yaml
+++ b/tests/main/interfaces-polkit/task.yaml
@@ -24,11 +24,14 @@ skip:
       if: not tests.session has-session-systemd-and-dbus
 
 prepare: |
+    snap set system experimental.parallel-instances=true
     tests.session -u test prepare
 
 restore: |
     rm -f /home/test/sleep.stamp
     tests.session -u test restore
+    snap remove --purge test-snapd-polkit_foo || true
+    snap set system experimental.parallel-instances=null
 
 execute: |
     echo "Install the test snap"
@@ -89,3 +92,41 @@ execute: |
         echo "The contents match the file provided by the snap"
         cmp /etc/polkit-1/rules.d/70-snap.test-snapd-polkit.polkit-rule.bar.rules "$snap_mount_dir"/test-snapd-polkit/current/meta/polkit/polkit-rule.bar.rules
     fi
+
+    echo "When a parallel install of the snap is installed"
+    # NOTE: The polkit slot is provided by the system (implicit slot).
+    # We test plug-side only -- verifying file names are instance-aware.
+    snap install --edge test-snapd-polkit_foo
+
+    if ! os.query is-core; then
+        echo "The parallel snap's polkit-action plug can be connected"
+        snap connect test-snapd-polkit_foo:polkit-action
+
+        echo "The parallel snap's policy file is installed with an instance-specific name"
+        test -f /usr/share/polkit-1/actions/snap.test-snapd-polkit_foo.interface.polkit-action.foo.policy
+
+        echo "The original snap's policy file still exists"
+        test -f /usr/share/polkit-1/actions/snap.test-snapd-polkit.interface.polkit-action.foo.policy
+    fi
+
+    if ! os.query is-ubuntu-le 22.04 && ! os.query is-debian 11; then
+        echo "The parallel snap's polkit-rule plug can be connected"
+        snap connect test-snapd-polkit_foo:polkit-rule
+
+        echo "The parallel snap's rule file is installed with an instance-specific name"
+        test -f /etc/polkit-1/rules.d/70-snap.test-snapd-polkit_foo.polkit-rule.bar.rules
+
+        echo "The original snap's rule file still exists"
+        test -f /etc/polkit-1/rules.d/70-snap.test-snapd-polkit.polkit-rule.bar.rules
+    fi
+
+    echo "When the original snap is removed"
+    snap remove --purge test-snapd-polkit
+
+    if ! os.query is-core; then
+        echo "Then the parallel snap's policy file still exists"
+        test -f /usr/share/polkit-1/actions/snap.test-snapd-polkit_foo.interface.polkit-action.foo.policy
+
+        echo "And the original snap's policy file is gone"
+        test ! -f /usr/share/polkit-1/actions/snap.test-snapd-polkit.interface.polkit-action.foo.policy
+    fi
``` 
- **Results:** PASSED on noble (plug-side). Parallel `test-snapd-polkit_foo` installed
instance-specific policy and rule files (e.g.,
`snap.test-snapd-polkit_foo.interface.polkit-action.foo.policy`) alongside the
original's files. After removing the original, the `_foo` files persisted and the
original's files were cleaned up.

---

### firewall-control
**Status: COMPATIBLE**

**Code analysis:**
- Grants capability to manipulate iptables/nftables rules
- AppArmor rules are purely capability-based (no snap-name-dependent paths)
- No D-Bus ownership, no shared memory, no instance-specific paths
- Multiple instances get the same system-level firewall access

**Reasoning**: Firewall manipulation is a global system capability. Multiple instances
with the plug connected can all modify iptables, same as multiple different snaps with
firewall-control. No snap-name-scoped resources involved.

**Verification:**
```diff
diff --git a/tests/main/interfaces-firewall-control/task.yaml b/tests/main/interfaces-firewall-control/task.yaml
index 5c05147971..164a21fc97 100644
--- a/tests/main/interfaces-firewall-control/task.yaml
+++ b/tests/main/interfaces-firewall-control/task.yaml
@@ -24,6 +24,7 @@ environment:
 
 prepare: |
     echo "Given a snap declaring a plug on the firewall-control interface is installed"
+    snap set system experimental.parallel-instances=true
     "$TESTSTOOLS"/snaps-state install-local firewall-control-consumer
 
     echo "And a service is listening"
@@ -43,6 +44,8 @@ restore: |
         systemctl stop "$SERVICE_NAME"
     fi
     rm -f "$REQUEST_FILE"
+    snap remove --purge firewall-control-consumer_foo || true
+    snap set system experimental.parallel-instances=null
 
 execute: |
     echo "Then the plug is disconnected by default"
@@ -76,3 +79,25 @@ execute: |
         exit 1
     fi
     MATCH "Permission denied" < firewall-create.error
+
+    echo "When a parallel install of the snap is installed"
+    "$TESTSTOOLS"/snaps-state install-local-as firewall-control-consumer firewall-control-consumer_foo
+    snap connect firewall-control-consumer_foo:firewall-control
+
+    echo "Then the parallel snap can create a firewall rule"
+    firewall-control-consumer_foo.create
+
+    echo "And the service is accessible through the destination IP"
+    nc -w 2 "$DESTINATION_IP" "$PORT" < "$REQUEST_FILE" | MATCH 'ok$'
+
+    echo "And the parallel snap can delete the firewall rule"
+    firewall-control-consumer_foo.delete
+
+    echo "When the original snap is removed"
+    snap remove --purge firewall-control-consumer
+
+    echo "Then the parallel snap can still create and delete firewall rules"
+    firewall-control-consumer_foo.create
+    nc -w 2 "$DESTINATION_IP" "$PORT" < "$REQUEST_FILE" | MATCH 'ok$'
+    firewall-control-consumer_foo.delete
+    not nc -w 2 "$DESTINATION_IP" "$PORT" < "$REQUEST_FILE"
```
- **Result**: PASSED on noble.

---

### ssh-keys
**Status: COMPATIBLE**

**Code analysis:**
- Read/write access to `~/.ssh/` files
- No shared memory, no D-Bus, no instance-specific paths
- Multiple instances reading/writing SSH keys is the same as having SSH access

**Verification:**
```diff

```
- **Result**: PASSED on noble.

---

### ssh-public-keys
**Status: COMPATIBLE**

**Code analysis:**
- Read access to SSH public keys (`~/.ssh/*.pub`, `/etc/ssh/ssh_host_*_key.pub`)
- No shared memory, no D-Bus, no writes to global resources

**Verification:**
```diff
diff --git a/tests/main/interfaces-ssh-public-keys/task.yaml b/tests/main/interfaces-ssh-public-keys/task.yaml
index cb07794b9e..19a278ea45 100644
--- a/tests/main/interfaces-ssh-public-keys/task.yaml
+++ b/tests/main/interfaces-ssh-public-keys/task.yaml
@@ -13,6 +13,7 @@ environment:
 
 
 prepare: |
+    snap set system experimental.parallel-instances=true
     "$TESTSTOOLS"/snaps-state install-local test-snapd-sh
 
     "$TESTSTOOLS"/fs-state mock-dir "$KEYSDIR"
@@ -27,6 +28,8 @@ prepare: |
 
 
 restore: |
+    snap remove --purge test-snapd-sh_foo || true
+    snap set system experimental.parallel-instances=null
     "$TESTSTOOLS"/fs-state restore-dir "$KEYSDIR"
     "$TESTSTOOLS"/fs-state restore-file "$TESTKEY_HOST_ECDSA"
     "$TESTSTOOLS"/fs-state restore-file "$TESTKEY_HOST_ECDSA".pub
@@ -64,16 +67,29 @@ execute: |
     fi
     MATCH "Permission denied" < call.error
 
-    echo "Then the snap is not able to access the ssh private host keys"
-    not test-snapd-sh.with-ssh-public-keys-plug -c "cat $TESTKEY_HOST_ECDSA"
-    not test-snapd-sh.with-ssh-public-keys-plug -c "cat $TESTKEY_HOST_RSA"
-    not test-snapd-sh.with-ssh-public-keys-plug -c "cat $TESTKEY_HOST_ED25519"
+    echo "When a parallel install of the snap is installed"
+    "$TESTSTOOLS"/snaps-state install-local-as test-snapd-sh test-snapd-sh_foo
+    snap connect test-snapd-sh_foo:ssh-public-keys
+
+    echo "Then the parallel snap is able to see ssh version"
+    test-snapd-sh_foo.with-ssh-public-keys-plug -c "ssh -V"
+
+    echo "When the original snap is removed"
+    snap remove --purge test-snapd-sh
+
+    echo "Then the parallel snap is still able to access the ssh public keys"
+    test-snapd-sh_foo.with-ssh-public-keys-plug -c "cat $TESTKEY.pub"
+
+    echo "Then the parallel snap is not able to access the ssh private host keys"
+    not test-snapd-sh_foo.with-ssh-public-keys-plug -c "cat $TESTKEY_HOST_ECDSA"
+    not test-snapd-sh_foo.with-ssh-public-keys-plug -c "cat $TESTKEY_HOST_RSA"
+    not test-snapd-sh_foo.with-ssh-public-keys-plug -c "cat $TESTKEY_HOST_ED25519"
 
     echo "When the plug is disconnected"
-    snap disconnect test-snapd-sh:ssh-public-keys
+    snap disconnect test-snapd-sh_foo:ssh-public-keys
     
     echo "Then the snap is not able to access the ssh public keys"
-    if test-snapd-sh.with-ssh-public-keys-plug -c "cat $TESTKEY.pub" 2> call.error; then
+    if test-snapd-sh_foo.with-ssh-public-keys-plug -c "cat $TESTKEY.pub" 2> call.error; then
         echo "Expected permission error accessing to ssh"
         exit 1
     fi

```
- **Result**: PASSED on noble.

---

### personal-files
**Status: COMPATIBLE**

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

**Reasoning**: personal-files grants access to user-owned paths that are completely
outside the snap's data directories. Two parallel instances accessing the same user
files is identical to two different snaps with the same personal-files declaration.
No snap-name-dependent paths are involved.

**Verification**: 
```diff
diff --git a/tests/main/interfaces-personal-files/task.yaml b/tests/main/interfaces-personal-files/task.yaml
index 11e7568436..8b737a51a2 100644
--- a/tests/main/interfaces-personal-files/task.yaml
+++ b/tests/main/interfaces-personal-files/task.yaml
@@ -13,6 +13,7 @@ environment:
     ROOT_OWNED_DIR: /etc
 
 prepare: |
+    snap set system experimental.parallel-instances=true
     "$TESTSTOOLS"/snaps-state install-local test-snapd-sh
 
     # First layer of dirs and files
@@ -70,6 +71,8 @@ restore: |
     "$TESTSTOOLS"/fs-state restore-dir /var/tmp/root
     rm -rf "$TEST_USER_HOME/.testdir1"
     rm -rf "$TEST_USER_HOME/.missing/testdir1"
+    snap remove --purge test-snapd-sh_foo || true
+    snap set system experimental.parallel-instances=null
 
 execute: |
     echo "The interface is not connected by default"
@@ -187,3 +190,19 @@ execute: |
         exit 1
     fi
     MATCH "Permission denied" < call.error
+
+    echo "When a parallel install of the snap is installed"
+    "$TESTSTOOLS"/snaps-state install-local-as test-snapd-sh test-snapd-sh_foo
+    snap connect test-snapd-sh_foo:personal-files
+
+    echo "Then the parallel snap is able to access personal files"
+    test-snapd-sh_foo.with-personal-files-plug -c "cat /root/.testfile1" | MATCH "mock file"
+    test-snapd-sh_foo.with-personal-files-plug -c "ls /root/.testdir1"
+    test-snapd-sh_foo.with-personal-files-plug -c "echo test >> /root/.testfile1"
+
+    echo "When the original snap is removed"
+    snap remove --purge test-snapd-sh
+
+    echo "Then the parallel snap can still access personal files"
+    test-snapd-sh_foo.with-personal-files-plug -c "cat /root/.testfile1" | MATCH "mock file"
+    test-snapd-sh_foo.with-personal-files-plug -c "ls /root/.testdir1"
```
-Result: PASSED on noble. Parallel instance read/wrote same personal files,
survived removal of original snap.

---

### system-files
**Status: COMPATIBLE**

**Code analysis:**
Same implementation as personal-files (both use `commonFilesInterface` in
`common_files.go`).

1. **Paths are absolute system paths** from plug attributes (e.g., `/etc/foo`,
   `/var/lib/bar`). No snap-name variables.

2. **AppArmor rules are snap-name-agnostic**: Same as personal-files -- raw paths are
   used directly in the AppArmor snippet.

3. **No instance-specific scoping**: Both instances get the same rules.

**Reasoning**: system-files grants access to fixed system paths. No snap-name-dependent
resources are involved. Two parallel instances can access the same system files without
conflict at the interface level (though they could conflict at the application level if
both write to the same file).

**Verification**: 
```diff
diff --git a/tests/main/interfaces-system-files/task.yaml b/tests/main/interfaces-system-files/task.yaml
index f5eccef87b..fe140f7776 100644
--- a/tests/main/interfaces-system-files/task.yaml
+++ b/tests/main/interfaces-system-files/task.yaml
@@ -8,6 +8,7 @@ environment:
     TESTDIR: /mnt/testdir
 
 prepare: |
+    snap set system experimental.parallel-instances=true
     "$TESTSTOOLS"/snaps-state install-local test-snapd-sh
 
     # Fist layer of dirs and files
@@ -30,6 +31,8 @@ restore: |
     "$TESTSTOOLS"/fs-state restore-dir "$TESTDIR"
     "$TESTSTOOLS"/fs-state restore-dir /root/.testdir1
     "$TESTSTOOLS"/fs-state restore-dir /root/.testfile1
+    snap remove --purge test-snapd-sh_foo || true
+    snap set system experimental.parallel-instances=null
 
 execute: |
     echo "The interface is not connected by default"
@@ -79,3 +82,20 @@ execute: |
         exit 1
     fi
     MATCH "Permission denied" < call.error
+
+    echo "When a parallel install of the snap is installed"
+    "$TESTSTOOLS"/snaps-state install-local-as test-snapd-sh test-snapd-sh_foo
+    snap connect test-snapd-sh_foo:system-files
+
+    echo "Then the parallel snap is able to access the system files"
+    test-snapd-sh_foo.with-system-files-plug -c "cat $TESTDIR/.testfile1" | MATCH "mock file"
+    test-snapd-sh_foo.with-system-files-plug -c "ls $TESTDIR/.testdir1"
+    test-snapd-sh_foo.with-system-files-plug -c "echo test >> $TESTDIR/.testfile1"
+    test-snapd-sh_foo.with-system-files-plug -c "touch $TESTDIR/.testdir1/testfile3"
+
+    echo "When the original snap is removed"
+    snap remove --purge test-snapd-sh
+
+    echo "Then the parallel snap can still access the system files"
+    test-snapd-sh_foo.with-system-files-plug -c "cat $TESTDIR/.testfile1" | MATCH "mock file"
+    test-snapd-sh_foo.with-system-files-plug -c "ls $TESTDIR/.testdir1"
```
- **Result:** PASSED on noble. Parallel instance read/wrote same system files,
survived removal of original snap.

---

## System Configuration Interfaces

These interfaces grant access to global system configuration files and services. They
are all plug-only (system-provided implicit slot), use D-Bus as a client (send-only,
no name ownership), and have no snap-name-dependent paths. Multiple parallel instances
receive identical AppArmor/seccomp profiles and can all safely access the same global
system resources.

### hostname-control
**Status: COMPATIBLE**

**Code analysis:**
- D-Bus client to `org.freedesktop.hostname1` (send-only, `hostname_control.go:45-72`)
- Writes to `/etc/hostname`, `/etc/writable/hostname` (`hostname_control.go:35-38`)
- Has `sethostname` seccomp rule (`hostname_control.go:83-87`)
- System-provided implicit slot (`implicitOnCore: true`, `implicitOnClassic: true`)
- No `dbus (bind)`, no `DBusPermanentSlot`, no `SnapName()`/`InstanceName()` usage

**Reasoning**: Pure capability interface. All paths are global system config. No
snap-name-dependent resources. Parallel instances get identical permissions.

**Verification**: 
```diff
diff --git a/tests/main/interfaces-hostname-control/task.yaml b/tests/main/interfaces-hostname-control/task.yaml
index 58a7bcf353..2ac191901c 100644
--- a/tests/main/interfaces-hostname-control/task.yaml
+++ b/tests/main/interfaces-hostname-control/task.yaml
@@ -5,8 +5,13 @@ details: |
 
 prepare: |
     echo "Install test hostname-control snap"
+    snap set system experimental.parallel-instances=true
     "$TESTSTOOLS"/snaps-state install-local test-snapd-sh
 
+restore: |
+    snap remove --purge test-snapd-sh_foo || true
+    snap set system experimental.parallel-instances=null
+
 execute: |
     hostname="$(hostname)"
 
@@ -54,3 +59,21 @@ execute: |
     echo "And the /etc/hostname file and the hostname command are still available even without the connection."
     test-snapd-sh.with-hostname-control-plug -c "test -f /etc/hostname"
     test-snapd-sh.with-hostname-control-plug -c "test -x /bin/hostname"
+
+    echo "When a parallel install of the snap is installed"
+    "$TESTSTOOLS"/snaps-state install-local-as test-snapd-sh test-snapd-sh_foo
+    snap connect test-snapd-sh_foo:hostname-control
+
+    echo "Then the parallel snap can read the hostname"
+    snap_hostname_foo="$(test-snapd-sh_foo.with-hostname-control-plug -c "/bin/hostname")"
+    [ "$hostname" = "$snap_hostname_foo" ]
+
+    echo "And the parallel snap can set the hostname through dbus"
+    test-snapd-sh_foo.with-hostname-control-plug -c "hostnamectl set-hostname $hostname"
+
+    echo "When the original snap is removed"
+    snap remove --purge test-snapd-sh
+
+    echo "Then the parallel snap can still read and set the hostname"
+    test-snapd-sh_foo.with-hostname-control-plug -c "hostnamectl" | MATCH "$hostname"
+    test-snapd-sh_foo.with-hostname-control-plug -c "hostnamectl set-hostname $hostname"
```
- **Results:** PASSED on noble.

---

### locale-control
**Status: COMPATIBLE**

**Code analysis:**
- D-Bus client to `org.freedesktop.locale1` (send-only, `locale_control.go:41-64`)
- Writes to `/etc/default/locale` (`locale_control.go:67`)
- No seccomp snippet
- System-provided implicit slot

**Reasoning**: Simplest of the six. Pure D-Bus client + one global config file. No
snap-name-dependent resources.

**Verification**: 
```diff
diff --git a/tests/main/interfaces-locale-control/task.yaml b/tests/main/interfaces-locale-control/task.yaml
index 0fd67ba14d..ec444e452f 100644
--- a/tests/main/interfaces-locale-control/task.yaml
+++ b/tests/main/interfaces-locale-control/task.yaml
@@ -24,6 +24,7 @@ prepare: |
         fi
     fi
 
+    snap set system experimental.parallel-instances=true
     echo "Given a snap declaring a plug on the locale-control interface is installed"
     "$TESTSTOOLS"/snaps-state install-local locale-control-consumer
 
@@ -44,6 +45,8 @@ restore: |
     fi
 
     "$TESTSTOOLS"/fs-state restore-file /etc/default/locale
+    snap remove --purge locale-control-consumer_foo || true
+    snap set system experimental.parallel-instances=null
 
 execute: |
     if os.query is-core; then
@@ -96,3 +99,21 @@ execute: |
         exit 1
     fi
     MATCH "Permission denied" < locale-write.error
+
+    echo "When a parallel install of the snap is installed"
+    "$TESTSTOOLS"/snaps-state install-local-as locale-control-consumer locale-control-consumer_foo
+    snap connect locale-control-consumer_foo:locale-control
+
+    echo "Then the parallel snap can read the locale configuration"
+    locale-control-consumer_foo.get LANG
+
+    echo "And the parallel snap can write the locale configuration"
+    locale-control-consumer_foo.set LANG parallellang
+    MATCH 'LANG=\"parallellang\"' < /etc/default/locale
+
+    echo "When the original snap is removed"
+    snap remove --purge locale-control-consumer
+
+    echo "Then the parallel snap can still read and write the locale"
+    locale-control-consumer_foo.set LANG stilllang
+    MATCH 'LANG=\"stilllang\"' < /etc/default/locale
```

- **Results:** PASSED on noble.

---

### timezone-control
**Status: COMPATIBLE**

**Code analysis:**
- D-Bus client to `org.freedesktop.timedate1` (send-only, `timezone_control.go:49-83`)
- Reads `/usr/share/zoneinfo/**`, writes `/etc/timezone`, `/etc/localtime`
  (`timezone_control.go:41-45`)
- System-provided implicit slot

**Reasoning**: Global timezone configuration. No snap-name-dependent resources.

**Verification**: 
```diff
diff --git a/tests/main/interfaces-timezone-control/task.yaml b/tests/main/interfaces-timezone-control/task.yaml
index e33da6bd9d..9e1aed855e 100644
--- a/tests/main/interfaces-timezone-control/task.yaml
+++ b/tests/main/interfaces-timezone-control/task.yaml
@@ -5,6 +5,7 @@ details: |
     can access timezone information and update it.
 
 prepare: |
+    snap set system experimental.parallel-instances=true
     # Install a snap declaring a plug on timezone-control
     if systemctl is-enabled systemd-timesyncd.service ; then
         # Install the base core24 variant with timedatectl that supports systemd-timesyncd commands.
@@ -24,6 +25,8 @@ restore: |
     # localtime -> ../usr/share/zoneinfo/Etc/UTC but originally was
     # localtime -> /usr/share/zoneinfo/Etc/UTC
     "$TESTSTOOLS"/fs-state skip-monitor /etc/localtime
+    snap remove --purge test-snapd-timedate-control-consumer_foo || true
+    snap set system experimental.parallel-instances=null
 
 execute: |
     echo "The interface is disconnected by default"
@@ -72,3 +75,21 @@ execute: |
         exit 1
     fi
     MATCH "Permission denied" < call.error
+
+    echo "When a parallel install of the snap is installed"
+    "$TESTSTOOLS"/snaps-state install-local-as test-snapd-timedate-control-consumer test-snapd-timedate-control-consumer_foo
+    snap connect test-snapd-timedate-control-consumer_foo:timezone-control
+
+    echo "Then the parallel snap can get the timezone status"
+    test-snapd-timedate-control-consumer_foo.timedatectl-timezone status
+
+    echo "And the parallel snap can set the timezone"
+    test-snapd-timedate-control-consumer_foo.timedatectl-timezone set-timezone "$timezone1"
+    test "$(test-snapd-timedate-control-consumer_foo.timedatectl-timezone status | grep -oP 'Time zone: \K(.*)(?= \()')" = "$timezone1"
+
+    echo "When the original snap is removed"
+    snap remove --purge test-snapd-timedate-control-consumer
+
+    echo "Then the parallel snap can still set the timezone"
+    test-snapd-timedate-control-consumer_foo.timedatectl-timezone set-timezone "$timezone2"
+    test "$(test-snapd-timedate-control-consumer_foo.timedatectl-timezone status | grep -oP 'Time zone: \K(.*)(?= \()')" = "$timezone2"
```

- **Results:** PASSED on noble.

---

### timeserver-control
**Status: COMPATIBLE**

**Code analysis:**
- D-Bus client to `org.freedesktop.timedate1`, `org.freedesktop.timesync1`,
  `org.freedesktop.network1` (send-only, `timeserver_control.go:51-106`)
- Writes to `/etc/systemd/timesyncd.conf` (`timeserver_control.go:47`)
- System-provided implicit slot

**Reasoning**: Global NTP configuration. No snap-name-dependent resources.

**Verification**: 
```diff
diff --git a/tests/main/interfaces-timeserver-control/task.yaml b/tests/main/interfaces-timeserver-control/task.yaml
index ccd7f5af90..929dfbbf1b 100644
--- a/tests/main/interfaces-timeserver-control/task.yaml
+++ b/tests/main/interfaces-timeserver-control/task.yaml
@@ -32,6 +32,7 @@ prepare: |
     esac
 
     # Install a snap declaring a plug on timeserver-control.
+    snap set system experimental.parallel-instances=true
     if systemctl is-enabled systemd-timesyncd.service ; then
         # Install the base core20 variant with timedatectl that supports systemd-timesyncd commands.
         "$TESTSTOOLS"/snaps-state install-local-variant test-snapd-timedate-control-consumer-core24 test-snapd-timedate-control-consumer
@@ -40,6 +41,8 @@ prepare: |
         "$TESTSTOOLS"/snaps-state install-local test-snapd-timedate-control-consumer
     fi
     tests.cleanup defer snap remove --purge test-snapd-timedate-control-consumer
+    tests.cleanup defer snap remove --purge test-snapd-timedate-control-consumer_foo
+    tests.cleanup defer snap set system experimental.parallel-instances=null
 
 execute: |
     # If we cannot use network time protocol then the test is meaningless.
@@ -113,3 +116,21 @@ execute: |
         exit 1
     fi
     MATCH "Permission denied" < call.error
+
+    echo "When a parallel install of the snap is installed"
+    "$TESTSTOOLS"/snaps-state install-local-as test-snapd-timedate-control-consumer test-snapd-timedate-control-consumer_foo
+    snap connect test-snapd-timedate-control-consumer_foo:timeserver-control
+
+    echo "Then the parallel snap can get timeserver status"
+    test-snapd-timedate-control-consumer_foo.timedatectl-timeserver
+
+    echo "And the parallel snap can toggle NTP"
+    test-snapd-timedate-control-consumer_foo.timedatectl-timeserver set-ntp true
+    retry --wait 5 sh -c 'test "$(busctl get-property org.freedesktop.timedate1 /org/freedesktop/timedate1 org.freedesktop.timedate1 NTP)" = "b true"'
+
+    echo "When the original snap is removed"
+    snap remove --purge test-snapd-timedate-control-consumer
+
+    echo "Then the parallel snap can still toggle NTP"
+    test-snapd-timedate-control-consumer_foo.timedatectl-timeserver set-ntp false
+    retry --wait 5 sh -c 'test "$(busctl get-property org.freedesktop.timedate1 /org/freedesktop/timedate1 org.freedesktop.timedate1 NTP)" = "b false"'
```

- **Results:** PASSED on noble.

---

### network-setup-control
**Status: COMPATIBLE**

**Code analysis:**
- D-Bus client to `io.netplan.Netplan` (send-only, `network_setup_control.go:74-87`)
- Writes to `/etc/netplan/{,**}`, `/etc/network/{,**}`, `/etc/systemd/network/{,**}`,
  `/run/systemd/network/*` (`network_setup_control.go:38-68`)
- Executes `/usr/sbin/netplan`
- System-provided implicit slot

**Reasoning**: Global network configuration. No snap-name-dependent resources. All
paths are global system directories.

**Verification**: 
```diff
diff --git a/tests/main/interfaces-network-setup-control/task.yaml b/tests/main/interfaces-network-setup-control/task.yaml
index 5cf8f8d305..5332aaba6b 100644
--- a/tests/main/interfaces-network-setup-control/task.yaml
+++ b/tests/main/interfaces-network-setup-control/task.yaml
@@ -7,10 +7,14 @@ details: |
 systems: [-ubuntu-core-*]
 
 prepare: |
+    snap set system experimental.parallel-instances=true
     "$TESTSTOOLS"/snaps-state install-local test-snapd-sh
 
 restore: |
     rm -f /etc/network/test001 /etc/netplan/test001
+    rm -f /etc/network/test-foo /etc/netplan/test-foo
+    snap remove --purge test-snapd-sh_foo || true
+    snap set system experimental.parallel-instances=null
 
 execute: |
     dirs="/etc/netplan /etc/network"
@@ -48,3 +52,24 @@ execute: |
 
     echo "Then the interface can be connected again"
     snap connect test-snapd-sh:network-setup-control
+
+    echo "When a parallel install of the snap is installed"
+    "$TESTSTOOLS"/snaps-state install-local-as test-snapd-sh test-snapd-sh_foo
+    snap connect test-snapd-sh_foo:network-setup-control
+
+    echo "Then the parallel snap can write to netplan and network directories"
+    for dir in $dirs; do
+        if [ -d "$dir" ]; then
+            test-snapd-sh_foo.with-network-setup-control-plug -c "touch $dir/test-foo"
+        fi
+    done
+
+    echo "When the original snap is removed"
+    snap remove --purge test-snapd-sh
+
+    echo "Then the parallel snap can still write to the directories"
+    for dir in $dirs; do
+        if [ -d "$dir" ]; then
+            test-snapd-sh_foo.with-network-setup-control-plug -c "test -f $dir/test-foo"
+        fi
+    done
```

- **Results:** PASSED on noble.

---

### account-control
**Status: COMPATIBLE (code analysis -- not yet verified by test)**

**Code analysis:**
- D-Bus client to `org.freedesktop.Accounts` (send-only, `account_control.go:44-73`)
- Writes to `/var/lib/extrausers/**`, `/var/log/faillog`, `/var/log/lastlog`
  (`account_control.go:75-109`)
- Executes `useradd`, `userdel`, `chpasswd` (`account_control.go:77-80`)
- Dynamic seccomp template resolves shadow file GID at runtime -- system-global
  constant, not snap-specific (`account_control.go:114-138`)
- System-provided implicit slot

**Reasoning**: Global user account management. No snap-name-dependent resources. The
dynamic seccomp GID resolution is deterministic regardless of instance.

**Verification**:
```diff
diff --git a/tests/main/interfaces-account-control/task.yaml b/tests/main/interfaces-account-control/task.yaml
index 1f8659fe0c..08680dd93d 100644
--- a/tests/main/interfaces-account-control/task.yaml
+++ b/tests/main/interfaces-account-control/task.yaml
@@ -13,6 +13,7 @@ prepare: |
     #shellcheck source=tests/lib/core-config.sh
     . "$TESTSLIB"/core-config.sh
 
+    snap set system experimental.parallel-instances=true
     echo "Given a snap declaring a plug on account-control is installed"
     SUFFIX="$(get_test_snap_suffix)"
     "$TESTSTOOLS"/snaps-state install-local "${TSNAP}${SUFFIX}"
@@ -25,11 +26,14 @@ restore: |
     . "$TESTSLIB"/core-config.sh
     SUFFIX="$(get_test_snap_suffix)"
 
-    echo "Ensure alice is gone from the system"
+    echo "Ensure alice and bob are gone from the system"
     for f in /var/lib/extrausers/*; do
         sed -i '/^alice:/d' "$f"
+        sed -i '/^bob:/d' "$f"
     done
-    snap remove --purge "${TSNAP}${SUFFIX}"
+    snap remove --purge "${TSNAP}${SUFFIX}" || true
+    snap remove --purge "${TSNAP}${SUFFIX}_foo" || true
+    snap set system experimental.parallel-instances=null
 
 execute: |
     #shellcheck source=tests/lib/core-config.sh
@@ -43,3 +47,17 @@ execute: |
     echo alice:password | snap run "${TSNAP}${SUFFIX}".chpasswd
 
     snap run "${TSNAP}${SUFFIX}".userdel --extrausers alice
+
+    echo "When a parallel install of the snap is installed"
+    "$TESTSTOOLS"/snaps-state install-local-as "${TSNAP}${SUFFIX}" "${TSNAP}${SUFFIX}_foo"
+    snap connect "${TSNAP}${SUFFIX}_foo":account-control
+
+    echo "Then the parallel snap can manage users"
+    snap run "${TSNAP}${SUFFIX}_foo".useradd --extrausers bob
+    echo bob:password | snap run "${TSNAP}${SUFFIX}_foo".chpasswd
+
+    echo "When the original snap is removed"
+    snap remove --purge "${TSNAP}${SUFFIX}"
+
+    echo "Then the parallel snap can still manage users"
+    snap run "${TSNAP}${SUFFIX}_foo".userdel --extrausers bob
```

- **Results:** passed on core 18

---

## Hardware Interfaces

### joystick
**Status: COMPATIBLE**

**Code analysis:**
- Access to `/dev/input/js*` and `/dev/input/event*` devices
- UDev tagging by input subsystem
- No D-Bus, no shared memory, no instance-specific paths
- Multiple processes accessing the same input device is normal (e.g., multiple game
  controllers)

**Verification:**
```diff
diff --git a/tests/main/interfaces-joystick/task.yaml b/tests/main/interfaces-joystick/task.yaml
@@ prepare: |
+    snap set system experimental.parallel-instances=true
@@ restore: |
+    snap remove --purge test-snapd-sh_foo || true
+    snap set system experimental.parallel-instances=null
@@ execute: |
+    echo "When a parallel install of the snap is installed"
+    "$TESTSTOOLS"/snaps-state install-local-as test-snapd-sh test-snapd-sh_foo
+    snap connect test-snapd-sh_foo:joystick
+
+    echo "Then the parallel snap is able to access the device input"
+    test-snapd-sh_foo.with-joystick-plug -c "echo test >> /dev/input/js31"
+    test-snapd-sh_foo.with-joystick-plug -c "cat /run/udev/data/c13:31"
```
- **Result**: PASSED on noble.

---

### hardware-observe
**Status: COMPATIBLE**

**Code analysis:**
- Read-only access to `/sys/`, `/proc/`, hardware information
- No writes, no D-Bus, no shared memory
- Multiple processes reading hardware info simultaneously is the normal case

**Verification:**
```diff
diff --git a/tests/main/interfaces-hardware-observe/task.yaml b/tests/main/interfaces-hardware-observe/task.yaml
@@ prepare: |
+    snap set system experimental.parallel-instances=true
@@ execute: |
+    echo "When a parallel install of the snap is installed"
+    "$TESTSTOOLS"/snaps-state install-local-as hardware-observe-consumer hardware-observe-consumer_foo
+    snap connect hardware-observe-consumer_foo:hardware-observe
+
+    echo "Then the parallel snap is able to read hardware information"
+    hardware-observe-consumer_foo.consumer
+
+    echo "When the original snap is removed"
+    snap remove --purge hardware-observe-consumer
+
+    echo "Then the parallel snap is still able to read hardware information"
+    hardware-observe-consumer_foo.consumer
```
- **Result**: PASSED on noble.

---

### hardware-random-control
**Status: COMPATIBLE**

**Code analysis:**
- Read/write access to `/dev/hwrng` and sysfs hw_random paths
- Single hardware resource, but multiple readers don't conflict
- Writers could theoretically conflict (setting `rng_current`), but this is an
  operational concern, not an interface/AppArmor concern

**Verification:**
```diff
diff --git a/tests/main/interfaces-hardware-random-control/task.yaml b/tests/main/interfaces-hardware-random-control/task.yaml
@@ prepare: |
+    snap set system experimental.parallel-instances=true
@@ execute: |
+    echo "When a parallel install of the snap is installed"
+    "$TESTSTOOLS"/snaps-state install-local-as test-snapd-hardware-random-control test-snapd-hardware-random-control_foo
+    snap connect test-snapd-hardware-random-control_foo:hardware-random-control
+
+    echo "Then the parallel snap is able to read hardware random information"
+    test-snapd-hardware-random-control_foo.check /dev/hwrng
+
+    echo "When the original snap is removed"
+    snap remove --purge test-snapd-hardware-random-control
+
+    echo "Then the parallel snap can still read hardware random information"
+    test-snapd-hardware-random-control_foo.check /dev/hwrng
```
- **Result**: PASSED on noble.

---

### hardware-random-observe
**Status: COMPATIBLE**

**Code analysis:**
- Read-only access to `/dev/hwrng` and sysfs hw_random paths
- Subset of hardware-random-control (read only)

**Verification:**
```diff
diff --git a/tests/main/interfaces-hardware-random-observe/task.yaml b/tests/main/interfaces-hardware-random-observe/task.yaml
@@ prepare: |
+    snap set system experimental.parallel-instances=true
@@ execute: |
+    echo "When a parallel install of the snap is installed"
+    "$TESTSTOOLS"/snaps-state install-local-as test-snapd-hardware-random-observe test-snapd-hardware-random-observe_foo
+    snap connect test-snapd-hardware-random-observe_foo:hardware-random-observe
+
+    echo "Then the parallel snap is able to read hardware random information"
+    test-snapd-hardware-random-observe_foo.check /dev/hwrng
+
+    echo "When the original snap is removed"
+    snap remove --purge test-snapd-hardware-random-observe
+
+    echo "Then the parallel snap can still read hardware random information"
+    test-snapd-hardware-random-observe_foo.check /dev/hwrng
```
- **Result**: PASSED on noble.

---

## Shared Memory Interfaces

### shared-memory (non-private/named mode)
**Status: NOT COMPATIBLE (kernel-global SHM namespace)**

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

**Reasoning**: In non-private mode, SHM names are kernel-global. When both the original
slot and a parallel slot write to the same named SHM path, they operate on the same
kernel object. The `_foo` slot's write clobbers the original's data. There is no
per-instance isolation of named SHM objects.

**Verification:**
```diff
diff --git a/tests/main/interfaces-shared-memory/task.yaml b/tests/main/interfaces-shared-memory/task.yaml
index df23c14a18..8f8b69bb98 100644
--- a/tests/main/interfaces-shared-memory/task.yaml
+++ b/tests/main/interfaces-shared-memory/task.yaml
@@ -5,6 +5,7 @@ details: |
     object declared in the slot of the provider snap.
 
 prepare: |
+    snap set system experimental.parallel-instances=true
     "$TESTSTOOLS"/snaps-state install-local shm-slot
     "$TESTSTOOLS"/snaps-state install-local shm-plug
 
@@ -92,3 +93,21 @@ execute: |
     if shm-plug.cmd cat /dev/shm/readable-bar; then
         exit 1
     fi
+
+    echo "When parallel installs are installed"
+    "$TESTSTOOLS"/snaps-state install-local-as shm-slot shm-slot_foo
+    "$TESTSTOOLS"/snaps-state install-local-as shm-plug shm-plug_foo
+    snap connect shm-plug_foo:shmem shm-slot_foo:shmem
+    snap connect shm-plug_foo:shmem-wildcard shm-slot_foo:shmem-wildcard
+
+    echo "Reconnect the originals for the isolation test"
+    snap connect shm-plug:shmem shm-slot:shmem
+
+    echo "The original slot writes data to its shared memory"
+    shm-slot.cmd sh -c 'echo "original data" > /dev/shm/writable-bar'
+
+    echo "The parallel slot writes different data to its shared memory"
+    shm-slot_foo.cmd sh -c 'echo "parallel data" > /dev/shm/writable-bar'
+
+    echo "The original plug should see its own slot's data (not the parallel's)"
+    shm-plug.cmd cat /dev/shm/writable-bar | MATCH "original data"
```
- **Result**: Expected failure. The original plug reads `parallel data` instead of
  `original data`, because `shm-slot_foo` overwrote the same kernel SHM object at
  `/dev/shm/writable-bar`. The named SHM paths are not instance-scoped.

---

### shared-memory (private mode)
**Status: COMPATIBLE**

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

**Reasoning**: Private shared-memory is designed for per-snap isolation. The
`InstanceName()` usage ensures parallel instances get separate namespaces. This is the
most isolation-friendly mode of shared-memory.

**Verification**: 
```diff
diff --git a/tests/main/interfaces-shared-memory-private/task.yaml b/tests/main/interfaces-shared-memory-private/task.yaml
index 186895f405..306b5c4448 100644
--- a/tests/main/interfaces-shared-memory-private/task.yaml
+++ b/tests/main/interfaces-shared-memory-private/task.yaml
@@ -14,13 +14,17 @@ systems:
     - -ubuntu-14.04*
 
 prepare: |
+    snap set system experimental.parallel-instances=true
     "$TESTSTOOLS"/snaps-state install-local shm-private
     tests.session -u test prepare
 
 restore: |
     tests.session -u test restore
     snap remove --purge shm-private
+    snap remove --purge shm-private_foo || true
     rm -rf /dev/shm/snap.shm-private
+    rm -rf /dev/shm/snap.shm-private_foo
+    snap set system experimental.parallel-instances=null
 
 execute: |
     echo "shared-memory plugs with 'private: true' set are autoconnected"
@@ -50,3 +54,25 @@ execute: |
     rm -rf /dev/shm/snap.shm-private
     snap connect shm-private:shmem-private
     shm-private.cmd stat -c %a /dev/shm | MATCH '^1777$'
+
+    echo "When a parallel install of the snap is installed"
+    "$TESTSTOOLS"/snaps-state install-local-as shm-private shm-private_foo
+
+    echo "The parallel snap's private plug is autoconnected"
+    snap connections shm-private_foo | MATCH "shared-memory +shm-private_foo:shmem-private +:shared-memory +-"
+
+    echo "The parallel snap can create segments in its own private /dev/shm"
+    shm-private_foo.cmd touch /dev/shm/foo-segment
+
+    echo "The parallel snap's segments are stored in its own subdirectory"
+    test -f /dev/shm/snap.shm-private_foo/foo-segment
+
+    echo "The parallel snap cannot see the original snap's segments"
+    shm-private_foo.cmd test ! -f /dev/shm/root-segment
+
+    echo "When the original snap is removed"
+    snap remove --purge shm-private
+
+    echo "Then the parallel snap can still create segments"
+    shm-private_foo.cmd touch /dev/shm/another-segment
+    test -f /dev/shm/snap.shm-private_foo/another-segment
```
-Result: PASSED on noble. Parallel instance got its own `/dev/shm/snap.shm-private_foo/`
namespace, segments were isolated from original, survived removal of original snap.

---

### posix-mq
**Status: NOT COMPATIBLE (kernel-global queue namespace)**

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

**Reasoning**: POSIX MQs are kernel-global -- there is no per-namespace isolation.
When two parallel instances both create queue `/test`, they operate on the same
kernel object. Messages sent by one instance can be received by the other. The
AppArmor peer labels don't help because the queue itself is the shared resource, not
the D-Bus-style peer communication.

**Verification:**
```diff
diff --git a/tests/main/interfaces-posix-mq/task.yaml b/tests/main/interfaces-posix-mq/task.yaml
index 8735bac749..52b2318e10 100644
--- a/tests/main/interfaces-posix-mq/task.yaml
+++ b/tests/main/interfaces-posix-mq/task.yaml
@@ -26,9 +26,14 @@ systems:
 
 prepare: |
     # Source code is at https://github.com/canonical/test-snapd-posix-mq
+    snap set system experimental.parallel-instances=true
     snap install test-snapd-posix-mq
     snap warnings | MATCH 'No further warnings.|No warnings.'
 
+restore: |
+    snap remove --purge test-snapd-posix-mq_foo || true
+    snap set system experimental.parallel-instances=null
+
 execute: |
     # We cannot create a queue before connecting the can-create slot.
     not test-snapd-posix-mq.mqctl create /test read-only 600 max-size=16,max-count=10
@@ -90,3 +95,37 @@ execute: |
     snap connect test-snapd-posix-mq:posix-mq test-snapd-posix-mq:can-delete
     test-snapd-posix-mq.mqctl unlink /test
     test ! -f /dev/mqueue/test
+
+    echo "When a parallel install of the snap is installed"
+    snap install test-snapd-posix-mq_foo
+    snap connect test-snapd-posix-mq_foo:posix-mq test-snapd-posix-mq_foo:can-create
+    snap connect test-snapd-posix-mq_foo:posix-mq test-snapd-posix-mq_foo:can-read
+    snap connect test-snapd-posix-mq_foo:posix-mq test-snapd-posix-mq_foo:can-write
+    snap connect test-snapd-posix-mq_foo:posix-mq test-snapd-posix-mq_foo:can-delete
+
+    echo "The original snap creates a queue and sends a message"
+    snap connect test-snapd-posix-mq:posix-mq test-snapd-posix-mq:can-create
+    snap connect test-snapd-posix-mq:posix-mq test-snapd-posix-mq:can-write
+    snap connect test-snapd-posix-mq:posix-mq test-snapd-posix-mq:can-read
+    test-snapd-posix-mq.mqctl create /test read-only 600 max-size=16,max-count=10 | MATCH 'mq_open did not fail'
+    test-snapd-posix-mq.mqctl send /test write-only "Original message" 7 | MATCH 'mq_send did not fail'
+
+    echo "The parallel snap creates its own queue with the same name -- it should be isolated"
+    test-snapd-posix-mq_foo.mqctl create /test read-only 600 max-size=16,max-count=10 | MATCH 'mq_open did not fail'
+    test-snapd-posix-mq_foo.mqctl send /test write-only "Parallel message" 3 | MATCH 'mq_send did not fail'
+
+    test-snapd-posix-mq_foo.mqctl recv /test read-only > same-named-queue-read
+
+    echo "When the original snap is removed"
+    snap connect test-snapd-posix-mq:posix-mq test-snapd-posix-mq:can-delete
+    test-snapd-posix-mq.mqctl unlink /test
+    snap remove --purge test-snapd-posix-mq
+
+    echo "Then the parallel snap can still create and use its own queues"
+    test-snapd-posix-mq_foo.mqctl create /test read-only 600 max-size=16,max-count=10 | MATCH 'mq_open did not fail'
+    test-snapd-posix-mq_foo.mqctl send /test write-only "Still works" 1 | MATCH 'mq_send did not fail'
+    test-snapd-posix-mq_foo.mqctl recv /test read-only | MATCH 'Received message with priority 1: Still works'
+    test-snapd-posix-mq_foo.mqctl unlink /test
+    
+    echo "Before when the original snap was also installed, the parallel snap read from the queue -- it should get its own message, not the original's"
+    MATCH 'Received message with priority 3: Parallel message' <same-named-queue-read
```
- **Result**: Expected failure. The `_foo` instance received `priority 7: Original message`
  instead of `priority 3: Parallel message`. Since POSIX MQs are priority-ordered and
  kernel-global, the read returns the highest-priority message from the shared queue --
  which was the original instance's message.
---

## Mount Interfaces

### mount-control
**Status: NOT COMPATIBLE**

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

**Reasoning**: The mount-control interface has a fundamental inconsistency: AppArmor rules
and permission checks use `SnapName()` (namespace-internal perspective), but the systemd
mount unit operates on host paths (which are instance-specific). A parallel instance
trying to use `mount` (direct syscall) is denied by AppArmor because the host path
(`/var/snap/..._foo/...`) doesn't match the AppArmor rule (which uses the base name). A
parallel instance using `snapctl mount` would create a unit pointing to the wrong
directory on the host.

**Verification (interfaces-mount-control):**
```diff
diff --git a/tests/main/interfaces-mount-control/task.yaml b/tests/main/interfaces-mount-control/task.yaml
index 5c196f3674..b0534bf046 100644
--- a/tests/main/interfaces-mount-control/task.yaml
+++ b/tests/main/interfaces-mount-control/task.yaml
@@ -10,8 +10,12 @@ environment:
     MOUNT_SRC: /var/tmp/test-snapd-mount-control
     SNAP_COMMON: /var/snap/test-snapd-mount-control/common
     SNAP_NAME: test-snapd-mount-control
+    PARALLEL_SNAP_NAME: test-snapd-mount-control_foo
+    PARALLEL_SNAP_COMMON: /var/snap/test-snapd-mount-control_foo/common
     # what: /var/tmp/** | where: $SNAP_COMMON/target1 | options: [rw, bind] | persistent
     MOUNT_DEST1: $SNAP_COMMON/target1
+    # what: /var/tmp/** | where: $PARALLEL_SNAP_COMMON/target1 | options: [rw, bind] | persistent
+    PARALLEL_MOUNT_DEST1: $PARALLEL_SNAP_COMMON/target1
     # what: none | where: $SNAP_COMMON/target2/* | type: [tmpfs] | options: [rw]
     MOUNT_DEST2: $SNAP_COMMON/target2/path
     # what: /usr/** | where: $SNAP_COMMON/target3/** | options: [rw, bind]
@@ -23,12 +27,15 @@ prepare: |
         . "$TESTSLIB/pkgdb.sh"
         distro_install_package auditd
     fi
+    snap set system experimental.parallel-instances=true
     mkdir -p "$MOUNT_SRC/dir1"
     echo "Something" > "$MOUNT_SRC/file1"
 
 restore: |
     rm -f connect_error.log
     rm -rf "$MOUNT_SRC"
+    snap remove --purge test-snapd-mount-control_foo || true
+    snap set system experimental.parallel-instances=null
 
 execute: |
     if [ "$SPREAD_REBOOT" = 0 ]; then
@@ -152,6 +159,18 @@ execute: |
         "${SNAP_NAME}".cmd grep "$MOUNT_DEST1" /proc/self/mountinfo
         "${SNAP_NAME}".cmd test -e "$MOUNT_DEST1/file1"
 
+        echo "When a parallel install of the snap is installed"
+        "$TESTSTOOLS"/snaps-state install-local-as "$SNAP_NAME" "$PARALLEL_SNAP_NAME"
+        snap connect "$PARALLEL_SNAP_NAME":mntctl
+        mkdir -p "$PARALLEL_MOUNT_DEST1"
+
+        echo "Then the parallel snap can perform a mount to its own SNAP_COMMON"
+        "$PARALLEL_SNAP_NAME".cmd mount -o bind,rw "$MOUNT_SRC" "$PARALLEL_MOUNT_DEST1"
+
+        echo "Verify the mount"
+        "$PARALLEL_SNAP_NAME".cmd grep "$PARALLEL_MOUNT_DEST1" /proc/self/mountinfo
+        "$PARALLEL_SNAP_NAME".cmd test -e "$PARALLEL_MOUNT_DEST1/file1"
+
         REBOOT
     else
         # after reboot
```
- **Result**: Expected failure. `mount: mount /var/tmp/test-snapd-mount-control on
  /var/snap/test-snapd-mount-control_foo/common/target1 failed: Permission denied`.
  AppArmor denies the mount because the rule uses `SnapName()` which only allows
  `/var/snap/test-snapd-mount-control/common/...`, not the instance-specific path.

---

## Service Interfaces

### password-manager-service
**Status: COMPATIBLE**

**Code analysis:**
- Session bus D-Bus access to `org.freedesktop.secrets` (gnome-keyring)
- The plug only sends/receives -- it does not own the keyring service name
- Multiple clients accessing the same keyring is the normal use case
- The `secret-tool` utility just performs operations on the user's keyring

**Reasoning**: gnome-keyring is a user-session service. Multiple snap instances are just
additional clients of the same session service, no different from multiple different
snaps accessing the keyring.

**Previous audit errors**:
- Classified as "NOT COMPATIBLE" -- INCORRECT. Test proves it works.

**Verification:**
```diff
diff --git a/tests/main/interfaces-password-manager-service/task.yaml b/tests/main/interfaces-password-manager-service/task.yaml
@@ prepare: |
+    snap set system experimental.parallel-instances=true
@@ restore: |
+    snap remove --purge test-snapd-password-manager-consumer_foo || true
+    snap set system experimental.parallel-instances=null
@@ execute: |
+    echo "When a parallel install of the snap is installed"
+    snap install --edge test-snapd-password-manager-consumer_foo
+    snap connect test-snapd-password-manager-consumer_foo:password-manager-service
+    tests.session -u test exec test-snapd-password-manager-consumer_foo.secret-tool clear foo bar
+
+    echo "When the original snap is removed"
+    snap remove --purge test-snapd-password-manager-consumer
+
+    echo "Then the parallel snap can still use the libsecret service"
+    tests.session -u test exec test-snapd-password-manager-consumer_foo.secret-tool clear foo bar
```
- **Result**: PASSED on noble.

---

### calendar-service
**Status: COMPATIBLE**

**Code analysis:**
- Session bus D-Bus access to Evolution Data Server (calendar component)
- Same architecture as contacts-service (session bus, client-only)
- Multiple clients accessing the same EDS calendar is normal

**Previous audit errors**:
- Classified as "NOT COMPATIBLE" -- INCORRECT. Test proves it works.

**Verification:**
```diff
diff --git a/tests/main/interfaces-calendar-service/task.yaml b/tests/main/interfaces-calendar-service/task.yaml
@@ prepare: |
+    snap set system experimental.parallel-instances=true
@@ restore: |
+    snap remove --purge test-snapd-eds_foo || true
+    snap set system experimental.parallel-instances=null
@@ execute: |
+    echo "When a parallel install of the snap is installed"
+    snap install --edge test-snapd-eds_foo
+    snap connect test-snapd-eds_foo:calendar-service
+    tests.session -u test exec test-snapd-eds_foo.calendar load test-calendar << EOF
+    BEGIN:VEVENT
+    ...
+    END:VEVENT
+    EOF
+
+    echo "When the original snap is removed"
+    snap remove --purge test-snapd-eds
+
+    echo "Then the parallel snap can still retrieve calendars"
+    tests.session -u test exec test-snapd-eds_foo.calendar list test-calendar
```
- **Result**: PASSED on noble.

---

## Read-Only, Capability, and Device Access Interfaces (Priority 3)

These interfaces are all plug-only with system-provided implicit slots. They have no
D-Bus name ownership, no snap-name-dependent paths, and no file generation using snap
names. Multiple parallel instances receive identical AppArmor/seccomp profiles. All are
expected to be COMPATIBLE with parallel installs.

### log-observe
**Status: COMPATIBLE (code analysis -- not yet verified by test)**

Read-only access to system logs (`/var/log/`, journal). No D-Bus, no snap-name paths.

**Verification**: Passed on noble. Test at `tests/main/interfaces-log-observe`.

### network-observe
**Status: COMPATIBLE (code analysis -- not yet verified by test)**

Read-only network status queries (D-Bus client to systemd-resolved, read /proc/sys).
No D-Bus ownership.

**Verification**: Passed on noble. Test at `tests/main/interfaces-network-observe`.

### mount-observe
**Status: COMPATIBLE (code analysis -- not yet verified by test)**

Read-only access to `/proc/<pid>/mounts` and mount propagation info. No D-Bus, no
snap-name paths.

**Verification**: Passed on noble. Test at `tests/main/interfaces-mount-observe`.

### system-observe
**Status: COMPATIBLE (code analysis -- not yet verified by test)**

Read-only access to system info (D-Bus client to hostnamed/systemd, read /proc, /boot).
No D-Bus ownership.

**Verification**: Passed on noble. Test at `tests/main/interfaces-system-observe`.

### process-control
**Status: COMPATIBLE (code analysis -- not yet verified by test)**

Capability-based: `kill` syscall, signal sending, priority changes. No paths, no D-Bus.

**Verification**: Passed on noble. Test at `tests/main/interfaces-process-control`.

### gpg-keys
**Status: COMPATIBLE (code analysis -- not yet verified by test)**

Read/write access to `~/.gnupg/` (user file access). No D-Bus, no snap-name paths.

**Verification**: Passed on noble. Test at `tests/main/interfaces-gpg-keys`.

### gpg-public-keys
**Status: COMPATIBLE (code analysis -- not yet verified by test)**

Read-only access to `~/.gnupg/` public keys. No D-Bus, no snap-name paths.

**Verification**: Passed on noble. Test at `tests/main/interfaces-gpg-public-keys`.

### removable-media
**Status: COMPATIBLE (code analysis -- not yet verified by test)**

Access to `/media/`, `/run/media/`, `/mnt/` mount points. No D-Bus, no snap-name paths.

**Verification**: Passed on noble. Test at `tests/main/interfaces-removable-media`.

### kvm
**Status: COMPATIBLE (code analysis -- not yet verified by test)**

Device access to `/dev/kvm`. No D-Bus, no snap-name paths.

**Verification**: Passed on noble. Test at `tests/main/interfaces-kvm`.

### raw-usb
**Status: COMPATIBLE (code analysis -- not yet verified by test)**

Device access to `/dev/bus/usb/`, `/sys/bus/usb/`. No D-Bus, no snap-name paths.

**Verification**: Passed on noble. Test at `tests/main/interfaces-raw-usb`.

### raw-input
**Status: COMPATIBLE (code analysis -- not yet verified by test)**

Device access to `/dev/input/*`. No D-Bus, no snap-name paths.

**Verification**: Passed on noble. Test at `tests/main/interfaces-raw-input`.

### dvb
**Status: COMPATIBLE (code analysis -- not yet verified by test)**

Device access to `/dev/dvb/adapter*`. No D-Bus, no snap-name paths.

**Verification**: Passed on noble. Test at `tests/main/interfaces-dvb`.

### device-buttons
**Status: COMPATIBLE (code analysis -- not yet verified by test)**

Device access to gpio-keys input event devices. No D-Bus, no snap-name paths.

**Verification**: Passed on noble. Test at `tests/main/interfaces-device-buttons`.

### uhid
**Status: COMPATIBLE (code analysis -- not yet verified by test)**

Device access to `/dev/uhid` for creating/destroying HID devices. No D-Bus, no
snap-name paths.

**Verification**: Passed on noble. Test at `tests/main/interfaces-uhid`.

### block-devices
**Status: COMPATIBLE (code analysis -- not yet verified by test)**

Device access to block devices (`/dev/sd*`, `/dev/nvme*`). No D-Bus, no snap-name paths.

**Verification**: Passed on noble. Test at `tests/main/interfaces-block-devices`.

### daemon-notify
**Status: COMPATIBLE (code analysis -- not yet verified by test)**

Write access to `/run/systemd/notify` socket. No D-Bus ownership, no snap-name paths.

**Verification**: Passed on noble. Test at `tests/main/interfaces-daemon-notify`.

### browser-support
**Status: COMPATIBLE (code analysis -- not yet verified by test)**

Path/capability access for browser sandbox. Uses `@{SNAP_INSTANCE_NAME}` correctly
for parallel-install-aware paths.

**Verification**: Passed on noble. Test at `tests/main/interfaces-browser-support`.

### kerberos-tickets
**Status: COMPATIBLE (code analysis -- not yet verified by test)**

Read/write access to Kerberos ticket caches. No D-Bus, no snap-name paths.

**Verification**: Passed on noble. Test at `tests/main/interfaces-kerberos-tickets`.

### audio-playback-record
**Status: COMPATIBLE (code analysis -- not yet verified by test)**

PulseAudio playback/record mediation. Same architecture as pulseaudio interface
(plug-side client, shared memory is intentional). No D-Bus ownership.

**Verification**: Passed on noble. Test at `tests/main/interfaces-audio-playback-record`.

### adb-support
**Status: COMPATIBLE (code analysis -- not yet verified by test)**

UDev rules for Android USB debugging. Rules files use security tag (instance-aware).
No D-Bus, no snap-name path conflicts.

**Verification**: Passed on noble. Test at `tests/main/interfaces-adb-support`.

### netlink-audit
**Status: COMPATIBLE (code analysis -- not yet verified by test)**

Netlink audit socket creation/binding. Pure capability, no paths or D-Bus.

**Verification**: Passed on noble. Test at `tests/main/interfaces-netlink-audit`.

### netlink-connector
**Status: COMPATIBLE (code analysis -- not yet verified by test)**

Netlink connector socket creation/binding. Pure capability, no paths or D-Bus.

**Verification**: Passed on noble. Test at `tests/main/interfaces-netlink-connector`.

---

## Interfaces Not Verified (from original audit)

These interfaces were classified but not tested:

| Interface | Original Status | Assessment |
|-----------|----------------|------------|
| pipewire | NOT COMPATIBLE | Likely COMPATIBLE (plug-side), same pattern as pulseaudio |
| serial-port | POTENTIALLY COMPATIBLE | Likely COMPATIBLE for distinct devices |
| hidraw | POTENTIALLY COMPATIBLE | Likely COMPATIBLE for distinct devices |
| i2c | COMPATIBLE | Unverified but likely correct |
| tpm | NOT COMPATIBLE | Correct -- unique hardware resource with read/write |
| media-control | COMPATIBLE | Unverified but likely correct |
| gsettings | COMPATIBLE | Unverified but likely correct |

### Analyzed but awaiting test verification

| Interface | Status | Key finding |
|-----------|--------|-------------|
| cups (parallel provider) | NOT COMPATIBLE | Socket path expansion uses `PerspectiveSelf`/`SnapName()` for slot -- likely bug. Consumer plug-side verified PASSED. |

---

## Summary of Corrections from Previous Audit

### Interfaces reclassified from "NOT COMPATIBLE" to "COMPATIBLE"

| Interface | Reason for reclassification |
|-----------|---------------------------|
| pulseaudio | No D-Bus used. Plug-side shared memory is intentional client-server IPC. Test passed. |
| avahi-observe | `dbus (bind)` only in slot snippet. Plug-side only sends/receives. Test passed. |
| network-control | Only sends to D-Bus (no bind/own). Test passed. |
| shared-memory (private mode) | Private mode uses instance-scoped paths (`InstanceName()`). Test passed. |
| wayland | Plug-side multi-client is normal. Test passed. |
| password-manager-service | Session bus client only. Test passed. |
| calendar-service | Session bus client only. Test passed. |

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

### Test bugs found and fixed

| Test | Bug | Fix Applied |
|------|-----|-------------|
| interfaces-x11-unix-socket | Missing `experimental.parallel-instances=true` | Added `prepare:` section with flag and cleanup in `restore:` |
| interfaces-desktop-launch | `install-local X_foo` instead of `install-local-as X X_foo` | Changed to `install-local-as` |
| interfaces-ssh-public-keys | Uses removed snap's commands after `snap remove` | All post-removal refs now use `_foo` instance |
| interfaces-location-control | MATCH "Permission denied" but error is "AccessDenied" | Pattern now accepts both strings |
| interfaces-mount-control | Removed original snap before reboot, then used it after | Keep original for reboot verification |
| parallel-install-mount-control | `$SNAP_COMMON` in single quotes (never expanded) | Use double quotes with `\$` for inner shell expansion |
| interfaces-system-dbus | Expected success where failure is correct | Assert failure with `not`, then success after original removed |
| interfaces-cups-control | No CUPS printer configured | Environment issue, not parallel (no code fix needed) |

---


## Interfaces Not Yet Audited

This section catalogs the 137 interfaces registered in snapd that were not covered in the original audit. They are grouped by category to help prioritize future verification.

---

### Super Privileged (plug-side `deny-auto-connection: true`) — 50 interfaces

These interfaces require manual connection approval (plug-side `deny-auto-connection: true`). They are listed below for completeness, but they remain outside the compatibility conclusions for the audit as a whole:

`auditd-support`, `checkbox-support`, `classic-support`, `cuda-driver-libs`, `devlxd`, `dm-crypt`, `dm-multipath`, `docker-support`, `egl-driver-libs`, `firmware-updater-support`, `gbm-driver-libs`, `gpio-control`, `greengrass-support`, `ion-memory-control`, `iscsi-initiator`, `kernel-firmware-control`, `kernel-module-control`, `kernel-module-load`, `kubernetes-support`, `lxd-support`, `microceph-support`, `microstack-support`, `multipass-support`, `nomad-support`, `nvidia-drivers-support`, `nvidia-video-driver-libs`, `nvme-control`, `opengl-driver-libs`, `opengles-driver-libs`, `packagekit-control`, `polkit-agent`, `remoteproc`, `ros-snapd-support`, `scsi-generic`, `sd-control`, `shutdown`, `snap-fde-control`, `snap-interfaces-requests-control`, `snap-refresh-control`, `snap-refresh-observe`, `snap-themes-control`, `snapd-control`, `steam-support`, `tee`, `ubuntu-pro-control`, `uinput`, `userns`, `vulkan-driver-libs`, `xdg-portal-permission-store`, `xilinx-dma`

#### cuda-driver-libs
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- The interface is mostly about publishing CUDA driver libraries and config metadata.
- `BeforePrepareSlot()` validates the compatibility expression and source directories (lines 61-77).
- `LdconfigConnectedPlug()` and `ConfigfilesConnectedPlug()` expose the slot's libraries/config through system helper paths (lines 79-103).
- The implementation is system-oriented and does not introduce snap-instance-specific paths.

**Reasoning**: This is a library exposure interface scoped by compatibility metadata and system paths. Parallel installs don’t create a snap instance naming issue in the code shown.

**Verification:** No verification has yet been done.

#### dm-crypt
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slots are provided by core only (lines 24-29), with implicit slots on core and classic (lines 88-89).
- AppArmor grants access to `/dev/mapper/control`, `/dev/dm-*`, cryptsetup, mount helpers, and mount points under `/run/media` and `/media` (lines 39-62).
- Seccomp only adds keyring-related syscalls (lines 64-69).
- KMod and UDev rules are tied to the device-mapper stack (lines 71-82).
- The mount points are generic system locations, not snap-instance-specific paths.

**Reasoning**: dm-crypt is a global device-mapper interface. The mount path handling is generic and not keyed by snap instance names, so there is no instance collision surface in the policy code.

**Verification:** No verification has yet been done.

#### dm-multipath
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 40-45), with implicit slots on classic (line 84) and app/slot declarations intended for system use.
- AppArmor grants access to multipath configuration, device-mapper control, multipath device nodes, and the multipathd abstract socket (lines 48-65).
- UDev and KMod rules are for the device-mapper/multipath stack (lines 67-78).
- The socket address is a fixed abstract address, not a snap-instance-specific path.

**Reasoning**: Multipath management is a global storage daemon/device interface. Parallel instances are just concurrent clients of the same system multipath stack; the code does not show an instance naming problem.

**Verification:** No verification has yet been done.

#### iscsi-initiator
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 39-44), with implicit slots on classic (line 103).
- AppArmor grants access to iSCSI config/state files, sysfs session/host data, and the iscsiadm abstract socket (lines 47-88).
- KMod modules are declared for iSCSI transport support (lines 94-97).
- No snap-instance-specific paths are used.

**Reasoning**: iSCSI initiator behavior is driven by system-wide daemon/config files and an abstract Unix socket. Parallel instances are just concurrent clients and the interface code does not reveal an instance-naming issue.

**Verification:** No verification has yet been done.

#### packagekit-control
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 30-35), with implicit slot on classic (line 107).
- AppArmor rules are D-Bus client-only and talk to the PackageKit daemon on the system bus (lines 44-100).
- The transaction object paths are random, numeric/hex identifiers under `/[0-9]*_[0-9a-f...]` (lines 74-100), not snap-name-derived.
- No snap-instance-specific paths, sockets, or mount operations are present.
- No D-Bus ownership is granted; this interface only sends and receives on the PackageKit endpoints.

**Reasoning**: PackageKit is a shared system service and the interface is just a D-Bus client. Parallel instances are ordinary concurrent clients talking to the same daemon, and the transaction object paths are generated by PackageKit itself rather than by snapd. No instance-naming issue is visible.

**Verification:** No verification has yet been done.

#### polkit-agent
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only when the helper exists, and the interface is implicitly on core/classic depending on helper availability (line 142).
- AppArmor rules allow registering with polkitd on the system bus and talking to accounts-daemon for UI prompts (lines 47-129).
- The helper subprofile uses `@{SNAP_INSTANCE_NAME}` in the signal peer label (line 114), which is instance-aware.
- The helper can read `/var/lib/extrausers/shadow` and `/var/lib/extrausers/gshadow`, but those are global system auth databases, not snap-scoped paths.
- Seccomp only adds audit-related socket/bind permissions (lines 132-136).

**Reasoning**: The interface is about acting as a polkit agent, which is a client role. The only snap-instance-specific element is the helper signal peer label, and that uses `SNAP_INSTANCE_NAME` correctly. The shared auth databases and D-Bus service are system-wide resources, so parallel instances do not create snap-instance collisions in the interface code.

**Verification:** No verification has yet been done.

#### snap-refresh-observe
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 30-35), with implicit slots on core and classic (lines 42-43).
- The interface has no AppArmor, seccomp, mount, or udev snippets of its own.
- It is used as a marker interface in snapd's refresh/inhibit code paths.
- There are no snap-instance-specific paths or name-ownership rules in the interface definition itself.

**Reasoning**: This interface is essentially a marker/read-access capability used by snapd to gate refresh/inhibit behavior. Because the interface definition itself contributes no filesystem or D-Bus policy, there is no parallel-install collision surface in this code.

**Verification:** No verification has yet been done.

#### ubuntu-pro-control
**Status: NOT COMPATIBLE (slot-side singleton); COMPATIBLE (plug-side)**

**Code analysis:**
- Slot is provided by core only (lines 30-35), with implicit slot on classic (line 128).
- AppArmor rules talk to `com.canonical.UbuntuAdvantage` on the system bus and query the object hierarchy with `ObjectManager`, properties, and introspection (lines 38-121).
- The interface is clearly designed around a single daemon service with a well-known bus name.
- No snap-instance-specific paths are used; the only filesystem access is `/etc/ubuntu-advantage/uaclient.conf` (line 43).
- No mount or shared-memory rules are present.

**Reasoning**: Ubuntu Pro control is a daemon-client interface on top of a singleton service. Parallel consumers are fine, but parallel providers would contend for the same well-known D-Bus name, so slot-side is not compatible.

**Verification:** No verification has yet been done.

#### xdg-portal-permission-store
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 30-35), with implicit slot on core and classic (lines 69-70).
- AppArmor rules grant session-bus access to the portal PermissionStore object at `/org/freedesktop/impl/portal/PermissionStore` (lines 38-63).
- The interface is client-only: it sends and receives on the portal object but does not own a bus name.
- No snap-instance-specific paths, sockets, or mount rules are present.

**Reasoning**: This is a shared portal service on the session bus. Multiple parallel instances can safely access the same PermissionStore as concurrent clients. No instance naming or global-file conflict is visible.

**Verification:** No verification has yet been done.

#### shutdown
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 30-35), with implicit slots on core and classic (lines 93-94).
- AppArmor rules only talk to systemd-logind and systemd over the system bus for poweroff/reboot/shutdown operations (lines 43-76).
- The interface also grants a Unix socket bind rule for `@*/bus/*/system` (line 81), which is pattern-based rather than snap-name-based.
- Seccomp only adds `bind` (lines 84-87).
- No snap-instance-specific paths or per-instance file generation are present.

**Reasoning**: Shutdown is a system-wide capability interface. Parallel instances can all request the same system power operations; there is no snap-instance collision in the policy code.

**Verification:** No verification has yet been done.

#### kernel-firmware-control
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 31-36), with implicit slots on core and classic (lines 48-49).
- AppArmor rules only grant write access to `/sys/module/firmware_class/parameters/path` (line 41).
- No D-Bus, sockets, mounts, or snap-instance-specific paths are involved.

**Reasoning**: The interface controls a global kernel firmware search path parameter. Multiple instances get the same permission, and the code does not include any snap-instance-dependent logic.

**Verification:** No verification has yet been done.

#### ion-memory-control
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 24-30), with an explicit plug-installation restriction (lines 32-36).
- AppArmor rules grant access to `/dev/ion` (lines 38-44).
- UDev tags the `ion` device (lines 46-48).
- No snap-instance-specific names, sockets, or mounts are involved.

**Reasoning**: The Android ION allocator is a global device interface. Multiple parallel instances can access the same device node without any snapd policy collision in the interface code.

**Verification:** No verification has yet been done.

#### nvme-control
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 40-45), with explicit plug-installation restriction (lines 34-38).
- AppArmor grants access to NVMe config files, sysfs, the fabrics character device, and NVMe controller/namespace nodes (lines 48-68).
- UDev tags NVMe and nvme-fabrics devices (lines 70-73).
- KMod module loading hints are declared for `nvme` and `nvme-tcp` (lines 79-82).
- No snap-instance-specific names are used.

**Reasoning**: NVMe is global storage hardware and the interface is device-path based. Parallel installs can access the same controllers/namespaces from separate snaps without snapd policy collision.

**Verification:** No verification has yet been done.

#### remoteproc
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 30-35), with implicit slots on core and classic (lines 52-53).
- AppArmor grants access to remoteproc sysfs state under `/sys/devices/platform/**/remoteproc/remoteproc[0-9]/...` (lines 38-46).
- No D-Bus, sockets, or snap-instance-specific paths are used.

**Reasoning**: Remoteproc is a global kernel framework. Multiple instances can observe/control the same remoteproc nodes as allowed by the slot, with no snap instance name dependency.

**Verification:** No verification has yet been done.

#### sd-control
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 30-35), with implicit slots on core and classic (lines 95-96).
- AppArmor/UDev permissions are conditionally added when the plug’s `flavor` is `dual-sd` (lines 60-86).
- Access is to `/dev/DualSD` and its corresponding udev tag; there are no snap-instance-specific paths.
- The interface uses plug attributes to control scope rather than snap naming.

**Reasoning**: The interface is hardware/flavor specific, not instance specific. Parallel installs just reuse the same hardware access if the plug flavor matches.

**Verification:** No verification has yet been done.

#### uinput
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 39-44), with implicit slots on core and classic (lines 74-75).
- AppArmor grants write access to `/dev/uinput` and `/dev/input/uinput` (lines 47-53).
- UDev tags the `uinput` device (line 64).
- The comments explicitly note this is sensitive because it can inject arbitrary input, but no snap-instance-specific paths are present.

**Reasoning**: This is a global input injection device. Multiple parallel instances can share the same device access; the code does not use instance naming or per-snap mount paths.

**Verification:** No verification has yet been done.

#### xilinx-dma
**Status: COMPATIBLE (code analysis -- not yet verified)**

**Code analysis:**
- Slot is provided by core only (lines 32-37), with implicit slots on core and classic (lines 74-75).
- AppArmor grants access to Xilinx XDMA/QDMA device nodes and driver sysfs state (lines 42-61).
- UDev tags the relevant `xdma` and `qdma` subsystems (lines 64-68).
- The interface note says the xdma subsystem alone should uniquely identify relevant devices (line 63).
- No snap-instance-specific paths are used.

**Reasoning**: This is hardware-device based and the code is scoped by the device subsystem rather than the snap instance. Parallel instances can access the same PCIe DMA hardware without snapd-level collision.

**Verification:** No verification has yet been done.

#### kernel-module-control
**Status: COMPATIBLE (code analysis -- not yet verified by test)**

Capability-based: insmod/rmmod/lsmod, read `/sys/module/`. No D-Bus, no snap-name paths.

**Verification**: Passed on noble. Test at `tests/main/interfaces-kernel-module-control`.

#### gpio-control
**Status: SKIPPED (super-privileged; excluded from compatibility analysis)**

**Code analysis:**
- Not analyzed further for parallel-install compatibility.
- This interface grants broad control of all GPIO pins and device nodes (`/sys/class/gpio`, `/sys/devices/platform/**/gpio`, `/dev/gpiochip[0-9]*`) (lines 43-57).
- The comments explicitly describe the interface as privileged and potentially impacting the system and other snaps (lines 25-27, 44-45).

**Reasoning**: This is super-privileged hardware control. Per audit scope, super-privileged interfaces are excluded from compatibility analysis because their privileges are broad enough that instance-name behavior is not the relevant question.

**Verification:** Not analyzed.

---

### Hardware Device Interfaces — 34 interfaces

These interfaces are hardware-backed or device-backed interfaces (for example `/dev/accel/accel*` or `/dev/video[0-9]*`). Most are exclusive resources and poor fits for parallel installs; a few are shared-client style interfaces and are called out below.

---

#### accel

**Code analysis:**
- Device access: `/dev/accel/accel*`
- Compute accelerator devices (AI/ML acceleration)
- Plug-side interface with implicit slot on core and classic
- No D-Bus, no shared memory, no instance-specific paths

**Parallel install assessment:** Named device paths (`/dev/accel/accel*`) are global hardware resources. Multiple instances would compete for the same accelerator device.

---

#### acrn-support

**Code analysis:**
- Device access: `/dev/acrn_hsm`
- ACRN hypervisor management interface
- Plug-side, slot on core

**Parallel install assessment:** Single `/dev/acrn_hsm` device node is a global resource. Only one instance can manage the hypervisor.

---

#### allegro-vcu

**Code analysis:**
- Device access: `/dev/allegroDecodeIP`, `/dev/allegroIP`, `/dev/dmaproxy`
- Allegro Video Codec Unit encoder/decoder
- Plug-side

**Parallel install assessment:** Hardware codec devices are shared resources. Not meaningful for multiple parallel instances.

---

#### broadcom-asic-control

**Code analysis:**
- Device access: `/dev/linux-user-bde`, `/dev/linux-kernel-bde`, `/dev/linux-bcm-knet`
- Broadcom ASIC kernel module interface
- Plug-side

**Parallel install assessment:** Kernel module + device node for specific ASIC hardware. Single-instance hardware.

---

#### camera

**Code analysis:**
- Device access: `/dev/video[0-9]*`, `/dev/vchiq`
- Camera device access (video capture)
- Plug-side, implicit on core and classic
- No D-Bus, no shared memory, no instance-specific paths

**Parallel install assessment:** Physical camera devices are global hardware resources. Multiple instances would read from the same camera.

---

#### can-bus

**Code analysis:**
- Socket access: `AF_CAN` socket protocol
- CAN bus networking interface
- Plug-side, implicit on core and classic

**Parallel install assessment:** CAN bus is a shared medium. Multiple instances can connect concurrently as clients; the bus itself is the shared resource.

---

#### cpu-control

**Code analysis:**
- Path access: `/sys/devices/system/cpu/**`
- CPU frequency scaling, governor control, hotplug
- Plug-side

**Parallel install assessment:** CPU sysfs knobs are system-global. Two instances writing different governor settings would conflict.

---

#### dcdbas-control

**Code analysis:**
- Path access: `/sys/devices/platform/dcdbas/*`
- Dell Systems Management Base Driver
- Plug-side

**Parallel install assessment:** Dell BMC sysfs interface is a single system resource.

---

#### dsp

**Code analysis:**
- Device access: `/dev/ucode`, `/dev/iav*`
- Ambarella DSP coprocessor
- Plug-side

**Parallel install assessment:** DSP hardware device is a single-instance resource.

---

#### fpga

**Code analysis:**
- Device access: `/dev/fpga[0-9]*`
- FPGA subsystem (programmable logic)
- Plug-side

**Parallel install assessment:** Numbered FPGA device nodes are shared. Multiple instances programming the same FPGA would conflict.

---

#### framebuffer

**Code analysis:**
- Device access: `/dev/fb[0-9]*`
- Linux framebuffer device
- Plug-side, implicit on core and classic

**Parallel install assessment:** Framebuffer devices are global display resources. Two instances writing to `/dev/fb0` would conflict.

---

#### gpio

**Code analysis:**
- Path access: `/sys/class/gpio/gpio<N>` (specific numbered GPIO pin)
- Specific GPIO pin control via slot-declared pin number
- Both plug and slot sides

**Parallel install assessment:** GPIO pins are physical hardware resources. Two instances claiming the same pin would conflict at the kernel level.

---

#### gpio-memory-control

**Code analysis:**
- Device access: `/dev/gpiomem`
- GPIO physical memory access
- Plug-side, implicit on core and classic

**Parallel install assessment:** `/dev/gpiomem` provides direct GPIO register access. Single system resource.

---

#### hugepages-control

**Code analysis:**
- Path access: `/sys/kernel/mm/hugepages/*`
- Control hugepage pool sizes
- Plug-side

**Parallel install assessment:** System-wide kernel memory configuration. Only one instance should manage hugepages.

---

#### iio

**Code analysis:**
- Device access: `/dev/iio:device*` (numbered)
- Industrial I/O sensor device (accelerometer, gyroscope, etc.)
- Plug-side

**Parallel install assessment:** Numbered IIO devices are physical sensors. Shared hardware resource.

---

#### intel-mei

**Code analysis:**
- Device access: `/dev/mei[0-9]*`
- Intel Management Engine Interface
- Plug-side, implicit on core and classic

**Parallel install assessment:** MEI is a system-management bus. Single-instance hardware.

---

#### intel-qat

**Code analysis:**
- Device access: `/dev/vfio/*`, IOMMU sysfs
- Intel QuickAssist Technology accelerator
- Plug-side

**Parallel install assessment:** QAT acceleration hardware is a shared PCIe device.

---

#### io-ports-control

**Code analysis:**
- Device access: `/dev/port`
- Syscalls: `ioperm`, `iopl`
- All I/O port access
- Plug-side

**Parallel install assessment:** Grants full I/O port access. System-global resource.

---

#### kernel-crypto-api

**Code analysis:**
- Socket access: `AF_ALG` socket family
- Linux kernel crypto API (hardware-accelerated crypto)
- Plug-side, implicit on core and classic

**Parallel install assessment:** Multiple instances can use the kernel crypto API simultaneously. This is more of a system capability than an exclusive device.

---

#### mediatek-accel

**Code analysis:**
- Device access: `/dev/apu`, `/dev/vpu`
- MediaTek Genio APU/VPU accelerators
- Both plug and slot sides

**Parallel install assessment:** Hardware accelerator devices are shared resources.

---

#### opengl

**Code analysis:**
- GPU device nodes (DRM render nodes)
- OpenGL rendering acceleration
- Plug-side, implicit on core and classic

**Parallel install assessment:** Multiple processes accessing the same GPU is normal and supported by the driver stack. Parallel instances can share the GPU, so this is likely COMPATIBLE for plug-side usage.

---

#### optical-drive

**Code analysis:**
- Device access: `/dev/sr[0-9]*`, `/dev/scd[0-9]*`
- CD/DVD/Blu-ray optical drives
- Plug-side

**Parallel install assessment:** Optical drives are exclusive-access hardware. Only one process can read from a physical optical drive at a time.

---

#### physical-memory-control

**Code analysis:**
- Device access: `/dev/mem` (read/write)
- Full physical memory access
- Plug-side, implicit on core and classic

**Parallel install assessment:** `/dev/mem` provides access to all physical memory. System-global resource, not meaningful for parallel installs.

---

#### physical-memory-observe

**Code analysis:**
- Device access: `/dev/mem` (read-only)
- Read-only physical memory inspection
- Plug-side, implicit on core and classic

**Parallel install assessment:** Read-only access, so two instances can coexist reading `/dev/mem`, though this is an extreme privilege. Likely COMPATIBLE for parallel installs.

---

#### power-control

**Code analysis:**
- Path access: `/sys/devices/**/power/*`
- System power management control
- Plug-side

**Parallel install assessment:** Power management sysfs is system-global configuration. Two instances setting different power policies would conflict.

---

#### ptp

**Code analysis:**
- Device access: `/dev/ptp[0-9]*`
- Precision Time Protocol hardware clock
- Plug-side, implicit on core and classic

**Parallel install assessment:** PTP hardware clocks are physical timestamping devices. Shared resource.

---

#### pwm

**Code analysis:**
- Path access: `/sys/class/pwm/pwmchip<N>` (numbered channel)
- Specific PWM channel control
- Plug-side

**Parallel install assessment:** Numbered PWM channels are physical hardware outputs. Two instances claiming the same channel would conflict.

---

#### spi

**Code analysis:**
- Device access: `/dev/spidev<N>.<M>` (numbered bus and chip select)
- Specific SPI bus access
- Both plug and slot sides

**Parallel install assessment:** SPI buses are numbered physical hardware. Two instances accessing the same SPI bus simultaneously would cause bus contention.

---

#### u2f-devices

**Code analysis:**
- UDev rules: USB vendor/product patterns for U2F/FIDO keys
- FIDO/U2F authentication device access
- Plug-side

**Parallel install assessment:** U2F devices are physical USB tokens. Only one process can interact with a specific hardware token at a time.

---

#### uio

**Code analysis:**
- Device access: `/dev/uio[0-9]*` (numbered)
- Userspace I/O device driver framework
- Both plug and slot sides

**Parallel install assessment:** UIO devices are physical hardware exposed to userspace. Numbered device nodes are shared.

---

#### usb-gadget

**Code analysis:**
- Configfs access: USB gadget configuration filesystem
- USB peripheral mode gadget control
- Both plug and slot sides

**Parallel install assessment:** USB gadget configfs is a single system-wide interface. Two instances cannot both configure the USB gadget simultaneously.

---

#### vcio

**Code analysis:**
- Device access: `/dev/vcio`
- VideoCore I/O (Raspberry Pi GPU co-processor)
- Plug-side, implicit on core and classic

**Parallel install assessment:** `/dev/vcio` is a single hardware mailbox interface for the VideoCore GPU. Shared resource.

---

#### raw-volume

**Code analysis:**
- Specific disk partition access using a slot-declared device node
- Valid partitions are limited to disk partition names such as `sdX1`, `nvme0n1p1`, `mmcblk0p1`, etc.
- Uses AppArmor and udev rules derived from the slot's path attribute
- Device-specific and not instance-aware

**Parallel install assessment:** This interface is tied to a specific partition rather than an instance name. Two parallel instances can only be safe if they are deliberately connected to different partitions.

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
