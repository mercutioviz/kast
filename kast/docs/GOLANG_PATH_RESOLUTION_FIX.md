# Golang Path Resolution Fix

## Issue Description

The installer experienced a critical path inconsistency issue where Go detection and Go usage logic were mismatched:

**Symptom:**
```
[INFO] Go installation strategy is 'SKIP_ALREADY_INSTALLED', skipping manual install
[INFO] Installing Node.js...
...
[INFO] Installing ProjectDiscovery tools...
[ERROR] Go binary not found at /usr/local/go/bin/go
[ERROR] Go must be installed before installing Go tools
```

**Root Cause:**
- Go detection logic was flexible (checked `command -v go` in PATH)
- Go usage logic was rigid (hardcoded `/usr/local/go/bin/go`)
- When Go was installed via APT (at `/usr/bin/go`), the detection succeeded but usage failed

## Technical Analysis

### The Inconsistency

**Detection Logic** (in prerequisite validation):
```bash
# Line 66-68
TOOL_CHECK_COMMANDS["golang"]="(command -v go >/dev/null 2>&1 && go version 2>/dev/null | awk '{print \$3}' | sed 's/go//') || (/usr/local/go/bin/go version 2>/dev/null | awk '{print \$3}' | sed 's/go//')"
```
This checks for Go in PATH first (could be `/usr/bin/go` from APT), then falls back to manual install location.

**Usage Logic** (in `install_go_tools()`):
```bash
# Old code - Line ~1048
local go_binary="/usr/local/go/bin/go"
```
This always assumed Go was at `/usr/local/go/bin/go` (manual installation location).

### When This Occurs

1. **First Run**: Go installed via APT (or pre-existing)
   - Located at `/usr/bin/go`
   - Strategy: `SKIP_ALREADY_INSTALLED`
   - Go tools installation tries `/usr/local/go/bin/go` → **FAILS**

2. **Second Run After Cancel**: APT cache updated
   - Different version detected
   - Different strategy chosen
   - May work by coincidence

3. **Re-runs with Manual Install**: Go at `/usr/local/go/bin/go`
   - Works correctly by luck

## Solution Implemented

### Three-Tier Path Resolution

The fix implements a robust, multi-source path detection system:

#### 1. Global Binary Path Storage
```bash
# Added at line 98
declare -gA TOOL_BINARY_PATHS
```

This array stores detected binary locations during prerequisite validation for later use.

#### 2. Path Storage During Validation
```bash
# Added in validate_prerequisites() function
if [[ "$strategy" == "SKIP_ALREADY_INSTALLED" ]]; then
    if [[ "$tool" == "golang" ]]; then
        local go_path=$(command -v go 2>/dev/null)
        if [[ -n "$go_path" ]]; then
            TOOL_BINARY_PATHS["golang"]="$go_path"
            log_info "  - Detected Go binary at: $go_path"
        fi
    fi
fi
```

When Go is already installed, we capture where it actually is.

#### 3. Dynamic Resolution in install_go_tools()

The function now tries three sources in order:

```bash
# First: Check stored path from validation
if [[ -n "${TOOL_BINARY_PATHS[golang]}" ]]; then
    go_binary="${TOOL_BINARY_PATHS[golang]}"
    log_info "Using Go binary from stored path: $go_binary"
fi

# Second: Try current PATH
if [[ -z "$go_binary" ]] || [[ ! -x "$go_binary" ]]; then
    local path_go=$(command -v go 2>/dev/null)
    if [[ -n "$path_go" ]] && [[ -x "$path_go" ]]; then
        go_binary="$path_go"
        log_info "Found Go binary in PATH: $go_binary"
    fi
fi

# Third: Check manual install location
if [[ -z "$go_binary" ]] || [[ ! -x "$go_binary" ]]; then
    if [[ -x "/usr/local/go/bin/go" ]]; then
        go_binary="/usr/local/go/bin/go"
        log_info "Found Go binary at manual install location: $go_binary"
    fi
fi
```

### Enhanced Error Diagnostics

If all resolution attempts fail, the error message now shows what was tried:

```bash
log_error "Go binary not found"
log_error "Searched locations:"
log_error "  - Stored path: ${TOOL_BINARY_PATHS[golang]:-<not set>}"
log_error "  - PATH lookup: $(command -v go 2>/dev/null || echo '<not found>')"
log_error "  - Manual install: /usr/local/go/bin/go"
log_error ""
log_error "Go must be installed before installing Go tools"
log_error "Installation strategy was: ${INSTALL_STRATEGY[golang]}"
```

### Binary Verification

Added verification that the Go binary actually works:

```bash
# Verify the Go binary actually works
local go_version=$("$go_binary" version 2>/dev/null | awk '{print $3}' | sed 's/go//')
if [[ -z "$go_version" ]]; then
    log_error "Go binary at $go_binary exists but does not work"
    log_error "Cannot determine Go version"
    return 1
fi

log_success "Using Go $go_version at: $go_binary"
```

## Testing Scenarios

### Scenario 1: APT-Installed Go
```bash
# System has Go via APT at /usr/bin/go
sudo ./install.sh
# Expected: Uses /usr/bin/go, succeeds
```

### Scenario 2: Manually-Installed Go
```bash
# System has Go via manual install at /usr/local/go/bin/go
sudo ./install.sh
# Expected: Uses /usr/local/go/bin/go, succeeds
```

### Scenario 3: No Go Initially
```bash
# System has no Go
sudo ./install.sh
# Expected: Installs Go, stores path, uses it, succeeds
```

### Scenario 4: Multiple Go Installations
```bash
# System has both APT and manual Go
# Manual install has higher priority in PATH
sudo ./install.sh
# Expected: Uses the one in PATH (highest priority), succeeds
```

### Scenario 5: Re-run After Interrupt
```bash
# First run interrupted during Go tool installation
sudo ./install.sh  # Ctrl-C
# Second run with Go already available
sudo ./install.sh
# Expected: Detects existing Go, stores path, succeeds
```

## Code Changes Summary

### Files Modified
- `install.sh`

### Lines Changed
1. **Line 98**: Added `declare -gA TOOL_BINARY_PATHS`
2. **Lines ~642-650**: Store Go binary path during validation
3. **Lines ~1063-1125**: Complete rewrite of Go binary detection in `install_go_tools()`

### Backward Compatibility
- ✅ Works with existing manual installations
- ✅ Works with APT installations
- ✅ Works with no existing Go installation
- ✅ Does not break existing installation strategies

## Benefits

### User Experience
- **Eliminates confusing errors**: No more "Go not found" when Go is clearly installed
- **Consistent behavior**: Same result on repeated runs
- **Better diagnostics**: Clear indication of what was searched and where

### Technical Robustness
- **Multiple fallbacks**: Three different detection methods ensure success
- **Strategy alignment**: Detection and usage logic now consistent
- **Future-proof**: Can easily extend to other tools

### Maintenance
- **Self-documenting**: Log messages show exactly what happened
- **Debuggable**: Clear error messages indicate what went wrong
- **Extensible**: Pattern can be applied to other tools (Java, Node.js)

## Related Issues

This fix also improves the resolution of issues documented in:
- `INSTALLER_WGET_IMPROVEMENTS.md` - Wget hanging issue
- `GOLANG_DETECTION_FIX.md` - Original Go detection improvements

## Future Enhancements

### Could Be Added
1. **Extend to other tools**: Apply same pattern to Java and Node.js
2. **PATH priority control**: Allow users to specify preferred Go binary
3. **Version-specific resolution**: Prefer newer Go version if multiple exist
4. **Configuration file**: Store tool paths in config for faster resolution

### Not Recommended
- Removing any of the three fallback methods (reduces robustness)
- Making PATH resolution synchronous during validation (slows down validation)
- Automatic binary selection without user notification (reduces transparency)

## Version History

- **2024-12-14**: Initial implementation of dynamic Go path resolution
  - Added `TOOL_BINARY_PATHS` global array
  - Implemented three-tier path resolution
  - Enhanced error diagnostics
  - Added binary verification

## References

- Original issue: "Go binary not found at /usr/local/go/bin/go"
- Related: `INSTALLER_WGET_IMPROVEMENTS.md`
- Bash best practices: https://www.gnu.org/software/bash/manual/
- Go installation guide: https://go.dev/doc/install
