# Infrastructure Test Scripts

## Overview

These test scripts allow you to test the Terraform infrastructure provisioning and teardown process independently from the full ZAP scan workflow.

## Scripts

### 1. monitor_zap.py

**Purpose:** Interactive monitor for ZAP scans with automatic infrastructure discovery.

**Usage:**
```bash
# Auto-discover ZAP URL from infrastructure state
python3 monitor_zap.py

# Specify ZAP URL manually
python3 monitor_zap.py --url http://34.220.11.146:8080

# One-time status check (non-interactive)
python3 monitor_zap.py --once

# Custom API key
python3 monitor_zap.py --api-key my-key

# Manual URL with one-time check
python3 monitor_zap.py --url http://34.220.11.146:8080 --once
```

**What it does:**
1. Auto-discovers ZAP URL from most recent infrastructure state file (searches `test_output/` and `output/` directories)
2. Connects to ZAP API
3. Displays real-time scan progress with visual progress bars
4. Shows alerts grouped by risk level (High, Medium, Low, Informational)
5. Interactive menu for viewing detailed alerts and generating reports

**Interactive Mode Features:**
- **[Enter]** - Refresh scan status
- **[a]** - Show all alerts with details
- **[r]** - Generate JSON report
- **[h]** - Show help menu
- **[q]** - Quit

**Example Output:**
```
🔍 Auto-discovering ZAP infrastructure...
✅ Found ZAP at http://34.220.11.146:8080 (deployed: 20251203_151754)

🔌 Connecting to http://34.220.11.146:8080...

  ZAP SCAN MONITOR

✅ Connected to ZAP at http://34.220.11.146:8080

----------------------------------------------------------------------
ZAP Version: 2.14.0
API URL: http://34.220.11.146:8080

📊 Scan Progress:
  Spider:      [████████████████░░░░░░░░░░░░░░] 55%
  Active Scan: [████████░░░░░░░░░░░░░░░░░░░░░░] 28%

  Status: 🔄 In Progress
  Alerts Found: 12

🚨 Alerts by Risk:
  🔴 High             3 finding(s)
  🟠 Medium           5 finding(s)
  🟡 Low              4 finding(s)
----------------------------------------------------------------------

Choice (h for help):
```

**Note:** Infrastructure must be running for monitoring to work.

---

### 2. find_zap_url.py

**Purpose:** Simple utility to find and print the ZAP API URL from infrastructure state.

**Usage:**
```bash
python3 find_zap_url.py
```

**Output:**
```
http://34.220.11.146:8080
```

**Exit Codes:**
- `0` - URL found and printed
- `1` - No infrastructure found

**Use Cases:**
```bash
# Save URL to variable
ZAP_URL=$(python3 find_zap_url.py)

# Use in curl commands
curl -s "$(python3 find_zap_url.py)/JSON/core/view/version/" | jq

# Check if infrastructure is running
if python3 find_zap_url.py > /dev/null 2>&1; then
    echo "ZAP infrastructure found"
fi
```

---

### 3. test_zap_scan.py

**Purpose:** Run a ZAP scan on already-provisioned infrastructure using the ZAP automation plan.

**Usage:**
```bash
python test_zap_scan.py <state_file> <target_url>
```

**Arguments:**
- `state_file` - Path to infrastructure state file from `test_infrastructure_provision.py`
- `target_url` - Target URL to scan (must start with http:// or https://)

**Example:**
```bash
# After provisioning infrastructure
python test_zap_scan.py /opt/kast/test_output/infra_test_aws_20251126_200617/infrastructure_state.txt https://example.com
```

**What it does:**
1. Loads infrastructure state (public IP, SSH details)
2. Loads cloud configuration
3. Prepares ZAP automation plan with target URL substitution
4. Connects to instance via SSH
5. Uploads automation plan to instance
6. Starts ZAP Docker container with automation framework
7. Waits for ZAP to be ready
8. Monitors scan progress with real-time status updates
9. Downloads results when scan completes
10. Displays summary of findings

**Output:**
- Results saved to: `test_output/zap_scan_TIMESTAMP/zap_report.json`
- Summary displayed in console with alert counts by risk level

**Note:** Infrastructure remains running after scan - use `test_infrastructure_teardown.py` to clean up.

---

### 2. test_infrastructure_provision.py
Provisions cloud infrastructure for testing without running a ZAP scan.

### 3. test_infrastructure_teardown.py
Tears down infrastructure created by the provision script.

## Prerequisites

1. **Terraform installed** and in PATH
2. **Python dependencies** installed: `pip install -r requirements.txt`
3. **Cloud credentials** configured (see below)

## Cloud Credentials Setup

### AWS
```bash
export AWS_ACCESS_KEY_ID="your_access_key"
export AWS_SECRET_ACCESS_KEY="your_secret_key"
```

### Azure
```bash
export AZURE_SUBSCRIPTION_ID="your_subscription_id"
export AZURE_TENANT_ID="your_tenant_id"
export AZURE_CLIENT_ID="your_client_id"
export AZURE_CLIENT_SECRET="your_client_secret"
```

### GCP
```bash
export GCP_PROJECT_ID="your_project_id"
# Ensure credentials file path is set in zap_cloud_config.yaml
```

## Usage

### Provisioning Infrastructure

Test AWS infrastructure:
```bash
cd kast/scripts
python test_infrastructure_provision.py aws
```

Test Azure infrastructure:
```bash
python test_infrastructure_provision.py azure
```

Test GCP infrastructure:
```bash
python test_infrastructure_provision.py gcp
```

**Expected Output:**
```
======================================================================
  Infrastructure Provisioning Test - AWS
======================================================================

  → Output directory: /path/to/test_output/infra_test_aws_20231126_195030

[Step 1] Loading cloud configuration
----------------------------------------------------------------------
  → Configuration loaded for provider: aws

[Step 2] Generating SSH keypair
----------------------------------------------------------------------
  → Generating SSH keypair...
  → SSH keypair saved to: /path/to/test_output/.../test_ssh_key

✓ SUCCESS: SSH keypair generated

[Step 3] Preparing Terraform variables
----------------------------------------------------------------------
  → Variables prepared for aws

[Step 4] Initializing Terraform manager
----------------------------------------------------------------------
  → Terraform found: Terraform v1.5.0

✓ SUCCESS: Terraform manager initialized

[Step 5] Provisioning infrastructure (this may take several minutes)
----------------------------------------------------------------------
  → Running: terraform init → plan → apply
  → Running terraform init...
  → Terraform init successful
  → Running terraform plan...
  → Terraform plan successful
  → Running terraform apply...
  → Terraform apply successful

✓ SUCCESS: Infrastructure provisioned successfully

[Step 6] Infrastructure outputs
----------------------------------------------------------------------
  → instance_id: i-0abc123def456...
  → public_ip: 54.123.45.67
  → vpc_id: vpc-0xyz789...
  → security_group_id: sg-0def456...
  → scan_identifier: kast-zap-a1b2c3d4
  → ssh_user: ubuntu
  → zap_api_url: http://54.123.45.67:8080

[Step 7] Saving state information
----------------------------------------------------------------------
  → State information saved to: /path/to/test_output/.../infrastructure_state.txt

======================================================================
  Provisioning Complete
======================================================================

✓ SUCCESS: AWS infrastructure is running

  → Public IP: 54.123.45.67
  → SSH User: ubuntu
  → ZAP API URL: http://54.123.45.67:8080

======================================================================
  IMPORTANT: Remember to run the teardown script to cleanup!
  python test_infrastructure_teardown.py /path/to/infrastructure_state.txt
======================================================================
```

### Tearing Down Infrastructure

#### Method 1: Using State File Path
After provisioning, the script provides the exact teardown command:
```bash
python test_infrastructure_teardown.py /path/to/test_output/.../infrastructure_state.txt
```

#### Method 2: Interactive Mode
List and select from available infrastructure:
```bash
python test_infrastructure_teardown.py
```

Interactive output:
```
======================================================================
  Interactive Teardown
======================================================================

  → Found 2 infrastructure state(s):

  [1] AWS - 20231126_195030
      /path/to/test_output/infra_test_aws_20231126_195030/infrastructure_state.txt

  [2] GCP - 20231126_200145
      /path/to/test_output/infra_test_gcp_20231126_200145/infrastructure_state.txt

  [0] Tear down ALL infrastructure
  [q] Quit

Select infrastructure to tear down: 1
```

#### Method 3: Tear Down All
Destroy all test infrastructure at once:
```bash
python test_infrastructure_teardown.py --all
```

With force flag (no confirmation):
```bash
python test_infrastructure_teardown.py --all --force
```

**Teardown Output:**
```
======================================================================
  Infrastructure Teardown
======================================================================

[Step 1] Loading infrastructure state
----------------------------------------------------------------------
  → Provider: aws
  → Terraform Directory: /path/to/test_output/.../terraform_aws

✓ SUCCESS: State information loaded

[Step 2] Verifying Terraform directory
----------------------------------------------------------------------

✓ SUCCESS: Terraform directory found

[Step 3] Confirmation
----------------------------------------------------------------------

⚠ WARNING: You are about to destroy cloud infrastructure!

  → Provider: aws
  → Terraform Directory: /path/to/test_output/.../terraform_aws

Are you sure you want to proceed? (yes/no): yes

✓ SUCCESS: Teardown confirmed

[Step 4] Initializing Terraform manager
----------------------------------------------------------------------

✓ SUCCESS: Terraform manager initialized

[Step 5] Destroying infrastructure (this may take several minutes)
----------------------------------------------------------------------
  → Running: terraform destroy
  → Running terraform destroy...
  → Terraform destroy successful

✓ SUCCESS: Infrastructure destroyed successfully

[Step 6] Cleaning up workspace
----------------------------------------------------------------------

✓ SUCCESS: Workspace cleaned up

[Step 7] Removing state info file
----------------------------------------------------------------------
  → Removed: /path/to/test_output/.../infrastructure_state.txt

======================================================================
  Teardown Complete
======================================================================

✓ SUCCESS: AWS infrastructure has been destroyed

  → All cloud resources have been removed

======================================================================
```

## Test Workflow

### Full Test Cycle

1. **Set environment variables** for your chosen cloud provider
2. **Provision infrastructure:**
   ```bash
   python test_infrastructure_provision.py aws
   ```
3. **Note the state file path** from the output
4. **Verify infrastructure** in cloud console (optional)
5. **Test SSH connection** (optional):
   ```bash
   ssh -i /path/to/test_ssh_key ubuntu@<public_ip>
   ```
6. **Tear down infrastructure:**
   ```bash
   python test_infrastructure_teardown.py /path/to/infrastructure_state.txt
   ```
7. **Verify cleanup** in cloud console (optional)

### Testing All Providers

Test each provider sequentially:
```bash
# AWS
python test_infrastructure_provision.py aws
# ... verify ...
python test_infrastructure_teardown.py --all --force

# Azure
python test_infrastructure_provision.py azure
# ... verify ...
python test_infrastructure_teardown.py --all --force

# GCP
python test_infrastructure_provision.py gcp
# ... verify ...
python test_infrastructure_teardown.py --all --force
```

## Files Created

### During Provisioning
```
test_output/
└── infra_test_<provider>_<timestamp>/
    ├── infrastructure_state.txt       # State information
    ├── test_ssh_key                   # Private SSH key (600 perms)
    ├── test_ssh_key.pub              # Public SSH key
    └── terraform_<provider>/         # Terraform workspace
        ├── main.tf
        ├── variables.tf
        ├── outputs.tf
        ├── terraform.tfvars
        ├── terraform.tfstate
        └── .terraform/
```

### After Teardown
All files are removed except for logs if any errors occurred.

## What Gets Tested

### Provisioning Test Verifies:
- ✅ Configuration loading
- ✅ SSH keypair generation
- ✅ Terraform variable preparation
- ✅ Terraform initialization
- ✅ Terraform plan creation
- ✅ Terraform apply execution
- ✅ Infrastructure outputs retrieval
- ✅ State file creation

### Teardown Test Verifies:
- ✅ State file loading
- ✅ Terraform directory verification
- ✅ User confirmation
- ✅ Terraform destroy execution
- ✅ Workspace cleanup
- ✅ State file removal

## Troubleshooting

### Provision Script Issues

**Error: Terraform not found**
```
✗ ERROR: Terraform is not installed or not in PATH
```
Solution: Install Terraform and add to PATH

**Error: Environment variable not set**
```
✗ ERROR: Environment variable not set: AWS_ACCESS_KEY_ID
```
Solution: Set required environment variables

**Error: Terraform apply failed**
```
✗ ERROR: Infrastructure provisioning failed
```
Solution: Check Terraform logs in the terraform_* directory, verify credentials and permissions

### Teardown Script Issues

**Error: State file not found**
```
✗ ERROR: State file not found: /path/to/infrastructure_state.txt
```
Solution: Verify the path or use interactive mode

**Error: Terraform directory not found**
```
✗ ERROR: Terraform directory not found
```
Solution: Infrastructure may have already been destroyed, check cloud console

**Warning: Infrastructure may still be running**
```
⚠ WARNING: Infrastructure may still be running - check cloud console
```
Solution: Manually verify and delete resources in cloud console if needed

## Manual Cleanup

If scripts fail to clean up infrastructure:

### AWS
```bash
# Find resources by tag
aws ec2 describe-instances --filters "Name=tag:Project,Values=KAST"
aws ec2 describe-vpcs --filters "Name=tag:Project,Values=KAST"

# Terminate instances
aws ec2 terminate-instances --instance-ids <instance-id>

# Delete VPC and associated resources
aws ec2 delete-vpc --vpc-id <vpc-id>
```

### Azure
```bash
# List resource groups
az group list --query "[?tags.Project=='KAST']"

# Delete resource group
az group delete --name <resource-group-name> --yes
```

### GCP
```bash
# List instances
gcloud compute instances list --filter="labels.project=kast"

# Delete instance
gcloud compute instances delete <instance-name> --zone=<zone>

# Delete network
gcloud compute networks delete <network-name>
```

## Integration with CI/CD

### Example: GitLab CI
```yaml
test_infrastructure:
  stage: test
  script:
    - cd kast/scripts
    - python test_infrastructure_provision.py aws
    - python test_infrastructure_teardown.py --all --force
  only:
    - merge_requests
```

### Example: GitHub Actions
```yaml
- name: Test Infrastructure
  run: |
    cd kast/scripts
    python test_infrastructure_provision.py aws
    python test_infrastructure_teardown.py --all --force
```

## Cost Considerations

Each provisioning test creates billable resources:
- **Duration**: Typically 5-15 minutes for provision + teardown
- **Cost**: ~$0.01-0.02 per test (spot/preemptible instances)
- **Important**: Always run teardown to avoid ongoing charges

## Best Practices

1. **Always tear down** after testing
2. **Use interactive mode** if you've lost track of running infrastructure
3. **Check cloud console** after teardown to verify cleanup
4. **Set billing alerts** in your cloud provider
5. **Test one provider at a time** to avoid confusion
6. **Save state file paths** if testing multiple simultaneously
7. **Use --force flag** in automated testing to skip confirmations

## Support

For issues:
- Check Terraform logs in the terraform_* directory
- Enable debug output by examining script source
- Verify cloud credentials and permissions
- Check cloud provider console for resource status
- Review the main ZAP plugin documentation
