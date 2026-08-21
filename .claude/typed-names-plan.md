# Plan: Typed `naming.SnapName` / `naming.InstanceName` to prevent name-argument swaps

## Objective
Introduce distinct Go types for snap names and snap instance names so the compiler rejects passing one where the other is expected. Migrate incrementally via self-contained patches, ending with validating constructors wired into existing input boundaries.

## Settled design decisions
- Types live in `snap/naming` (package `snap` can't host them; `snap.InstanceName(...)` already exists as a function).
- **Defined types**, not aliases:
  ```go
  type SnapName string
  type InstanceName string
  ```
  `SnapName` name is intentional despite coexisting with `SnapRef.SnapName()` (method) and `ComponentRef.SnapName` (field). Legal Go, slightly noisy, accepted.
- **Two-tier construction:**
  - Free unchecked conversion `naming.InstanceName(s)` / `naming.SnapName(s)` for the trusted interior and error-free accessors.
  - Validating boundary constructors `ParseSnapName` / `ParseInstanceName` wrapping existing `ValidateSnap` / `ValidateInstance`.
- This yields **documented**, not type-enforced, validity (accessors and JSON/state unmarshal cast unchecked). Accepted as the pragmatic norm.
- **Do NOT touch:** literal `@{SNAP_NAME}` / `@{SNAP_INSTANCE_NAME}` AppArmor vars, `SNAP_NAME`/`SNAP_INSTANCE_NAME` env keys, profile templates — these are strings, not semantic values.
- Persisted JSON/YAML/state fields stay `string`; convert at (de)serialization with `.String()` / cast. Reason is review-noise, not correctness.

---

## Patch sequence
Each patch must compile, pass `./run-checks --static` and `./run-checks --unit`, stay ≤500 lines, and avoid test changes except compile fixes.

### ✅ Patch 1 — Add types + helpers + tests (`snap/naming` only, inert)
**Status: COMPLETED**

Added to `snap/naming`:
```go
type SnapName string
type InstanceName string

func (n SnapName) String() string
func (n InstanceName) String() string
func NewInstanceName(snap SnapName, instanceKey string) InstanceName
func (n InstanceName) SnapName() SnapName        // split, drop key
func (n InstanceName) InstanceKey() string
func ParseSnapName(s string) (SnapName, error)       // wraps ValidateSnap
func ParseInstanceName(s string) (InstanceName, error) // wraps ValidateInstance
```

Tests: plain `"foo"`, parallel `"foo_bar"`, build-from-parts, `String()`, and `Parse*` accept/reject cases (reuse `ValidateSuite` data). No existing call sites change. No behavior change.

**Files modified:**
- `snap/naming/name.go` (new)
- `snap/naming/name_test.go` (new)

**Commit message:**
```
snap/naming: add typed SnapName and InstanceName

Add distinct SnapName and InstanceName types with helpers and
validating Parse constructors to guard against passing a snap name
where an instance name is expected, and vice versa. This is an inert
addition; no existing call sites are changed yet.
```

### ✅ Patch 2 — Leaf filesystem path helpers (island in `snap`)
**Status: COMPLETED**

Convert instance-name params to `naming.InstanceName` in:
- Path helpers: `BaseDir`, `MountDir`, `MountFile`, `MountFileInDir`, `DataDir`, `BaseDataDir`, `CommonDataDir`, `CommonDataSaveDir`, `HooksDir`, `UserDataDir`, `UserCommonDataDir`, `UserSnapDir`, `UserXdgRuntimeDir`, `BaseDataHomeDirs`
- Container place info constructors: `MinimalPlaceInfo`, `MinimalSnapContainerPlaceInfo`
- Component helpers: `ComponentMountDir`, `ComponentHooksDir`, `ComponentsBaseDir`, `MinimalComponentContainerPlaceInfo`

Callers cast at call site with unchecked `naming.InstanceName(...)` since values originate from already-validated `snap.Info` or state.

**Files modified:** ~40 files
- `snap/info.go` - 15 function signatures
- `snap/component.go` - 3 function signatures
- Internal callers: `snap.Info` methods, `componentPlaceInfo`
- External callers across: `snap/snapenv`, `kernel`, `interfaces`, `cmd/*`, `daemon`, `overlord/*`, `seed`, `gadget/install`, `store/tooling`, test helpers

**Commit message:**
```
snap: type filesystem path helpers with naming.InstanceName

Convert instance-name parameters to naming.InstanceName for filesystem
path helpers (BaseDir, MountDir, DataDir, UserDataDir, etc.) and
container place info constructors. Callers cast at call sites with
unchecked conversions since values originate from already-validated
snap.Info or state. This provides compile-time protection against
swapping snap names and instance names in path construction.
```

### ✅ Patch 3 — Snap/app + security-tag helpers (island in `snap`)
**Status: COMPLETED**

Convert instance-name params to `naming.InstanceName` in:
- Security tags: `SecurityTag`, `ScopedSecurityTag`, `AppSecurityTag`, `HookSecurityTag`, `ComponentHookSecurityTag`, `NoneSecurityTag`
- Snap/app helpers: `JoinSnapApp(snap naming.InstanceName, app string)`, `SplitSnapApp(snapApp string) (naming.InstanceName, string)`

Security tags are per-instance (include instance key when present). `SplitSnapApp` now returns typed `InstanceName`, requiring `.String()` at string boundaries (e.g., JSON structs, API responses).

**Files modified:** ~25 files
- `snap/info.go` - 8 function signatures + internal `AppInfo`/`HookInfo` methods
- External callers across: `interfaces/*`, `store`, `wrappers`, `overlord/snapstate`, `overlord/hookstate/ctlcmd`, `daemon`, `cmd/snapd/cli`, `cmd/snapctl/tool/snap-exec`

**Key patterns:**
- Cast to typed with `naming.InstanceName(...)` when calling
- Convert back with `.String()` at persistence/API boundaries

**Commit message:**
```
snap: type security tags and app helpers with naming.InstanceName

Convert instance-name parameters to naming.InstanceName for security
tag functions (AppSecurityTag, HookSecurityTag, SecurityTag, etc.) and
snap/app helpers (JoinSnapApp, SplitSnapApp). Security tags are
per-instance, so this provides compile-time protection against using
snap names where instance names are required. SplitSnapApp now returns
the typed InstanceName, requiring .String() at string boundaries.
```

### ✅ Patch 4 — `interfaces.SnapAppSet.InstanceName()` typed return
**Status: COMPLETED**

Typed `SnapAppSet.InstanceName()` to return `naming.InstanceName`. Updated all call sites in `interfaces` package backends (apparmor, dbus, kmod, mount, polkit, seccomp, systemd, udev, plus configfiles, ldconfig, symlinks) to use `.String()` for map keys and string operations.

Left persisted `PlugRef.Snap` / `SlotRef.Snap` as `string` (JSON fields); convert at boundaries with `.String()` / cast.

**Files modified:**
- `interfaces/snap_app_set.go` - typed `InstanceName()` return
- `interfaces/builtin/*_backend.go` - 26 call sites fixed with `.String()`


### Patch 5 — `overlord/snapstate` internals (COMPLETED - split into 3 commits)
Type returns of `SnapSetup.SnapName()/InstanceName()` and `SnapState.InstanceName()` (unchecked casts; persisted `SideInfo.RealName` / `InstanceKey` stay strings). Update all call sites across overlord.

**Completed as 3 commits (~926 lines total):**

**Patch 5a (9606d159):** Type accessors + fix small files (66 lines, 5 files)
- `overlord/snapstate/snapmgr.go` - typed `SnapSetup`/`SnapState` accessor returns
- `overlord/snapstate/autorefresh.go` - 32 `.String()` additions
- `overlord/snapstate/autorefresh_gating.go` - 6 additions
- `overlord/snapstate/component.go` - 10 additions
- `overlord/snapstate/conflict.go` - 6 additions

**Patch 5b (3df99a9a):** Fix all call sites across overlord (730 lines, 24 files)
- **snapstate**: handlers.go (322 changes), snapstate.go (112), snapmgr.go (12), snap.go (96), storehelpers.go (10), target.go (8), handlers_components.go (30), handlers_prereq.go (4), reboot.go (22), seed.go (6), aliasesv2.go (2)
- **snapstate subdirs**: policy/ (4 files), agentnotify/ (1 file)
- **assertstate**: assertmgr.go (2 locations)
- **devicestate**: handlers_gadget.go (3 locations), systems.go (2 locations)
- **ifacestate**: handlers.go (many locations), helpers.go (3 locations), ifacestate.go (4 locations)
- **servicestate**: quota_handlers.go (2 locations)
- **hookstate/ctlcmd**: helpers.go (1 location)

**Patch 5c (58fddeace6):** Fix test files (130 lines, 13 test files)
- **ifacestate**: ifacestate_test.go (44 changes)
- **snapstate**: snapstate_update_test.go (24), handlers_prereq_test.go (24), snapstate_test.go (8), handlers_link_test.go (4), backend_test.go (2), handlers_test.go (2), refresh_test.go (2), target_test.go (2)
- **devicestate**: devicestate_systems_test.go (8), firstboot20_test.go (2)
- **managers_test.go** (6 changes)
- **hookstate/ctlcmd**: services_test.go (2 changes)

**Key challenges addressed:**
- Variable shadowing (string `snapName` parameters vs typed `snapsup.InstanceName()` returns)
- Map keys, struct literals, function arguments all needed `.String()`
- Test assertions comparing typed values with string literals required wrapping
- Changes rippled across 6 different overlord managers due to cross-package usage

### Patch 6 — `overlord/hookstate` accessor (`Context.InstanceName()`) - COMPLETED

Type `hookstate.Context.InstanceName()` to return `naming.InstanceName`. Update all call sites across hookstate and dependent packages.

**Status: COMPLETED**

**Files modified (46 total):**

**Core change:**
- `overlord/hookstate/context.go` - typed `Context.InstanceName()` return + import

**Call site updates (29 non-test files):**
- `overlord/hookstate/hooks.go` - 15 `.String()` additions
- `overlord/hookstate/ctlcmd/*.go` - 16 files updated:
  - fail.go, get.go, helpers.go, install.go, is_connected.go, kmod.go
  - model.go, mount.go, refresh.go, remove.go, services.go, set.go, umount.go, unset.go
- `overlord/configstate/hooks.go` - 6 `.String()` additions + import
- `overlord/confdbstate/confdbstate.go` - 1 `.String()` addition
- `overlord/healthstate/healthstate.go` - 1 `.String()` addition

**Test file updates (16 test files):**
- `overlord/hookstate/*_test.go` - 3 files (context_test.go, hookstate_test.go, hooks_test.go) + import
- `overlord/configstate/configstate_test.go` - 2 assertions + import
- `overlord/devicestate/*_test.go` - 3 files (firstboot_test.go, firstboot_preseed_test.go, devicestate_test.go) - 4 assertions + imports
- `overlord/servicestate/quota_handlers_test.go` - 4 assertions + import
- `overlord/snapstate/*_test.go` - 7 files + imports:
  - aliasesv2_test.go, autorefresh_test.go, handlers_link_test.go, handlers_rerefresh_test.go
  - handlers_test.go, snapstate_install_test.go, snapstate_update_test.go, target_test.go
- `overlord/snapstate/agentnotify/agentnotify_test.go` - 1 assertion + import

**Key patterns:**
- ~250+ call sites updated with `.String()` for string boundaries
- ~70 test assertions fixed with `naming.InstanceName()` or `naming.SnapName()` wrappers
- Cross-package ripple: hookstate, ctlcmd, configstate, confdbstate, healthstate, devicestate, servicestate, snapstate

**Commit message:**
```
overlord/hookstate: type Context.InstanceName() with naming.InstanceName

Type Context.InstanceName() to return naming.InstanceName for compile-time
protection against passing snap names where instance names are expected.
Update all call sites across hookstate, ctlcmd, and dependent overlord
packages to use .String() at string boundaries. Fix test assertions to
compare typed values with naming.InstanceName() wrappers.
```

### Patch 7 — `overlord/ifacestate` type aliases - COMPLETED

Type the `triggeringSnap` and `affectedSnap` type aliases to use `naming.InstanceName` instead of `string`.

**Status: COMPLETED**

**Files modified:**
- `overlord/ifacestate/handlers.go` - Changed type aliases from `string` to `= naming.InstanceName`
  - Updated `.String()` call when converting for logging

**Commit message:**
```
overlord/ifacestate: type triggeringSnap and affectedSnap with naming.InstanceName

Type the triggeringSnap and affectedSnap type aliases to use naming.InstanceName
instead of string for compile-time type safety. These represent instance names of
snaps that trigger or are affected by delayed interface side effects.
```

### Patches 8-10 — Remaining managers - NO ACTION NEEDED

Survey of remaining managers (snapshotstate, servicestate, devicestate) found no local
accessor methods that return instance/snap names. These managers only have persisted
struct fields (with JSON tags) which correctly stay as `string` per the plan.

**Finding:** After Patch 6 typed `hookstate.Context.InstanceName()` and Patch 5 typed
`snapstate.SnapSetup/SnapState` accessors, no other overlord managers have local
instance name accessor methods that need typing.

### ✅ Patch N — Central `PlaceInfo` interface return types

Change `PlaceInfo.SnapName()/InstanceName()` interface methods to typed returns. Also type `naming.SnapRef.SnapName()`. This is the one truly cross-cutting change affecting the core `snap.Info` type and all code using snap/instance names.

**Status: COMPLETED**

**Changes:**
- ✅ Typed PlaceInfo.InstanceName() → naming.InstanceName
- ✅ Typed PlaceInfo.SnapName() → naming.SnapName  
- ✅ Typed naming.SnapRef.SnapName() → naming.SnapName
- ✅ Updated all implementers: snap.Info, ModelSnap, ValidationSetSnap, OptionsSnap, SeedSnap, seed.Snap, internal.Snap20
- ✅ Fixed all call sites (~230+ files) with .String() additions where typed names are used as strings
- ✅ Added installSnapInfo.InstanceName() wrapper method for MinimalInstallInfo interface
- ✅ Fixed all test assertions (typed vs string comparisons)
- ✅ Fixed assertion headers to use .String() for string values
- ✅ Special handling for types implementing MinimalInstallInfo (already return string)

**Key patterns:**
- Add `.String()` when typed name used as: function parameter, map key, struct field, array element, string concatenation
- Keep typed when comparing with typed constructor: `info.InstanceName(), Equals, naming.InstanceName(x)`
- Convert to string when comparing with literal: `info.InstanceName().String(), Equals, "foo"`
- Types that wrap or implement MinimalInstallInfo correctly return `string` from their `InstanceName()` method

**Files modified:** 173 files (1117 insertions, 1071 deletions)

**Test results:**
- ✅ All packages compile
- ✅ All unit tests pass (`./run-checks --unit`)
- ✅ All static checks pass (`./run-checks --static`)

**Commit message:**
```
snap,naming: type PlaceInfo and SnapRef interface methods

Type PlaceInfo.InstanceName() to return naming.InstanceName and
PlaceInfo.SnapName() to return naming.SnapName. Also type
naming.SnapRef.SnapName() consistently. This provides compile-time
protection against passing snap names where instance names are
expected throughout the codebase.

This is the largest cross-cutting change in the typed names
refactoring, affecting the core snap.Info type and ~230+ call sites
across the entire codebase. All implementers of PlaceInfo are updated,
and .String() is added at boundaries where typed names are used as
strings (function parameters, map keys, assertion headers, etc.).

Special handling for types that implement MinimalInstallInfo interface:
refreshCandidate.InstanceName() returns string (wraps SnapSetup), so
test assertions comparing with these values should not add .String().
```

### Patch N+1 — Boundary constructor conversions
Convert existing validate-then-use sites (~20 locations) so validation yields the typed value.

**→ `ParseInstanceName` (instance-name validators):**
- `daemon/api_sideload_n_try.go:528`
- `daemon/api_notices.go:356` (verified instance name)
- `asserts/cluster.go:183`
- `overlord/configstate/configcore/vitality.go:192`
- `interfaces/repo.go:425`
- `overlord/snapstate/snapstate.go:796, 3579`
- `overlord/snapstate/target.go:762, 1621`

**→ `ParseSnapName` (true snap-name validators):**
- ⏭️ `daemon/api_find.go`: NOT FOUND - line numbers outdated
- ✅ `seed/seedwriter/writer.go:476`: snap name validation
- ⏭️ `seed/internal/options20.go:97`, `seed/internal/seed_yaml.go:83`: Already converted in bulk
- ✅ `asserts/model.go:225,356,450`: snap name validations (3 sites)
- ✅ `asserts/preseed.go:119,205`: snap name validations (2 sites)
- ✅ `asserts/snap_resource_asserts.go:153`: resource name validation
- ✅ `asserts/validation_set.go:105`: snap name validation
- ✅ `asserts/repair.go:167`: bases validation
- ✅ `overlord/servicestate/quota_handlers.go:861`: snap name validation

**Not converted (as intended):**
- Component name validators (validate component names, not snap names)
- Test files
- `snap/validate.go:45,50` wrappers (public API wrappers)

**Files modified:** 10 files (27 insertions, 25 deletions)

**Test results:**
- ✅ All affected packages compile
- ✅ All tests pass

**Commit message:**
```
snap/naming: convert validate-then-use sites to ParseInstanceName/ParseSnapName

Convert existing validate-then-use patterns to use the typed constructor
functions ParseInstanceName and ParseSnapName. This ensures validation
yields the typed value directly, providing compile-time type safety at
input boundaries.
```

### ✅ Patch N+2 — Eliminate redundant type conversions

**Status: COMPLETED (including tests and snap.InstanceName() typing!)**

Clean up all occurrences of `naming.InstanceName(x.InstanceName())` and 
`naming.InstanceName(x.InstanceName().String())` that were introduced during 
the gradual refactoring. These conversions are now unnecessary since 
`PlaceInfo.InstanceName()` returns typed `naming.InstanceName` directly.

**Phase 1: Non-test files** (Commit b75a943b45)
- 22 files changed, 65 insertions, 71 deletions

**Phase 2: .String() round-trips** (Commit 2f5f4105ef)
- 4 files: seed/seed20.go, store/tooling/tooling.go, overlord/install/install.go, wrappers/desktop.go
- Removed: `naming.InstanceName(x.SnapName().String())` → `naming.InstanceName(x.SnapName())`

**Phase 3: Test files** (Commit 26771be432)
- 6 test files changed, 24 insertions, 25 deletions
- Fixed overlord/ifacestate (16 occurrences), snap/snapenv (2), cmd/snapd/cli (2), overlord/snapstate (4)

**Phase 4: Type snap.InstanceName() function** (Commit d7cfa55cfa)
- Changed `snap.InstanceName(snapName, instanceKey string) string` → returns `naming.InstanceName`
- Eliminated 2 more redundant wrappings: `naming.InstanceName(snap.InstanceName(...))`
- Updated 5 call sites + 6 test files
- 8 files changed, 24 insertions, 24 deletions

**Categories fixed:**
1. **snap.Info wrapper methods** (8 fixes): MountDir, MountFile, HooksDir, DataDir, etc.
2. **Type round-tripping** (~15 fixes in overlord/snapstate and related packages)
3. **Old string helpers on typed values** (3 fixes): Replaced `snap.SplitInstanceName(x.InstanceName().String())` with `x.InstanceName().InstanceKey()`
4. **Test helpers** (3 fixes in snap/snaptest)
5. **Additional AppInfo/HookInfo methods** (6 fixes in snap/info.go)
6. **Across the codebase** (~10 more fixes in daemon, overlord/devicestate, cmd/*, interfaces)
7. **Test files** (25 fixes across 6 test files)
8. **snap.InstanceName() helper** (2 redundant wrappers eliminated, function now typed)

**Final verification:**
- ✅ Zero `naming.InstanceName(x.InstanceName())` patterns remain
- ✅ Zero `naming.InstanceName(x.InstanceName().String())` patterns remain
- ✅ Zero `naming.InstanceName(x.SnapName().String())` patterns remain
- ✅ Zero `naming.SnapName(x.SnapName())` patterns remain
- ✅ All packages compile
- ✅ All tests pass

**Total cleanup:** 40 files changed across 4 commits

**Categories fixed:**
1. **snap.Info wrapper methods** (8 fixes): MountDir, MountFile, HooksDir, DataDir, etc.
2. **Type round-tripping** (~15 fixes in overlord/snapstate and related packages)
3. **Old string helpers on typed values** (3 fixes): Replaced `snap.SplitInstanceName(x.InstanceName().String())` with `x.InstanceName().InstanceKey()`
4. **Test helpers** (3 fixes in snap/snaptest)
5. **Additional AppInfo/HookInfo methods** (6 fixes in snap/info.go)
6. **Across the codebase** (~10 more fixes in daemon, overlord/devicestate, cmd/*, interfaces)

**Total cleanup:** 22 files changed, 65 insertions, 71 deletions

**Result:** All non-test code now has zero redundant type wrapping patterns.

**Test results:**
- ✅ All affected packages compile
- ✅ All tests pass

**Commit:** b75a943b45

### Patch N+3 (optional) — Deprecate old string helpers
Once the typed refactoring is fully adopted, consider adding deprecation
notices to `snap.InstanceName()`, `snap.InstanceSnap()`, and
`snap.SplitInstanceName()` to guide future code toward using the typed API.

Note: These functions still have ~60 legitimate uses in string-based code,
so removal is not appropriate. Deprecation notices would be optional.

---

## Current Status

**Completed:** Patches 1-7, Patch N, Patch N+1, Patch N+2 (all core typing work complete!)
**Optional future work:** Patch N+3 (add deprecation notices to old string helpers)

**Progress tracking:**
- [x] Patch 1: Types + helpers + tests
- [x] Patch 2: Leaf filesystem path helpers
- [x] Patch 3: Snap/app + security-tag helpers
- [x] Patch 4: Interface connection helpers
- [x] Patch 5: snapstate.SnapSetup/SnapState accessors
- [x] Patch 6: hookstate.Context.InstanceName()
- [x] Patch 7: ifacestate type aliases
- [x] Patches 8-10: Surveyed, no action needed
- [x] Patch N: PlaceInfo and SnapRef interface methods
- [x] Patch N+1: Boundary constructor conversions
- [x] Patch N+2: Eliminate redundant type conversions
- [ ] Patch N+3: Add deprecation notices (optional)

---

## Coverage Analysis: Key Subsystems

This section documents the typing status of major snapd subsystems to ensure comprehensive coverage.

### ✅ Fully Typed Subsystems (No Further Work Needed)

#### 1. SnapInfo Helpers (`snap/info.go`)
**Status:** Complete

The `snap.Info` struct is the central type representing a snap. All naming-related methods are properly typed:
- `InstanceName() naming.InstanceName` - Returns instance name with optional key
- `SnapName() naming.SnapName` - Returns the global snap name without instance key
- `ExpandSnapVariables(path string) string` - Uses typed names internally for variable expansion

**Evidence:** ~44 uses of naming types in info.go. All PlaceInfo implementers return typed names.

#### 2. snapctl (`cmd/snapctl`)
**Status:** Complete (no direct work needed)

snapctl is a thin wrapper that routes commands to snapd via socket. It doesn't directly manipulate snap names:
- Gets context from environment variables (`SNAP_COOKIE`, `SNAP_CONTEXT`)
- Passes context ID to snapd for resolution
- Actual name handling is in `hookstate.Context` which already returns typed `naming.InstanceName`

#### 3. SnapExpandVariables (`snap/info.go:808-855`)
**Status:** Complete

Two related functions expand snap-specific environment variables:
- `ExpandSnapVariables(path string)` - Simple version using defaults
- `ExpandSnapVariablesSetSnapMountDir(path, snapMountDir, expandFor)` - Advanced version

**Behavior:**
- Expands `$SNAP`, `$SNAP_DATA`, `$SNAP_COMMON` in paths
- Has two perspectives: `PerspectiveSelf` (snap name) vs `PerspectiveOther` (instance name)
- Used in layout validation, interface specs (apparmor, mount), and interface implementations
- Internally uses typed `naming.InstanceName` correctly

#### 4. snapenv Package (`snap/snapenv`)
**Status:** Complete

Generates environment variables for snap execution (SNAP_NAME, SNAP_INSTANCE_NAME, SNAP_DATA, etc.):
- `ExtendEnvForRun()` - Main entry point for setting environment
- `basicEnv()` - Sets core snap environment variables
- Uses `info.SnapName()` and `info.InstanceName()` throughout
- Correctly distinguishes between SNAP_NAME (snap name) and SNAP_INSTANCE_NAME (instance name)

#### 5. Layouts (`snap/info.go:470-510`, `snap/validate.go`)
**Status:** Complete (indirect typing)

Layouts allow snaps to make files/directories appear in specific locations:
- `Layout` struct has `Snap *Info` reference
- Validation uses `info.ExpandSnapVariables(layout.Path)`
- Mount/apparmor specs use typed instance names via parent `snap.Info`
- No direct name handling - all access goes through typed `Info.InstanceName()` / `Info.SnapName()`

### ⚠️ Partially Typed Subsystems (Additional Work Available)

#### 6. Hooks (`overlord/hookstate`)
**What it does:** Manages hook execution, coordinates hook lifecycle, maintains hook context.

**Current status:**
- ✅ `Context.InstanceName()` returns typed `naming.InstanceName` (completed in Patch 6)
- ❌ `HookSetup.Snap` field is still `string` (should be `naming.InstanceName`)
- ❌ Hook setup functions accept `string` for snap names

**Key structures:**
```go
type HookSetup struct {
    Snap        string  // ← Should be naming.InstanceName
    Revision    snap.Revision
    Hook        string
    Optional    bool
    // ... other fields
}
```

**Functions needing updates:**
- `SetupInstallHook(st, snapName string, rev, lane) *HookSetup`
- `SetupPreRefreshHook(st, snapName string) *HookSetup`
- `SetupPostRefreshHook(st, snapName string) *HookSetup`
- `SetupRemoveHook(st, snapName string) *HookSetup`
- Similar functions for configure, check-health, gate-auto-refresh hooks

**Scope:** ~10-15 function signatures in `overlord/hookstate/hooks.go`

**Value:** Medium - Eliminates string handling in hook task creation, provides type safety for all hook operations.

#### 7. Service Control (`overlord/servicestate`, `wrappers`)
**What it does:** Manages systemd service lifecycle (start/stop/restart) for snap applications.

**Current status:**
- ✅ Service names use typed instance names via `AppInfo.SecurityTag()`
- ✅ Systemd unit names correctly derived from typed security tags
- ❌ `ServiceAction.SnapName` field is still `string` (should be `naming.InstanceName`)

**Key structures:**
```go
type ServiceAction struct {
    SnapName string  // ← Should be naming.InstanceName
    Action   string  // "start", "stop", "restart", etc.
}

type Instruction struct {
    Action   string
    Names    []string
    StartOptions *StartOptions
    StopOptions  *StopOptions
    RestartOptions *RestartOptions
}
```

**Functions needing updates:**
- Service control handlers in `overlord/servicestate/service_control.go`
- Instruction parsing that extracts snap names

**Scope:** ~5-10 affected functions

**Value:** Medium - Service operations are frequent; typing prevents name/instance confusion.

#### 8. Udev Rules (`interfaces/udev`)
**What it does:** Manages udev rules and device cgroup policies for snap device access.

**Current status:**
- ⚠️ Functions take `string` for snap names, manually wrap in `naming.InstanceName()`
- Backend.Setup() receives typed `appSet.InstanceName()` but casts back to string

**Key patterns:**
```go
// Current pattern (backend.go:93)
tag := snap.SecurityTag(naming.InstanceName(snapName))
// Could be simplified if snapName parameter was typed
```

**Functions needing updates:**
- `snapRulesFilePath(snapName string) string` - internal helper
- Other internal helpers that construct udev rule paths

**Scope:** ~3-5 internal function signatures

**Value:** Low - Mostly internal, but improves consistency and removes manual wrapping.

#### 9. Cgroups and RAA Tracking (`sandbox/cgroup`)
**What it does:**
- **Cgroups:** Track snap processes via systemd cgroup hierarchy
- **RAA (Refresh App Awareness):** Experimental feature to track running apps during snap refresh

**Current status:**
- ⚠️ Uses `naming.SecurityTag` internally (which embeds typed names)
- ❌ Public API returns/accepts `string` for snap names
- ✅ SecurityTag parsing uses `naming.ParseSecurityTag()` correctly

**Key functions:**
```go
// Returns string, could return naming.InstanceName
func SnapNameFromPid(pid int) (string, error)

// Takes string, could take naming.InstanceName
func PidsOfSnap(snapInstanceName string) (map[string][]int, error)

// Properly typed - returns naming.SecurityTag
func SecurityTagFromCgroupPath(path string) naming.SecurityTag
```

**Functions needing updates:**
- `SnapNameFromPid(pid int)` → return `naming.InstanceName`
- `PidsOfSnap(snapInstanceName string)` → accept `naming.InstanceName`
- Related helper functions in scanning/tracking

**Scope:** ~10-15 functions in `sandbox/cgroup/`

**Value:** Medium - RAA is important for smooth refreshes; typing helps prevent bugs in process tracking.

### Summary Table

| Subsystem | Location | Status | Work Needed | Scope | Priority |
|-----------|----------|--------|-------------|-------|----------|
| SnapInfo helpers | `snap/info.go` | ✅ Complete | None | N/A | N/A |
| snapctl | `cmd/snapctl` | ✅ Complete | None | N/A | N/A |
| SnapExpandVariables | `snap/info.go` | ✅ Complete | None | N/A | N/A |
| snapenv | `snap/snapenv` | ✅ Complete | None | N/A | N/A |
| Layouts | `snap/` | ✅ Complete | None | N/A | N/A |
| **Hooks** | `overlord/hookstate` | ⚠️ Partial | Type HookSetup.Snap field | ~10-15 funcs | Medium |
| **Service control** | `overlord/servicestate` | ⚠️ Partial | Type ServiceAction.SnapName | ~5-10 funcs | Medium |
| **Udev rules** | `interfaces/udev` | ⚠️ Partial | Type internal helpers | ~3-5 funcs | Low |
| **Cgroups/RAA** | `sandbox/cgroup` | ⚠️ Partial | Type public API | ~10-15 funcs | Medium |

**Total remaining work:** ~28-45 function signatures across 4 subsystems (all optional improvements)

---

## Constraints & principles

- **Primary goal:** Compile-time protection against swapping snap names and instance names
- **Secondary goal:** Runtime validation at boundaries via `Parse*` constructors
- Each patch must compile, pass `./run-checks`, and stay ≤500 lines where practical
- Refactor patches avoid test edits beyond compile fixes (per repo PR guidelines)
- Keep diffs self-contained and independently reviewable
- Persisted fields stay `string` (minimize review noise)
- Free casting documents intent but doesn't enforce validity (accepted)
- Commit titles follow repo style: `affected/packages: short summary in lowercase`

---

## Open questions / decisions log

### Q1: `naming.InstanceName(info.InstanceName())` double-wrap clunkiness
**Decision:** Handle island-by-island by typing each package's local accessors within its own patch (Patches 5-10), rather than deferring all accessors to a single Patch N. This minimizes the number of double-wraps that ever exist and makes each patch more self-contained. Only the truly cross-cutting `PlaceInfo` interface remains in Patch N.

### Q2: Validation at boundaries vs. unchecked casts
**Decision:** Use both. Free unchecked casts (`naming.InstanceName(s)`) for trusted interior data already validated at installation/read time. Use validating constructors (`ParseInstanceName`) only at genuine input boundaries (~20 sites). This is pragmatic and matches existing code patterns.

### Q3: Should `SnapName` coexist with `SnapRef.SnapName()` method?
**Decision:** Yes, accepted. While slightly noisy, it's legal Go and the types serve a different purpose (compile-time swap protection) than the interface method (accessor pattern).

---

## Representative outcome

```go
// Before (compiles, but is a latent bug):
p1 := snap.DataDir(info.InstanceName(), rev) // correct
p2 := snap.DataDir(info.SnapName(), rev)     // WRONG, silently compiles

// After (the bug becomes a compile error):
p1 := snap.DataDir(info.InstanceName(), rev) // correct
p2 := snap.DataDir(info.SnapName(), rev)     // ❌ compile error: cannot use SnapName as InstanceName
```

---

## References

- Original motivation: Prevent snap-name vs. instance-name confusion in filesystem paths and security tags
- Related discussions: Parallel installs (instance keys), security isolation, path construction bugs
- Existing validators: `naming.ValidateSnap` (validate.go:83), `naming.ValidateInstance` (validate.go:62)
