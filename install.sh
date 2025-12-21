#!/bin/bash

# KAST Installation Script - Enhanced Version
# Handles fresh installs, upgrades, and recovery from aborted installations

###############################################################################
# CONSTANTS AND CONFIGURATION
###############################################################################

SCRIPT_VERSION="2.8.1"
INSTALL_STATE_FILE=".kast_install_state"
VERSION_FILE=".kast_version"
LOCK_FILE="/tmp/kast_install.lock"
LOG_DIR="/var/log/kast"
INSTALL_LOG="$LOG_DIR/install.log"
BACKUP_PREFIX="/opt/kast.backup"

# Mode flags
TOOLS_ONLY_MODE=false
AUTO_MODE=false

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Installation checkpoints
CHECKPOINT_INIT="initialization"
CHECKPOINT_PREREQ_VALIDATION="prerequisite_validation"
CHECKPOINT_PACKAGES="system_packages"
CHECKPOINT_NODEJS="nodejs"
CHECKPOINT_GO_TOOLS="go_tools"
CHECKPOINT_GECKO="geckodriver"
CHECKPOINT_TERRAFORM="terraform"
CHECKPOINT_OBSERVATORY="observatory"
CHECKPOINT_LIBPANGO="libpango"
CHECKPOINT_FILES="file_copy"
CHECKPOINT_VENV="python_venv"
CHECKPOINT_FTAP="ftap"
CHECKPOINT_LAUNCHERS="launcher_scripts"
CHECKPOINT_COMPLETE="complete"

###############################################################################
# TOOL REQUIREMENTS REGISTRY
###############################################################################

# This registry defines minimum version requirements for tools that may have
# version dependencies. It enables intelligent installation decisions:
# - Use apt if available version meets requirements
# - Fall back to manual installation (tarball, etc.) if apt version insufficient
# - Skip if already installed with correct version

# Declare associative arrays for tool requirements
declare -gA TOOL_MIN_VERSIONS
declare -gA TOOL_APT_PACKAGES
declare -gA TOOL_CHECK_COMMANDS
declare -gA TOOL_REQUIRED_BY
declare -gA TOOL_MANUAL_INSTALL

# Go/Golang - Required by ProjectDiscovery tools
TOOL_MIN_VERSIONS["golang"]="1.24.0"
TOOL_APT_PACKAGES["golang"]="golang"
# Check for go in PATH first, then try absolute path (for sudo context)
TOOL_CHECK_COMMANDS["golang"]="(command -v go >/dev/null 2>&1 && go version 2>/dev/null | awk '{print \$3}' | sed 's/go//') || (/usr/local/go/bin/go version 2>/dev/null | awk '{print \$3}' | sed 's/go//')"
TOOL_REQUIRED_BY["golang"]="katana, subfinder, httpx"
TOOL_MANUAL_INSTALL["golang"]="golang_tarball"

# Java Runtime Environment - Required by OWASP ZAP
TOOL_MIN_VERSIONS["java"]="11.0.0"
TOOL_APT_PACKAGES["java"]="openjdk-21-jre"
TOOL_CHECK_COMMANDS["java"]="java -version 2>&1 | grep -oP 'version \"?\K[0-9]+\.[0-9]+\.[0-9]+' | head -n1"
TOOL_REQUIRED_BY["java"]="OWASP ZAP"
TOOL_MANUAL_INSTALL["java"]="openjdk_tarball"

# Node.js - Required by MDN Observatory
TOOL_MIN_VERSIONS["nodejs"]="20.0.0"
TOOL_APT_PACKAGES["nodejs"]="nodejs"
TOOL_CHECK_COMMANDS["nodejs"]="node --version 2>/dev/null | sed 's/v//'"
TOOL_REQUIRED_BY["nodejs"]="MDN Observatory CLI"
TOOL_MANUAL_INSTALL["nodejs"]="nodesource_repo"

# Installation strategy results (populated during validation)
declare -gA INSTALL_STRATEGY
declare -gA APT_AVAILABLE_VERSIONS
declare -gA TOOL_BINARY_PATHS

###############################################################################
# LOGGING AND OUTPUT FUNCTIONS
###############################################################################

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$INSTALL_LOG"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" | tee -a "$INSTALL_LOG"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*" | tee -a "$INSTALL_LOG"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*" | tee -a "$INSTALL_LOG"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $*" | tee -a "$INSTALL_LOG"
}

###############################################################################
# CLEANUP AND ERROR HANDLING
###############################################################################

cleanup() {
    log_info "Performing cleanup..."
    if [[ -f "$LOCK_FILE" ]]; then
        rm -f "$LOCK_FILE"
        log_info "Removed lock file"
    fi
}

handle_error() {
    local exit_code=$?
    local line_number=$1
    log_error "Installation failed at line $line_number with exit code $exit_code"
    
    if [[ -n "$INSTALL_DIR" ]] && [[ -f "$INSTALL_DIR/$INSTALL_STATE_FILE" ]]; then
        echo "IN_PROGRESS" > "$INSTALL_DIR/$INSTALL_STATE_FILE"
        log_warning "Installation state saved. You can resume by running the installer again."
    fi
    
    cleanup
    exit $exit_code
}

handle_interrupt() {
    log_warning "Installation interrupted by user"
    if [[ -n "$INSTALL_DIR" ]] && [[ -f "$INSTALL_DIR/$INSTALL_STATE_FILE" ]]; then
        echo "IN_PROGRESS" > "$INSTALL_DIR/$INSTALL_STATE_FILE"
    fi
    cleanup
    exit 130
}

# Set up traps
trap 'handle_error ${LINENO}' ERR
trap 'handle_interrupt' INT TERM
trap 'cleanup' EXIT

###############################################################################
# STATE MANAGEMENT FUNCTIONS
###############################################################################

save_checkpoint() {
    local checkpoint=$1
    if [[ -n "$INSTALL_DIR" ]] && [[ -d "$INSTALL_DIR" ]]; then
        echo "$checkpoint" > "$INSTALL_DIR/$INSTALL_STATE_FILE"
        log_info "Checkpoint saved: $checkpoint"
    fi
}

get_last_checkpoint() {
    if [[ -f "$INSTALL_DIR/$INSTALL_STATE_FILE" ]]; then
        cat "$INSTALL_DIR/$INSTALL_STATE_FILE"
    else
        echo ""
    fi
}

checkpoint_completed() {
    local checkpoint=$1
    local last_checkpoint=$(get_last_checkpoint)
    
    # Define checkpoint order
    local checkpoints=(
        "$CHECKPOINT_INIT"
        "$CHECKPOINT_PREREQ_VALIDATION"
        "$CHECKPOINT_PACKAGES"
        "$CHECKPOINT_NODEJS"
        "$CHECKPOINT_GO_TOOLS"
        "$CHECKPOINT_GECKO"
        "$CHECKPOINT_TERRAFORM"
        "$CHECKPOINT_OBSERVATORY"
        "$CHECKPOINT_LIBPANGO"
        "$CHECKPOINT_FILES"
        "$CHECKPOINT_VENV"
        "$CHECKPOINT_FTAP"
        "$CHECKPOINT_LAUNCHERS"
        "$CHECKPOINT_COMPLETE"
    )
    
    # Find indices
    local target_idx=-1
    local last_idx=-1
    for i in "${!checkpoints[@]}"; do
        if [[ "${checkpoints[$i]}" == "$checkpoint" ]]; then
            target_idx=$i
        fi
        if [[ "${checkpoints[$i]}" == "$last_checkpoint" ]]; then
            last_idx=$i
        fi
    done
    
    # Return true if last checkpoint is at or after target
    [[ $last_idx -ge $target_idx ]]
}

###############################################################################
# VALIDATION FUNCTIONS
###############################################################################

detect_os() {
    # Check if /etc/os-release exists (standard for modern Linux distributions)
    if [[ ! -f /etc/os-release ]]; then
        echo "UNKNOWN"
        return 1
    fi
    
    # Source the os-release file to get distribution info
    source /etc/os-release
    
    # Return distribution ID (lowercase)
    echo "${ID:-UNKNOWN}"
    return 0
}

get_os_version() {
    # Check if /etc/os-release exists
    if [[ ! -f /etc/os-release ]]; then
        echo "0"
        return 1
    fi
    
    source /etc/os-release
    
    # For Kali Rolling, extract year from VERSION_ID if present
    # For others, return VERSION_ID directly
    if [[ "${ID}" == "kali" ]]; then
        # Kali Rolling may have VERSION_ID like "2024.3" or just be "kali-rolling"
        if [[ -n "$VERSION_ID" ]]; then
            # Extract year (first part before dot)
            echo "${VERSION_ID}" | cut -d'.' -f1
        else
            # Kali Rolling without VERSION_ID - assume current/supported
            echo "2024"
        fi
    else
        # Debian/Ubuntu - return major version
        echo "${VERSION_ID:-0}" | cut -d'.' -f1
    fi
    
    return 0
}

validate_os_support() {
    local os_id=$(detect_os)
    local os_version=$(get_os_version)
    
    log_info "Detected OS: $os_id (version: $os_version)"
    
    # Check if apt is available (Debian-based system requirement)
    if ! command -v apt &>/dev/null; then
        log_error "APT package manager not found. This installer requires a Debian-based system."
        return 1
    fi
    
    # Validate distribution and version
    case "$os_id" in
        kali)
            if [[ $os_version -ge 2024 ]]; then
                log_success "Kali Linux $os_version is supported"
                return 0
            else
                log_error "Kali Linux version $os_version is not supported"
                log_error "Minimum required: Kali 2024.x or later"
                return 1
            fi
            ;;
        debian)
            if [[ $os_version -ge 12 ]]; then
                log_success "Debian $os_version is supported"
                return 0
            else
                log_error "Debian version $os_version is not supported"
                log_error "Minimum required: Debian 12 or later"
                return 1
            fi
            ;;
        ubuntu)
            if [[ $os_version -ge 24 ]]; then
                log_success "Ubuntu $os_version is supported"
                return 0
            else
                log_error "Ubuntu version $os_version is not supported"
                log_error "Minimum required: Ubuntu 24 or later"
                return 1
            fi
            ;;
        *)
            log_error "Unsupported operating system: $os_id"
            display_unsupported_os "$os_id" "$os_version"
            return 1
            ;;
    esac
}

display_unsupported_os() {
    local os_id=$1
    local os_version=$2
    
    echo ""
    echo -e "${RED}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║                  UNSUPPORTED OPERATING SYSTEM                  ║${NC}"
    echo -e "${RED}╚════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}Detected OS:${NC} $os_id (version: $os_version)"
    echo ""
    echo "KAST requires one of the following Debian-based distributions:"
    echo ""
    echo "  • Kali Linux 2024.x or later"
    echo "  • Debian 12 (Bookworm) or later"
    echo "  • Ubuntu 24.04 (Noble Numbat) or later"
    echo ""
    echo "Your system does not meet these requirements."
    echo ""
    echo -e "${YELLOW}Possible reasons:${NC}"
    echo "  1. You are running an older version of a supported distribution"
    echo "  2. You are running a non-Debian-based distribution"
    echo "  3. System information could not be detected properly"
    echo ""
    echo -e "${YELLOW}Recommendations:${NC}"
    echo "  • Update your system to a supported version"
    echo "  • Install KAST on a supported distribution"
    echo "  • For manual installation, refer to the documentation"
    echo ""
}

validate_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This installer must be run as root (use sudo)"
        exit 1
    fi
}

validate_user_home() {
    local user=$1
    local home=$2
    
    # Validate user exists
    if ! id "$user" &>/dev/null; then
        log_error "User '$user' does not exist"
        return 1
    fi
    
    # Validate home directory exists
    if [[ ! -d "$home" ]]; then
        log_error "Home directory '$home' does not exist"
        return 1
    fi
    
    log_success "User validation passed: $user ($home)"
    return 0
}

check_installation_state() {
    local state="FRESH"
    
    if [[ -d "$INSTALL_DIR" ]]; then
        if [[ -f "$INSTALL_DIR/$VERSION_FILE" ]]; then
            local installed_version=$(cat "$INSTALL_DIR/$VERSION_FILE")
            if [[ "$installed_version" == "$SCRIPT_VERSION" ]]; then
                state="SAME_VERSION"
            else
                state="OLDER_VERSION"
            fi
        elif [[ -f "$INSTALL_DIR/$INSTALL_STATE_FILE" ]]; then
            local last_state=$(cat "$INSTALL_DIR/$INSTALL_STATE_FILE")
            if [[ "$last_state" != "$CHECKPOINT_COMPLETE" ]]; then
                state="ABORTED"
            else
                state="COMPLETE_NO_VERSION"
            fi
        else
            state="PARTIAL"
        fi
    fi
    
    echo "$state"
}

###############################################################################
# VERSION DETECTION AND COMPARISON FUNCTIONS
###############################################################################

# Detect system architecture for tarball downloads
detect_architecture() {
    local arch=$(dpkg --print-architecture 2>/dev/null)
    if [[ -z "$arch" ]]; then
        arch=$(uname -m)
        case "$arch" in
            x86_64) arch="amd64" ;;
            aarch64) arch="arm64" ;;
            armv7l) arch="armhf" ;;
        esac
    fi
    echo "$arch"
}

# Compare semantic versions (returns 0 if v1 >= v2, 1 otherwise)
version_compare() {
    local version1=$1
    local version2=$2
    
    # Handle empty versions
    if [[ -z "$version1" ]] || [[ -z "$version2" ]]; then
        return 1
    fi
    
    # Normalize versions by removing leading 'v' and trailing junk
    version1=$(echo "$version1" | sed 's/^v//;s/[^0-9.].*//')
    version2=$(echo "$version2" | sed 's/^v//;s/[^0-9.].*//')
    
    # Split versions into arrays
    IFS='.' read -ra v1_parts <<< "$version1"
    IFS='.' read -ra v2_parts <<< "$version2"
    
    # Compare each part
    local max_parts=${#v1_parts[@]}
    [[ ${#v2_parts[@]} -gt $max_parts ]] && max_parts=${#v2_parts[@]}
    
    for ((i=0; i<max_parts; i++)); do
        local part1=${v1_parts[$i]:-0}
        local part2=${v2_parts[$i]:-0}
        
        # Remove non-numeric suffixes
        part1=$(echo "$part1" | sed 's/[^0-9].*//')
        part2=$(echo "$part2" | sed 's/[^0-9].*//')
        
        # Default to 0 if empty
        part1=${part1:-0}
        part2=${part2:-0}
        
        if [[ $part1 -gt $part2 ]]; then
            return 0
        elif [[ $part1 -lt $part2 ]]; then
            return 1
        fi
    done
    
    # Versions are equal
    return 0
}

# Get currently installed version of a tool (if installed)
get_installed_version() {
    local tool=$1
    local check_command="${TOOL_CHECK_COMMANDS[$tool]}"
    
    if [[ -z "$check_command" ]]; then
        echo ""
        return 1
    fi
    
    # Execute the check command and capture output
    local version=$(eval "$check_command" 2>/dev/null)
    echo "$version"
    return 0
}

# Query apt for available package version
get_apt_version() {
    local package=$1
    
    # Note: APT cache should be updated once at the start of validate_prerequisites()
    # to ensure consistent version detection across all tool checks
    
    # Try apt-cache policy first (most reliable)
    local version=$(apt-cache policy "$package" 2>/dev/null | grep "Candidate:" | awk '{print $2}')
    
    # If that didn't work or returned (none), try apt-cache show
    if [[ -z "$version" ]] || [[ "$version" == "(none)" ]]; then
        version=$(apt-cache show "$package" 2>/dev/null | grep "^Version:" | head -n1 | awk '{print $2}')
    fi
    
    # If still empty, package doesn't exist
    if [[ -z "$version" ]] || [[ "$version" == "(none)" ]]; then
        return 1
    fi
    
    # Clean up version string (remove epoch and Debian release suffix)
    # Examples: "2:1.19~1" -> "1.19", "17.0.17+10-1~deb12u1" -> "17.0.17"
    version=$(echo "$version" | sed 's/^[0-9]*://;s/[+~-].*//')
    
    echo "$version"
    return 0
}

# Check if a tool's version requirement is satisfied
check_version_requirement() {
    local tool=$1
    local min_version="${TOOL_MIN_VERSIONS[$tool]}"
    local current_version=$2
    
    if [[ -z "$min_version" ]]; then
        # No version requirement
        return 0
    fi
    
    if [[ -z "$current_version" ]]; then
        # Tool not available
        return 1
    fi
    
    if version_compare "$current_version" "$min_version"; then
        return 0
    else
        return 1
    fi
}

# Determine installation strategy for a tool
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

###############################################################################
# BACKUP AND RESTORE FUNCTIONS
###############################################################################

create_backup() {
    if [[ -d "$INSTALL_DIR" ]]; then
        local timestamp=$(date +%Y%m%d_%H%M%S)
        local backup_dir="${BACKUP_PREFIX}.${timestamp}"
        
        log_info "Creating backup at $backup_dir..."
        cp -a "$INSTALL_DIR" "$backup_dir"
        
        if [[ -d "$backup_dir" ]]; then
            log_success "Backup created successfully"
            echo "$backup_dir"
            return 0
        else
            log_error "Failed to create backup"
            return 1
        fi
    fi
    return 0
}

###############################################################################
# PREREQUISITE VALIDATION
###############################################################################

# Perform prerequisite validation and determine installation strategies
validate_prerequisites() {
    if checkpoint_completed "$CHECKPOINT_PREREQ_VALIDATION"; then
        log_info "Prerequisites already validated, skipping..."
        return 0
    fi
    
    echo ""
    echo "======================================================================"
    echo "  Pre-Requisite Analysis"
    echo "======================================================================"
    echo ""
    
    # Update APT cache once at the beginning for consistent version detection
    log_info "Updating APT package cache..."
    if apt update -qq 2>&1 | grep -q "Err:"; then
        log_warning "APT cache update encountered errors (continuing anyway)"
    else
        log_success "APT cache updated successfully"
    fi
    
    log_info "Analyzing tool version requirements..."
    
    # Detect system architecture
    local sys_arch=$(detect_architecture)
    log_info "System architecture: $sys_arch"
    
    # Analyze each tool in the registry
    local tools=("golang" "java" "nodejs")
    
    for tool in "${tools[@]}"; do
        local min_version="${TOOL_MIN_VERSIONS[$tool]}"
        local installed_version=$(get_installed_version "$tool")
        local apt_package="${TOOL_APT_PACKAGES[$tool]}"
        
        # Determine strategy
        local strategy=$(determine_install_strategy "$tool")
        INSTALL_STRATEGY["$tool"]="$strategy"
        
        # Store binary path for tools that are already installed
        if [[ "$strategy" == "SKIP_ALREADY_INSTALLED" ]]; then
            if [[ "$tool" == "golang" ]]; then
                local go_path=$(command -v go 2>/dev/null)
                if [[ -n "$go_path" ]]; then
                    TOOL_BINARY_PATHS["golang"]="$go_path"
                    log_info "  - Detected Go binary at: $go_path"
                fi
            fi
        fi
        
        # Log the strategy with context
        log_info "Analyzing $tool:"
        log_info "  - Minimum required: $min_version"
        log_info "  - Currently installed: ${installed_version:-Not installed}"
        log_info "  - APT available: ${APT_AVAILABLE_VERSIONS[$tool]:-N/A}"
        log_info "  - Installation strategy: $strategy"
        
        # Add warnings based on what we found
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
    
    # Display summary table
    display_validation_summary
    
    # Ask user to proceed
    echo ""
    read -p "Proceed with installation? [Y/n]: " proceed
    proceed=${proceed:-Y}
    
    if [[ ! "$proceed" =~ ^[Yy]$ ]]; then
        log_info "Installation cancelled by user during prerequisite validation"
        exit 0
    fi
    
    save_checkpoint "$CHECKPOINT_PREREQ_VALIDATION"
    log_success "Prerequisite validation complete"
    
    return 0
}

# Display validation summary table
display_validation_summary() {
    echo ""
    echo "┌──────────────┬──────────────┬──────────────┬──────────────┬─────────────────────┐"
    echo "│ Tool         │ Min Required │ Installed    │ APT Available│ Installation Method │"
    echo "├──────────────┼──────────────┼──────────────┼──────────────┼─────────────────────┤"
    
    local tools=("golang" "java" "nodejs")
    
    for tool in "${tools[@]}"; do
        local min_ver="${TOOL_MIN_VERSIONS[$tool]}"
        local installed_ver=$(get_installed_version "$tool")
        local apt_ver="${APT_AVAILABLE_VERSIONS[$tool]}"
        local strategy="${INSTALL_STRATEGY[$tool]}"
        
        # Format versions (truncate if too long)
        [[ -z "$installed_ver" ]] && installed_ver="Not installed"
        [[ -z "$apt_ver" ]] && apt_ver="N/A"
        
        # Truncate to fit column width
        min_ver=$(printf "%.11s" "$min_ver")
        installed_ver=$(printf "%.11s" "$installed_ver")
        apt_ver=$(printf "%.11s" "$apt_ver")
        
        # Determine method description
        local method=""
        case "$strategy" in
            SKIP_ALREADY_INSTALLED)
                method="Skip (already OK)"
                ;;
            USE_APT)
                method="APT package manager"
                ;;
            USE_MANUAL)
                local manual_type="${TOOL_MANUAL_INSTALL[$tool]}"
                if [[ -n "$manual_type" ]]; then
                    case "$manual_type" in
                        golang_tarball)
                            method="Manual (tarball)"
                            ;;
                        openjdk_tarball)
                            method="Manual (tarball)"
                            ;;
                        nodesource_repo)
                            method="NodeSource repo"
                            ;;
                        *)
                            method="Manual installation"
                            ;;
                    esac
                else
                    method="Manual installation"
                fi
                ;;
            *)
                method="Unknown (check logs)"
                ;;
        esac
        
        # Print row
        printf "│ %-12s │ %-12s │ %-12s │ %-12s │ %-19s │\n" \
            "$tool" "$min_ver" "$installed_ver" "$apt_ver" "$method"
    done
    
    echo "└──────────────┴──────────────┴──────────────┴──────────────┴─────────────────────┘"
    echo ""
    
    # Display explanations for manual installations
    local has_manual=false
    for tool in "${tools[@]}"; do
        if [[ "${INSTALL_STRATEGY[$tool]}" == "USE_MANUAL" ]]; then
            has_manual=true
            break
        fi
    done
    
    if [[ "$has_manual" == "true" ]]; then
        echo -e "${YELLOW}Note:${NC} Manual installations will be performed for tools where APT versions"
        echo "are insufficient. This ensures all version requirements are met."
        echo ""
        
        for tool in "${tools[@]}"; do
            if [[ "${INSTALL_STRATEGY[$tool]}" == "USE_MANUAL" ]]; then
                local required_by="${TOOL_REQUIRED_BY[$tool]}"
                echo "  • $tool: Required by $required_by"
            fi
        done
        echo ""
    fi
}

###############################################################################
# INSTALLATION FUNCTIONS
###############################################################################

install_system_packages() {
    if checkpoint_completed "$CHECKPOINT_PACKAGES"; then
        log_info "System packages already installed, skipping..."
        return 0
    fi
    
    log_info "Installing system packages..."
    
    # Install base tools first (including build-essential for CGO support)
    apt install -y ca-certificates curl gnupg rsync jq build-essential
    
    # Determine OS-specific packages
    local os_id=$(detect_os)
    local os_version=$(get_os_version)
    local java_package=""
    local firefox_package=""
    
    # Set OS-specific package names based on distribution and version
    # Java: Different distributions and versions have different OpenJDK packages
    if [[ "$os_id" == "debian" ]]; then
        if [[ $os_version -ge 13 ]]; then
            java_package="openjdk-21-jre"  # Debian 13+ (Trixie, Forky)
            firefox_package="firefox-esr"
        elif [[ $os_version -ge 12 ]]; then
            java_package="openjdk-17-jre"  # Debian 12 (Bookworm)
            firefox_package="firefox-esr"
        else
            java_package="openjdk-17-jre"  # Fallback
            firefox_package="firefox-esr"
        fi
    elif [[ "$os_id" == "ubuntu" ]]; then
        java_package="openjdk-21-jre"  # Ubuntu 24+ uses OpenJDK 21
        firefox_package=""  # Ubuntu uses Firefox snap
        log_info "Ubuntu detected - Firefox will be installed via snap (if not already present)"
    elif [[ "$os_id" == "kali" ]]; then
        java_package="openjdk-21-jre"  # Kali uses OpenJDK 21
        firefox_package="firefox-esr"
    else
        # Fallback for unknown distributions
        java_package="openjdk-21-jre"
        firefox_package="firefox-esr"
        log_warning "Unknown distribution '$os_id' - using default Java package"
    fi
    
    log_info "Target Java package: $java_package"
    
    # Build package lists - separate critical from optional
    local critical_packages="git gpg python3 python3-venv build-essential"
    local tool_packages="htop nginx sslscan wafw00f"
    local optional_packages=""
    
    # Add distribution-specific packages
    # Note: testssl and whatweb have different package names across distributions
    case "$os_id" in
        debian|kali)
            optional_packages="testssl.sh whatweb"
            ;;
        ubuntu)
            # Ubuntu may have different package names
            optional_packages="testssl.sh whatweb"
            ;;
    esac
    
    # Add firefox if specified
    if [[ -n "$firefox_package" ]]; then
        optional_packages="$firefox_package $optional_packages"
    fi
    
    # Add Java package
    if [[ -n "$java_package" ]]; then
        tool_packages="$tool_packages $java_package"
    fi
    
    # Only add golang if strategy says to use APT
    if [[ "${INSTALL_STRATEGY[golang]}" == "USE_APT" ]]; then
        tool_packages="$tool_packages golang"
        log_info "Adding golang from APT (strategy: USE_APT)"
    else
        log_info "Skipping golang from APT (strategy: ${INSTALL_STRATEGY[golang]})"
    fi
    
    # Install critical packages first (must succeed)
    log_info "Installing critical packages..."
    if ! apt install -y $critical_packages; then
        log_error "Failed to install critical packages"
        return 1
    fi
    
    # Verify python3-venv specifically since it's critical
    if ! dpkg -l | grep -q "python3.*-venv"; then
        log_info "Installing python3-venv package specifically..."
        # Try with Python version detection
        local py_version=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
        apt install -y python${py_version}-venv 2>/dev/null || apt install -y python3-venv || {
            log_error "Failed to install python3-venv"
            return 1
        }
    fi
    
    # Install tool packages (continue on failure)
    log_info "Installing tool packages..."
    local failed_tools=()
    for pkg in $tool_packages; do
        log_info "  Installing $pkg..."
        if apt install -y $pkg 2>/dev/null; then
            log_success "    ✓ $pkg installed"
        else
            log_warning "    ✗ $pkg failed to install"
            failed_tools+=("$pkg")
        fi
    done
    
    # Install optional packages (continue on failure)
    log_info "Installing optional packages..."
    local failed_optional=()
    for pkg in $optional_packages; do
        log_info "  Installing $pkg..."
        if apt install -y $pkg 2>/dev/null; then
            log_success "    ✓ $pkg installed"
        else
            log_warning "    ✗ $pkg failed to install"
            failed_optional+=("$pkg")
        fi
    done
    
    # Report summary
    if [[ ${#failed_tools[@]} -gt 0 ]] || [[ ${#failed_optional[@]} -gt 0 ]]; then
        echo ""
        log_warning "Package Installation Summary:"
        if [[ ${#failed_tools[@]} -gt 0 ]]; then
            log_warning "  Failed tool packages: ${failed_tools[*]}"
        fi
        if [[ ${#failed_optional[@]} -gt 0 ]]; then
            log_warning "  Failed optional packages: ${failed_optional[*]}"
        fi
        echo ""
        log_info "Installation will continue. Some features may be unavailable."
        echo ""
    fi
    
    save_checkpoint "$CHECKPOINT_PACKAGES"
    log_success "System packages installed"
}

install_golang_manual() {
    local min_version="${TOOL_MIN_VERSIONS[golang]}"
    local arch=$(detect_architecture)
    
    log_info "Installing Go manually (tarball method)..."
    log_info "Minimum required version: $min_version"
    log_info "System architecture: $arch"
    
    # Determine Go version to install
    # ProjectDiscovery tools require Go 1.24+ (their go.mod specifies version 1.24)
    local go_version="1.24.1"
    local go_tarball="go${go_version}.linux-${arch}.tar.gz"
    local download_url="https://go.dev/dl/${go_tarball}"
    
    # Check network connectivity before attempting download
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
    
    log_info "Downloading Go ${go_version} (approximately 150MB)..."
    log_info "This may take several minutes on slow connections..."
    
    # Download to /tmp
    cd /tmp
    
    # Use wget with timeout, retries, and progress display
    # --timeout=60: 60 second timeout per network operation
    # --tries=3: retry up to 3 times
    # --show-progress: display progress bar
    # --progress=bar:force: force progress bar even if output is redirected
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
    
    log_info "Removing old Go installations..."
    
    # Remove any existing /usr/local/go installation
    rm -rf /usr/local/go
    
    # Remove all APT golang packages more thoroughly
    log_info "Removing all APT golang packages to prevent PATH conflicts..."
    apt remove -y golang golang-go golang-src golang-doc 2>/dev/null || true
    apt remove -y golang-1.19 golang-1.19-go golang-1.19-src golang-1.19-doc 2>/dev/null || true
    
    # Remove old Go binaries from /usr/bin if they exist
    rm -f /usr/bin/go /usr/bin/gofmt 2>/dev/null || true
    
    # Clean up any remaining go installations in standard locations
    rm -rf /usr/lib/go* 2>/dev/null || true
    
    log_info "Extracting Go tarball..."
    if ! tar -C /usr/local -xzf "$go_tarball"; then
        log_error "Failed to extract Go tarball"
        rm -f "$go_tarball"
        return 1
    fi
    
    # Clean up tarball
    rm -f "$go_tarball"
    
    # Update system-wide Go path
    log_info "Updating PATH for Go..."
    
    # Add to /etc/profile.d for system-wide access (prepend to PATH)
    cat > /etc/profile.d/go.sh <<'EOF'
export PATH=/usr/local/go/bin:$PATH
export GOPATH=$HOME/go
export PATH=$PATH:$GOPATH/bin
EOF
    
    chmod +x /etc/profile.d/go.sh
    
    # Also add to user's shell RC file for immediate availability
    local user_home="$ORIG_HOME"
    local shell_rc=""
    
    # Determine which shell RC file to use
    if [[ -f "$user_home/.zshrc" ]]; then
        shell_rc="$user_home/.zshrc"
    elif [[ -f "$user_home/.bashrc" ]]; then
        shell_rc="$user_home/.bashrc"
    else
        # Create .bashrc if neither exists
        shell_rc="$user_home/.bashrc"
        touch "$shell_rc"
        chown "$ORIG_USER:$ORIG_USER" "$shell_rc"
    fi
    
    log_info "Adding Go PATH to $shell_rc..."
    
    # Check if Go PATH is already in the RC file
    if ! grep -q "/usr/local/go/bin" "$shell_rc" 2>/dev/null; then
        cat >> "$shell_rc" <<'EOF'

# Go programming language
export PATH=/usr/local/go/bin:$PATH
export GOPATH=$HOME/go
export PATH=$PATH:$GOPATH/bin
EOF
        chown "$ORIG_USER:$ORIG_USER" "$shell_rc"
        log_success "Added Go PATH to $shell_rc"
    else
        log_info "Go PATH already present in $shell_rc"
    fi
    
    # CRITICAL: Force PATH update in current installer session
    # This ensures the new Go takes precedence over any existing installation
    export PATH=/usr/local/go/bin:$PATH
    export GOPATH=$ORIG_HOME/go
    export PATH=$PATH:$GOPATH/bin
    
    log_info "Updated PATH in current session:"
    log_info "  PATH=$PATH"
    log_info "  GOPATH=$GOPATH"
    
    # Verify installation using full path first
    local installed_version=$(/usr/local/go/bin/go version 2>/dev/null | awk '{print $3}' | sed 's/go//')
    
    if [[ -z "$installed_version" ]]; then
        log_error "Go installation verification failed"
        return 1
    fi
    
    log_success "Go ${installed_version} installed successfully to /usr/local/go"
    
    # Verify which go is being used in current session
    local go_path=$(which go 2>/dev/null)
    local active_version=$(go version 2>/dev/null | awk '{print $3}' | sed 's/go//')
    log_info "Active Go binary in installer: $go_path (version: $active_version)"
    
    # Verify it meets minimum requirements
    if version_compare "$installed_version" "$min_version"; then
        log_success "Installed Go version meets minimum requirement ($min_version)"
        return 0
    else
        log_error "Installed Go version ($installed_version) still below minimum ($min_version)"
        return 1
    fi
}

install_nodejs() {
    if checkpoint_completed "$CHECKPOINT_NODEJS"; then
        log_info "Node.js already installed, skipping..."
        return 0
    fi
    
    log_info "Installing Node.js..."
    mkdir -p /etc/apt/keyrings
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --yes --dearmor -o /etc/apt/keyrings/nodesource.gpg
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list
    apt update
    apt install -y nodejs
    
    save_checkpoint "$CHECKPOINT_NODEJS"
    log_success "Node.js installed"
}

install_go_tools() {
    if checkpoint_completed "$CHECKPOINT_GO_TOOLS"; then
        log_info "Go tools already installed, skipping..."
        return 0
    fi
    
    log_info "Installing ProjectDiscovery tools..."
    
    # Create Go bin directory with proper ownership
    mkdir -p "$ORIG_HOME/go/bin"
    chown -R "$ORIG_USER:$ORIG_USER" "$ORIG_HOME/go"
    
    # CRITICAL: Dynamically locate Go binary
    # Try multiple sources in order of preference:
    # 1. Stored path from prerequisite validation (if Go was already installed)
    # 2. Current PATH (dynamic lookup)
    # 3. Manual install location (/usr/local/go/bin/go)
    local go_binary=""
    local gopath="$ORIG_HOME/go"
    
    # First: Check if we stored the path during prerequisite validation
    if [[ -n "${TOOL_BINARY_PATHS[golang]}" ]]; then
        go_binary="${TOOL_BINARY_PATHS[golang]}"
        log_info "Using Go binary from stored path: $go_binary"
    fi
    
    # Second: Try to find Go in current PATH
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
    
    # Verify we found a working Go binary
    if [[ -z "$go_binary" ]] || [[ ! -x "$go_binary" ]]; then
        log_error "Go binary not found"
        log_error "Searched locations:"
        log_error "  - Stored path: ${TOOL_BINARY_PATHS[golang]:-<not set>}"
        log_error "  - PATH lookup: $(command -v go 2>/dev/null || echo '<not found>')"
        log_error "  - Manual install: /usr/local/go/bin/go"
        log_error ""
        log_error "Go must be installed before installing Go tools"
        log_error "Installation strategy was: ${INSTALL_STRATEGY[golang]}"
        return 1
    fi
    
    # Verify the Go binary actually works
    local go_version=$("$go_binary" version 2>/dev/null | awk '{print $3}' | sed 's/go//')
    if [[ -z "$go_version" ]]; then
        log_error "Go binary at $go_binary exists but does not work"
        log_error "Cannot determine Go version"
        return 1
    fi
    
    log_success "Using Go $go_version at: $go_binary"
    
    # Install katana (requires CGO for go-tree-sitter dependency)
    if [[ ! -f "$ORIG_HOME/go/bin/katana" ]] || [[ ! -f "/usr/local/bin/katana" ]]; then
        log_info "Installing katana..."
        
        # Verify gcc is available (required for CGO)
        if ! command -v gcc &>/dev/null; then
            log_error "gcc not found - required for katana (CGO dependency)"
            log_error "Ensure build-essential package is installed"
            return 1
        fi
        
        log_info "Building katana with CGO enabled (required for go-tree-sitter)..."
        sudo -u "$ORIG_USER" bash -c "
            export CGO_ENABLED=1
            export GOPATH='$gopath'
            export GOBIN='$gopath/bin'
            '$go_binary' install github.com/projectdiscovery/katana/cmd/katana@latest
        "
        if [[ -f "$ORIG_HOME/go/bin/katana" ]]; then
            cp -f "$ORIG_HOME/go/bin/katana" /usr/local/bin/katana
            log_success "Katana installed successfully"
        else
            log_error "Katana installation failed"
        fi
    else
        log_info "Katana already installed"
    fi
    
    # Install subfinder
    if [[ ! -f "$ORIG_HOME/go/bin/subfinder" ]] || [[ ! -f "/usr/local/bin/subfinder" ]]; then
        log_info "Installing subfinder..."
        sudo -u "$ORIG_USER" bash -c "
            export GOPATH='$gopath'
            export GOBIN='$gopath/bin'
            '$go_binary' install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
        "
        if [[ -f "$ORIG_HOME/go/bin/subfinder" ]]; then
            cp -f "$ORIG_HOME/go/bin/subfinder" /usr/local/bin/subfinder
            log_success "Subfinder installed successfully"
        else
            log_error "Subfinder installation failed"
        fi
    else
        log_info "Subfinder already installed"
    fi
    
    # Install httpx
    if [[ ! -f "$ORIG_HOME/go/bin/httpx" ]] || [[ ! -f "/usr/local/bin/httpx" ]]; then
        log_info "Installing httpx..."
        sudo -u "$ORIG_USER" bash -c "
            export GOPATH='$gopath'
            export GOBIN='$gopath/bin'
            '$go_binary' install -v github.com/projectdiscovery/httpx/cmd/httpx@latest
        "
        if [[ -f "$ORIG_HOME/go/bin/httpx" ]]; then
            cp -f "$ORIG_HOME/go/bin/httpx" /usr/local/bin/httpx
            log_success "httpx installed successfully"
        else
            log_error "httpx installation failed"
        fi
    else
        log_info "httpx already installed"
    fi
    
    save_checkpoint "$CHECKPOINT_GO_TOOLS"
    log_success "Go tools installed"
}

install_geckodriver() {
    if checkpoint_completed "$CHECKPOINT_GECKO"; then
        log_info "Geckodriver already installed, skipping..."
        return 0
    fi
    
    log_info "Installing Geckodriver..."
    
    # Use jq for proper JSON parsing
    if command -v jq &>/dev/null; then
        GECKO_VERSION=$(curl -s https://api.github.com/repos/mozilla/geckodriver/releases/latest | jq -r '.tag_name')
    else
        # Fallback if jq not available (though we install it now)
        GECKO_VERSION=$(curl -s https://api.github.com/repos/mozilla/geckodriver/releases/latest | python3 -c "import sys, json; print(json.load(sys.stdin)['tag_name'])")
    fi
    
    if [[ -z "$GECKO_VERSION" ]] || [[ "$GECKO_VERSION" == "null" ]]; then
        log_error "Failed to determine Geckodriver version"
        return 1
    fi
    
    log_info "Geckodriver version: $GECKO_VERSION"
    
    wget -q "https://github.com/mozilla/geckodriver/releases/download/$GECKO_VERSION/geckodriver-$GECKO_VERSION-linux64.tar.gz"
    
    if [[ $? -ne 0 ]]; then
        log_error "Failed to download Geckodriver"
        return 1
    fi
    
    tar -xzf "geckodriver-$GECKO_VERSION-linux64.tar.gz"
    mv geckodriver /usr/local/bin/
    chmod +x /usr/local/bin/geckodriver
    rm "geckodriver-$GECKO_VERSION-linux64.tar.gz"
    
    # Verify installation
    if geckodriver --version &>/dev/null; then
        log_success "Geckodriver installed successfully"
    else
        log_warning "Geckodriver may not have installed correctly"
    fi
    
    save_checkpoint "$CHECKPOINT_GECKO"
    log_success "Geckodriver installed"
}

install_terraform() {
    if checkpoint_completed "$CHECKPOINT_TERRAFORM"; then
        log_info "Terraform already installed, skipping..."
        return 0
    fi
    
    log_info "Installing Terraform..."
    wget -4 -O - https://apt.releases.hashicorp.com/gpg | gpg --yes --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(grep -oP '(?<=UBUNTU_CODENAME=).*' /etc/os-release || lsb_release -cs) main" | tee /etc/apt/sources.list.d/hashicorp.list
    apt update && apt install -y terraform
    
    save_checkpoint "$CHECKPOINT_TERRAFORM"
    log_success "Terraform installed"
}

install_observatory() {
    if checkpoint_completed "$CHECKPOINT_OBSERVATORY"; then
        log_info "Observatory already installed, skipping..."
        return 0
    fi
    
    log_info "Installing MDN Observatory CLI tool..."
    npm install --global @mdn/mdn-http-observatory --unsafe-perm
    
    save_checkpoint "$CHECKPOINT_OBSERVATORY"
    log_success "Observatory installed"
}

install_libpango() {
    if checkpoint_completed "$CHECKPOINT_LIBPANGO"; then
        log_info "Libpango already installed, skipping..."
        return 0
    fi
    
    log_info "Installing libpango for PDF generation..."
    apt install -y libpango-1.0-0 libpangoft2-1.0-0
    
    save_checkpoint "$CHECKPOINT_LIBPANGO"
    log_success "Libpango installed"
}

install_pdf_fonts() {
    log_info "Installing fonts for PDF generation..."
    
    # Track font installation results
    local fonts_installed=0
    local fonts_failed=0
    local failed_fonts=()
    
    # Define font packages to install
    # Priority order: Essential -> Important -> Optional
    local essential_fonts=(
        "fonts-noto-core:Core Latin and common scripts"
        "fonts-noto-color-emoji:Emoji support"
    )
    
    local important_fonts=(
        "fonts-dejavu:Extended Unicode coverage"
        "fonts-dejavu-extra:Additional DejaVu fonts"
        "fonts-liberation2:Professional document fonts"
    )
    
    local optional_fonts=(
        "fonts-noto-cjk:Asian language support (CJK)"
        "fonts-symbola:Extensive symbol coverage"
    )
    
    # Function to install a single font package
    install_font_package() {
        local package_info=$1
        local package_name=$(echo "$package_info" | cut -d':' -f1)
        local package_desc=$(echo "$package_info" | cut -d':' -f2)
        
        log_info "  Installing $package_name ($package_desc)..."
        
        if apt install -y "$package_name" 2>/dev/null; then
            log_success "    ✓ $package_name installed"
            ((fonts_installed++))
            return 0
        else
            log_warning "    ✗ $package_name failed to install"
            failed_fonts+=("$package_name")
            ((fonts_failed++))
            return 1
        fi
    }
    
    # Install essential fonts
    log_info "Installing essential fonts..."
    for font in "${essential_fonts[@]}"; do
        install_font_package "$font"
    done
    
    # Install important fonts
    log_info "Installing important fonts..."
    for font in "${important_fonts[@]}"; do
        install_font_package "$font"
    done
    
    # Install optional fonts (continue even if these fail)
    log_info "Installing optional fonts..."
    for font in "${optional_fonts[@]}"; do
        install_font_package "$font" || true  # Don't fail if optional fonts fail
    done
    
    # Update font cache
    log_info "Updating font cache..."
    if fc-cache -f -v >/dev/null 2>&1; then
        log_success "Font cache updated"
    else
        log_warning "Font cache update failed (non-critical)"
    fi
    
    # Display summary
    echo ""
    log_info "Font Installation Summary:"
    log_info "  Fonts installed: $fonts_installed"
    if [[ $fonts_failed -gt 0 ]]; then
        log_warning "  Fonts failed: $fonts_failed"
        log_warning "  Failed packages: ${failed_fonts[*]}"
        echo ""
        log_warning "Some fonts failed to install. This may impact PDF report rendering"
        log_warning "of special characters, emojis, and international text."
        log_warning "PDF reports will still be generated but may show rectangles (□)"
        log_warning "for unsupported characters."
        echo ""
    else
        log_success "  All fonts installed successfully"
    fi
    
    log_success "PDF fonts installation complete"
}

copy_project_files() {
    if checkpoint_completed "$CHECKPOINT_FILES"; then
        log_info "Project files already copied, skipping..."
        return 0
    fi
    
    log_info "Copying project files to $INSTALL_DIR..."
    mkdir -p "$INSTALL_DIR"
    
    echo "Skipping $(basename "$0")"
    echo "Skipping .git"
    
    rsync -av --exclude="$(basename "$0")" --exclude=".git" --exclude="*.backup.*" ./ "$INSTALL_DIR/"
    
    save_checkpoint "$CHECKPOINT_FILES"
    log_success "Project files copied"
}

setup_python_venv() {
    if checkpoint_completed "$CHECKPOINT_VENV"; then
        log_info "Python virtual environment already set up, skipping..."
        return 0
    fi
    
    log_info "Creating Python virtual environment..."
    python3 -m venv "$INSTALL_DIR/venv"
    
    # Create requirements.txt if it doesn't exist
    if [ ! -f "$INSTALL_DIR/requirements.txt" ]; then
        echo "# KAST requirements" > "$INSTALL_DIR/requirements.txt"
    fi
    
    log_info "Installing Python dependencies..."
    "$INSTALL_DIR/venv/bin/pip" install --upgrade pip
    "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
    
    save_checkpoint "$CHECKPOINT_VENV"
    log_success "Python environment configured"
}

install_ftap() {
    if checkpoint_completed "$CHECKPOINT_FTAP"; then
        log_info "FTAP already installed, skipping..."
        return 0
    fi
    
    log_info "Installing custom FTAP..."
    cd "$ORIG_HOME"
    
    if [[ -d "$ORIG_HOME/ftap" ]]; then
        log_warning "FTAP directory already exists, updating..."
        cd ftap
        sudo -u "$ORIG_USER" git pull
    else
        sudo -u "$ORIG_USER" git clone https://github.com/mercutioviz/ftap
        chown -R "$ORIG_USER:$ORIG_USER" ftap
    fi
    
    save_checkpoint "$CHECKPOINT_FTAP"
    log_success "FTAP installed"
}

create_launcher_scripts() {
    if checkpoint_completed "$CHECKPOINT_LAUNCHERS"; then
        log_info "Launcher scripts already created, skipping..."
        return 0
    fi
    
    log_info "Creating launcher script at /usr/local/bin/kast..."
    cat > /usr/local/bin/kast <<EOF
#!/bin/bash
KAST_DIR="$INSTALL_DIR"
source "\$KAST_DIR/venv/bin/activate"
cd "\$KAST_DIR"
python -m kast.main "\$@"
EOF
    
    log_info "Creating launcher script at /usr/local/bin/ftap..."
    cat > /usr/local/bin/ftap <<EOF
#!/bin/bash
FTAP_DIR="$ORIG_HOME/ftap"
KAST_DIR="$INSTALL_DIR"
source "\$KAST_DIR/venv/bin/activate"
cd "\$FTAP_DIR"
python finder.py "\$@"
EOF
    
    chmod +x /usr/local/bin/kast
    chmod +x /usr/local/bin/ftap
    
    save_checkpoint "$CHECKPOINT_LAUNCHERS"
    log_success "Launcher scripts created"
}

finalize_installation() {
    log_info "Finalizing installation..."
    
    # Create default target log directory
    mkdir -p /var/log/kast
    chown "$ORIG_USER:$ORIG_USER" /var/log/kast
    
    # Save version
    echo "$SCRIPT_VERSION" > "$INSTALL_DIR/$VERSION_FILE"
    
    # Mark installation as complete
    save_checkpoint "$CHECKPOINT_COMPLETE"
    
    log_success "Installation complete!"
}

###############################################################################
# POST-INSTALL VERIFICATION
###############################################################################

verify_installation() {
    log_info "Verifying installation..."
    local failed=0
    local os_id=$(detect_os)
    
    # Check if launcher scripts exist and are executable
    if [[ ! -x /usr/local/bin/kast ]]; then
        log_error "KAST launcher script not found or not executable"
        ((failed++))
    fi
    
    if [[ ! -x /usr/local/bin/ftap ]]; then
        log_error "FTAP launcher script not found or not executable"
        ((failed++))
    fi
    
    # Check if Python venv exists
    if [[ ! -f "$INSTALL_DIR/venv/bin/python" ]]; then
        log_error "Python virtual environment not found"
        ((failed++))
    fi
    
    # Check if key Go tools are accessible
    if ! command -v katana &>/dev/null; then
        log_warning "Katana not found in PATH"
        ((failed++))
    fi
    
    if ! command -v subfinder &>/dev/null; then
        log_warning "Subfinder not found in PATH"
        ((failed++))
    fi
    
    if ! command -v httpx &>/dev/null; then
        log_warning "httpx not found in PATH"
        ((failed++))
    fi
    
    # Check OS-specific tools
    # Firefox check - optional on Ubuntu (uses snap)
    if [[ "$os_id" != "ubuntu" ]]; then
        if ! command -v firefox &>/dev/null && ! command -v firefox-esr &>/dev/null; then
            log_warning "firefox not found in PATH"
            ((failed++))
        fi
    fi
    
    # Check other tools
    if ! command -v geckodriver &>/dev/null; then
        log_warning "geckodriver not found in PATH"
        ((failed++))
    fi
    
    if ! command -v terraform &>/dev/null; then
        log_warning "terraform not found in PATH"
        ((failed++))
    fi
    
    # testssl.sh has different command names on different systems
    if ! command -v testssl.sh &>/dev/null && ! command -v testssl &>/dev/null; then
        log_warning "testssl not found in PATH"
        ((failed++))
    fi
    
    if ! command -v whatweb &>/dev/null; then
        log_warning "whatweb not found in PATH"
        ((failed++))
    fi
    
    if [[ $failed -eq 0 ]]; then
        log_success "All verification checks passed!"
        return 0
    else
        log_warning "Installation completed with $failed warnings"
        return 1
    fi
}

###############################################################################
# TOOLS-ONLY MODE FUNCTION
###############################################################################

check_and_install_tools() {
    log_info "Running external tools check and installation..."
    echo ""
    
    # Validate prerequisites (determines installation strategies)
    validate_prerequisites
    
    # Track what gets installed
    local tools_installed=0
    local tools_skipped=0
    
    echo ""
    echo "======================================================================"
    echo "  Installing Missing Tools"
    echo "======================================================================"
    echo ""
    
    # Check and install Go if needed
    if [[ "${INSTALL_STRATEGY[golang]}" == "USE_MANUAL" ]]; then
        log_info "Installing Go (manual installation required)..."
        if install_golang_manual; then
            ((tools_installed++))
        fi
    elif [[ "${INSTALL_STRATEGY[golang]}" == "SKIP_ALREADY_INSTALLED" ]]; then
        log_info "✓ Go already installed with sufficient version"
        ((tools_skipped++))
    elif [[ "${INSTALL_STRATEGY[golang]}" == "USE_APT" ]]; then
        log_info "Installing Go from APT..."
        if apt install -y golang; then
            ((tools_installed++))
        fi
    fi
    
    # Install Go tools (katana, subfinder, httpx)
    if install_go_tools; then
        ((tools_installed++))
    fi
    
    # Check and install Node.js if needed
    if [[ "${INSTALL_STRATEGY[nodejs]}" == "USE_MANUAL" ]]; then
        log_info "Installing Node.js..."
        if install_nodejs; then
            ((tools_installed++))
        fi
    elif [[ "${INSTALL_STRATEGY[nodejs]}" == "SKIP_ALREADY_INSTALLED" ]]; then
        log_info "✓ Node.js already installed with sufficient version"
        ((tools_skipped++))
    elif [[ "${INSTALL_STRATEGY[nodejs]}" == "USE_APT" ]]; then
        log_info "Installing Node.js from APT..."
        if apt install -y nodejs; then
            ((tools_installed++))
        fi
    fi
    
    # Install Observatory (requires Node.js)
    if ! command -v observatory &>/dev/null; then
        log_info "Installing Observatory..."
        if install_observatory; then
            ((tools_installed++))
        fi
    else
        log_info "✓ Observatory already installed"
        ((tools_skipped++))
    fi
    
    # Install Geckodriver
    if ! command -v geckodriver &>/dev/null; then
        log_info "Installing Geckodriver..."
        if install_geckodriver; then
            ((tools_installed++))
        fi
    else
        log_info "✓ Geckodriver already installed"
        ((tools_skipped++))
    fi
    
    echo ""
    echo "======================================================================"
    echo "  Tools Check Summary"
    echo "======================================================================"
    echo ""
    log_success "Tools check complete"
    log_info "  Tools installed/updated: $tools_installed"
    log_info "  Tools already present: $tools_skipped"
    echo ""
}

###############################################################################
# USER INTERACTION FUNCTIONS
###############################################################################

show_usage() {
    cat <<EOF
Usage: sudo ./install.sh [OPTIONS]

Install KAST and all required dependencies.

OPTIONS:
    --check-tools, --tools-only
                        Check and install only external tools (safe for
                        existing installations). Skips Python venv, file
                        copying, and launcher scripts.
    --auto             Non-interactive mode (auto-accept defaults)
    --install-dir <path>
                        Installation directory (default: /opt/kast)
    -h, --help         Show this help message

EXAMPLES:
    # Normal installation
    sudo ./install.sh

    # Check and install missing tools only
    sudo ./install.sh --check-tools

    # Automated tools check (for scripts)
    sudo ./install.sh --check-tools --auto --install-dir /opt/kast

For full documentation, see the KAST documentation.
EOF
}

prompt_user_choice() {
    local prompt=$1
    shift
    local options=("$@")
    
    echo "" >&2
    echo "$prompt" >&2
    for i in "${!options[@]}"; do
        echo "  $((i+1)). ${options[$i]}" >&2
    done
    echo "" >&2
    
    while true; do
        read -p "Enter your choice [1-${#options[@]}]: " choice
        if [[ "$choice" =~ ^[0-9]+$ ]] && [[ $choice -ge 1 ]] && [[ $choice -le ${#options[@]} ]]; then
            echo $((choice - 1))
            return 0
        else
            echo "Invalid choice. Please enter a number between 1 and ${#options[@]}." >&2
        fi
    done
}

handle_fresh_install() {
    log_info "Performing fresh installation..."
    save_checkpoint "$CHECKPOINT_INIT"
    return 0
}

handle_aborted_install() {
    local last_checkpoint=$(get_last_checkpoint)
    log_warning "Detected aborted installation. Last checkpoint: $last_checkpoint"
    
    echo ""
    echo -e "${YELLOW}Previous installation was interrupted.${NC}"
    echo "Last completed step: $last_checkpoint"
    echo ""
    
    local choice=$(prompt_user_choice "How would you like to proceed?" \
        "Resume from last checkpoint" \
        "Start fresh (clean install)" \
        "Exit installer")
    
    case $choice in
        0)
            log_info "Resuming installation from checkpoint: $last_checkpoint"
            return 0
            ;;
        1)
            log_info "Starting fresh installation..."
            rm -f "$INSTALL_DIR/$INSTALL_STATE_FILE"
            save_checkpoint "$CHECKPOINT_INIT"
            return 0
            ;;
        2)
            log_info "Installation cancelled by user"
            exit 0
            ;;
    esac
}

handle_same_version() {
    log_warning "KAST version $SCRIPT_VERSION is already installed"
    
    echo ""
    echo -e "${YELLOW}KAST version $SCRIPT_VERSION is already installed.${NC}"
    echo ""
    
    local choice=$(prompt_user_choice "How would you like to proceed?" \
        "Reinstall (overwrite existing)" \
        "Repair installation" \
        "Exit installer")
    
    case $choice in
        0)
            log_info "Reinstalling KAST..."
            create_backup
            rm -f "$INSTALL_DIR/$INSTALL_STATE_FILE"
            save_checkpoint "$CHECKPOINT_INIT"
            return 0
            ;;
        1)
            log_info "Repairing installation..."
            # Start from file copy to repair
            echo "$CHECKPOINT_LIBPANGO" > "$INSTALL_DIR/$INSTALL_STATE_FILE"
            return 0
            ;;
        2)
            log_info "Installation cancelled by user"
            exit 0
            ;;
    esac
}

handle_older_version() {
    local installed_version=$(cat "$INSTALL_DIR/$VERSION_FILE")
    log_warning "Detected older version: $installed_version (current: $SCRIPT_VERSION)"
    
    echo ""
    echo -e "${YELLOW}Upgrade Available${NC}"
    echo "Installed version: $installed_version"
    echo "New version: $SCRIPT_VERSION"
    echo ""
    
    local choice=$(prompt_user_choice "How would you like to proceed?" \
        "Upgrade (recommended)" \
        "Clean install" \
        "Exit installer")
    
    case $choice in
        0)
            log_info "Upgrading KAST..."
            create_backup
            # Preserve state but allow reinstallation of components
            rm -f "$INSTALL_DIR/$INSTALL_STATE_FILE"
            save_checkpoint "$CHECKPOINT_INIT"
            return 0
            ;;
        1)
            log_info "Performing clean installation..."
            create_backup
            rm -rf "$INSTALL_DIR"
            mkdir -p "$INSTALL_DIR"
            save_checkpoint "$CHECKPOINT_INIT"
            return 0
            ;;
        2)
            log_info "Installation cancelled by user"
            exit 0
            ;;
    esac
}

handle_partial_install() {
    log_warning "Detected partial installation (no version info)"
    
    echo ""
    echo -e "${YELLOW}Partial installation detected.${NC}"
    echo "KAST directory exists but installation appears incomplete."
    echo ""
    
    local choice=$(prompt_user_choice "How would you like to proceed?" \
        "Complete installation" \
        "Start fresh (clean install)" \
        "Exit installer")
    
    case $choice in
        0)
            log_info "Completing installation..."
            save_checkpoint "$CHECKPOINT_INIT"
            return 0
            ;;
        1)
            log_info "Starting fresh installation..."
            create_backup
            rm -rf "$INSTALL_DIR"
            mkdir -p "$INSTALL_DIR"
            save_checkpoint "$CHECKPOINT_INIT"
            return 0
            ;;
        2)
            log_info "Installation cancelled by user"
            exit 0
            ;;
    esac
}

###############################################################################
# MAIN EXECUTION
###############################################################################

main() {
    # Parse command-line arguments first
    while [[ $# -gt 0 ]]; do
        case $1 in
            --check-tools|--tools-only)
                TOOLS_ONLY_MODE=true
                shift
                ;;
            --auto)
                AUTO_MODE=true
                shift
                ;;
            --install-dir)
                INSTALL_DIR="$2"
                shift 2
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
    
    # Validate root
    validate_root
    
    # Create log directory early
    mkdir -p "$LOG_DIR"
    
    # Capture original user and home directory
    ORIG_USER=${SUDO_USER:-$USER}
    ORIG_HOME=$(getent passwd "$ORIG_USER" | cut -d: -f6)
    
    # Handle tools-only mode
    if [[ "$TOOLS_ONLY_MODE" == true ]]; then
        echo ""
        echo "======================================================================"
        echo "  KAST External Tools Check Mode"
        echo "======================================================================"
        echo ""
        
        # Use existing installation directory or default
        INSTALL_DIR=${INSTALL_DIR:-/opt/kast}
        
        log_info "Checking and installing external tools..."
        log_info "Installation started by user: $ORIG_USER"
        
        check_and_install_tools
        exit 0
    fi
    
    # Display banner
    if [[ -f "assets/mascot.ans" ]]; then
        cat assets/mascot.ans
    fi
    
    echo ""
    echo "======================================================================"
    echo "  KAST Installer v${SCRIPT_VERSION}"
    echo "  Kali Automated Scan Tool"
    echo "======================================================================"
    echo ""
    echo "This installer will set up KAST on your system."
    echo "KAST works best on a fresh Debian or Kali instance."
    echo ""
    
    # Create log directory early for OS validation logging
    mkdir -p "$LOG_DIR"
    
    # Validate OS compatibility before proceeding
    echo ""
    echo "======================================================================"
    echo "  System Compatibility Check"
    echo "======================================================================"
    echo ""
    
    if ! validate_os_support; then
        log_error "OS validation failed. Installation cannot proceed."
        echo ""
        echo "Installation aborted due to unsupported operating system."
        exit 1
    fi
    
    echo ""
    
    # Capture original user and home directory
    ORIG_USER=${SUDO_USER:-$USER}
    ORIG_HOME=$(getent passwd "$ORIG_USER" | cut -d: -f6)
    
    log_info "Installation started by user: $ORIG_USER"
    log_info "User home directory: $ORIG_HOME"
    
    # Validate user and home
    if ! validate_user_home "$ORIG_USER" "$ORIG_HOME"; then
        log_error "User validation failed. Cannot proceed."
        exit 1
    fi
    
    # Check for concurrent installations
    if [[ -f "$LOCK_FILE" ]]; then
        log_error "Another installation is already in progress (lock file exists)"
        log_error "If this is an error, remove $LOCK_FILE and try again"
        exit 1
    fi
    
    # Create lock file
    touch "$LOCK_FILE"
    
    # Create log directory
    mkdir -p "$LOG_DIR"
    
    # Get installation directory
    read -p "Enter install directory [/opt/kast]: " INSTALL_DIR
    INSTALL_DIR=${INSTALL_DIR:-/opt/kast}
    
    log_info "Target installation directory: $INSTALL_DIR"
    
    # Check installation state
    local state=$(check_installation_state)
    log_info "Installation state: $state"
    
    # Handle different installation states
    case $state in
        FRESH)
            handle_fresh_install
            ;;
        ABORTED)
            handle_aborted_install
            ;;
        SAME_VERSION)
            handle_same_version
            ;;
        OLDER_VERSION)
            handle_older_version
            ;;
        PARTIAL|COMPLETE_NO_VERSION)
            handle_partial_install
            ;;
        *)
            log_error "Unknown installation state: $state"
            exit 1
            ;;
    esac
    
    echo ""
    echo "======================================================================"
    echo "  Beginning Installation"
    echo "======================================================================"
    echo ""
    
    # Validate prerequisites before installation
    validate_prerequisites
    
    # Execute installation steps
    install_system_packages
    
    # Debug: Check what strategies were determined
    log_info "DEBUG: Checking installation strategies..."
    log_info "DEBUG: golang strategy = '${INSTALL_STRATEGY[golang]}'"
    log_info "DEBUG: java strategy = '${INSTALL_STRATEGY[java]}'"
    log_info "DEBUG: nodejs strategy = '${INSTALL_STRATEGY[nodejs]}'"
    
    # Check if Go needs manual installation before installing Go tools
    if [[ "${INSTALL_STRATEGY[golang]}" == "USE_MANUAL" ]]; then
        log_info "Go requires manual installation (APT version insufficient)"
        install_golang_manual
    else
        log_info "Go installation strategy is '${INSTALL_STRATEGY[golang]}', skipping manual install"
    fi
    
    install_nodejs
    install_go_tools
    install_geckodriver
    install_terraform
    install_observatory
    install_libpango
    install_pdf_fonts
    copy_project_files
    setup_python_venv
    install_ftap
    create_launcher_scripts
    finalize_installation
    
    # Verify installation
    echo ""
    echo "======================================================================"
    echo "  Verifying Installation"
    echo "======================================================================"
    echo ""
    
    verify_installation
    
    echo ""
    echo "======================================================================"
    echo "  Installation Complete!"
    echo "======================================================================"
    echo ""
    echo "KAST has been installed to: $INSTALL_DIR"
    echo "Version: $SCRIPT_VERSION"
    echo ""
    
    # Check if Go was manually installed
    if [[ "${INSTALL_STRATEGY[golang]}" == "USE_MANUAL" ]]; then
        echo -e "${YELLOW}IMPORTANT: Go was installed/updated during this installation.${NC}"
        echo -e "${YELLOW}To use the new Go version, you must reload your shell:${NC}"
        echo ""
        echo "  Option 1: Start a new terminal session"
        echo "  Option 2: Run: source ~/.bashrc (or source ~/.zshrc)"
        echo "  Option 3: Run: exec \$SHELL"
        echo ""
        echo "After reloading, verify with:"
        echo "  go version     # Should show 1.24.1"
        echo "  which go       # Should show /usr/local/go/bin/go"
        echo ""
    fi
    
    echo "Quick Start:"
    echo "  - Run 'kast --help' to see available options"
    echo "  - Run 'ftap --help' for FTAP usage"
    echo "  - Logs are stored in: /var/log/kast/"
    echo "  - Installation log: $INSTALL_LOG"
    echo ""
    
    if [[ -n "$(find /opt -maxdepth 1 -name 'kast.backup.*' 2>/dev/null)" ]]; then
        echo "Backup(s) created:"
        find /opt -maxdepth 1 -name 'kast.backup.*' -type d | sed 's/^/  - /'
        echo ""
    fi
    
    log_success "KAST installation completed successfully!"
}

# Run main function
main "$@"
