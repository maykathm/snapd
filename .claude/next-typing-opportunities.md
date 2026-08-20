# Next Typing Opportunities

## Already Completed ✅

### Functions & Methods
- `snap.InstanceName()` → returns `naming.InstanceName`
- `snap.ReadInfo(name)` → takes `naming.InstanceName`
- `snap.ReadCurrentInfo(name)` → takes `naming.InstanceName`
- `PlaceInfo.InstanceName()` → returns `naming.InstanceName`
- `PlaceInfo.SnapName()` → returns `naming.SnapName`

### Struct Methods
- `SnapSetup.InstanceName()` → returns `naming.InstanceName`
- `SnapState.InstanceName()` → returns `naming.InstanceName`
- `hookstate.Context.InstanceName()` → returns `naming.InstanceName`

## Tier 1: Public API Entry Points (HIGHEST VALUE) 🎯

**Location:** `overlord/snapstate/target.go`

These structs are the main entry points for snap installation and updates. Every snap operation flows through these APIs. Typing them provides maximum safety.

### 1. PathSnap.InstanceName ⭐ TOP PRIORITY
```go
type PathSnap struct {
    Path         string
    InstanceName string  // ← Change to naming.InstanceName
    SideInfo     *snap.SideInfo
}
```
- **Usage:** 61 struct literals across codebase
- **Entry point for:** Local snap installs (`snap install ./foo.snap`)
- **Impact:** HIGH - validates at API boundary, prevents invalid names
- **Benefit:** Eliminates internal validation, forces caller to parse/validate

### 2. StoreSnap.InstanceName ⭐ TOP PRIORITY
```go
type StoreSnap struct {
    InstanceName string  // ← Change to naming.InstanceName
    Components   []string
    RevOpts      RevisionOptions
}
```
- **Usage:** 32 struct literals across codebase
- **Entry point for:** Store snap installs (`snap install firefox`)
- **Impact:** HIGH - validates at API boundary
- **Benefit:** Compile-time guarantee of valid instance names

### 3. StoreUpdate.InstanceName
```go
type StoreUpdate struct {
    InstanceName         string  // ← Change to naming.InstanceName
    RevOpts              RevisionOptions
    AdditionalComponents []string
}
```
- **Usage:** 65 struct literals across codebase
- **Entry point for:** Store snap updates/refreshes
- **Impact:** HIGH - validates updates at boundary
- **Benefit:** Type safety for all refresh operations

### 4. PathUpdate.InstanceName
```go
type PathUpdate struct {
    Path         string
    InstanceName string  // ← Change to naming.InstanceName
    RevOpts      RevisionOptions
}
```
- **Usage:** 0 struct literals (may be new or unused)
- **Entry point for:** Local snap updates
- **Impact:** MEDIUM - less used but should match PathSnap
- **Benefit:** Consistency with PathSnap

**Estimated effort:** 2-3 hours
- Update 4 struct field definitions
- Update ~158 struct literal sites (mostly mechanical)
- Update any helper functions that construct these
- Run tests on affected packages

**Expected outcome:**
- Cleaner validation at API boundaries
- Eliminates runtime validation inside functions
- Catches invalid names at compile time
- Makes refactoring's benefits visible to API consumers

---

## Tier 2: Network Boundary Structs (GOOD VALUE) 📦

**Location:** `store/store_action.go`

These structs communicate with the snap store. Typing provides validation before network calls.

### 5. CurrentSnap.InstanceName
```go
type CurrentSnap struct {
    InstanceName     string  // ← Change to naming.InstanceName
    SnapID           string
    Revision         snap.Revision
    TrackingChannel  string
    IgnoreValidation bool
    Block            []snap.Revision
    Epoch            snap.Epoch
    CohortKey        string
}
```
- **Purpose:** Tell store what's currently installed
- **Impact:** MEDIUM - validates before network boundary
- **Usage:** Created when querying store for updates

### 6. SnapAction.InstanceName
```go
type SnapAction struct {
    Action       string
    InstanceName string  // ← Change to naming.InstanceName
    SnapID       string
    Channel      string
    Revision     snap.Revision
    CohortKey    string
    Flags        SnapActionFlags
    Epoch        snap.Epoch
}
```
- **Purpose:** Store API requests (install/refresh/download)
- **Impact:** MEDIUM - validates store operations
- **Usage:** Created for each store action

**Estimated effort:** 1-2 hours
**Benefit:** Type safety at network boundary

---

## Tier 3: Seed Operations (MODERATE VALUE) 🌱

**Location:** `overlord/snapstate/seed.go`

### 7. SeedRefreshCandidate.InstanceName
```go
type SeedRefreshCandidate struct {
    InstanceName     string  // ← Change to naming.InstanceName
    SnapSetupTaskIDs []string
}
```
- **Purpose:** Track snaps during seed refresh operations
- **Impact:** MEDIUM - seed operations are important but less frequent
- **Usage:** Internal to seed refresh logic

**Estimated effort:** 30 minutes
**Benefit:** Consistency with other typed structs

---

## Tier 4: Display/Response Structs (LOW VALUE) 💬

These are mostly for JSON serialization, display, or logging. Lower priority because:
- Less likely to have logic bugs (mostly passing data through)
- Often need JSON tags anyway (would still be `string` in JSON)
- Don't provide compile-time safety at critical boundaries

**Examples:**
- `daemon/response.go: RespJSON.SnapName`
- `daemon/api_download.go: fileResponse.SnapName`
- `usersession/client/client.go: PendingSnapRefreshInfo.InstanceName`
- `overlord/servicestate/service_control.go: Instruction.SnapName`
- `overlord/restart/restart_parameters.go: RestartBootloaderAndSystem.SnapName`

**Estimated effort:** 2-3 hours for all
**Benefit:** Consistency, not much practical safety gain

---

## Tier 5: Internal Helper Functions (LOWEST VALUE) 🔧

Many internal functions still take `string` parameters:
```go
func checkSnap(st *state.State, snapFilePath, instanceName string, ...) error
func CheckChangeConflict(st *state.State, instanceName string, ...) error
func validatedInfoFromPathAndSideInfo(instanceName string, ...) (*snap.Info, error)
```

**Why low priority:**
- These are internal (not exported APIs)
- They're typically called from typed contexts already
- Less benefit since validation already happens at boundaries
- Would cascade to many internal functions

**Consider only if:** You want exhaustive typing or find specific bugs

---

## Recommendation

### Do Now (High ROI):
**Tier 1: Public API Entry Points** (overlord/snapstate/target.go)
- StoreSnap.InstanceName
- PathSnap.InstanceName
- StoreUpdate.InstanceName
- PathUpdate.InstanceName

This gives you the most value with reasonable effort (~158 call sites, mostly mechanical updates).

### Do Next (If continuing):
**Tier 2: Network Boundary** (store/store_action.go)
- CurrentSnap.InstanceName
- SnapAction.InstanceName

### Consider Later (Diminishing returns):
- Tier 3: Seed operations
- Tier 4: Display/response structs
- Tier 5: Internal helpers (probably not worth it)

---

## Implementation Strategy

For Tier 1 (target.go structs):

1. **Change struct definitions** (4 fields)
2. **Update constructors** that build these structs
3. **Update struct literals** (~158 sites) - use regex/perl:
   - `InstanceName: name` → add validation/conversion
   - Sites that already have typed names: remove `.String()`
   - Sites with string literals: add `naming.InstanceName("...")`
4. **Run tests** on affected packages:
   - `go test ./overlord/snapstate/...`
   - `go test ./daemon/...`
5. **Commit** with clear message about API boundary typing

Expected pattern at call sites:
```go
// Before
goal := snapstate.StoreInstallGoal(snapstate.StoreSnap{
    InstanceName: name,  // name is string, runtime validation later
})

// After (when name is string)
instName, err := naming.ParseInstanceName(name)
if err != nil {
    return err
}
goal := snapstate.StoreInstallGoal(snapstate.StoreSnap{
    InstanceName: instName,  // compile-time guarantee
})

// After (when name is already typed)
goal := snapstate.StoreInstallGoal(snapstate.StoreSnap{
    InstanceName: snapst.InstanceName(),  // no .String() needed!
})
```

This pushes validation to the API boundary where it belongs.
