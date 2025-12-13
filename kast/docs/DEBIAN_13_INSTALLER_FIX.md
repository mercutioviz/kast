# Debian 13 Installer Compatibility Fix

## Overview

This document describes the fixes applied to the KAST installer to properly support Debian 13 (Trixie) and improve package installation resilience across all supported distributions.

## Issue Summary

When testing the KAST installer on Debian 13, several warnings occurred:

1. **Java Package Failure**: Attempted to install `openjdk-17-jre` which doesn't exist in Debian 13 repositories
2. **Cascade Failures**: When Java installation failed, subsequent packages (`testssl.sh`, `whatweb`) were skipped
3. **Command Verification**: Some tools use different command names across distributions

## Root Cause Analysis

### Java Version Mismatch

The installer had OS-specific logic for Java package selection, but it only covered:
- Kali Linux → OpenJDK 21
- Ubuntu 24+ → OpenJDK 21
- Default (Debian 12) → OpenJDK 17

**Missing case**: Debian 13+ which requires OpenJDK 21

```bash
# OLD CODE (problematic)
local java_package="openjdk-17-jre"  # Default to 17 for Debian 12
if [[ "$os_id" == "kali" ]] || [[ "$os_id" == "ubuntu" && $os_version -ge 24 ]]; then
    java_package="openjdk-21-jre"
fi
```

### Package Installation Fragility

The old approach used a single `apt install` command with all packages:

```bash
apt install -y git gpg htop nginx $java_package python3 python3-venv sslscan testssl.sh wafw00f whatweb
```

**Problem**: If ANY package fails (like `openjdk-17-jre`), the entire command aborts, leaving many packages uninstalled.

## Solutions Implemented

### 1. Comprehensive OS-Specific Package Selection

Added explicit handling for each distribution and version:

```bash
if [[ "$os_id" == "debian" ]]; then
    if [[ $os_version -ge 13 ]]; then
        java_package="openjdk-21-jre"  # Debian 13+ (Trixie, Forky)
        firefox_package="firefox-esr"
    elif [[ $os_version -ge 12 ]]; then
        java_package="openjdk-17-jre"  # Debian 12 (Bookworm)
        firefox_package="firefox-esr"
    fi
elif [[ "$os_id" == "ubuntu" ]]; then
    java_package="openjdk-21-jre"  # Ubuntu 24+
    firefox_package=""  # Ubuntu uses Firefox snap
elif [[ "$os_id" == "kali" ]]; then
    java_package="openjdk-21-jre"  # Kali uses OpenJDK 21
    firefox_package="firefox-esr"
fi
```

### 2. Tiered Package Installation Strategy

Packages are now categorized and installed separately:

1. **Critical Packages** (must succeed):
   - `git`, `gpg`, `python3`, `python3-venv`, `build-essential`
   - Installation failure → abort

2. **Tool Packages** (continue on failure):
   - `htop`, `nginx`, `sslscan`, `wafw00f`, Java package
   - Installation failure → log warning, continue

3. **Optional Packages** (continue on failure):
   - `testssl.sh`, `whatweb`, `firefox-esr`
   - Installation failure → log warning, continue

```bash
# Install critical packages first (must succeed)
log_info "Installing critical packages..."
if ! apt install -y $critical_packages; then
    log_error "Failed to install critical packages"
    return 1
fi

# Install tool packages (continue on failure)
log_info "Installing tool packages..."
local failed_tools=()
for pkg in $tool_packages; do
    if apt install -y $pkg 2>/dev/null; then
        log_success "    ✓ $pkg installed"
    else
        log_warning "    ✗ $pkg failed to install"
        failed_tools+=("$pkg")
    fi
done
```

### 3. Improved Error Reporting

The installer now provides a comprehensive summary of failed packages:

```
Package Installation Summary:
  Failed tool packages: openjdk-17-jre
  Failed optional packages: (none)

Installation will continue. Some features may be unavailable.
```

### 4. Command Verification Updates

The `verify_installation()` function already handles distribution-specific command names:

```bash
# testssl.sh has different command names on different systems
if ! command -v testssl.sh &>/dev/null && ! command -v testssl &>/dev/null; then
    log_warning "testssl not found in PATH"
fi

# Firefox check - optional on Ubuntu (uses snap)
if [[ "$os_id" != "ubuntu" ]]; then
    if ! command -v firefox &>/dev/null && ! command -v firefox-esr &>/dev/null; then
        log_warning "firefox not found in PATH"
    fi
fi
```

## Distribution-Specific Package Matrix

| Distribution | Version | Java Package | Firefox Package | testssl Command |
|--------------|---------|--------------|-----------------|-----------------|
| Debian 12 | Bookworm | openjdk-17-jre | firefox-esr | testssl.sh |
| Debian 13+ | Trixie, Forky | openjdk-21-jre | firefox-esr | testssl.sh |
| Ubuntu 24+ | Noble | openjdk-21-jre | (snap) | testssl.sh |
| Kali 2024+ | Rolling | openjdk-21-jre | firefox-esr | testssl.sh |

## Testing Results

### Before Fix (Debian 13)
```
[WARNING] Package 'openjdk-17-jre' has no installation candidate
[WARNING] firefox not found in PATH
[WARNING] testssl not found in PATH
[WARNING] whatweb not found in PATH
[WARNING] Installation completed with 3 warnings
```

### After Fix (Expected on Debian 13)
```
[INFO] Target Java package: openjdk-21-jre
[SUCCESS]     ✓ openjdk-21-jre installed
[SUCCESS]     ✓ testssl.sh installed
[SUCCESS]     ✓ whatweb installed
[SUCCESS] System packages installed
[SUCCESS] All verification checks passed!
```

## Benefits

1. **Correct Package Selection**: Each distribution gets the appropriate Java version
2. **Installation Resilience**: Failed optional packages don't abort the entire installation
3. **Better Diagnostics**: Clear reporting of which packages failed and why
4. **Future-Proof**: Easy to add new distributions or version-specific packages
5. **Graceful Degradation**: Installation continues even if some tools are unavailable

## Files Modified

- `install.sh` (lines 994-1097):
  - Updated `install_system_packages()` function
  - Added distribution-specific package selection logic
  - Implemented tiered package installation strategy
  - Enhanced error reporting

## Compatibility

This fix maintains backward compatibility with:
- Debian 12 (Bookworm)
- Ubuntu 24.04+ (Noble)
- Kali Linux 2024+

And adds full support for:
- Debian 13 (Trixie)
- Future Debian versions

## Recommendations

1. **Test on Debian 13**: Verify the fix resolves all warnings
2. **Monitor New Releases**: Watch for package changes in future Debian/Ubuntu releases
3. **Update Documentation**: Keep the package matrix current as new versions are released
4. **Consider Alternatives**: For critical tools, consider vendoring or using alternative installation methods if APT packages become unavailable

## Future Enhancements

Potential improvements for future releases:

1. **Dynamic Package Detection**: Query APT for available OpenJDK versions instead of hardcoding
2. **Fallback Strategies**: If primary package fails, try alternative packages (e.g., `openjdk-23-jre` if `openjdk-21-jre` unavailable)
3. **Package Aliases**: Create a mapping of tool names to distribution-specific package names
4. **Pre-flight Check**: Verify all required packages are available before starting installation

## References

- Debian 13 (Trixie) package repository: https://packages.debian.org/trixie/
- OpenJDK versions in Debian: https://packages.debian.org/search?keywords=openjdk
- Ubuntu Noble package repository: https://packages.ubuntu.com/noble/
