# Function Parameter/Return Type Analysis

Comprehensive analysis of functions that should be converted from `string` to typed names.

---

## Summary Tiers

### 🔥 TIER S: Critical Public APIs (Must Type)

The absolute highest value - these are the main entry points that ALL snap operations flow through.

**overlord/snapstate - Core Operations (14 functions)**

#### State Access
1. **Get(st, name string, snapst) error** → `naming.InstanceName`
2. **Set(st, name string, snapst)** → `naming.InstanceName`

#### Info Queries
3. **Info(st, name string, revision) (*snap.Info, error)** → `naming.InstanceName`
4. **CurrentInfo(st, name string) (*snap.Info, error)** → `naming.InstanceName`

#### Lifecycle Operations
5. **Install(ctx, st, name string, opts, userID, flags) (*state.TaskSet, error)** → `naming.InstanceName`
6. **InstallWithDeviceContext(ctx, st, name string, ...) (*state.TaskSet, error)** → `naming.InstanceName`
7. **Update(st, name string, opts, userID, flags) (*state.TaskSet, error)** → `naming.InstanceName`
8. **UpdateWithDeviceContext(st, name string, ...) (*state.TaskSet, error)** → `naming.InstanceName`
9. **Remove(st, name string, revision, flags) (*state.TaskSet, error)** → `naming.InstanceName`
10. **Enable(st, name string) (*state.TaskSet, error)** → `naming.InstanceName`
11. **Disable(st, name string) (*state.TaskSet, error)** → `naming.InstanceName`
12. **Revert(st, name string, flags, fromChange) (*state.TaskSet, error)** → `naming.InstanceName`
13. **RevertToRevision(st, name string, rev, flags, fromChange) (*state.TaskSet, error)** → `naming.InstanceName`
14. **Switch(st, name string, opts) (*state.TaskSet, error)** → `naming.InstanceName`

**Why TIER S:**
- These are THE main APIs that everything else calls
- Every snap operation (install/update/remove/query) goes through these
- Typing them provides maximum compile-time safety
- Forces validation at the right boundary
- Eliminates entire classes of bugs (passing snap name where instance name needed)

**Estimated Call Sites:** ~100-200 (mostly from daemon/ and cmd/)

**Impact:** ⭐⭐⭐⭐⭐ Maximum - these are the most important functions to type

---

## 🎯 TIER A: High-Value Utilities (Should Type)

Functions that are frequently used and provide good safety gains.

### snap/ package

1. **snap.SequenceFile(name string) string** → `naming.InstanceName`
   - Purpose: Get path to sequence file for a snap instance
   - Usage: State persistence
   - Impact: HIGH
   
2. **snap.InstallDate(name string) time.Time** → `naming.InstanceName`
   - Purpose: Get when snap was installed
   - Usage: Queries, display
   - Impact: MEDIUM-HIGH

3. **snap.SplitSnapComponentInstanceName(name string) (string, string)** → 
   - Input: Keep `string` (needs parsing)
   - Returns: Change to `(naming.InstanceName, string)`
   - Purpose: Parse "snap_instance:component" notation
   - Impact: MEDIUM

4. **snap.SplitSnapInstanceAndComponents(name string) (string, []string)** →
   - Input: Keep `string` (needs parsing)
   - Returns: Change to `(naming.InstanceName, []string)`
   - Purpose: Parse snap name with component list
   - Impact: MEDIUM

### overlord/snapstate - Additional Operations

5. **UpdatePathWithDeviceContext(st, si, path, name string, ...) (*state.TaskSet, error)** → `naming.InstanceName`
   - Purpose: Update from local path
   - Impact: HIGH

6. **LinkNewBaseOrKernel(st, name string, fromChange, deviceCtx) (*state.TaskSet, error)** → `naming.InstanceName`
   - Purpose: Link new system snap
   - Impact: MEDIUM

7. **SwitchToNewGadget(st, name string, fromChange) (*state.TaskSet, error)** → `naming.InstanceName`
   - Purpose: Switch gadget snap
   - Impact: MEDIUM

**Impact:** ⭐⭐⭐⭐ High - frequently used, good safety gains

---

## 📦 TIER B: Internal Helpers (Nice to Have)

Internal functions that could be typed but have lower priority.

### overlord/snapstate - Internal

1. **checkSnap(st, snapFilePath, instanceName string, si, curInfo, flags, deviceCtx) error**
   - Already takes instanceName as string, should be `naming.InstanceName`
   - Internal function, called from already-validated contexts
   
2. **CheckChangeConflict(st, instanceName string, snapst) error**
   - Should be `naming.InstanceName`
   - Internal conflict checking

3. **validatedInfoFromPathAndSideInfo(instanceName string, path string, si) (*snap.Info, error)**
   - Should be `naming.InstanceName`
   - Internal helper

4. **writeSeqFile(name string, snapst) error**
   - Should be `naming.InstanceName`
   - Internal state persistence

### overlord/snapstate - Query Helpers

5. **findTasksMatchingKindAndSnap(st, kind string, snapName string, revision) ([]*state.Task, error)**
   - Parameter is called "snapName" but should probably be `naming.InstanceName`
   - Internal task lookup

6. **pruneHoldStatesForSnap(gating, snapName string) bool**
   - Should clarify: is this SnapName or InstanceName? Probably InstanceName.
   - Internal hold management

**Impact:** ⭐⭐ Medium - consistency gain, less practical safety benefit

---

## 🔌 TIER C: Boundary Functions (Keep as String)

These functions are at input boundaries (HTTP, CLI) and SHOULD stay as `string` - they're responsible for parsing and validating.

### daemon/ - HTTP API handlers

- `findOne(c, r, user, name string) Response` - receives from HTTP request
- `iconGet(st, name string) Response` - receives from URL
- `checkSnapInstalled(st, name string) error` - validates string input

**These should:**
1. Keep `string` parameters (from JSON/URL)
2. Parse/validate internally using `naming.ParseInstanceName()`
3. Call typed APIs (Tier S) with typed values

**Impact:** ⭐ Low - these SHOULD be string (input boundary)

---

## Special Cases

### Functions With "snapName" vs "instanceName" Ambiguity

Some functions have parameters named "snapName" but may actually need instance names for parallel installs. Need to audit each:

1. **overlord/snapstate.Prefer(st, name string) (*state.TaskSet, error)**
   - Purpose: Prefer snap aliases over another
   - Question: Does this work per-instance or per-snap?
   - Need to check: Can you have different alias preferences for firefox vs firefox_dev?
   - Probably: `naming.InstanceName` (most operations are per-instance)

2. **Various component-related functions**
   - Components are always associated with a specific snap instance
   - Should use `naming.InstanceName`

---

## Recommended Implementation Order

### Phase 1: Core State APIs (Tier S - Top Priority)
**Estimated effort:** 2-3 days
**Call sites:** ~150-200

Type these 14 critical functions in `overlord/snapstate`:
- Get, Set, Info, CurrentInfo
- Install, InstallWithDeviceContext
- Update, UpdateWithDeviceContext
- Remove, Enable, Disable
- Revert, RevertToRevision, Switch

**Why first:**
- Maximum impact - every operation uses these
- Forces validation at API boundaries
- Makes the refactoring's benefits visible throughout codebase
- Other changes build on this foundation

**Expected pattern at call sites:**
```go
// Before
ts, err := snapstate.Install(ctx, st, name, opts, userID, flags)

// After (at boundary - daemon, cmd)
instName, err := naming.ParseInstanceName(name)
if err != nil {
    return err
}
ts, err := snapstate.Install(ctx, st, instName, opts, userID, flags)

// After (internal - overlord)
ts, err := snapstate.Install(ctx, st, snapst.InstanceName(), opts, userID, flags)
// No more .String() conversions!
```

### Phase 2: Utility Functions (Tier A)
**Estimated effort:** 1-2 days
**Call sites:** ~50-100

Type snap package utilities:
- SequenceFile, InstallDate
- SplitSnapComponentInstanceName, SplitSnapInstanceAndComponents
- Additional snapstate operations

### Phase 3: Internal Helpers (Tier B) - Optional
**Estimated effort:** 1-2 days
**Call sites:** ~50-100

Type internal functions for consistency.
Only if pursuing exhaustive typing.

---

## Benefits Analysis

### Typing Tier S Functions (Core APIs)

**Safety Benefits:**
- ✅ Prevents passing snap name where instance name needed
- ✅ Prevents passing instance name where snap name needed
- ✅ Catches errors at compile time vs runtime
- ✅ Eliminates runtime validation in function bodies
- ✅ Self-documenting APIs (clear what type of name is needed)

**Code Quality Benefits:**
- ✅ Cleaner call sites (no more .String() on already-typed values)
- ✅ Forces validation at boundaries (good architecture)
- ✅ Makes parallel install support explicit in API
- ✅ Easier to audit for correctness

**Example Bug Prevented:**
```go
// This would compile today (BAD!)
snapName := snap.SnapName("firefox")
snapstate.Install(ctx, st, string(snapName), ...)  // Wrong! Need instance name

// With typing, this won't compile (GOOD!)
snapName := naming.SnapName("firefox")
snapstate.Install(ctx, st, snapName, ...)  // Compile error: expected InstanceName

// Force developer to be explicit:
instName := naming.NewInstanceName(snapName, "")  // Convert snap→instance
snapstate.Install(ctx, st, instName, ...)  // Type-safe!
```

---

## Migration Strategy for Call Sites

### Category 1: Already Have Typed Values (Easy)
```go
// Before
snapstate.Install(ctx, st, snapst.InstanceName().String(), opts, userID, flags)

// After
snapstate.Install(ctx, st, snapst.InstanceName(), opts, userID, flags)
```
**Benefit:** Removes redundant .String() calls - cleaner code!

### Category 2: Have String, Need to Validate (Boundary)
```go
// Before (no validation!)
ts, err := snapstate.Install(ctx, st, name, opts, userID, flags)

// After (forced validation)
instName, err := naming.ParseInstanceName(name)
if err != nil {
    return fmt.Errorf("invalid snap name %q: %v", name, err)
}
ts, err := snapstate.Install(ctx, st, instName, opts, userID, flags)
```
**Benefit:** Forces validation at boundary - prevents bugs!

### Category 3: Have Trusted String (Internal)
```go
// Before
ts, err := snapstate.Install(ctx, st, name, opts, userID, flags)

// After (trusted conversion)
ts, err := snapstate.Install(ctx, st, naming.InstanceName(name), opts, userID, flags)
```
**Benefit:** Documents trust, no runtime overhead

---

## Implementation Checklist

For each function to be typed:

1. **Change function signature**
   ```go
   // Before
   func Install(ctx context.Context, st *state.State, name string, ...) (*state.TaskSet, error)
   
   // After
   func Install(ctx context.Context, st *state.State, name naming.InstanceName, ...) (*state.TaskSet, error)
   ```

2. **Remove internal validation** (if any)
   ```go
   // DELETE: if err := naming.ValidateInstance(name); err != nil { ... }
   // Now enforced by type system!
   ```

3. **Update call sites** using patterns above
   - grep for all calls: `grep -rn "snapstate\.Install(" --include="*.go"`
   - Update each based on category (1/2/3 above)

4. **Update tests**
   - Test files can use `naming.InstanceName("test-snap")` directly
   - No need for ParseInstanceName in tests (trusted data)

5. **Verify compilation**
   ```bash
   go build ./...
   ```

6. **Run tests**
   ```bash
   go test ./overlord/snapstate ./daemon ./...
   ```

7. **Run checks**
   ```bash
   ./run-checks
   ```

8. **Commit with clear message**
   ```
   overlord/snapstate: type Install and Update parameters
   
   Change Install, Update, and related functions to take naming.InstanceName
   instead of string parameters. This provides compile-time type safety for
   all snap lifecycle operations.
   
   Functions updated:
   - Install, InstallWithDeviceContext
   - Update, UpdateWithDeviceContext
   - Remove, Enable, Disable
   - Revert, RevertToRevision
   
   Call sites updated across daemon, cmd, overlord packages to:
   - Remove redundant .String() where values already typed
   - Add naming.ParseInstanceName() at input boundaries
   - Use naming.InstanceName() for trusted internal strings
   
   This eliminates entire class of bugs where snap names could be
   passed where instance names were needed.
   ```

---

## Conclusion

**Immediate Priority: Tier S (Core APIs)**

Type the 14 core snapstate functions. This gives you:
- Maximum safety (all operations type-checked)
- Maximum value (most frequently used)
- Clean foundation for future work
- Clear API semantics

**Estimated total effort:** 2-3 days for Tier S, including testing.

**After Tier S:** Evaluate if Tier A utilities are worth typing, or if you're satisfied with coverage.

The Tier S functions are the "waist" of the system - everything flows through them. Typing them provides the most bang for your buck.
