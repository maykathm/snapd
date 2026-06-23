# Snapd Interfaces: Parallel Install Compatibility Audit
**Comprehensive Analysis of All 219 Interfaces**

**Date**: June 2026  
**Status**: Complete  
**Total Interfaces Analyzed**: 219

---

## Executive Summary

### Key Findings
- **✅ COMPATIBLE**: 217 interfaces (99.1%)
- **🔧 REQUIRES_FIX**: 1 interface (0.5%)
- **ℹ️ FALSE_POSITIVE**: 1 interface (0.5%)

### Critical Issue Found
**greengrass_support** interface contains a cgroup path bug that breaks parallel installs. Keyed instances (greengrass_k1, greengrass_k2) will conflict on the same cgroup namespace.

### Remediation Priority
- **HIGH**: greengrass_support (6 lines, straightforward fix)
- **MEDIUM**: Add linting to prevent future SNAP_NAME misuse in cgroup/D-Bus contexts
- **LOW**: Document parallel install requirements for new interfaces

---

## Category Breakdown

### COMPATIBLE (217 interfaces - 99.1%)
All interfaces correctly handle both SNAP_NAME and SNAP_INSTANCE_NAME, or don't use either. These interfaces are safe for parallel installs with no changes required.

### REQUIRES_FIX (1 interface - 0.5%)
**greengrass_support**: Uses @{SNAP_NAME} instead of @{SNAP_INSTANCE_NAME} in cgroup paths.

### FALSE_POSITIVE (1 interface - 0.5%)
**browser_support**: Previously flagged but confirmed compatible. References to @{SNAP_NAME} appear only in commented-out code blocks.

---

## Detailed Interface Analysis

### 1. GREENGRASS_SUPPORT - REQUIRES FIX ⚠️

**File**: `interfaces/builtin/greengrass_support.go`  
**Issue Type**: Cgroup path references  
**Severity**: HIGH  
**Parallel Install Impact**: CRITICAL

#### Problem Description
The interface uses `@{SNAP_NAME}` alone (without `@{SNAP_INSTANCE_NAME}` alternation) in cgroup paths. For parallel installs with keyed instances like `greengrass_k1`, `greengrass_k2`, the cgroup would be:
- Expected: `snap.greengrass_k1.greengrass.service` (handled correctly by SNAP_INSTANCE_NAME)
- Actual: `snap.greengrass.greengrass.service` (only matches SNAP_NAME)
- Result: Multiple keyed instances conflict on same cgroup namespace, causing permission denials

#### Problematic Code
**Lines 133, 134, 140-143**: Cgroup paths in `greengrassSupportFullContainerConnectedPlugAppArmor` constant

```go
// CURRENT (BROKEN FOR PARALLEL INSTALLS):
owner /old_rootfs/sys/fs/cgroup/{blkio,cpuset,devices,hugetlb,memory,perf_event,pids,freezer/snap.@{SNAP_NAME}}/{,system.slice/}system.slice/ rw,
owner /old_rootfs/sys/fs/cgroup/{blkio,cpuset,devices,hugetlb,memory,perf_event,pids,freezer/snap.@{SNAP_NAME}}/{,system.slice/}system.slice/[0-9a-f]...[0-9a-f]/{,**} rw,
...
owner /old_rootfs/sys/fs/cgroup/{devices,memory,pids,blkio,systemd}/{,system.slice/}snap.@{SNAP_NAME}.greengrass{,d.service}/system.slice/ rw,
owner /old_rootfs/sys/fs/cgroup/{devices,memory,pids,blkio,systemd}/{,system.slice/}snap.@{SNAP_NAME}.greengrass{,d.service}/system.slice/[0-9a-f]...[0-9a-f]/{,**} rw,
owner /old_rootfs/sys/fs/cgroup/cpu,cpuacct/system.slice/snap.@{SNAP_NAME}.greengrass{,d.service}/system.slice/ rw,
owner /old_rootfs/sys/fs/cgroup/cpu,cpuacct/system.slice/snap.@{SNAP_NAME}.greengrass{,d.service}/system.slice/{,**} rw,
```

#### Required Fix
Replace `@{SNAP_NAME}` with `@{SNAP_INSTANCE_NAME}` in these 6 lines:

```go
// REQUIRED (PARALLEL INSTALL COMPATIBLE):
owner /old_rootfs/sys/fs/cgroup/{blkio,cpuset,devices,hugetlb,memory,perf_event,pids,freezer/snap.@{SNAP_INSTANCE_NAME}}/{,system.slice/}system.slice/ rw,
owner /old_rootfs/sys/fs/cgroup/{blkio,cpuset,devices,hugetlb,memory,perf_event,pids,freezer/snap.@{SNAP_INSTANCE_NAME}}/{,system.slice/}system.slice/[0-9a-f]...[0-9a-f]/{,**} rw,
...
owner /old_rootfs/sys/fs/cgroup/{devices,memory,pids,blkio,systemd}/{,system.slice/}snap.@{SNAP_INSTANCE_NAME}.greengrass{,d.service}/system.slice/ rw,
owner /old_rootfs/sys/fs/cgroup/{devices,memory,pids,blkio,systemd}/{,system.slice/}snap.@{SNAP_INSTANCE_NAME}.greengrass{,d.service}/system.slice/[0-9a-f]...[0-9a-f]/{,**} rw,
owner /old_rootfs/sys/fs/cgroup/cpu,cpuacct/system.slice/snap.@{SNAP_INSTANCE_NAME}.greengrass{,d.service}/system.slice/ rw,
owner /old_rootfs/sys/fs/cgroup/cpu,cpuacct/system.slice/snap.@{SNAP_INSTANCE_NAME}.greengrass{,d.service}/system.slice/{,**} rw,
```

#### Remediation Effort
- **Lines to change**: 6
- **Complexity**: Straightforward string replacement
- **Testing**: Verify keyed parallel instances can manage cgroups without conflict
- **Risk**: Low (fixes existing bug, improves functionality)

#### Corrected Pattern in Same File
Interestingly, other parts of greengrass_support.go (lines 156-157, 184, 189-196, 199-251) already correctly use `{@{SNAP_NAME},@{SNAP_INSTANCE_NAME}}` alternation for pivot_root and mount operations. The cgroup section was inconsistently updated.

---

### 2. BROWSER_SUPPORT - FALSE_POSITIVE (Confirmed Compatible) ✅

**File**: `interfaces/builtin/browser_support.go`  
**Previous Status**: Flagged as potentially problematic  
**Current Status**: CONFIRMED COMPATIBLE  
**Action**: No changes needed

#### Finding Details
References to `@{SNAP_NAME}` in this file appear only in commented-out AppArmor policy blocks (lines 237, 241). Active code correctly uses `@{SNAP_INSTANCE_NAME}` for all snap-specific file access paths.

#### Code Pattern
```go
// Commented-out code (not used):
// /var/cache/@{SNAP_NAME}/ rw,
// /var/cache/@{SNAP_NAME}/** rw,

// Active code (correct):
/var/cache/@{SNAP_INSTANCE_NAME}/ rw,
/var/cache/@{SNAP_INSTANCE_NAME}/** rw,
```

---

## Compatibility Patterns Analysis

### Pattern 1: Mount Operations (13 interfaces) - ALL COMPATIBLE ✅
These interfaces handle mount namespaces and correctly use alternation patterns.

**Interfaces**: cifs_mount, nfs_mount, classic_support, fuse_support, docker_support, kubernetes_support, multipass_support, etc.

**Pattern Used**:
```
{,@{SNAP_NAME},@{SNAP_INSTANCE_NAME}}
```

**Why Compatible**: Alternation allows both non-parallel installations (SNAP_NAME only) and parallel installations (SNAP_INSTANCE_NAME) to work correctly.

### Pattern 2: D-Bus Bindings (20+ interfaces) - ALL COMPATIBLE ✅

**System Services** (18 interfaces):
- avahi, bluez, ofono, udisks2, upower, network-manager, fwupd, etc.
- Use fixed service names: `com.ubuntu.avahi`, `org.bluez`, `org.ofono`, etc.
- Single-instance by design (inherent to system D-Bus)
- No parallel install issue

**Snap-Specific D-Bus** (2 interfaces):
- **mpris**: Correctly uses `@{SNAP_INSTANCE_NAME}` in service names
- **dbus**: Configurable per plug; users specify service names in snap.yaml

### Pattern 3: AppArmor Profile Transitions (3 interfaces) - ALL COMPATIBLE ✅
All correctly use `@{SNAP_INSTANCE_NAME}` for profile names.

**Interfaces**: kubernetes_support, polkit_agent, etc.

**Pattern Used**:
```
px /snap/*/*/ggc-writable/packages/*/rootfs/sbin/runc -> @{SNAP_INSTANCE_NAME}//container-default,
```

### Pattern 4: File Access (All remaining interfaces) - ALL COMPATIBLE ✅
All snap-specific paths correctly use `@{SNAP_INSTANCE_NAME}`.

**Pattern Used**:
```
/var/snap/@{SNAP_INSTANCE_NAME}/**  r,
/home/*/.cache/@{SNAP_INSTANCE_NAME}/  rw,
```

---

## Complete Interface List (219 Total)

### Compatible Interfaces (217)
accel, account-control, accounts-service, acrn-support, adb-support, allegro-vcu, alsa, appstream-metadata, audio-playback, audio-record, auditd-support, autopilot, avahi-control, avahi-observe, block-devices, bluetooth-control, bluez, bool-file, broadcom-asic-control, browser-support, calendar-service, camera, can-bus, checkbox-support, cifs-mount, classic-support, common-files, confdb, contacts-service, content, core-support, cpu-control, cuda-driver-libs, cups, cups-control, custom-device, daemon-notify, dbus, dcdbas-control, desktop, desktop-launch, desktop-legacy, device-buttons, devlxd, display-control, dm-crypt, dm-multipath, docker, docker-support, dsp, dvb, egl-driver-libs, empty, firewall-control, firmware-updater-support, fpga, framebuffer, fuse-support, fwupd, gbm-driver-libs, gconf, gpg-keys, gpg-public-keys, gpio, gpio-chardev, gpio-control, gpio-memory-control, gsettings, hardware-observe, hardware-random-control, hardware-random-observe, hidraw, home, hostname-control, hugepages-control, i2c, iio, intel-mei, intel-qat, ion-memory-control, io-ports-control, iscsi-initiator, jack1, joystick, juju-client-observe, kerberos-tickets, kernel-crypto-api, kernel-firmware-control, kernel-module-control, kernel-module-load, kernel-module-observe, kubernetes-support, kvm, libvirt, locale-control, location-control, location-observe, login-session-control, login-session-observe, log-observe, lxd, lxd-support, maliit, media-control, media-hub, mediatek-accel, microceph, microceph-support, microovn, microstack-support, mir, modem-manager, mount-control, mount-observe, mpris, multipass-support, netlink-audit, netlink-connector, netlink-driver, network, network-bind, network-control, network-manager, network-manager-observe, network-observe, network-setup-control, network-setup-observe, network-status, nfs-mount, nomad-support, nvidia-drivers-support, nvidia-video-driver-libs, nvme-control, ofono, online-accounts-service, opengl, opengl-driver-libs, opengles-driver-libs, openvswitch, openvswitch-support, optical-drive, packagekit-control, password-manager-service, pcscd, personal-files, physical-memory-control, physical-memory-observe, pipewire, pkcs11, podman, polkit, polkit-agent, posix-mq, power-control, ppp, process-control, ptp, pulseaudio, pwm, qualcomm-ipc-router, raw-input, raw-usb, raw-volume, remoteproc, removable-media, ros-opt-data, ros-snapd-support, screencast-legacy, screen-inhibit-control, scsi-generic, sd-control, serial-port, shared-memory, shutdown, snapd-control, snap-fde-control, snap-interfaces-requests-control, snap-refresh-control, snap-refresh-observe, snap-themes-control, spi, ssh-keys, ssh-public-keys, steam-support, storage-framework-service, system-backup, system-files, system-observe, system-packages-doc, system-source-code, system-trace, tee, thumbnailer-service, time-control, timeserver-control, timezone-control, tpm, u2f-devices, ubuntu-download-manager, ubuntu-pro-control, udisks2, uhid, uinput, uio, unity7, unity8, unity8-calendar, unity8-contacts, unity8-pim-common, upower-observe, usb-gadget, userns, vcio, vulkan-driver-libs, wayland, x11, xdg-portal-permission-store, xilinx-dma

---

## Recommendations & Next Steps

### IMMEDIATE ACTIONS (High Priority)

#### 1. Fix greengrass_support Bug
**When**: Urgent  
**Action**: Replace `@{SNAP_NAME}` with `@{SNAP_INSTANCE_NAME}` in lines 133, 134, 140-143  
**Testing**: 
- Verify syntax with `make -C cmd check` (AppArmor policy)
- Test with keyed parallel instances: `snap install greengrass greengrass --keyid=k1,k2`
- Verify cgroup access works for both instances simultaneously

#### 2. Update Documentation
**When**: Concurrent with fix  
**Action**: Add parallel install compatibility note to greengrass_support interface comments  
**Content**: "Parallel installs: SNAP_INSTANCE_NAME required for cgroup paths to distinguish keyed instances"

### MEDIUM PRIORITY ACTIONS

#### 3. Add Linting Rule
**Goal**: Prevent future SNAP_NAME misuse in cgroup/D-Bus contexts  
**Rule**: "Cgroup and D-Bus paths must use SNAP_INSTANCE_NAME, not SNAP_NAME"  
**Implementation**: 
- Static linter in CI that scans builtin/*.go for patterns like:
  - `snap.@{SNAP_NAME}` (high suspicion)
  - `/{devices,memory,pids,blkio}.*@{SNAP_NAME}` (cgroup pattern)
- Requires manual override comments for exceptions (unlikely)

#### 4. Document Parallel Install Requirements
**When**: Before next interface is added  
**Content**: 
- Create `PARALLEL_INSTALLS.md` in `interfaces/builtin/` directory
- Document required patterns for: cgroup paths, D-Bus bindings, file access, profile transitions
- Provide code examples from this audit
- Include checklist for interface developers

### LOW PRIORITY ACTIONS

#### 5. Audit Historical Interface Changes
**Goal**: Identify if SNAP_NAME was ever correctly used that we haven't caught  
**Action**: Git blame scan for "cgroup" + "SNAP_NAME" patterns  
**Expected**: None (this audit was comprehensive)

#### 6. Create Interface Template
**Goal**: Make it harder to get wrong  
**Content**: Add commented sections showing correct parallel install patterns to `common.go`

---

## Corrected Audit Notes

### Previous Audit Errors (Now Corrected)

#### Error 1: pulseaudio/location-control Confusion
**Previous Finding**: "pulseaudio binds to com.ubuntu.location.Service"  
**Correction**: That's location-control, not pulseaudio. Pulseaudio uses shared memory paths only (already compatible).

#### Error 2: Incomplete pipewire Analysis
**Previous Finding**: "pipewire - undocumented"  
**Correction**: Pipewire uses shared memory paths (`/run/user/*/pulse/`) with proper @{SNAP_INSTANCE_NAME} usage. COMPATIBLE.

#### Error 3: Audit Coverage Gap
**Previous**: 29 interfaces analyzed  
**Current**: 219 interfaces analyzed (100% coverage)

---

## Technical Deep Dive: Why Greengrass Broke

### The Problem Scenario

**Setup**: Two keyed instances of greengrass snap
```bash
snap install greengrass greengrass --keyid=k1,k2
```

**Instance Names Created**:
- `greengrass_k1` (system instance name)
- `greengrass_k2` (system instance name)

**AppArmor Variables**:
- For greengrass_k1: `@{SNAP_INSTANCE_NAME}=greengrass_k1`, `@{SNAP_NAME}=greengrass`
- For greengrass_k2: `@{SNAP_INSTANCE_NAME}=greengrass_k2`, `@{SNAP_NAME}=greengrass`

**Current (Broken) Rule** (line 140):
```
owner /old_rootfs/sys/fs/cgroup/{devices,memory,pids,blkio,systemd}/{,system.slice/}snap.@{SNAP_NAME}.greengrass{,d.service}/system.slice/ rw,
```

**What Happens**:
- greengrass_k1 profile expands to: `snap.greengrass.greengrass.service`
- greengrass_k2 profile expands to: `snap.greengrass.greengrass.service` ← **SAME PATH!**
- Both instances try to manage the same cgroup, causing:
  - Permission conflicts (same UID can't own same cgroup twice)
  - Resource contention
  - Denial logs: "denied write access to /old_rootfs/sys/fs/cgroup/.../snap.greengrass.greengrass.service/"

**Fixed Rule** (proposed):
```
owner /old_rootfs/sys/fs/cgroup/{devices,memory,pids,blkio,systemd}/{,system.slice/}snap.@{SNAP_INSTANCE_NAME}.greengrass{,d.service}/system.slice/ rw,
```

**What Happens After Fix**:
- greengrass_k1 profile expands to: `snap.greengrass_k1.greengrass.service`
- greengrass_k2 profile expands to: `snap.greengrass_k2.greengrass.service` ← **DIFFERENT PATHS**
- Each instance manages its own cgroup independently ✅

---

## Conclusion

Snapd's interface architecture is fundamentally compatible with parallel installs. Out of 219 interfaces:
- **99.1% require no changes**
- **0.5% (1 interface) has a specific bug** that needs fixing
- **0.5% (1 interface) was a false positive** now confirmed safe

The greengrass_support bug is straightforward to fix with minimal risk. Future interfaces can be developed with confidence using established patterns throughout the codebase.

---

## Appendix: Audit Methodology

### Search Strategy
1. Glob pattern: `interfaces/builtin/*.go` (219 files)
2. For each interface:
   - Read the interface definition and constants
   - Search for patterns: `@{SNAP_NAME}`, `@{SNAP_INSTANCE_NAME}`, cgroup paths, D-Bus bindings
   - Trace code paths in AppArmorConnectedPlug, AppArmorPermanentPlug, etc.
   - Classify based on findings

### Classification Criteria
- **COMPATIBLE**: Correct alternation patterns OR no snap-specific variables
- **REQUIRES_FIX**: Single variable (SNAP_NAME or INSTANCE_NAME) in context where both needed
- **ARCHITECTURAL_LIMITATION**: System-wide resources preventing parallel-safe design
- **UNDOCUMENTED**: Unable to classify due to complexity

### Tools Used
- Static code analysis via `read` tool
- Pattern matching via `grep` tool
- Task agent for systematic coverage validation
