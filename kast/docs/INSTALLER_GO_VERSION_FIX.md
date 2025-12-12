# Installer Go Version Detection Fix

## Problem Summary

The installer's pre-requisite validation system was correctly identifying that Go 1.19.8 was insufficient (minimum required: 1.21.0), but the manual Go installation was never triggered. This resulted in katana and subfinder failing to install due to incompatible Go versions.

## Root Cause

The issue had three interconnected problems:

### 1. Strategy Value Contamination

The `determine_install_strategy()` function was calling `log_warning()` internally. When bash captured the function's output with `$(command)`, it captured **all stdout**, including log messages. This caused the strategy value to contain:

```
[WARNING] golang is installed but version 1.19.8 is below minimum 1.21.0
[WARNING] APT version of golang (1.19) is below minimum required (1.21.0)
USE_MANUAL
```

Instead of just:
```
USE_MANUAL
```

### 2. Strategy Comparison Failure

When the code checked:
```bash
if [[ "${INSTALL_STRATEGY[golang]}" == "USE_MANUAL" ]]; then
```

It failed because the actual value was a multi-line string starting with `[WARNING]` instead of `USE_MANUAL`.

### 3. Scope Issues (Previously Fixed)

The associative arrays needed to be declared with `-gA` for global scope to be accessible in the main() function.

## Solution Implemented

### Fix 1: Remove Logging from Strategy Determination

Modified `determine_install_strategy()` to only return strategy values without any log output:

```bash
determine_install_strategy() {
    local tool=$1
    local apt_package="${TOOL_APT_PACKAGES[$tool]}"
    local min_version="${TOOL_MIN_VERSIONS[$tool]}"
    
    # Check if already installed with sufficient version
    local installed_version=$(get_installed_version "$tool")
    if [[ -n "$installed_version" ]]; then
        if check_version_requirement "$tool" "$installed_version"; then
            echo "SKIP_ALREADY_INSTALLED"
            return 0
        fi
        # Don't log here - let caller handle it
    fi
    
    # Check apt availability and version
    if [[ -n "$apt_package" ]]; then
        local apt_version=$(get_apt_version "$apt_package")
        APT_AVAILABLE_VERSIONS["$tool"]="$apt_version"
        
        if [[ -n "$apt_version" ]]; then
            if check_version_requirement "$tool" "$apt_version"; then
                echo "USE_APT"
                return 0
            fi
            # Don't log here - let caller handle it
        fi
        # Don't log here - let caller handle it
    fi
    
    # Fall back to manual installation
    echo "USE_MANUAL"
    return 0
}
```

### Fix 2: Move Logging to Caller

Updated `validate_prerequisites()` to handle all logging after capturing the strategy:

```bash
for tool in "${tools[@]}"; do
    local min_version="${TOOL_MIN_VERSIONS[$tool]}"
    local installed_version=$(get_installed_version "$tool")
    local apt_package="${TOOL_APT_PACKAGES[$tool]}"
    
    # Determine strategy (clean output, no logs)
    local strategy=$(determine_install_strategy "$tool")
    INSTALL_STRATEGY["$tool"]="$strategy"
    
    # Log the strategy with context (after capture)
    log_info "Analyzing $tool:"
    log_info "  - Minimum required: $min_version"
    log_info "  - Currently installed: ${installed_version:-Not installed}"
    log_info "  - APT available: ${APT_AVAILABLE_VERSIONS[$tool]:-N/A}"
    log_info "  - Installation strategy: $strategy"
    
    # Add contextual warnings
    if [[ -n "$installed_version" ]]; then
        if ! check_version_requirement "$tool" "$installed_version"; then
            log_warning "$tool is installed but version $installed_version is below minimum $min_version"
        fi
    fi
    
    if [[ "$strategy" == "USE_MANUAL" ]]; then
        local apt_ver="${APT_AVAILABLE_VERSIONS[$tool]}"
        if [[ -n "$apt_ver" ]]; then
            log_warning "APT version of $tool ($apt_ver) is below minimum required ($min_version)"
        else
            log_warning "Package $apt_package not available in APT repositories"
        fi
    fi
done
```

### Fix 3: Enhanced Debug Logging

Added debug output to trace strategy values:

```bash
# Debug: Check what strategies were determined
log_info "DEBUG: Checking installation strategies..."
log_info "DEBUG: golang strategy = '${INSTALL_STRATEGY[golang]}'"
log_info "DEBUG: java strategy = '${INSTALL_STRATEGY[java]}'"
log_info "DEBUG: nodejs strategy = '${INSTALL_STRATEGY[nodejs]}'"
```

## Expected Behavior After Fix

When running the installer on a system with Go 1.19.8, you should see:

1. **Pre-Requisite Analysis** showing:
   ```
   [INFO] Analyzing golang:
   [INFO]   - Minimum required: 1.21.0
   [INFO]   - Currently installed: 1.19.8
   [INFO]   - APT available: 1.19
   [INFO]   - Installation strategy: USE_MANUAL
   [WARNING] golang is installed but version 1.19.8 is below minimum 1.21.0
   [WARNING] APT version of golang (1.19) is below minimum required (1.21.0)
   ```

2. **Strategy Table** showing:
   ```
   │ golang       │ 1.21.0       │ 1.19.8       │ 1.19         │ Manual (tarball)    │
   ```

3. **Debug Output** showing:
   ```
   [INFO] DEBUG: golang strategy = 'USE_MANUAL'
   ```

4. **Manual Installation Triggered**:
   ```
   [INFO] Go requires manual installation (APT version insufficient)
   [INFO] Installing Go manually (tarball method)...
   [INFO] Downloading Go 1.21.13...
   ```

5. **Successful Installation**:
   ```
   [SUCCESS] Go 1.21.13 installed successfully
   [SUCCESS] Installed Go version meets minimum requirement (1.21.0)
   ```

6. **ProjectDiscovery Tools Install Successfully**:
   ```
   [INFO] Installing katana...
   [INFO] Installing subfinder...
   [SUCCESS] Go tools installed
   ```

## Testing

To test the fix:

1. Run the installer on a system with Go 1.19.x:
   ```bash
   sudo ./install.sh
   ```

2. Verify the strategy is correctly identified as `USE_MANUAL`

3. Verify manual Go installation is triggered and completes

4. Verify katana and subfinder install successfully with the newer Go version

## Files Modified

- `install.sh` - Fixed strategy contamination and added enhanced logging
- `test_version_detection.sh` - Created test script for validation

## Version

Fixed in KAST Installer v2.6.4
