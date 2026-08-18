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
Each patch must compile, pass `./run-checks`, stay ≤500 lines, and avoid test changes except compile fixes.

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


### Patch 5 — `overlord/snapstate` internals
Type returns of `SnapSetup.SnapName()/InstanceName()` and `SnapState.InstanceName()` (unchecked casts; persisted `SideInfo.RealName` / `InstanceKey` stay strings). Then local install/check/conflict/prereq/alias helpers.

**Important:** Type the accessors within this patch to eliminate `naming.InstanceName(snapsup.InstanceName())` double-wraps immediately, rather than deferring to Patch N.

**Files to modify:**
- `overlord/snapstate/snapmgr.go` - `SnapSetup` accessors
- `overlord/snapstate/snapstate.go` - `SnapState.InstanceName()`, local helpers
- `overlord/snapstate/handlers*.go` - task handlers
- `overlord/snapstate/backend/*.go` - backend operations

### Patches 6–10 — Remaining managers, one island per patch
Order: `hookstate`, `ifacestate`, `snapshotstate`, `devicestate`, `servicestate`. Each compiles its own package; no unrelated managers touched.

**For each manager patch:**
- Type any local accessors that return instance names
- Convert local helper functions
- Update call sites within the package

This approach avoids accumulating double-wraps by typing accessors island-by-island rather than deferring all to Patch N.

### Patch N — Central `PlaceInfo` interface return types (single big-ripple patch)
Change `PlaceInfo.SnapName()/InstanceName()` interface methods to typed returns. This is the one truly cross-cutting change.

**Files to modify:**
- `snap/info.go` - `PlaceInfo` interface definition
- All implementers: `Info`, `componentPlaceInfo`, etc.
- All callers that assigned into `string` variables

Sequenced last because Go's lack of return covariance forces all implementers + callers in one commit. By this point, most consumers are already typed from earlier patches, so the churn is minimized.

Optional: Also handle `naming.SnapRef.SnapName()` if integrating the new types into that interface.

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
- `daemon/api_find.go:158`
- `seed/internal/options20.go:97`, `seed/internal/seed_yaml.go:83`
- `seed/seedwriter/writer.go:476`, `seedwriter/manifest.go:301`
- `asserts/model.go:225,356,450`, `preseed.go:119,205`, `snap_resource_asserts.go:153`, `validation_set.go:105`, `repair.go:167`
- `overlord/servicestate/quota_handlers.go:861`

**Explicitly NOT converted** (these validate component/other names, not snap names):
- `snap/naming/componentref.go:57`
- `seed/internal/options20.go:118` (comp.Name)
- `seedwriter/writer.go:439` (optComp.Name)
- `asserts/validation_set.go:180` (compName)
- `overlord/hookstate/ctlcmd/helpers.go:524` (comp)
- `snap/validate.go:45,50` wrappers
- All `*_test.go`

### Patch N+2 (optional) — Deprecate/remove old string helpers
Once callers are typed, remove or deprecate `snap.InstanceName`, `snap.InstanceSnap`, `snap.SplitInstanceName`.

---

## Current Status

**Completed:** Patches 1-4 (types, filesystem helpers, security tags, interfaces typed returns)
**Next:** Patch 5 (`overlord/snapstate` accessors)

**Progress tracking:**
- [x] Patch 1: Types + helpers + tests
- [x] Patch 2: Leaf filesystem path helpers
- [x] Patch 3: Snap/app + security-tag helpers
- [x] Patch 4: `interfaces.SnapAppSet.InstanceName()` typed return
- [ ] Patch 5: `overlord/snapstate` accessors (`SnapSetup`, `SnapState`)
- [ ] Patches 6-10: Remaining managers
- [ ] Patch N: Central `PlaceInfo` interface
- [ ] Patch N+1: Boundary constructor conversions
- [ ] Patch N+2: Deprecate old string helpers

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
