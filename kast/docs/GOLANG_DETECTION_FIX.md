# Golang Detection and Installation Fix

## Overview

Critical bugs were discovered in the KAST installer's Go detection and installation process on Debian 12. This document describes the issues and their solutions.

## Issues Identified

### Issue 1: Go Detection Fails Under Sudo

**Problem:**
```bash
# As regular user
$ go version
go version go1.24.1 linux/amd64

# Under sudo (installer context)
Currently installed: Not installed
```

**Root Cause:**
The `get_installed_version("golang")` function executed `go version` which only checked PATH. When running under sudo, the PATH doesn't include `/usr/local/go/bin` (added to user's `.bashrc` but not available to sudo).

**Solution:**
Updated the golang check command to try both PATH and absolute path:
```bash
TOOL_CHECK_COMMANDS["golang"]="(command -v go >/dev/null 2>&1 && go version 2>/dev/null | awk '{print \$3}' | sed 's/go//') || (/usr/local/go/bin/go version 2>/dev/null | awk '{print \$3}' | sed 's/go//')"
```

This ensures detection works in both user and sudo contexts.

### Issue 2: APT Installs Old Golang Unconditionally (CRITICAL)

**Problem:**
Even when installation strategy was `USE_MANUAL`, the installer still ran:
```bash
apt install -y git golang gpg htop nginx ...
```

This installed golang 1.19 from APT, creating a conflict with the manually installed Go 1.24.1.

**Root Cause:**
The `install_system_packages()` function blindly included `golang` in the package list without checking the installation strategy first.

**Solution:**
Made golang inclusion conditional based on strategy:
```bash
# Build package list without golang
local packages="git gpg htop nginx $java_package python3 python3-venv sslscan testssl.sh wafw00f whatweb"

# Only add golang if strategy says to use APT
if [[ "${INSTALL_STRATEGY[golang]}" == "USE_APT" ]]; then
    packages="golang $packages"
    log_info "Adding golang from APT (strategy: USE_APT)"
else
    log_info "Skipping golang from APT (strategy: ${INSTALL_STRATEGY[golang]})"
fi
```

### Issue 3: Go Not Available to Sudo Commands

**Problem:**
Even with Go installed at `/usr/local/go/bin/go`, when running:
```bash
sudo -u "$ORIG_USER" bash -c "go install ..."
```

The go command was not found because non-interactive shells don't source `.bashrc`.

**Solution:**
Use absolute path to Go binary instead of relying on PATH:
```bash
local go_binary="/usr/local/go/bin/go"

# Verify Go is available
if [[ ! -x "$go_binary" ]]; then
    log_error "Go binary not found at $go_binary"
    return 1
fi

# Install with absolute path
sudo -u "$ORIG_USER" bash -c "
    export GOPATH='$gopath'
    export GOBIN='$gopath/bin'
    '$go_binary' install github.com/projectdiscovery/katana/cmd/katana@latest
"
```

## Implementation Details

### Modified Functions

1. **Tool Check Command (line ~59)**
   - Added fallback to absolute path for Go detection
   - Works in both user and sudo contexts

2. **`install_system_packages()` (lines ~655-687)**
   - Removed golang from default package list
   - Added conditional inclusion based on `INSTALL_STRATEGY[golang]`
   - Added logging for transparency

3. **`install_go_tools()` (lines ~823-887)**
   - Changed from relying on PATH to using absolute Go binary path
   - Added verification that Go binary exists before attempting installation
   - Improved error logging for failed installations

## Expected Behavior After Fix

### Scenario 1: Go 1.24.1 Already Installed

```
[INFO] Analyzing golang:
[INFO]   - Minimum required: 1.24.0
[INFO]   - Currently installed: 1.24.1
[INFO]   - APT available: N/A
[INFO]   - Installation strategy: SKIP_ALREADY_INSTALLED

[INFO] Skipping golang from APT (strategy: SKIP_ALREADY_INSTALLED)

[INFO] Go installation strategy is 'SKIP_ALREADY_INSTALLED', skipping manual install

[INFO] Installing ProjectDiscovery tools...
[INFO] Installing katana...
[SUCCESS] Katana installed successfully
[INFO] Installing subfinder...
[SUCCESS] Subfinder installed successfully
```

### Scenario 2: Fresh Install (No Go Present)

```
[INFO] Analyzing golang:
[INFO]   - Minimum required: 1.24.0
[INFO]   - Currently installed: Not installed
[INFO]   - APT available: N/A
[INFO]   - Installation strategy: USE_MANUAL

[INFO] Skipping golang from APT (strategy: USE_MANUAL)

[INFO] Go requires manual installation (APT version insufficient)
[INFO] Installing Go manually (tarball method)...
[INFO] Downloading Go 1.24.1...
[SUCCESS] Go 1.24.1 installed successfully to /usr/local/go

[INFO] Installing ProjectDiscovery tools...
[INFO] Installing katana...
[SUCCESS] Katana installed successfully
```

## Testing

Tested on:
- ✅ Debian 12 (fresh install)
- ✅ Debian 12 (with Go 1.24.1 pre-installed)
- ✅ Ubuntu 24.04 (various scenarios)

All scenarios now work correctly:
1. Fresh install: Installs Go 1.24.1, skips APT golang
2. Go pre-installed: Detects correctly, skips all Go installation
3. Go tools: Install successfully using absolute path

## Related Issues

- This fix combines with `INSTALLER_GO_VERSION_FIX.md` (Go 1.24.1 installation)
- Works with `UBUNTU_24_COMPATIBILITY.md` (OS-specific package handling)

## Version

Fixed in KAST Installer v2.6.4
