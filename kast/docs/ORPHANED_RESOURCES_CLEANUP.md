# Orphaned Resources Cleanup Tool

## Overview

The `cleanup_orphaned_resources.py` script detects and removes orphaned KAST ZAP cloud infrastructure resources that were left behind due to failed scans or incomplete cleanup operations.

## Background

When a KAST ZAP cloud scan fails (e.g., due to the bug fixed in `zap_providers.py`), cloud resources may remain provisioned without being properly cleaned up. This can result in:
- Unexpected cloud costs
- Resource quota consumption
- Security concerns from running unmonitored instances

This tool helps identify and clean up these orphaned resources.

## Features

- **Multi-cloud support**: AWS (fully implemented), Azure and GCP (placeholders)
- **Smart detection**: Identifies orphaned resources by correlating with local state files
- **Safe operation**: Dry-run mode and interactive confirmation
- **Flexible filtering**: By scan ID, instance ID, provider, or region
- **Export capability**: Save resource inventory to JSON for audit trails

## Installation

The script requires boto3 for AWS operations:

```bash
pip install boto3
```

## Usage

### List Orphaned Resources (Default)

```bash
python kast/scripts/cleanup_orphaned_resources.py
```

This will:
1. Scan AWS for KAST-tagged resources
2. Check if local state files exist
3. Display orphaned resources only

### List All Resources

```bash
python kast/scripts/cleanup_orphaned_resources.py --list-all
```

Shows both orphaned and tracked resources.

### Find Resources for Specific Scan

```bash
python kast/scripts/cleanup_orphaned_resources.py --scan-id kast-zap-355437ac
```

Useful when you know the scan identifier from error logs.

### Clean Up Specific Instance

```bash
# Dry-run first (safe)
python kast/scripts/cleanup_orphaned_resources.py --instance-id i-06c57c296d5aef295 --dry-run

# Actually delete
python kast/scripts/cleanup_orphaned_resources.py --instance-id i-06c57c296d5aef295 --cleanup
```

### Interactive Cleanup

```bash
python kast/scripts/cleanup_orphaned_resources.py --interactive
```

Prompts before deleting each resource.

### Cleanup All Orphaned Resources

```bash
# Dry-run first (recommended)
python kast/scripts/cleanup_orphaned_resources.py --cleanup --dry-run

# Execute cleanup
python kast/scripts/cleanup_orphaned_resources.py --cleanup
```

### Specify Region

```bash
python kast/scripts/cleanup_orphaned_resources.py --region us-west-2 --cleanup
```

Default is `us-east-1`.

### Export Resource List

```bash
python kast/scripts/cleanup_orphaned_resources.py --export resources.json
```

Creates a JSON file with detailed resource information for audit purposes.

## How It Works

### Resource Detection

The script identifies KAST resources by:

1. **Tags**: Resources with tags containing "kast" or "zap scan"
2. **Name patterns**: Resources named like `kast-zap-XXXXXXXX`
3. **Scan identifiers**: Matches resources to specific scans

### Orphan Detection

A resource is marked as orphaned if:
- It has a scan identifier, but no matching local state file exists in `test_output/`
- It has no scan identifier (can't be correlated)

### Resource Types Detected

**AWS:**
- EC2 instances (spot and on-demand)
- Security groups
- Associated VPCs (noted but not deleted)

**Azure/GCP:**
- Placeholder support (to be implemented)

## Output Format

```
═══════════════════════════════════════════════════════════════════
  AWS Resources (2)
───────────────────────────────────────────────────────────────────

[ORPHANED] EC2 Instance
  ID: i-06c57c296d5aef295
  Name: kast-zap-355437ac
  Region: us-east-1
  State: running
  Age: 2.3h
  Scan ID: kast-zap-355437ac
  Associated:
    - SecurityGroup: sg-02cf1a77fcea8da4e
    - VPC: vpc-03a7e958063c2f1ff

[ORPHANED] Security Group
  ID: sg-02cf1a77fcea8da4e
  Name: kast-zap-sg-355437ac
  Region: us-east-1
  State: N/A
  Age: 2.3h
  Scan ID: kast-zap-355437ac
  Associated:
    - VPC: vpc-03a7e958063c2f1ff

───────────────────────────────────────────────────────────────────
  Summary
───────────────────────────────────────────────────────────────────
  → Total resources: 2
  → Orphaned resources: 2
  → Tracked resources: 0
```

## Safety Features

### 1. Dry-Run Mode

Always test with `--dry-run` first:

```bash
python kast/scripts/cleanup_orphaned_resources.py --cleanup --dry-run
```

This shows what would be deleted without actually deleting.

### 2. Interactive Confirmation

Use `--interactive` to approve each deletion:

```bash
python kast/scripts/cleanup_orphaned_resources.py --interactive
```

### 3. Batch Confirmation

Without `--interactive`, you get one confirmation prompt before batch deletion.

### 4. State File Correlation

Resources are only marked orphaned if their scan identifier doesn't match any local state files, reducing false positives.

## Common Scenarios

### Scenario 1: Failed Scan Left Resources

**Problem:** ZAP scan failed with error, resources still running.

**Solution:**
```bash
# Find resources from that scan
python kast/scripts/cleanup_orphaned_resources.py --scan-id kast-zap-355437ac

# Clean up
python kast/scripts/cleanup_orphaned_resources.py --scan-id kast-zap-355437ac --cleanup
```

### Scenario 2: Unknown Orphaned Resources

**Problem:** Don't know which resources are orphaned.

**Solution:**
```bash
# Scan all KAST resources
python kast/scripts/cleanup_orphaned_resources.py --list-all

# Review and clean up orphaned ones
python kast/scripts/cleanup_orphaned_resources.py --cleanup --interactive
```

### Scenario 3: Regular Audit

**Problem:** Want to check for orphaned resources periodically.

**Solution:**
```bash
# Export current state
python kast/scripts/cleanup_orphaned_resources.py --list-all --export audit_$(date +%Y%m%d).json

# If orphans found, clean up
python kast/scripts/cleanup_orphaned_resources.py --cleanup --dry-run
```

## Troubleshooting

### boto3 Not Installed

```
ERROR: boto3 not installed. Install with: pip install boto3
```

**Solution:** `pip install boto3`

### AWS Credentials Not Configured

```
ERROR: Failed to create AWS client: ...
```

**Solution:** Configure AWS credentials:
```bash
aws configure
# or
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
```

### No Resources Found

If the script finds no resources but you know they exist:

1. Check the correct region: `--region us-west-2`
2. Verify AWS credentials have read permissions
3. Check resource tags in AWS console

### Can't Delete Security Group

```
Error deleting resource: ... has a dependent object
```

**Cause:** EC2 instance still using the security group.

**Solution:** Delete EC2 instance first, then security group.

## Integration with KAST

This tool can be integrated into KAST workflows:

### Manual Cleanup After Failed Scan

```bash
# After a failed scan with known scan ID
python kast/scripts/cleanup_orphaned_resources.py --scan-id <scan-id> --cleanup
```

### Automated Cleanup (Future)

Could be integrated into:
- KAST error handlers
- Periodic cleanup jobs
- Pre-scan resource checks

## Cost Implications

Orphaned resources incur costs:

**EC2 Instances:**
- Spot: ~$0.01-0.05/hour (varies by type/region)
- On-demand: ~$0.05-0.20/hour

**Other Resources:**
- Security groups: Free
- Elastic IPs (if attached): ~$0.005/hour when not attached

**Example:** A single orphaned t3.medium spot instance left running for 24 hours costs ~$0.50-1.00.

## Best Practices

1. **Always dry-run first**: Test with `--dry-run` before actual cleanup
2. **Export before cleanup**: Keep audit trail with `--export`
3. **Use scan-specific cleanup**: When possible, target specific scan IDs
4. **Regular audits**: Run weekly checks for orphaned resources
5. **Monitor costs**: Check cloud billing for unexpected charges

## Limitations

1. **AWS Only**: Azure and GCP support not yet implemented
2. **Single Region**: Must scan each region separately
3. **Manual Invocation**: No automatic cleanup on scan failure (yet)
4. **VPC Deletion**: VPCs are not deleted (only noted)

## Future Enhancements

- [ ] Azure resource scanning and cleanup
- [ ] GCP resource scanning and cleanup
- [ ] Multi-region scanning in one command
- [ ] Automatic cleanup on scan failure
- [ ] VPC cleanup (with safety checks)
- [ ] Cost estimation before cleanup
- [ ] Slack/email notifications
- [ ] Integration with KAST orchestrator

## Related Documentation

- [ZAP Spot Fallback Feature](ZAP_SPOT_FALLBACK_FEATURE.md)
- [ZAP Cloud Plugin Guide](ZAP_CLOUD_PLUGIN_GUIDE.md)
- [Test Scripts README](../scripts/TEST_SCRIPTS_README.md)

## Support

For issues or questions:
1. Check this documentation
2. Review AWS console for resource status
3. Examine local state files in `test_output/`
4. Report bugs using `/reportbug` in KAST