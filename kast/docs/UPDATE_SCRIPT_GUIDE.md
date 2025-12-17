# KAST Update Script Guide

## Overview

The `update.sh` script provides a safe and reliable way to update an existing KAST installation from git repository changes. It includes comprehensive backup/rollback functionality, version tracking, and validation to ensure production systems can be updated with minimal risk.

## Features

### Core Capabilities

- **Automated Updates**: Pulls latest changes from git and applies them to installation
- **Backup System**: Creates timestamped backups before each update
- **Rollback Support**: Instantly revert to any previous backup if issues occur
- **Version Tracking**: Tracks current and target versions
- **Validation**: Pre and post-update validation ensures system integrity
- **Configuration Preservation**: Keeps user configurations during updates
- **Dependency Management**: Updates Python dependencies when requirements.txt changes
- **Progress Tracking**: Checkpoint system allows resuming interrupted updates
- **Multiple Modes**: Interactive, automated, and dry-run modes

### Safety Features

- **Pre-update Validation**: Checks installation state before proceeding
- **Disk Space Checks**: Ensures sufficient space for backup
- **Running Process Detection**: Warns if KAST is currently running
- **Automatic Rollback**: Offers rollback on failure
- **Configuration Merging**: Handles conflicts between old and new configs
- **Lock File Protection**: Prevents concurrent updates

## Installation

The update script is included in the KAST repository root. Make it executable:

```bash
chmod +x update.sh
```

## Usage

### Basic Usage

```bash
# Interactive update (recommended for first-time use)
sudo ./update.sh

# Automated update (for scripts/CI/CD)
sudo ./update.sh --auto

# Dry run to see what would change
sudo ./update.sh --dry-run
```

### Command-Line Options

```
--install-dir <path>    Target installation directory (default: /opt/kast)
--git-dir <path>        Git repository directory (default: current directory)
--auto                  Non-interactive mode (auto-accept defaults)
--force                 Force update despite warnings
--dry-run               Show what would be updated without making changes
--rollback <timestamp>  Rollback to a specific backup
--list-backups          List available backups
-h, --help              Show help message
```

## Update Process

The update script follows this workflow:

### Phase 1: Pre-Update Validation

1. **Installation Check**: Verifies KAST is installed at target directory
2. **Version Detection**: Identifies current and new versions
3. **Git Validation**: Checks git repository state
4. **Process Check**: Warns if KAST is running
5. **User Confirmation**: Asks user to proceed (unless --auto)

### Phase 2: Backup Creation

1. **Disk Space Check**: Ensures sufficient space
2. **Rsync Backup**: Creates complete backup of installation
3. **Inventory Update**: Records backup metadata
4. **Cleanup**: Removes old backups (keeps last 5)

### Phase 3: Update Execution

1. **Git Pull**: Updates repository from remote
2. **Dependency Update**: Updates Python packages if needed
3. **File Synchronization**: Copies files while preserving configs
4. **Version File Update**: Updates version information

### Phase 4: Post-Update Validation

1. **Installation Check**: Verifies all components present
2. **Import Test**: Tests Python module imports
3. **Plugin Check**: Counts available plugins
4. **Summary Generation**: Shows what changed

## Configuration File Handling

The update script intelligently handles configuration files:

### Preserved Files

These files are preserved during updates:
- `kast_default.yaml` - Default configuration
- `resume.cfg` - Resume state
- `.kast_custom_config` - Custom settings

### Conflict Resolution

When a preserved file is updated in the new version:

**Interactive Mode**:
```
Options:
  1. Keep your current configuration
  2. Use new configuration from git
  3. View differences
```

**Automated Mode**: Keeps your configuration by default

### Excluded Patterns

These are never synchronized:
- `.git/` directory
- `.gitignore` file
- `*.pyc` compiled Python
- `__pycache__/` directories
- `*.backup.*` files
- Update/install scripts
- State files

## Backup Management

### Backup Locations

Backups are stored in `/opt/kast.backup.<timestamp>` format:
```
/opt/kast.backup.20250117_143022
/opt/kast.backup.20250116_101530
```

### Backup Inventory

Metadata is tracked in `/var/log/kast/backup_inventory.json`:
```json
[
  {
    "timestamp": "20250117_143022",
    "version": "2.6.4",
    "path": "/opt/kast.backup.20250117_143022",
    "created": "2025-01-17T14:30:22+00:00",
    "size": "125829120"
  }
]
```

### Listing Backups

```bash
sudo ./update.sh --list-backups
```

Output:
```
======================================================================
  Available Backups
======================================================================

Timestamp            Version      Size         Status
----------------------------------------------------------------------
20250117_143022      2.6.4          120.0 MB   Available
20250116_101530      2.6.3          118.5 MB   Available

To rollback to a backup, run:
  sudo ./update.sh --rollback <timestamp>
```

### Automatic Cleanup

- Maximum of 5 backups retained
- Oldest backups automatically removed
- Configurable via `MAX_BACKUPS` variable

## Rollback Procedures

### Automatic Rollback

On update failure, the script offers automatic rollback:
```
[ERROR] Update failed
Update failed but backup exists at: /opt/kast.backup.20250117_143022

Would you like to rollback to the backup? [Y/n]:
```

### Manual Rollback

Rollback to a specific backup:
```bash
# List available backups
sudo ./update.sh --list-backups

# Rollback to specific timestamp
sudo ./update.sh --rollback 20250117_143022
```

### Safety Backup

Before rollback, a safety backup is created:
```
/opt/kast.backup.pre_rollback_<timestamp>
```

This allows you to undo the rollback if needed.

## Update Scenarios

### Scenario 1: Normal Update

```bash
# User workflow
cd /path/to/kast/repo
git pull
sudo ./update.sh

# Output
Pre-Update Validation
✓ Found KAST installation v2.6.3 at /opt/kast
✓ Git repository validated
✓ No running KAST processes detected

Ready to update KAST:
  From: v2.6.3
  To:   v2.6.4

Proceed with update? [Y/n]: y

Update Process
Step 1/6: Creating backup...
✓ Backup created successfully: 2847 files, 121M

Step 2/6: Updating git repository...
✓ Repository updated

Step 3/6: Updating Python dependencies...
✓ Dependencies updated successfully

Step 4/6: Synchronizing files...
✓ Files synchronized successfully

Step 5/6: Updating version file...
✓ Version file updated to 2.6.4

Step 6/6: Validating updated installation...
✓ Installation validation passed

Update Complete!
KAST has been successfully updated!
```

### Scenario 2: Configuration Conflict

```bash
Step 4/6: Synchronizing files...
Configuration file kast_default.yaml has been updated in new version

Options:
  1. Keep your current configuration
  2. Use new configuration from git
  3. View differences
Choose [1-3, default: 1]: 3

--- /opt/kast/kast_default.yaml.update_backup
+++ /path/to/repo/kast_default.yaml
@@ -10,7 +10,8 @@
   parallel: true
   max_workers: 4
+  timeout: 3600

Keep your configuration? [Y/n]: y
Keeping your configuration
```

### Scenario 3: Update Failure and Rollback

```bash
Step 3/6: Updating Python dependencies...
[ERROR] Failed to update dependencies

Rollback to backup? [Y/n]: y

Rollback Confirmation
Current installation: /opt/kast
Rollback to: /opt/kast.backup.20250117_143022
Target version: 2.6.3

Proceed with rollback? [y/N]: y

Creating safety backup: /opt/kast.backup.pre_rollback_20250117_143530
Restoring from backup...
✓ Files restored successfully
✓ Restored to version: 2.6.3
✓ Rollback completed successfully
```

### Scenario 4: Automated Update (CI/CD)

```bash
# Cron job or CI/CD pipeline
cd /opt/kast
sudo git pull
sudo ./update.sh --auto

# Script runs non-interactively
# - Uses defaults for all choices
# - Keeps user configurations
# - Auto-rollback on validation failure
# - Logs all output to /var/log/kast/update.log
```

### Scenario 5: Dry Run

```bash
sudo ./update.sh --dry-run

# Output shows what would happen
DRY RUN MODE - No changes will be made

The following steps would be performed:
  1. Create backup at /opt/kast.backup.20250117_150022
  2. Update git repository (git pull)
  3. Update Python dependencies (if requirements.txt changed)
  4. Synchronize files from git to installation
  5. Update version file to 2.6.4
  6. Validate updated installation

Dry run complete. No changes made.
```

## Troubleshooting

### Update Fails at Git Pull

**Problem**: Git repository has conflicts or uncommitted changes

**Solution**:
```bash
cd /path/to/kast/repo
git status
git stash  # Save local changes
sudo ./update.sh
```

Or use `--force` to bypass warnings:
```bash
sudo ./update.sh --force
```

### Insufficient Disk Space

**Problem**: Not enough space for backup

**Solution**:
```bash
# Check disk usage
df -h /opt

# Remove old backups manually
sudo rm -rf /opt/kast.backup.old_timestamp

# Or increase MAX_BACKUPS threshold
```

### Python Dependencies Fail

**Problem**: Pip install fails during update

**Solution**:
```bash
# Manual fix
cd /opt/kast
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

# Retry update
sudo ./update.sh
```

### Version File Missing

**Problem**: `.kast_version` file not found

**Solution**:
```bash
# Create version file manually
echo "2.6.4" | sudo tee /opt/kast/.kast_version

# Or reinstall
sudo ./install.sh
```

### Lock File Remains After Crash

**Problem**: Update interrupted, lock file prevents new updates

**Solution**:
```bash
sudo rm /tmp/kast_update.lock
sudo ./update.sh
```

## Logging

All update activity is logged to `/var/log/kast/update.log`:

```bash
# View recent updates
tail -f /var/log/kast/update.log

# View specific update
grep "2025-01-17" /var/log/kast/update.log

# Check for errors
grep ERROR /var/log/kast/update.log
```

## Best Practices

### Before Updating

1. **Read Release Notes**: Check what's changed
2. **Backup Data**: Ensure important data is backed up
3. **Check Disk Space**: Verify sufficient space
4. **Test in Staging**: Try update in non-production first
5. **Note Current Version**: Record current version

### During Updates

1. **Use Dry Run First**: Test with `--dry-run`
2. **Monitor Progress**: Watch for errors
3. **Don't Interrupt**: Let update complete
4. **Review Configs**: Check configuration conflicts
5. **Validate Changes**: Verify everything works

### After Updating

1. **Verify Version**: `kast --version`
2. **Test Plugins**: `kast --list-plugins`
3. **Run Test Scan**: Test on safe target
4. **Review Logs**: Check for warnings
5. **Keep Backup**: Don't delete backup immediately

### For Production Systems

1. **Schedule Maintenance**: Plan downtime window
2. **Use Automated Mode**: `--auto` for consistency
3. **Integrate with CI/CD**: Automate deployment
4. **Monitor Logs**: Set up alerting
5. **Document Rollback Plan**: Know how to recover

### Regular Maintenance

1. **Update Frequently**: Don't fall too far behind
2. **Clean Old Backups**: Remove very old backups
3. **Review Inventory**: Check backup inventory
4. **Test Rollback**: Periodically test rollback procedure
5. **Update Documentation**: Keep notes on customizations

## Integration Examples

### Cron Job (Daily Updates)

```bash
# /etc/cron.d/kast-update
0 2 * * * root cd /opt/kast && git pull && /opt/kast/update.sh --auto >> /var/log/kast/cron_update.log 2>&1
```

### Systemd Timer

```ini
# /etc/systemd/system/kast-update.timer
[Unit]
Description=KAST Update Timer

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

```ini
# /etc/systemd/system/kast-update.service
[Unit]
Description=KAST Update Service

[Service]
Type=oneshot
WorkingDirectory=/opt/kast
ExecStartPre=/usr/bin/git pull
ExecStart=/opt/kast/update.sh --auto
StandardOutput=journal
StandardError=journal
```

### Ansible Playbook

```yaml
---
- name: Update KAST installation
  hosts: kast_servers
  become: yes
  tasks:
    - name: Pull latest from git
      git:
        repo: 'https://github.com/yourusername/kast.git'
        dest: /opt/kast
        update: yes
      
    - name: Run update script
      command: /opt/kast/update.sh --auto
      args:
        chdir: /opt/kast
      register: update_result
      
    - name: Show update result
      debug:
        var: update_result.stdout_lines
```

### CI/CD Pipeline (GitHub Actions)

```yaml
name: Deploy KAST Update

on:
  push:
    tags:
      - 'v*'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to production
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.PROD_HOST }}
          username: ${{ secrets.PROD_USER }}
          key: ${{ secrets.PROD_SSH_KEY }}
          script: |
            cd /opt/kast
            git pull
            sudo ./update.sh --auto
```

## Version Comparison

The update script uses semantic versioning (semver) for intelligent updates:

### Version Format

`MAJOR.MINOR.PATCH` (e.g., 2.6.4)

### Update Types

- **Major Update**: 2.6.4 → 3.0.0 (Breaking changes)
- **Minor Update**: 2.6.4 → 2.7.0 (New features)
- **Patch Update**: 2.6.4 → 2.6.5 (Bug fixes)

### Handling No Version Change

If versions match, the script:
1. Warns about no version change
2. Offers to proceed anyway
3. Syncs files regardless (may have uncommitted changes)

## Advanced Configuration

### Customizing Preserved Files

Edit `PRESERVE_FILES` array in update.sh:

```bash
PRESERVE_FILES=(
    "kast_default.yaml"
    "resume.cfg"
    ".kast_custom_config"
    "my_custom_config.yaml"  # Add your file
)
```

### Customizing Exclude Patterns

Edit `EXCLUDE_PATTERNS` array:

```bash
EXCLUDE_PATTERNS=(
    ".git"
    "*.pyc"
    "__pycache__"
    "*.log"  # Add your pattern
)
```

### Changing Backup Retention

```bash
# Edit MAX_BACKUPS in update.sh
MAX_BACKUPS=10  # Keep 10 backups instead of 5
```

### Custom Log Location

```bash
# Edit LOG_DIR in update.sh
LOG_DIR="/custom/log/path"
```

## Security Considerations

### Root Requirements

- Update script requires root (sudo)
- Validates root before proceeding
- Preserves file ownership

### File Permissions

- Preserves original permissions
- Maintains venv ownership
- Respects user configurations

### Backup Security

- Backups stored in `/opt` (root access required)
- Inventory in `/var/log/kast` (limited access)
- No sensitive data exposed in logs

## Performance Considerations

### Disk Space

- Each backup ≈ installation size
- 5 backups ≈ 5× installation size
- Monitor `/opt` partition

### Update Duration

Typical update times:
- Small update (patch): 1-2 minutes
- Medium update (minor): 2-5 minutes
- Large update (major): 5-10 minutes
- With new dependencies: +5 minutes

### Network Requirements

- Git pull: varies with changes
- Python dependencies: varies with updates
- Total bandwidth: typically < 100MB

## Related Documentation

- [Installation Guide](../README.md)
- [Plugin Development Guide](README_CREATE_PLUGIN.md)
- [Configuration Guide](../kast_default.yaml)
- [Troubleshooting Guide](INSTALL_SCRIPT_IMPROVEMENTS.md)

## Support

For issues or questions:
1. Check logs: `/var/log/kast/update.log`
2. Review this documentation
3. Report bugs using `/reportbug` command
4. Check GitHub issues

## Changelog

### Version 1.0.0 (Initial Release)
- Full backup/rollback system
- Configuration preservation
- Version tracking
- Multi-mode operation
- Comprehensive validation
- Checkpoint system
- Automated and interactive modes
