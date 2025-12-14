# Installer Wget Improvements

## Issue Description

During installation on Debian 13.2, the install.sh script hung when attempting to download golang via wget. After pressing Ctrl-C and re-running, the script successfully used APT to install golang instead.

## Root Causes

### 1. Silent Wget Downloads
The wget command used `-q` (quiet) flag, suppressing all output and making downloads appear hung when actually progressing slowly.

### 2. No Timeout Configuration
No timeout was set on wget, allowing slow connections or DNS issues to cause indefinite hanging.

### 3. Inconsistent APT Cache Handling
APT cache was updated on-demand during version checks, leading to different strategies between runs:
- First run: Stale cache → old golang version detected → manual install attempted
- Second run: Fresh cache → newer golang version detected → APT install used

### 4. No Network Connectivity Validation
No pre-check to verify download sources were reachable before attempting downloads.

## Solutions Implemented

### High Priority Fixes

#### 1. Improved Wget Visibility and Reliability
**Location**: `install_golang_manual()` function (line ~832)

**Changes**:
```bash
# Before:
if ! wget -q "$download_url"; then

# After:
if ! wget --timeout=60 --tries=3 --show-progress --progress=bar:force "$download_url" 2>&1; then
```

**Benefits**:
- Users see download progress with visual progress bar
- 60-second timeout per network operation prevents indefinite hanging
- 3 automatic retry attempts improve reliability
- Clear failure indication with detailed error messages

#### 2. Network Connectivity Pre-check
**Location**: `install_golang_manual()` function (line ~847)

**Changes**:
Added connectivity check before wget:
```bash
log_info "Checking connectivity to go.dev..."
if ! curl -s --connect-timeout 10 --max-time 10 -I "https://go.dev" >/dev/null 2>&1; then
    log_error "Cannot reach go.dev. Please check your network connection."
    log_error "You may need to configure proxy settings or try again later."
    
    # Offer fallback to APT if available
    local apt_ver=$(get_apt_version "golang")
    if [[ -n "$apt_ver" ]]; then
        log_warning "APT version available: $apt_ver"
        echo ""
        read -p "Would you like to install golang from APT instead? [y/N]: " fallback
        if [[ "$fallback" =~ ^[Yy]$ ]]; then
            log_info "Installing golang from APT..."
            apt install -y golang
            return $?
        fi
    fi
    
    return 1
fi
```

**Benefits**:
- Validates connectivity before attempting large download
- Provides helpful error messages for network issues
- Offers APT fallback option if network unavailable

#### 3. Download Failure Fallback
**Location**: `install_golang_manual()` function (line ~875)

**Changes**:
Added fallback logic after wget failure:
```bash
if ! wget --timeout=60 --tries=3 --show-progress --progress=bar:force "$download_url" 2>&1; then
    log_error "Failed to download Go from $download_url"
    log_error "This could be due to:"
    log_error "  - Network connectivity issues"
    log_error "  - Slow connection that timed out"
    log_error "  - Proxy or firewall restrictions"
    
    # Offer fallback to APT if available
    local apt_ver=$(get_apt_version "golang")
    if [[ -n "$apt_ver" ]]; then
        log_warning "APT version available: $apt_ver"
        echo ""
        read -p "Would you like to install golang from APT instead? [y/N]: " fallback
        if [[ "$fallback" =~ ^[Yy]$ ]]; then
            log_info "Installing golang from APT..."
            apt install -y golang
            return $?
        fi
    fi
    
    return 1
fi
```

**Benefits**:
- Provides clear error diagnostics
- Offers user the option to use APT as fallback
- Graceful degradation instead of complete failure

### Medium Priority Fixes

#### 4. Consistent APT Cache Handling
**Location**: `validate_prerequisites()` function (line ~622)

**Changes**:
```bash
# Added to beginning of validate_prerequisites():
log_info "Updating APT package cache..."
if apt update -qq 2>&1 | grep -q "Err:"; then
    log_warning "APT cache update encountered errors (continuing anyway)"
else
    log_success "APT cache updated successfully"
fi

# Removed from get_apt_version():
# Old code that updated cache on-demand removed
```

**Benefits**:
- APT cache updated once at validation start
- Consistent version detection across all tool checks
- Same installation strategy will be used on repeated runs
- More predictable behavior

#### 5. Better User Communication
**Location**: `install_golang_manual()` function (line ~867)

**Changes**:
```bash
log_info "Downloading Go ${go_version} (approximately 150MB)..."
log_info "This may take several minutes on slow connections..."
```

**Benefits**:
- Sets user expectations about download size
- Prevents premature Ctrl-C interruptions
- Reduces confusion during long downloads

## Testing Recommendations

### Test Scenario 1: Normal Installation
```bash
# Clean Debian 13.2 system with good internet
sudo ./install.sh
# Expected: Progress bar shown, download completes successfully
```

### Test Scenario 2: Slow Connection
```bash
# Use traffic shaping to simulate slow connection (e.g., tc, trickle)
sudo ./install.sh
# Expected: Progress bar updates slowly, timeout after 60s if too slow
```

### Test Scenario 3: Network Unavailable
```bash
# Disconnect network or block go.dev
sudo ./install.sh
# Expected: Connectivity check fails, offers APT fallback
```

### Test Scenario 4: Repeated Runs
```bash
# Run installer twice in succession
sudo ./install.sh  # First run
sudo ./install.sh  # Second run
# Expected: Same installation strategy chosen both times
```

## Related Files

- `install.sh` - Main installation script with improvements
- `genai-instructions.md` - Project documentation (consider updating)
- `.clinerules` - Cline configuration

## Impact Analysis

### Positive Impacts
- **User Experience**: Clear progress indication prevents confusion
- **Reliability**: Timeouts and retries handle network issues gracefully
- **Consistency**: APT cache handling ensures predictable behavior
- **Robustness**: Fallback options prevent total installation failure

### Potential Concerns
- **Timeout Duration**: 60 seconds may be too short for very slow connections
  - Mitigation: 3 retries provides 180 seconds total
- **User Interruption**: Interactive prompts may confuse automation
  - Mitigation: Only shown on errors, not during normal flow

## Future Enhancements

### Could Be Added Later
1. **Configurable Timeout**: Allow users to set custom timeout via environment variable
2. **Mirror Selection**: Offer alternative download mirrors for Go tarball
3. **Bandwidth Detection**: Adjust timeout based on connection speed
4. **Silent Mode**: Add flag to skip interactive prompts for automation

### Not Recommended
- Removing progress bar (reduces user confidence)
- Shorter timeout periods (may cause false failures)
- Automatic APT fallback (removes user choice)

## Version History

- **2024-12-14**: Initial implementation of wget improvements
  - Added timeout, retries, and progress display
  - Added network connectivity checks
  - Added fallback to APT option
  - Implemented consistent APT cache handling

## References

- Original issue: Wget hanging on Debian 13.2 during golang download
- Wget documentation: https://www.gnu.org/software/wget/manual/wget.html
- APT cache behavior: https://wiki.debian.org/Apt
