# Ubuntu 24 Compatibility Fixes

## Overview

Several compatibility issues were identified when testing the KAST installer on Ubuntu 24.04. This document describes the problems encountered and the solutions implemented.

## Issues Identified

### 1. Go Tools Installation Failed (Critical)

**Problem:**
Even though Go 1.24.1 was installed successfully, katana and subfinder failed to install with the error:
```
bash: line 1: go: command not found
```

**Root Cause:**
When running `sudo -u "$ORIG_USER" bash -c "go install ..."`, the subshell didn't have access to the updated PATH because:
- Non-interactive shells don't automatically source `~/.bashrc`
- The PATH was only available in the installer's main shell

**Solution:**
Explicitly pass the Go PATH to sudo commands:
```bash
sudo -u "$ORIG_USER" bash -c "
    export PATH='/usr/local/go/bin:\$PATH'
    export GOPATH='$gopath'
    export GOBIN='$gopath/bin'
    go install github.com/projectdiscovery/katana/cmd/katana@latest
"
```

### 2. Package Name Differences

**Problem:**
- `firefox-esr` package doesn't exist on Ubuntu (only on Debian/Kali)
- Python version mismatch: script tried `python3.11-venv` but Ubuntu 24 has Python 3.12

**Root Cause:**
Ubuntu uses different package names and versions than Debian/Kali:
- Firefox is typically installed via snap on Ubuntu
- Python 3.12 is default on Ubuntu 24 (vs 3.11 on Debian 12/Kali)

**Solution:**

1. OS-specific package detection:
```bash
if [[ "$os_id" == "ubuntu" ]]; then
    firefox_package=""
    log_info "Ubuntu detected - Firefox will be installed via snap (if not already present)"
fi
```

2. Dynamic Python version detection:
```bash
local py_version=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
apt install -y python${py_version}-venv 2>/dev/null || apt install -y python3-venv
```

### 3. Verification Checks Incorrectly Named

**Problem:**
Verification was looking for wrong tool names:
- Checked for `testssl` but package installs `testssl.sh`
- Checked for `firefox` on Ubuntu where it may be a snap

**Solution:**
Updated verification to:
- Check for both `testssl.sh` and `testssl`
- Skip firefox check on Ubuntu (optional tool installed via snap)
- Handle OS-specific differences gracefully

## Implementation Details

### Modified Functions

1. **`install_go_tools()`**
   - Added explicit PATH export to sudo bash commands
   - Added success/failure logging per tool
   - Ensures Go binary is in PATH before running go install

2. **`install_system_packages()`**
   - Added OS detection for package name mapping
   - Dynamic firefox package selection (or skip on Ubuntu)
   - Python version auto-detection for venv package

3. **`verify_installation()`**
   - OS-aware tool checking
   - Optional firefox check for Ubuntu
   - Checks for multiple possible command names (testssl vs testssl.sh)

## Testing

The installer was tested on:
- ✅ Ubuntu 24.04 (AWS EC2 instance)
- ✅ Debian 12 (previous testing)
- ✅ Kali Linux 2024.x (previous testing)

### Expected Results After Fix

On Ubuntu 24.04, the installer should now:
1. ✅ Successfully install Go 1.24.1
2. ✅ Successfully install katana and subfinder using the new Go
3. ✅ Handle missing firefox-esr package gracefully
4. ✅ Install correct Python venv package (python3.12-venv)
5. ✅ Pass verification checks with appropriate warnings

## User Instructions

### After Installation on Ubuntu

When installation completes, you'll see:
```
IMPORTANT: Go was installed/updated during this installation.
To use the new Go version, you must reload your shell:

  Option 1: Start a new terminal session
  Option 2: Run: source ~/.bashrc (or source ~/.zshrc)
  Option 3: Run: exec $SHELL
```

**Then verify:**
```bash
go version        # Should show: go version go1.24.1 linux/amd64
which go          # Should show: /usr/local/go/bin/go
katana -version   # Should work
subfinder -version # Should work
```

## Known Differences Between Distributions

| Feature | Debian 12 | Ubuntu 24 | Kali 2024 |
|---------|-----------|-----------|-----------|
| Python Default | 3.11 | 3.12 | 3.11 |
| Firefox Package | firefox-esr | snap | firefox-esr |
| Java Default | openjdk-17 | openjdk-21 | openjdk-21 |
| Go in APT | 1.19 | Not available | 1.19 |

## Future Considerations

### Additional Distributions

To add support for more distributions:
1. Update `validate_os_support()` with new OS checks
2. Add OS-specific package mappings in `install_system_packages()`
3. Test thoroughly on target distribution
4. Update verification checks if tool names differ

### Package Version Tracking

Consider maintaining a distribution-specific package mapping:
```bash
declare -gA DISTRO_PACKAGES
DISTRO_PACKAGES["ubuntu_firefox"]=""  # Skip, use snap
DISTRO_PACKAGES["debian_firefox"]="firefox-esr"
DISTRO_PACKAGES["kali_firefox"]="firefox-esr"
```

## Related Documentation

- `INSTALLER_GO_VERSION_FIX.md` - Go 1.24.1 installation solution
- `INSTALL_SCRIPT_IMPROVEMENTS.md` - Pre-requisite validation system
- Main installer: `install.sh`

## Version

These fixes were implemented in KAST Installer v2.6.4
