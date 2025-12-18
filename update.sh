#!/bin/bash

# KAST Update Script
# Safely updates an existing KAST installation from git repository changes

###############################################################################
# CONSTANTS AND CONFIGURATION
###############################################################################

SCRIPT_VERSION="1.0.0"
UPDATE_STATE_FILE=".kast_update_state"
VERSION_FILE=".kast_version"
LOCK_FILE="/tmp/kast_update.lock"
LOG_DIR="/var/log/kast"
UPDATE_LOG="$LOG_DIR/update.log"
BACKUP_PREFIX="/opt/kast.backup"
BACKUP_INVENTORY="$LOG_DIR/backup_inventory.json"
MAX_BACKUPS=5

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Update checkpoints
CHECKPOINT_INIT="initialization"
CHECKPOINT_VALIDATION="pre_update_validation"
CHECKPOINT_BACKUP="backup_created"
CHECKPOINT_GIT_PULL="git_updated"
CHECKPOINT_PIP_UPDATE="dependencies_updated"
CHECKPOINT_FILE_SYNC="files_synchronized"
CHECKPOINT_POST_VALIDATION="post_update_validation"
CHECKPOINT_COMPLETE="update_complete"

# Files to preserve during update (user configurations)
PRESERVE_FILES=(
    "kast_default.yaml"
    "resume.cfg"
    ".kast_custom_config"
)

# Files to exclude from sync (generated or temporary)
EXCLUDE_PATTERNS=(
    ".git"
    ".gitignore"
    "*.pyc"
    "__pycache__"
    "*.backup.*"
    "update.sh"
    "install.sh"
    ".kast_update_state"
)

###############################################################################
# GLOBAL VARIABLES
###############################################################################

INSTALL_DIR=""
GIT_DIR=""
CURRENT_VERSION=""
NEW_VERSION=""
BACKUP_DIR=""
AUTO_MODE=false
FORCE_MODE=false
DRY_RUN=false
ROLLBACK_ID=""
LIST_BACKUPS=false

###############################################################################
# LOGGING AND OUTPUT FUNCTIONS
###############################################################################

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$UPDATE_LOG"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" | tee -a "$UPDATE_LOG"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*" | tee -a "$UPDATE_LOG"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*" | tee -a "$UPDATE_LOG"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $*" | tee -a "$UPDATE_LOG"
}

log_debug() {
    echo -e "${CYAN}[DEBUG]${NC} $*" | tee -a "$UPDATE_LOG"
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
    log_error "Update failed at line $line_number with exit code $exit_code"
    
    if [[ -n "$INSTALL_DIR" ]] && [[ -f "$INSTALL_DIR/$UPDATE_STATE_FILE" ]]; then
        echo "FAILED" > "$INSTALL_DIR/$UPDATE_STATE_FILE"
        log_warning "Update state saved as FAILED"
    fi
    
    # Offer rollback if backup exists
    if [[ -n "$BACKUP_DIR" ]] && [[ -d "$BACKUP_DIR" ]]; then
        log_error "Update failed but backup exists at: $BACKUP_DIR"
        if [[ "$AUTO_MODE" == false ]]; then
            echo ""
            read -p "Would you like to rollback to the backup? [Y/n]: " rollback_choice
            rollback_choice=${rollback_choice:-Y}
            if [[ "$rollback_choice" =~ ^[Yy]$ ]]; then
                perform_rollback "$BACKUP_DIR"
                exit 0
            fi
        fi
    fi
    
    cleanup
    exit $exit_code
}

handle_interrupt() {
    log_warning "Update interrupted by user"
    if [[ -n "$INSTALL_DIR" ]] && [[ -f "$INSTALL_DIR/$UPDATE_STATE_FILE" ]]; then
        echo "INTERRUPTED" > "$INSTALL_DIR/$UPDATE_STATE_FILE"
    fi
    cleanup
    exit 130
}

# Set up traps
trap 'handle_error ${LINENO}' ERR
trap 'handle_interrupt' INT TERM
trap 'cleanup' EXIT

###############################################################################
# VERSION COMPARISON FUNCTIONS
###############################################################################

version_compare() {
    local version1=$1
    local version2=$2
    
    # Handle empty versions
    if [[ -z "$version1" ]] || [[ -z "$version2" ]]; then
        return 1
    fi
    
    # Normalize versions by removing leading 'v'
    version1=$(echo "$version1" | sed 's/^v//')
    version2=$(echo "$version2" | sed 's/^v//')
    
    # Split versions into arrays
    IFS='.' read -ra v1_parts <<< "$version1"
    IFS='.' read -ra v2_parts <<< "$version2"
    
    # Compare each part
    local max_parts=${#v1_parts[@]}
    [[ ${#v2_parts[@]} -gt $max_parts ]] && max_parts=${#v2_parts[@]}
    
    for ((i=0; i<max_parts; i++)); do
        local part1=${v1_parts[$i]:-0}
        local part2=${v2_parts[$i]:-0}
        
        if [[ $part1 -gt $part2 ]]; then
            return 0  # v1 > v2
        elif [[ $part1 -lt $part2 ]]; then
            return 1  # v1 < v2
        fi
    done
    
    # Versions are equal
    return 0
}

get_update_type() {
    local current=$1
    local new=$2
    
    # Remove 'v' prefix if present
    current=$(echo "$current" | sed 's/^v//')
    new=$(echo "$new" | sed 's/^v//')
    
    IFS='.' read -ra curr_parts <<< "$current"
    IFS='.' read -ra new_parts <<< "$new"
    
    local curr_major=${curr_parts[0]:-0}
    local curr_minor=${curr_parts[1]:-0}
    local curr_patch=${curr_parts[2]:-0}
    
    local new_major=${new_parts[0]:-0}
    local new_minor=${new_parts[1]:-0}
    local new_patch=${new_parts[2]:-0}
    
    if [[ $new_major -gt $curr_major ]]; then
        echo "major"
    elif [[ $new_minor -gt $curr_minor ]]; then
        echo "minor"
    elif [[ $new_patch -gt $curr_patch ]]; then
        echo "patch"
    else
        echo "none"
    fi
}

###############################################################################
# STATE MANAGEMENT FUNCTIONS
###############################################################################

save_checkpoint() {
    local checkpoint=$1
    if [[ -n "$INSTALL_DIR" ]] && [[ -d "$INSTALL_DIR" ]]; then
        echo "$checkpoint" > "$INSTALL_DIR/$UPDATE_STATE_FILE"
        log_info "Checkpoint saved: $checkpoint"
    fi
}

get_last_checkpoint() {
    if [[ -f "$INSTALL_DIR/$UPDATE_STATE_FILE" ]]; then
        cat "$INSTALL_DIR/$UPDATE_STATE_FILE"
    else
        echo ""
    fi
}

###############################################################################
# BACKUP MANAGEMENT FUNCTIONS
###############################################################################

create_backup() {
    local timestamp=$(date +%Y%m%d_%H%M%S)
    BACKUP_DIR="${BACKUP_PREFIX}.${timestamp}"
    
    log_info "Creating backup at $BACKUP_DIR..."
    
    # Check disk space
    local install_size=$(du -sb "$INSTALL_DIR" 2>/dev/null | awk '{print $1}')
    local available_space=$(df -B1 /opt 2>/dev/null | awk 'NR==2 {print $4}')
    
    if [[ $install_size -gt 0 ]] && [[ $available_space -gt 0 ]]; then
        local required_space=$((install_size * 2))
        if [[ $available_space -lt $required_space ]]; then
            log_error "Insufficient disk space for backup"
            log_error "Required: $(numfmt --to=iec $required_space), Available: $(numfmt --to=iec $available_space)"
            return 1
        fi
    fi
    
    # Create backup using rsync for efficiency
    rsync -a --delete "$INSTALL_DIR/" "$BACKUP_DIR/"
    
    if [[ ! -d "$BACKUP_DIR" ]]; then
        log_error "Failed to create backup"
        return 1
    fi
    
    # Count files in backup
    local file_count=$(find "$BACKUP_DIR" -type f | wc -l)
    local backup_size=$(du -sh "$BACKUP_DIR" 2>/dev/null | awk '{print $1}')
    
    log_success "Backup created successfully: $file_count files, $backup_size"
    
    # Update backup inventory
    update_backup_inventory "$timestamp" "$CURRENT_VERSION"
    
    # Clean up old backups
    cleanup_old_backups
    
    return 0
}

update_backup_inventory() {
    local timestamp=$1
    local version=$2
    
    # Create inventory file if it doesn't exist
    if [[ ! -f "$BACKUP_INVENTORY" ]]; then
        echo "[]" > "$BACKUP_INVENTORY"
    fi
    
    # Add new backup entry
    local new_entry=$(cat <<EOF
{
  "timestamp": "$timestamp",
  "version": "$version",
  "path": "${BACKUP_PREFIX}.${timestamp}",
  "created": "$(date -Iseconds)",
  "size": "$(du -sb "${BACKUP_PREFIX}.${timestamp}" 2>/dev/null | awk '{print $1}')"
}
EOF
)
    
    # Update JSON inventory
    python3 -c "
import json
import sys

try:
    with open('$BACKUP_INVENTORY', 'r') as f:
        inventory = json.load(f)
    
    inventory.append($new_entry)
    
    with open('$BACKUP_INVENTORY', 'w') as f:
        json.dump(inventory, f, indent=2)
except Exception as e:
    print(f'Warning: Could not update backup inventory: {e}', file=sys.stderr)
" || log_warning "Could not update backup inventory"
}

cleanup_old_backups() {
    log_info "Checking for old backups to clean up..."
    
    # Get list of backups sorted by date (oldest first)
    local backups=($(find /opt -maxdepth 1 -type d -name "kast.backup.*" | sort))
    local backup_count=${#backups[@]}
    
    if [[ $backup_count -gt $MAX_BACKUPS ]]; then
        local to_remove=$((backup_count - MAX_BACKUPS))
        log_info "Removing $to_remove old backup(s) (keeping last $MAX_BACKUPS)"
        
        for ((i=0; i<to_remove; i++)); do
            local old_backup="${backups[$i]}"
            log_info "  Removing: $old_backup"
            rm -rf "$old_backup"
        done
        
        log_success "Cleaned up $to_remove old backup(s)"
    else
        log_info "No cleanup needed (${backup_count}/${MAX_BACKUPS} backups)"
    fi
}

list_available_backups() {
    echo ""
    echo "======================================================================"
    echo "  Available Backups"
    echo "======================================================================"
    echo ""
    
    if [[ ! -f "$BACKUP_INVENTORY" ]]; then
        echo "No backup inventory found."
        return
    fi
    
    python3 -c "
import json
import os
from datetime import datetime

try:
    with open('$BACKUP_INVENTORY', 'r') as f:
        inventory = json.load(f)
    
    if not inventory:
        print('No backups found in inventory.')
        return
    
    # Sort by timestamp (newest first)
    inventory.sort(key=lambda x: x['timestamp'], reverse=True)
    
    print(f'{'Timestamp':<20} {'Version':<12} {'Size':<12} {'Status':<10}')
    print('-' * 70)
    
    for backup in inventory:
        timestamp = backup['timestamp']
        version = backup['version']
        path = backup['path']
        size_bytes = int(backup.get('size', 0))
        size_mb = size_bytes / (1024 * 1024)
        
        # Check if backup still exists
        status = 'Available' if os.path.exists(path) else 'Missing'
        
        print(f'{timestamp:<20} {version:<12} {size_mb:>8.1f} MB   {status:<10}')
    
    print()
    print('To rollback to a backup, run:')
    print('  sudo ./update.sh --rollback <timestamp>')
    print()

except Exception as e:
    print(f'Error reading backup inventory: {e}')
"
}

perform_rollback() {
    local backup_path=$1
    
    log_warning "Initiating rollback to: $backup_path"
    
    if [[ ! -d "$backup_path" ]]; then
        log_error "Backup directory not found: $backup_path"
        return 1
    fi
    
    # Verify backup is readable
    if [[ ! -r "$backup_path" ]]; then
        log_error "Backup directory is not readable"
        return 1
    fi
    
    # Get version from backup
    local backup_version=""
    if [[ -f "$backup_path/$VERSION_FILE" ]]; then
        backup_version=$(cat "$backup_path/$VERSION_FILE")
    fi
    
    echo ""
    echo "======================================================================"
    echo "  Rollback Confirmation"
    echo "======================================================================"
    echo ""
    echo "Current installation: $INSTALL_DIR"
    echo "Rollback to: $backup_path"
    echo "Target version: ${backup_version:-Unknown}"
    echo ""
    
    if [[ "$AUTO_MODE" == false ]]; then
        read -p "Proceed with rollback? [y/N]: " confirm
        if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
            log_info "Rollback cancelled by user"
            return 1
        fi
    fi
    
    log_info "Starting rollback process..."
    
    # Create a backup of current state before rollback
    local pre_rollback_backup="${BACKUP_PREFIX}.pre_rollback_$(date +%Y%m%d_%H%M%S)"
    log_info "Creating safety backup: $pre_rollback_backup"
    rsync -a "$INSTALL_DIR/" "$pre_rollback_backup/"
    
    # Perform rollback
    log_info "Restoring from backup..."
    rsync -a --delete "$backup_path/" "$INSTALL_DIR/"
    
    # Verify rollback
    if [[ $? -eq 0 ]]; then
        log_success "Files restored successfully"
        
        # Verify version
        if [[ -f "$INSTALL_DIR/$VERSION_FILE" ]]; then
            local restored_version=$(cat "$INSTALL_DIR/$VERSION_FILE")
            log_success "Restored to version: $restored_version"
        fi
        
        # Run post-validation
        log_info "Validating restored installation..."
        if validate_installation "post_rollback"; then
            log_success "Rollback completed successfully"
            
            # Clean up pre-rollback backup if successful
            rm -rf "$pre_rollback_backup"
            
            return 0
        else
            log_error "Validation failed after rollback"
            log_warning "Pre-rollback backup available at: $pre_rollback_backup"
            return 1
        fi
    else
        log_error "Failed to restore files"
        log_warning "Pre-rollback backup available at: $pre_rollback_backup"
        return 1
    fi
}

###############################################################################
# VALIDATION FUNCTIONS
###############################################################################

validate_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

validate_installation_exists() {
    log_info "Validating installation directory..."
    
    if [[ ! -d "$INSTALL_DIR" ]]; then
        log_error "Installation directory not found: $INSTALL_DIR"
        return 1
    fi
    
    if [[ ! -f "$INSTALL_DIR/$VERSION_FILE" ]]; then
        log_error "Version file not found. Is this a valid KAST installation?"
        return 1
    fi
    
    CURRENT_VERSION=$(cat "$INSTALL_DIR/$VERSION_FILE")
    log_success "Found KAST installation v$CURRENT_VERSION at $INSTALL_DIR"
    
    return 0
}

validate_git_repository() {
    log_info "Validating git repository..."
    
    if [[ ! -d "$GIT_DIR/.git" ]]; then
        log_error "Not a git repository: $GIT_DIR"
        return 1
    fi
    
    cd "$GIT_DIR"
    
    # Check for uncommitted changes
    if [[ -n $(git status --porcelain) ]]; then
        log_warning "Git repository has uncommitted changes:"
        git status --short
        
        if [[ "$FORCE_MODE" == false ]] && [[ "$AUTO_MODE" == false ]]; then
            echo ""
            read -p "Continue anyway? [y/N]: " continue_choice
            if [[ ! "$continue_choice" =~ ^[Yy]$ ]]; then
                log_info "Update cancelled by user"
                exit 0
            fi
        fi
    fi
    
    # Get version from kast/main.py (single source of truth)
    if [[ -f "$GIT_DIR/kast/main.py" ]]; then
        NEW_VERSION=$(grep "^KAST_VERSION = " "$GIT_DIR/kast/main.py" | cut -d'"' -f2)
    else
        log_warning "Could not determine new version from git repository"
        NEW_VERSION="unknown"
    fi
    
    log_success "Git repository validated"
    
    return 0
}

validate_installation() {
    local context=${1:-"update"}
    log_info "Validating KAST installation ($context)..."
    
    local failed=0
    
    # Check if launcher scripts exist and are executable
    if [[ ! -x /usr/local/bin/kast ]]; then
        log_error "KAST launcher script not found or not executable"
        ((failed++))
    else
        log_success "✓ KAST launcher script"
    fi
    
    # Check if Python venv exists
    if [[ ! -f "$INSTALL_DIR/venv/bin/python" ]]; then
        log_error "Python virtual environment not found"
        ((failed++))
    else
        log_success "✓ Python virtual environment"
    fi
    
    # Test Python imports
    if ! "$INSTALL_DIR/venv/bin/python" -c "import kast" 2>/dev/null; then
        log_error "Cannot import kast module"
        ((failed++))
    else
        log_success "✓ Python imports"
    fi
    
    # Check if at least one plugin is available
    local plugin_count=$("$INSTALL_DIR/venv/bin/python" -m kast.main --list-plugins 2>/dev/null | grep -c "Plugin:" || echo "0")
    if [[ $plugin_count -eq 0 ]]; then
        log_warning "No plugins available"
    else
        log_success "✓ $plugin_count plugins available"
    fi
    
    # Check version file
    if [[ ! -f "$INSTALL_DIR/$VERSION_FILE" ]]; then
        log_error "Version file missing"
        ((failed++))
    else
        log_success "✓ Version file present"
    fi
    
    if [[ $failed -eq 0 ]]; then
        log_success "Installation validation passed"
        return 0
    else
        log_error "Installation validation failed ($failed errors)"
        return 1
    fi
}

check_kast_running() {
    log_info "Checking if KAST is currently running..."
    
    # Check for running KAST processes
    if pgrep -f "kast.main" >/dev/null; then
        log_warning "KAST appears to be running"
        
        if [[ "$FORCE_MODE" == false ]] && [[ "$AUTO_MODE" == false ]]; then
            echo ""
            log_warning "Updating while KAST is running may cause issues."
            read -p "Stop KAST and continue? [y/N]: " stop_choice
            if [[ "$stop_choice" =~ ^[Yy]$ ]]; then
                log_info "Attempting to stop KAST processes..."
                pkill -f "kast.main"
                sleep 2
            else
                log_info "Update cancelled by user"
                exit 0
            fi
        fi
    else
        log_success "No running KAST processes detected"
    fi
}

###############################################################################
# UPDATE FUNCTIONS
###############################################################################

update_git_repository() {
    log_info "Updating git repository..."
    
    cd "$GIT_DIR"
    
    # Store current commit for reference
    local current_commit=$(git rev-parse HEAD)
    log_debug "Current commit: $current_commit"
    
    # Fetch latest changes
    log_info "Fetching latest changes..."
    if ! git fetch origin 2>&1 | tee -a "$UPDATE_LOG"; then
        log_error "Failed to fetch from remote repository"
        return 1
    fi
    
    # Pull changes
    log_info "Pulling changes..."
    if ! git pull origin $(git branch --show-current) 2>&1 | tee -a "$UPDATE_LOG"; then
        log_error "Failed to pull changes"
        return 1
    fi
    
    # Check if anything changed
    local new_commit=$(git rev-parse HEAD)
    if [[ "$current_commit" == "$new_commit" ]]; then
        log_info "Repository is already up to date"
    else
        log_success "Repository updated: $current_commit -> $new_commit"
    fi
    
    return 0
}

update_python_dependencies() {
    log_info "Updating Python dependencies..."
    
    # Check if requirements.txt changed
    local req_file="$GIT_DIR/requirements.txt"
    local install_req_file="$INSTALL_DIR/requirements.txt"
    
    if [[ ! -f "$req_file" ]]; then
        log_warning "requirements.txt not found in git repository"
        return 0
    fi
    
    # Compare requirements files
    if [[ -f "$install_req_file" ]]; then
        if diff -q "$req_file" "$install_req_file" >/dev/null 2>&1; then
            log_info "No changes to requirements.txt, skipping dependency update"
            return 0
        else
            log_info "requirements.txt has changed, updating dependencies..."
        fi
    fi
    
    # Activate virtual environment
    source "$INSTALL_DIR/venv/bin/activate"
    
    # Upgrade pip first
    log_info "Upgrading pip..."
    python -m pip install --upgrade pip 2>&1 | tee -a "$UPDATE_LOG"
    
    # Install/update requirements
    log_info "Installing updated requirements..."
    if pip install -r "$req_file" 2>&1 | tee -a "$UPDATE_LOG"; then
        log_success "Dependencies updated successfully"
        
        # Copy updated requirements.txt to install dir
        cp "$req_file" "$install_req_file"
        
        deactivate
        return 0
    else
        log_error "Failed to update dependencies"
        deactivate
        return 1
    fi
}

sync_files() {
    log_info "Synchronizing files from git repository to installation..."
    
    # Build rsync exclude arguments
    local exclude_args=""
    for pattern in "${EXCLUDE_PATTERNS[@]}"; do
        exclude_args="$exclude_args --exclude=$pattern"
    done
    
    # Preserve user configuration files
    local preserve_args=""
    for file in "${PRESERVE_FILES[@]}"; do
        if [[ -f "$INSTALL_DIR/$file" ]]; then
            log_info "Preserving user configuration: $file"
            # Create backup of user file
            cp "$INSTALL_DIR/$file" "$INSTALL_DIR/${file}.update_backup"
            preserve_args="$preserve_args --exclude=$file"
        fi
    done
    
    # Perform sync
    log_info "Copying files..."
    if rsync -av $exclude_args $preserve_args "$GIT_DIR/" "$INSTALL_DIR/" 2>&1 | tee -a "$UPDATE_LOG"; then
        log_success "Files synchronized successfully"
        
        # Restore preserved files if they were overwritten
        for file in "${PRESERVE_FILES[@]}"; do
            if [[ -f "$INSTALL_DIR/${file}.update_backup" ]]; then
                if [[ -f "$GIT_DIR/$file" ]]; then
                    # New version exists, offer to merge
                    log_info "Configuration file $file has been updated in new version"
                    if [[ "$AUTO_MODE" == false ]]; then
                        echo ""
                        echo "Options:"
                        echo "  1. Keep your current configuration"
                        echo "  2. Use new configuration from git"
                        echo "  3. View differences"
                        read -p "Choose [1-3, default: 1]: " merge_choice
                        merge_choice=${merge_choice:-1}
                        
                        case $merge_choice in
                            1)
                                log_info "Keeping your configuration"
                                mv "$INSTALL_DIR/${file}.update_backup" "$INSTALL_DIR/$file"
                                ;;
                            2)
                                log_info "Using new configuration"
                                rm "$INSTALL_DIR/${file}.update_backup"
                                ;;
                            3)
                                diff -u "$INSTALL_DIR/${file}.update_backup" "$GIT_DIR/$file" || true
                                echo ""
                                read -p "Keep your configuration? [Y/n]: " keep_choice
                                if [[ ! "$keep_choice" =~ ^[Nn]$ ]]; then
                                    mv "$INSTALL_DIR/${file}.update_backup" "$INSTALL_DIR/$file"
                                else
                                    rm "$INSTALL_DIR/${file}.update_backup"
                                fi
                                ;;
                        esac
                    else
                        # Auto mode: keep user config
                        log_info "Auto mode: keeping your configuration for $file"
                        mv "$INSTALL_DIR/${file}.update_backup" "$INSTALL_DIR/$file"
                    fi
                else
                    # No new version, restore backup
                    mv "$INSTALL_DIR/${file}.update_backup" "$INSTALL_DIR/$file"
                fi
            fi
        done
        
        return 0
    else
        log_error "Failed to synchronize files"
        return 1
    fi
}

update_version_file() {
    log_info "Updating version file..."
    
    if [[ -n "$NEW_VERSION" ]] && [[ "$NEW_VERSION" != "unknown" ]]; then
        echo "$NEW_VERSION" > "$INSTALL_DIR/$VERSION_FILE"
        log_success "Version file updated to $NEW_VERSION"
        return 0
    else
        log_warning "Could not determine new version, version file not updated"
        return 1
    fi
}

generate_update_summary() {
    local update_type=$1
    
    echo ""
    echo "======================================================================"
    echo "  Update Summary"
    echo "======================================================================"
    echo ""
    echo "Update Type: $update_type"
    echo "Previous Version: $CURRENT_VERSION"
    echo "New Version: $NEW_VERSION"
    echo ""
    
    if [[ -n "$BACKUP_DIR" ]]; then
        echo "Backup Location: $BACKUP_DIR"
        echo ""
    fi
    
    # Show changed files
    if [[ -d "$GIT_DIR/.git" ]]; then
        cd "$GIT_DIR"
        local changed_files=$(git diff --name-status HEAD@{1} HEAD 2>/dev/null | head -20)
        if [[ -n "$changed_files" ]]; then
            echo "Changed Files:"
            echo "$changed_files" | while read status file; do
                case $status in
                    M) echo "  Modified: $file" ;;
                    A) echo "  Added:    $file" ;;
                    D) echo "  Deleted:  $file" ;;
                    *) echo "  $status:  $file" ;;
                esac
            done
            
            local total_changes=$(git diff --name-status HEAD@{1} HEAD 2>/dev/null | wc -l)
            if [[ $total_changes -gt 20 ]]; then
                echo "  ... and $((total_changes - 20)) more files"
            fi
            echo ""
        fi
    fi
}

###############################################################################
# MAIN EXECUTION
###############################################################################

display_banner() {
    echo ""
    echo "======================================================================"
    echo "  KAST Update Script v${SCRIPT_VERSION}"
    echo "  Safely update your KAST installation"
    echo "======================================================================"
    echo ""
}

show_usage() {
    cat <<EOF
Usage: sudo ./update.sh [OPTIONS]

Update an existing KAST installation from git repository changes.

OPTIONS:
    --install-dir <path>    Target installation directory (default: /opt/kast)
    --git-dir <path>        Git repository directory (default: current directory)
    --auto                  Non-interactive mode (auto-accept defaults)
    --force                 Force update despite warnings
    --dry-run               Show what would be updated without making changes
    --rollback <timestamp>  Rollback to a specific backup
    --list-backups          List available backups
    -h, --help              Show this help message

EXAMPLES:
    # Normal interactive update
    sudo ./update.sh

    # Update specific installation
    sudo ./update.sh --install-dir /opt/kast

    # Automated update (for scripts/CI)
    sudo ./update.sh --auto

    # Dry run to see what would change
    sudo ./update.sh --dry-run

    # List available backups
    sudo ./update.sh --list-backups

    # Rollback to previous version
    sudo ./update.sh --rollback 20250117_143022

For more information, see the KAST documentation.
EOF
}

parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --install-dir)
                INSTALL_DIR="$2"
                shift 2
                ;;
            --git-dir)
                GIT_DIR="$2"
                shift 2
                ;;
            --auto)
                AUTO_MODE=true
                shift
                ;;
            --force)
                FORCE_MODE=true
                shift
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --rollback)
                ROLLBACK_ID="$2"
                shift 2
                ;;
            --list-backups)
                LIST_BACKUPS=true
                shift
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
    
    # Set defaults
    INSTALL_DIR=${INSTALL_DIR:-/opt/kast}
    GIT_DIR=${GIT_DIR:-$(pwd)}
}

main() {
    # Display banner
    display_banner
    
    # Parse command-line arguments
    parse_arguments "$@"
    
    # Handle special modes
    if [[ "$LIST_BACKUPS" == true ]]; then
        list_available_backups
        exit 0
    fi
    
    if [[ -n "$ROLLBACK_ID" ]]; then
        validate_root
        mkdir -p "$LOG_DIR"
        
        # Find backup by timestamp
        local backup_path="${BACKUP_PREFIX}.${ROLLBACK_ID}"
        if [[ ! -d "$backup_path" ]]; then
            log_error "Backup not found: $backup_path"
            exit 1
        fi
        
        perform_rollback "$backup_path"
        exit $?
    fi
    
    # Validate root
    validate_root
    
    # Create log directory
    mkdir -p "$LOG_DIR"
    
    # Check for concurrent updates
    if [[ -f "$LOCK_FILE" ]]; then
        log_error "Another update is already in progress (lock file exists)"
        log_error "If this is an error, remove $LOCK_FILE and try again"
        exit 1
    fi
    
    # Create lock file
    touch "$LOCK_FILE"
    
    log_info "Update started by user: ${SUDO_USER:-$USER}"
    log_info "Installation directory: $INSTALL_DIR"
    log_info "Git repository: $GIT_DIR"
    
    # Pre-update validation
    echo ""
    echo "======================================================================"
    echo "  Pre-Update Validation"
    echo "======================================================================"
    echo ""
    
    validate_installation_exists || exit 1
    validate_git_repository || exit 1
    check_kast_running
    
    # Determine update type
    if [[ "$NEW_VERSION" != "unknown" ]]; then
        local update_type=$(get_update_type "$CURRENT_VERSION" "$NEW_VERSION")
        
        if [[ "$update_type" == "none" ]]; then
            log_warning "No version change detected"
            if version_compare "$CURRENT_VERSION" "$NEW_VERSION"; then
                log_info "Current version ($CURRENT_VERSION) >= Repository version ($NEW_VERSION)"
            fi
            
            if [[ "$FORCE_MODE" == false ]]; then
                echo ""
                read -p "Proceed with update anyway? [y/N]: " proceed
                if [[ ! "$proceed" =~ ^[Yy]$ ]]; then
                    log_info "Update cancelled by user"
                    exit 0
                fi
            fi
        else
            log_info "Update type: $update_type"
        fi
    fi
    
    save_checkpoint "$CHECKPOINT_VALIDATION"
    
    # Confirm update
    if [[ "$AUTO_MODE" == false ]] && [[ "$DRY_RUN" == false ]]; then
        echo ""
        echo "Ready to update KAST:"
        echo "  From: v$CURRENT_VERSION"
        echo "  To:   v$NEW_VERSION"
        echo ""
        read -p "Proceed with update? [Y/n]: " confirm
        confirm=${confirm:-Y}
        
        if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
            log_info "Update cancelled by user"
            exit 0
        fi
    fi
    
    if [[ "$DRY_RUN" == true ]]; then
        log_info "DRY RUN MODE - No changes will be made"
        echo ""
        echo "The following steps would be performed:"
        echo "  1. Create backup at ${BACKUP_PREFIX}.$(date +%Y%m%d_%H%M%S)"
        echo "  2. Update git repository (git pull)"
        echo "  3. Update Python dependencies (if requirements.txt changed)"
        echo "  4. Synchronize files from git to installation"
        echo "  5. Update version file to $NEW_VERSION"
        echo "  6. Validate updated installation"
        echo ""
        log_info "Dry run complete. No changes made."
        exit 0
    fi
    
    # Begin update process
    echo ""
    echo "======================================================================"
    echo "  Update Process"
    echo "======================================================================"
    echo ""
    
    save_checkpoint "$CHECKPOINT_INIT"
    
    # Step 1: Create backup
    echo ""
    log_info "Step 1/6: Creating backup..."
    if ! create_backup; then
        log_error "Failed to create backup. Aborting update."
        exit 1
    fi
    save_checkpoint "$CHECKPOINT_BACKUP"
    
    # Step 2: Update git repository
    echo ""
    log_info "Step 2/6: Updating git repository..."
    if ! update_git_repository; then
        log_error "Failed to update git repository"
        # Offer rollback
        if [[ "$AUTO_MODE" == false ]]; then
            read -p "Rollback to backup? [Y/n]: " rollback_choice
            rollback_choice=${rollback_choice:-Y}
            if [[ "$rollback_choice" =~ ^[Yy]$ ]]; then
                perform_rollback "$BACKUP_DIR"
            fi
        fi
        exit 1
    fi
    save_checkpoint "$CHECKPOINT_GIT_PULL"
    
    # Step 3: Update Python dependencies
    echo ""
    log_info "Step 3/6: Updating Python dependencies..."
    if ! update_python_dependencies; then
        log_error "Failed to update Python dependencies"
        if [[ "$AUTO_MODE" == false ]]; then
            read -p "Rollback to backup? [Y/n]: " rollback_choice
            rollback_choice=${rollback_choice:-Y}
            if [[ "$rollback_choice" =~ ^[Yy]$ ]]; then
                perform_rollback "$BACKUP_DIR"
            fi
        fi
        exit 1
    fi
    save_checkpoint "$CHECKPOINT_PIP_UPDATE"
    
    # Step 4: Synchronize files
    echo ""
    log_info "Step 4/6: Synchronizing files..."
    if ! sync_files; then
        log_error "Failed to synchronize files"
        if [[ "$AUTO_MODE" == false ]]; then
            read -p "Rollback to backup? [Y/n]: " rollback_choice
            rollback_choice=${rollback_choice:-Y}
            if [[ "$rollback_choice" =~ ^[Yy]$ ]]; then
                perform_rollback "$BACKUP_DIR"
            fi
        fi
        exit 1
    fi
    save_checkpoint "$CHECKPOINT_FILE_SYNC"
    
    # Step 5: Update version file
    echo ""
    log_info "Step 5/6: Updating version file..."
    update_version_file  # Non-critical, don't fail on this
    
    # Step 6: Post-update validation
    echo ""
    log_info "Step 6/6: Validating updated installation..."
    if ! validate_installation "post_update"; then
        log_error "Post-update validation failed"
        log_error "Installation may be in an inconsistent state"
        
        if [[ "$AUTO_MODE" == false ]]; then
            read -p "Rollback to backup? [Y/n]: " rollback_choice
            rollback_choice=${rollback_choice:-Y}
            if [[ "$rollback_choice" =~ ^[Yy]$ ]]; then
                perform_rollback "$BACKUP_DIR"
                exit 1
            fi
        else
            # Auto mode: rollback on validation failure
            log_info "Auto mode: Rolling back due to validation failure"
            perform_rollback "$BACKUP_DIR"
            exit 1
        fi
    fi
    save_checkpoint "$CHECKPOINT_POST_VALIDATION"
    
    # Mark update as complete
    save_checkpoint "$CHECKPOINT_COMPLETE"
    
    # Display success message
    echo ""
    echo "======================================================================"
    echo "  Update Complete!"
    echo "======================================================================"
    echo ""
    
    log_success "KAST has been successfully updated!"
    
    # Generate and display summary
    local update_type=$(get_update_type "$CURRENT_VERSION" "$NEW_VERSION")
    generate_update_summary "$update_type"
    
    echo "Installation: $INSTALL_DIR"
    echo "Version: $NEW_VERSION"
    echo "Backup: $BACKUP_DIR"
    echo ""
    echo "Update log: $UPDATE_LOG"
    echo ""
    
    if [[ "$NEW_VERSION" != "$CURRENT_VERSION" ]]; then
        echo "To verify the update:"
        echo "  kast --version"
        echo ""
    fi
    
    echo "If you encounter any issues, you can rollback:"
    echo "  sudo ./update.sh --rollback $(basename $BACKUP_DIR | sed 's/kast.backup.//')"
    echo ""
    
    log_success "Update completed successfully"
}

# Run main function
main "$@"
