# KAST Update Quick Reference

## Quick Start

```bash
# Pull latest changes
cd /path/to/kast/repo
git pull

# Run update
sudo ./update.sh
```

## Common Commands

```bash
# Interactive update (recommended)
sudo ./update.sh

# Automated update (for scripts)
sudo ./update.sh --auto

# Preview changes (no modifications)
sudo ./update.sh --dry-run

# List available backups
sudo ./update.sh --list-backups

# Rollback to previous version
sudo ./update.sh --rollback <timestamp>
```

## What Happens During Update

1. ✓ Validates current installation
2. ✓ Creates timestamped backup
3. ✓ Updates git repository
4. ✓ Updates Python dependencies (if needed)
5. ✓ Synchronizes files (preserves your configs)
6. ✓ Validates updated installation

## Safety Features

- **Automatic Backups**: Created before every update
- **Configuration Preservation**: Your settings are kept
- **Easy Rollback**: Restore any previous backup
- **Validation**: Pre and post-update checks
- **Lock Protection**: Prevents concurrent updates

## Typical Workflow

### 1. Check Current Version
```bash
kast --version
cat /opt/kast/.kast_version
```

### 2. Pull Latest Changes
```bash
cd /path/to/kast/repo
git pull
```

### 3. Preview Update (Optional)
```bash
sudo ./update.sh --dry-run
```

### 4. Perform Update
```bash
sudo ./update.sh
```

### 5. Verify Update
```bash
kast --version
kast --list-plugins
```

## If Something Goes Wrong

### Automatic Rollback
The script will offer to rollback automatically if update fails.

### Manual Rollback
```bash
# List backups
sudo ./update.sh --list-backups

# Rollback to specific backup
sudo ./update.sh --rollback 20250117_143022
```

### Check Logs
```bash
tail -f /var/log/kast/update.log
```

## Configuration Conflicts

When a config file is updated in the new version:

**Option 1**: Keep your configuration (recommended)
**Option 2**: Use new configuration
**Option 3**: View differences and decide

The script will ask you interactively (unless using `--auto` mode).

## Backup Management

### Backup Location
```
/opt/kast.backup.<timestamp>
```

### Automatic Cleanup
- Keeps last 5 backups
- Removes older backups automatically
- Configurable via MAX_BACKUPS variable

### Manual Cleanup
```bash
# Remove specific backup
sudo rm -rf /opt/kast.backup.20250101_120000

# Remove all old backups
sudo rm -rf /opt/kast.backup.*
```

## Production Systems

### Scheduled Updates (Cron)
```bash
# Daily at 2 AM
echo "0 2 * * * root cd /opt/kast && git pull && /opt/kast/update.sh --auto" | sudo tee /etc/cron.d/kast-update
```

### Pre-Update Checklist
- [ ] Read release notes
- [ ] Check disk space: `df -h /opt`
- [ ] Note current version
- [ ] Plan maintenance window
- [ ] Test in non-production first

### Post-Update Verification
- [ ] Check version: `kast --version`
- [ ] List plugins: `kast --list-plugins`
- [ ] Run test scan
- [ ] Review logs: `/var/log/kast/update.log`
- [ ] Monitor for issues

## Troubleshooting

### "Lock file exists"
```bash
sudo rm /tmp/kast_update.lock
```

### "Git has uncommitted changes"
```bash
cd /path/to/kast/repo
git stash
sudo ./update.sh
```

### "Insufficient disk space"
```bash
# Check space
df -h /opt

# Remove old backups
sudo ./update.sh --list-backups
sudo rm -rf /opt/kast.backup.<old_timestamp>
```

### "Python dependencies failed"
```bash
cd /opt/kast
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate
```

## Options Reference

| Option | Description |
|--------|-------------|
| `--install-dir <path>` | Target installation directory |
| `--git-dir <path>` | Git repository directory |
| `--auto` | Non-interactive mode |
| `--force` | Force update despite warnings |
| `--dry-run` | Preview without making changes |
| `--rollback <timestamp>` | Rollback to specific backup |
| `--list-backups` | Show available backups |
| `-h, --help` | Show help message |

## Log Files

| File | Purpose |
|------|---------|
| `/var/log/kast/update.log` | Update activity log |
| `/var/log/kast/backup_inventory.json` | Backup metadata |
| `/opt/kast/.kast_version` | Current version |
| `/opt/kast/.kast_update_state` | Update checkpoint state |

## Version Information

```bash
# Check installed version
kast --version

# Check version file
cat /opt/kast/.kast_version

# Check install script version
grep SCRIPT_VERSION /opt/kast/install.sh
```

## Getting Help

For detailed documentation, see:
- [Full Update Guide](kast/docs/UPDATE_SCRIPT_GUIDE.md)
- [Installation Guide](README.md)
- Update logs: `/var/log/kast/update.log`
- Report issues: Use `/reportbug` command

## Best Practices

✓ **Update regularly** - Don't fall too far behind  
✓ **Test first** - Use `--dry-run` to preview  
✓ **Read release notes** - Know what's changing  
✓ **Keep backups** - Don't delete immediately after update  
✓ **Monitor logs** - Check for warnings or errors  
✓ **Verify functionality** - Test after updating  

---

**Need more details?** See the [comprehensive update guide](kast/docs/UPDATE_SCRIPT_GUIDE.md)
