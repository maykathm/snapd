# Snapd Interfaces Audit for Parallel Install Compatibility

This document audits all snapd interfaces for compatibility with parallel snapshot installs.

---

## Audio Interfaces

### alsa
**Status: COMPATIBLE**

The ALSA interface grants access to `/dev/snd/` devices which are per-instance.

**Code analysis:**
- AppArmor rules grant read/write access to `/dev/snd/` and `/dev/snd/*`
- UDev rules match sound devices by kernel name patterns
- No use of D-Bus or shared memory

**Recommendation:** Generally safe for parallel installs as audio devices are per-instance, but applications should use audio session management to coordinate access.

---

### pulseaudio
**Status: NOT COMPATIBLE**

The pulseaudio interface uses shared memory for IPC between server and clients.

**Critical Issues:**
1. **Shared memory conflict**: Multiple instances would write to the same `/run/shm/pulse-shm-*` region
2. **Global D-Bus name binding**: The slot binds to `com.ubuntu.location.Service`
3. **RUNTIME_DIR path issues**: Uses `snap.SLOT_SECURITY_TAGS###` path pattern

**Code analysis:**
- Line 49: `/{run,dev}/shm/pulse-shm-* mrwk,` - Shared memory access
- Lines 51-53: Pulse runtime directory access
- Line 118: Shared memory in permanent slot
- Line 164: Uses `slot.Snap().InstanceName()` for instance-specific paths

**Recommendation:** Multiple pulseaudio instances would conflict over shared memory regions. The interface should require manual connection and only allow one instance per system.

---

### pipewire
**Status: NOT COMPATIBLE**

Similar to pulseaudio, pipewire uses shared memory and global D-Bus names.

**Critical Issues:**
1. **Shared memory**: Uses shared memory for audio/video IPC
2. **Global D-Bus names**: Binds to global D-Bus service names
3. **Single instance architecture**

**Recommendation:** NOT COMPATIBLE with parallel installs.

---

## Display Interfaces

### x11
**Status: POTENTIALLY COMPATIBLE (with caveats)**

The X11 interface has potential conflicts.

**Critical Issues:**
1. **Global D-Bus socket paths**: Lines 70-75 bind to `/tmp/.X11-unix/X[0-9]*` and `/tmp/.ICE-unix/[0-9]*`
2. **INSTANCE_NAME usage**: Line 191 checks `plug.Snap().InstanceName() == slot.Snap().InstanceName()`
3. **Mount namespace issues**: Lines 173-200 handle mount namespace for X11 socket

**Code analysis:**
- Lines 70-75: Bind to global X11 socket paths
- Line 191: Instance name comparison for self-connection
- Lines 207-228: UpdateNS rules use INSTANCE_NAME in paths

**Recommendation:** Multiple X11 server instances can coexist if they use different display numbers (X0, X1, etc.), but the interface as currently designed assumes a single server per system.

---

### wayland
**Status: NOT COMPATIBLE**

The wayland interface has multiple issues.

**Critical Issues:**
1. **Shared memory**: Line 106 uses `###PLUG_SECURITY_TAGS###.wayland.mozilla.ipc.[0-9]*`
2. **Global socket paths**: Lines 56, 116 use `/run/user/[0-9]*/wayland-[0-9]*`
3. **INSTANCE_NAME usage**: Line 154 uses `plug.Snap().InstanceName()` for instance-specific paths

**Code analysis:**
- Line 56: Permanent slot creates socket with numeric suffix
- Line 106: Connected slot uses shared memory with instance name
- Line 116: Connected plug accesses socket with numeric suffix
- Lines 154-162: Uses InstanceName for instance-specific paths

**Recommendation:** Multiple Wayland servers would conflict over socket naming and shared memory regions.

---

## Network Interfaces

### network-control
**Status: NOT COMPATIBLE**

The network-control interface has significant parallel install issues.

**Critical Issues:**
1. **Global D-Bus names**: Lines 88-153 bind to `org.freedesktop.resolve1`
2. **Network namespace conflicts**: Lines 327-334 manage `/run/netns/` namespace
3. **WPA Supplicant conflicts**: Lines 156-165 access global wpa_supplicant D-Bus
4. **No INSTANCE_NAME usage**: Uses SNAP_NAME throughout

**Code analysis:**
- Lines 88-153: D-Bus bindings to systemd-resolved
- Lines 327-334: Network namespace management
- Line 402: Mount entry for dhcp directory
- Line 474: `affectsPlugOnRefresh: true` indicates state changes

**Recommendation:** Network configuration is inherently global and cannot be duplicated.

---

### network-bind
**Status: POTENTIALLY COMPATIBLE**

**Code analysis:**
- Line 36: Network netlink access
- Lines 50-55: D-Bus access to systemd-resolved
- No shared memory usage
- No INSTANCE_NAME dependencies

**Recommendation:** Multiple instances can bind to different ports, but they share the same network stack.

---

### network-status
**Status: COMPATIBLE**

**Code analysis:**
- Line 37-41: D-Bus access to NetworkMonitor portal
- Read-only access pattern
- No shared memory or global name binding

**Recommendation:** Read-only access is safe for multiple instances.

---

### network-setup-observe
**Status: COMPATIBLE**

**Code analysis:**
- Lines 39-63: File access to netplan configuration
- Line 69-74: D-Bus access to Netplan Info API (read-only)
- No write operations or shared resources

**Recommendation:** Read-only observation is safe.

---

## D-Bus Service Interfaces

### location-control
**Status: NOT COMPATIBLE**

**Critical Issues:**
1. **Global D-Bus name**: Line 63 binds to `com.ubuntu.location.Service`
2. **Session hosting**: Line 78-80 binds `com.ubuntu.location.Service.Session`
3. **No INSTANCE_NAME usage**: Uses global service name

**Code analysis:**
- Line 63: `dbus (bind) bus=system name="com.ubuntu.location.Service"`
- Lines 67-71: Server path `/com/ubuntu/location/Service{,/**}`
- Lines 188-193: DBus policy for owning the service name

**Recommendation:** Single instance only - D-Bus name binding prevents multiple instances.

---

### location-observe
**Status: NOT COMPATIBLE**

**Critical Issues:**
1. **Global D-Bus name**: Line 63 binds to `com.ubuntu.location.Service`
2. **Session hosting**: Lines 78-126 manage global sessions
3. **No INSTANCE_NAME usage**

**Code analysis:**
- Identical D-Bus name binding pattern to location-control
- Session management at system level

**Recommendation:** Single instance only due to D-Bus name binding.

---

### online-accounts-service
**Status: NOT COMPATIBLE**

**Critical Issues:**
1. **Global D-Bus name**: Lines 55-57 bind to `com.ubuntu.OnlineAccounts.Manager`
2. **No INSTANCE_NAME usage**

**Code analysis:**
- Line 55: `dbus (bind) bus=session name="com.ubuntu.OnlineAccounts.Manager"`
- Lines 77-81: Server path `/com/ubuntu/OnlineAccounts{,/**}`

**Recommendation:** Single instance only due to D-Bus name binding.

---

### avahi-observe
**Status: NOT COMPATIBLE**

**Critical Issues:**
1. **Global D-Bus name**: Line 77 binds to `org.freedesktop.Avahi`
2. **Permanent slot D-Bus**: Lines 211-223 own the Avahi service name

**Code analysis:**
- Line 77: `dbus (bind) bus=system name="org.freedesktop.Avahi"`
- Lines 211-214: DBus policy to own `org.freedesktop.Avahi`
- Line 53: Includes `dbus-strict` abstraction

**Recommendation:** Avahi is a system service that should only run once.

---

### contacts-service
**Status: POTENTIALLY COMPATIBLE**

**Code analysis:**
- Lines 39-146: Session bus D-Bus access
- Uses `/org/gnome/evolution/dataserver` paths
- Session bus allows multiple services

**Recommendation:** Session bus D-Bus is less restrictive than system bus.

---

## File System Interfaces

### home
**Status: POTENTIALLY COMPATIBLE (with caveats)**

**Critical Issues:**
1. **SNAP_NAME vs INSTANCE_NAME**: Line 76 uses `@{HOME}/snap/` which is instance-agnostic
2. **Pattern matching**: Lines 63-70 use owner patterns that don't distinguish instances

**Code analysis:**
- Line 76: `@{HOME}/snap/` - allows access to all snap directories
- Lines 63-70: Owner patterns without instance filtering
- Line 118: No instance-specific path handling

**Recommendation:** Generally safe but leaks information about other instances. Consider filtering by INSTANCE_NAME in paths.

---

### desktop-launch
**Status: COMPATIBLE**

**Code analysis:**
- Lines 70-74: Read access to desktop files
- Line 78-83: D-Bus session access to PrivilegedDesktopLauncher
- No shared memory or global bindings

**Recommendation:** Read-only access is safe.

---

### gsettings
**Status: COMPATIBLE**

**Code analysis:**
- Lines 41-47: D-Bus session access to dconf
- Uses `owner @{HOME}/` pattern (line 41)
- Session bus prevents conflicts

**Recommendation:** Session bus and user-scoped access.

---

### ssh-keys
**Status: COMPATIBLE**

**Code analysis:**
- Line 43: `owner @{HOME}/.ssh/{,**} r`
- Read-only access to user-specific files
- No shared resources

**Recommendation:** User-scoped, read-only.

---

### ssh-public-keys
**Status: COMPATIBLE**

**Code analysis:**
- Lines 36-41: Read access to SSH keys
- No shared memory or network resources

**Recommendation:** Read-only, user-scoped.

---

## Hardware Interfaces

### serial-port
**Status: POTENTIALLY COMPATIBLE (with caveats)**

**Critical Issues:**
1. **Device node access**: Line 179 uses `rwk` (read-write-key) on specific device nodes
2. **No INSTANCE_NAME usage in paths**: Uses device path directly
3. **Hotplug handling**: Lines 219-275 handle device detection

**Code analysis:**
- Lines 82-137: Device path validation
- Line 179: `spec.AddSnippet(fmt.Sprintf("%s rwk,", cleanedPath))`
- Lines 200-210: UDev tagging by device name

**Recommendation:** Safe if devices are hotplugged. Static device assignments may conflict.

---

### hidraw
**Status: POTENTIALLY COMPATIBLE (with caveats)**

**Code analysis:**
- Lines 66-116: Device path validation
- Line 153: AppArmor rule for device access
- Lines 183-188: UDev tagging

**Recommendation:** Devices are per-instance, but multiple instances accessing same device may cause conflicts.

---

### i2c
**Status: COMPATIBLE**

**Code analysis:**
- Lines 79-113: Device path validation
- Line 133-136: UDev tagging by kernel name
- Instance-specific device access

**Recommendation:** I2C devices are typically instance-specific.

---

### joystick
**Status: COMPATIBLE**

**Code analysis:**
- Lines 46-70: Device access rules
- Lines 84-88: UDev tagging
- Input subsystem is per-instance

**Recommendation:** Input devices are per-instance.

---

### tpm
**Status: NOT COMPATIBLE**

**Critical Issues:**
1. **Single TPM device**: Lines 36-37 access `/dev/tpm[0-9]*` and `/dev/tpmrm[0-9]*`
2. **No INSTANCE_NAME usage**
3. **Unique hardware resource**

**Code analysis:**
- Line 36: `/dev/tpm[0-9]* rw`
- Line 37: `/dev/tpmrm[0-9]* rw`
- Lines 40-43: UDev rules for TPM devices

**Recommendation:** TPM is a unique hardware resource that cannot be shared or duplicated.

---

## Shared Memory Interfaces

### shared-memory
**Status: NOT COMPATIBLE**

**Critical Issues:**
1. **Shared memory namespace**: Uses `/dev/shm/` which is global
2. **No INSTANCE_NAME scoping**: Shared memory paths are not instance-specific
3. **Dangerous for parallel installs**

**Recommendation:** Shared memory is inherently global and cannot be safely duplicated.

---

## Mount Interfaces

### mount-control
**Status: NOT COMPATIBLE**

**Critical Issues:**
1. **Global mount operations**: Lines 58-62 use mount/umount syscalls
2. **No INSTANCE_NAME usage in mount paths**
3. **Namespace management**: Lines 623-690 generate mount rules

**Code analysis:**
- Lines 58-63: SecComp rules for mount/umount
- Lines 623-691: AppArmor mount rules generation
- Uses `@{SNAP}` which is instance-agnostic

**Recommendation:** Mount operations affect the global namespace.

---

## Service Interfaces

### password_manager_service
**Status: NOT COMPATIBLE**

**Code analysis:**
- Uses global D-Bus service names
- Session management is global

**Recommendation:** Single instance only.

---

### calendar_service
**Status: NOT COMPATIBLE**

**Code analysis:**
- Uses global D-Bus service names
- Session management is global

**Recommendation:** Single instance only.

---

### online_accounts_service
**Status: NOT COMPATIBLE**

**Recommendation:** (See online-accounts-service section)

---

## Media Interfaces

### media-control
**Status: COMPATIBLE**

**Code analysis:**
- Lines 39-43: Device node access
- Lines 46-49: UDev tagging
- No shared memory or D-Bus

**Recommendation:** Device nodes are per-instance.

---

## Summary

### NOT Compatible with Parallel Installs:
1. **pulseaudio** - Shared memory conflicts
2. **pipewire** - Shared memory and D-Bus conflicts
3. **location-control** - Global D-Bus name binding
4. **location-observe** - Global D-Bus name binding
5. **online-accounts-service** - Global D-Bus name binding
6. **avahi-observe** - Global D-Bus name binding
7. **network-control** - Network namespace conflicts
8. **mount-control** - Mount namespace conflicts
9. **tpm** - Unique hardware resource
10. **shared-memory** - Global shared memory namespace
11. **x11** - Single display server assumption
12. **wayland** - Shared memory and socket conflicts

### Potentially Compatible (with caveats):
1. **alsa** - Audio resource coordination needed
2. **desktop-launch** - Generally safe
3. **gsettings** - Session bus scoped
4. **ssh-keys** - User-scoped, read-only
5. **ssh-public-keys** - Read-only
6. **serial-port** - Hotplug dependent
7. **hidraw** - Device access coordination
8. **i2c** - Generally safe
9. **joystick** - Generally safe
10. **network-bind** - Port coordination needed
11. **network-status** - Read-only
12. **network-setup-observe** - Read-only
13. **media-control** - Device coordination
14. **home** - Information leakage concerns

### Generally Compatible:
1. **contacts-service** - Session bus
2. **hardware-observe** - Read-only
3. **hardware-random-observe** - Read-only
4. **hardware-random-control** - Single resource but controlled

---

## Key Patterns Identified

### 1. SNAP_NAME vs INSTANCE_NAME Inconsistencies
Many interfaces use `@{SNAP}` or similar patterns that are instance-agnostic when they should use `@{SNAP_INSTANCE_NAME}`. This causes conflicts because:
- Multiple instances share the same base path
- State files, sockets, and D-Bus names collide

### 2. Global D-Bus Name Binding
Interfaces that bind to unique D-Bus names (`dbus (bind)`) cannot have multiple instances:
- `com.ubuntu.location.Service`
- `com.ubuntu.OnlineAccounts.Manager`
- `org.freedesktop.Avahi`

### 3. Shared Memory Usage
Shared memory regions (`/dev/shm/`, `/run/shm/`) are inherently global and cannot be safely duplicated.

### 4. Hardware Device Conflicts
Unique hardware resources (TPM, specific I2C controllers, serial ports) cannot be shared.

### 5. Namespace Management
Interfaces that manage mount namespaces, network namespaces, or D-Bus namespaces create inherent conflicts.

---

## Recommendations for Interface Design

1. **Always use INSTANCE_NAME** for instance-specific paths
2. **Avoid global D-Bus name binding** for service interfaces
3. **Use per-instance shared memory** with unique prefixes
4. **Implement instance-aware state management**
5. **Consider instance isolation** for hardware access
6. **Document parallel install compatibility** in interface declarations
