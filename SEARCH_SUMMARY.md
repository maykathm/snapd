# Parallel Install Runtime Issues - Search Summary

## Search Completed: June 22, 2026

### Scope
- **Codebase Size:** 3,807 Go files + C/H source files
- **Search Categories:** 8 comprehensive areas
- **Duration:** Exhaustive codebase sweep

### Key Search Terms Used
1. SNAP_COMMON data directory access
2. CommonDataDir() function usage tracing
3. Mount-control interface instance awareness
4. InstanceKey and InstanceName usage
5. /run/snapd/ path conflicts
6. /run/user/ XDG_RUNTIME_DIR handling
7. Content interface mount point isolation
8. Refresh transaction instance tracking
9. snap-confine namespace segregation
10. Service socket binding with instances
11. Cleanup/removal with hasOtherInstances checks
12. State.json conflict management
13. AppArmor profile instance segregation

### Critical Finding

**One Critical Bug Identified:**

File: `snap/snapenv/snapenv.go`  
Line: 123  
Issue: `SNAP_COMMON` environment variable uses `info.SnapName()` instead of `info.InstanceName()`

**Impact:** Parallel installed snaps share the same `/var/snap/snapname/common` directory instead of having instance-specific directories.

**Recommendation:** Change line 123 from:
```go
"SNAP_COMMON": snap.CommonDataDir(info.SnapName()),
```

To:
```go
"SNAP_COMMON": snap.CommonDataDir(info.InstanceName()),
```

### Verified Safe Components

All other parallel install support mechanisms are properly implemented:
- Mount units use instance names correctly
- Namespace segregation uses instance names
- Conflict detection is instance-aware
- Cleanup logic properly checks hasOtherInstances
- XDG_RUNTIME_DIR properly segregates by instance
- Content interface uses proper perspectives for instance segregation
- snap-confine properly segregates namespaces

### Report Location

Full detailed report saved to: `PARALLEL_INSTALL_ISSUES_REPORT.md`

Contains:
- Detailed analysis of all 8 categories
- Code references with line numbers
- Root cause analysis
- Impact assessment
- Fix recommendations
- Test coverage requirements
