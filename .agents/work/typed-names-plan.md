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

### Patch 1 — Add types + helpers + tests (`snap/naming` only, inert)

Add to `snap/naming`:
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

### Patch 2 — Leaf filesystem path helpers (island in `snap`)

Convert instance-name params to `naming.InstanceName` in:
- Path helpers: `BaseDir`, `MountDir`, `MountFile`, `MountFileInDir`, `DataDir`, `BaseDataDir`, `CommonDataDir`, `CommonDataSaveDir`, `HooksDir`, `UserDataDir`, `UserCommonDataDir`, `UserSnapDir`, `UserXdgRuntimeDir`, `BaseDataHomeDirs`
- Container place info constructors: `MinimalPlaceInfo`, `MinimalSnapContainerPlaceInfo`
- Component helpers: `ComponentMountDir`, `ComponentHooksDir`, `ComponentsBaseDir`, `MinimalComponentContainerPlaceInfo`

Callers cast at call site with unchecked `naming.InstanceName(...)` since values originate from already-validated `snap.Info` or state.

**Why first:** 
- Isolated island (snap package)
- High bug value (wrong paths from name confusion)
- Many call sites = good test of approach

**Expected challenge:** ~40 files need casting at call sites

### Patch 3 — Snap/app + security-tag helpers (island in `snap`)

Target functions:
- Security: `AppSecurityTag`, `HookSecurityTag`, `SecurityTag`, etc.
- App naming: `JoinSnapApp`, `SplitSnapApp`

**Why second:**
- Another isolated island
- Security tags are per-instance (validates design)
- `SplitSnapApp` return type changes (ripple test)

**Expected challenge:** String boundary conversions (JSON, APIs)

**Key patterns:**
- Cast to typed with `naming.InstanceName(...)` when calling
- Convert back with `.String()` at persistence/API boundaries

### Patch 4 — `interfaces` internals
Type `SnapAppSet.InstanceName()` return value and internal repo/connection helpers. Leave persisted `PlugRef.Snap` / `SlotRef.Snap` as `string` (JSON); convert at those boundaries with `.String()`.

**Files to modify:**
- `interfaces/snap_app_set.go` - type `InstanceName()` return
- `interfaces/repo.go` - internal connection helpers
- `interfaces/core.go` - boundaries with `PlugRef`/`SlotRef`

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

**Next:** Patch 1 Types + helpers + tests

**Progress tracking:**
- [ ] Patch 1: Types + helpers + tests
- [ ] Patch 2: Leaf filesystem path helpers
- [ ] Patch 3: Snap/app + security-tag helpers
- [ ] Patch 4: `interfaces` internals
- [ ] Patch 5: `overlord/snapstate` internals
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
