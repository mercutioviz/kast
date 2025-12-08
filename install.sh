#!/bin/bash

# KAST Installation Script - Enhanced Version
# Handles fresh installs, upgrades, and recovery from aborted installations

###############################################################################
# CONSTANTS AND CONFIGURATION
###############################################################################

SCRIPT_VERSION="2.6.3"
INSTALL_STATE_FILE=".kast_install_state"
VERSION_FILE=".kast_version"
LOCK_FILE="/tmp/kast_install.lock"
LOG_DIR="/var/log/kast"
INSTALL_LOG="$LOG_DIR/install.log"
BACKUP_PREFIX="/opt/kast.backup"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Installation checkpoints
CHECKPOINT_INIT="initialization"
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
# INSTALLATION FUNCTIONS
###############################################################################

install_system_packages() {
    if checkpoint_completed "$CHECKPOINT_PACKAGES"; then
        log_info "System packages already installed, skipping..."
        return 0
    fi
    
    log_info "Installing system packages..."
    apt install -y ca-certificates curl gnupg rsync
    apt install -y firefox-esr git golang gpg htop nginx openjdk-21-jre python3 python3-venv sslscan testssl.sh wafw00f whatweb
    
    save_checkpoint "$CHECKPOINT_PACKAGES"
    log_success "System packages installed"
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
    
    # Install katana
    if [[ ! -f "$ORIG_HOME/go/bin/katana" ]] || [[ ! -f "/usr/local/bin/katana" ]]; then
        log_info "Installing katana..."
        sudo -u "$ORIG_USER" bash -c "GOBIN='$ORIG_HOME/go/bin' CGO_ENABLED=1 go install github.com/projectdiscovery/katana/cmd/katana@latest"
        ln -f -s "$ORIG_HOME/go/bin/katana" /usr/local/bin/katana
    else
        log_info "Katana already installed"
    fi
    
    # Install subfinder
    if [[ ! -f "$ORIG_HOME/go/bin/subfinder" ]] || [[ ! -f "/usr/local/bin/subfinder" ]]; then
        log_info "Installing subfinder..."
        sudo -u "$ORIG_USER" bash -c "GOBIN='$ORIG_HOME/go/bin' go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest"
        ln -f -s "$ORIG_HOME/go/bin/subfinder" /usr/local/bin/subfinder
    else
        log_info "Subfinder already installed"
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
    GECKO_VERSION=$(curl -s https://api.github.com/repos/mozilla/geckodriver/releases/latest | grep 'tag_name' | cut -d '"' -f 4)
    log_info "Geckodriver version: $GECKO_VERSION"
    
    wget -q "https://github.com/mozilla/geckodriver/releases/download/$GECKO_VERSION/geckodriver-$GECKO_VERSION-linux64.tar.gz"
    tar -xzf "geckodriver-$GECKO_VERSION-linux64.tar.gz"
    mv geckodriver /usr/local/bin/
    rm "geckodriver-$GECKO_VERSION-linux64.tar.gz"
    
    geckodriver --version
    
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
    
    # Check if key system tools are available
    local tools=(firefox geckodriver terraform testssl whatweb)
    for tool in "${tools[@]}"; do
        if ! command -v "$tool" &>/dev/null; then
            log_warning "$tool not found in PATH"
            ((failed++))
        fi
    done
    
    if [[ $failed -eq 0 ]]; then
        log_success "All verification checks passed!"
        return 0
    else
        log_warning "Installation completed with $failed warnings"
        return 1
    fi
}

###############################################################################
# USER INTERACTION FUNCTIONS
###############################################################################

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
    
    # Validate root
    validate_root
    
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
    
    # Execute installation steps
    install_system_packages
    install_nodejs
    install_go_tools
    install_geckodriver
    install_terraform
    install_observatory
    install_libpango
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
