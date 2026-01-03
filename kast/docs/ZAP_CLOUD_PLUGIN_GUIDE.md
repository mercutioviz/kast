# OWASP ZAP Cloud Plugin Guide

## Overview

The OWASP ZAP Cloud Plugin for KAST provides automated web application security scanning using OWASP ZAP deployed on ephemeral cloud infrastructure. This plugin mimics a CI/CD pipeline by:

1. Provisioning cloud infrastructure (AWS, Azure, or GCP)
2. Deploying OWASP ZAP in a Docker container
3. Running automated security scans using ZAP Automation Framework
4. Collecting and processing scan results
5. Tearing down infrastructure automatically

> **Note**: This guide focuses on Cloud Mode. The ZAP plugin now supports multiple execution modes (local, remote, cloud). See [ZAP Multi-Mode Guide](ZAP_MULTI_MODE_GUIDE.md) for a comprehensive overview of all modes.

## Multi-Mode Support

The ZAP plugin has evolved from a cloud-only solution to support three execution modes:

- **Local Mode**: Fast Docker-based scanning for development (no cloud costs)
- **Remote Mode**: Connect to existing ZAP instances for CI/CD
- **Cloud Mode**: This guide - isolated ephemeral infrastructure

All modes use the **ZAP Automation Framework** by default for consistent, repeatable scans.

## Features

- **Multi-cloud Support**: Deploy to AWS, Azure, or GCP
- **Cost Optimization**: Uses spot/preemptible instances for reduced costs
- **Ephemeral Infrastructure**: Automatically provisions and tears down resources
- **ZAP Automation Framework**: Uses YAML-based automation plans for reproducible scans (default for all modes)
- **YAML Validation**: Automation plans are validated before execution
- **CLI Overrides**: Customize scans via command line without editing config files
- **CI/CD Ready**: Designed for integration into automated security pipelines
- **Secure**: SSH key-based authentication, isolated VPC/VNet
- **Comprehensive Reporting**: Integrates with KAST's HTML/PDF reporting system

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      KAST Orchestrator                       │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     ZAP Cloud Plugin                         │
├─────────────────────────────────────────────────────────────┤
│  1. Load Configuration (zap_cloud_config.yaml)              │
│  2. Generate SSH Keypair                                     │
│  3. Provision Infrastructure (Terraform)                     │
│  4. Connect via SSH                                          │
│  5. Start ZAP Docker Container                              │
│  6. Run Automation Framework Scan                           │
│  7. Monitor Progress via ZAP API                            │
│  8. Download Results                                         │
│  9. Teardown Infrastructure                                  │
│ 10. Post-process Results                                     │
└─────────────────────────────────────────────────────────────┘
           │                │                │
           ▼                ▼                ▼
    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │   AWS    │    │  Azure   │    │   GCP    │
    │ Spot EC2 │    │ Spot VM  │    │ Preempt  │
    └────┬─────┘    └────┬─────┘    └────┬─────┘
         │               │               │
         └───────────────┴───────────────┘
                         │
                         ▼
                  ┌──────────────┐
                  │ ZAP Docker   │
                  │  Container   │
                  └──────────────┘
```

## Prerequisites

### Required Tools

1. **Terraform** (>= 1.0.0)
   ```bash
   # Installation varies by OS
   # Ubuntu/Debian
   wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
   echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
   sudo apt update && sudo apt install terraform
   ```

2. **Python Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

### Cloud Provider Setup

#### AWS
- **AWS CLI Installed and Configured**
  ```bash
  # Install AWS CLI
  sudo apt-get install awscli
  
  # Configure credentials
  aws configure
  # Enter: AWS Access Key ID, Secret Access Key, Region, Output format
  ```
- IAM user with appropriate permissions:
  - EC2 (create/delete instances, VPC, security groups)
  - EC2 Spot instances
- Credentials automatically resolved from:
  - AWS CLI configuration (~/.aws/credentials)
  - Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
  - IAM instance profiles (if running on EC2)

#### Azure
- Service Principal with Contributor role
- Subscription ID, Tenant ID, Client ID, Client Secret
- Permissions needed:
  - Resource Groups
  - Virtual Networks
  - Virtual Machines
  - Network Security Groups

#### GCP
- Service Account with appropriate roles
- Service account JSON key file
- Permissions needed:
  - Compute Engine Admin
  - Compute Network Admin

## Configuration

### 1. Cloud Configuration File

Edit `kast/config/zap_cloud_config.yaml`:

```yaml
# Select cloud provider: aws, azure, or gcp
cloud_provider: aws

# AWS Configuration
# Note: AWS credentials are automatically resolved using AWS CLI configuration
# from ~/.aws/credentials or environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
# Run 'aws configure' to set up credentials
aws:
  region: us-west-2
  instance_type: t3.xlarge
  ami_id: ""  # Leave empty to use default Ubuntu 22.04 LTS
  spot_max_price: "0.10"

# Azure Configuration (if using Azure)
azure:
  subscription_id: ${AZURE_SUBSCRIPTION_ID}
  tenant_id: ${AZURE_TENANT_ID}
  client_id: ${AZURE_CLIENT_ID}
  client_secret: ${AZURE_CLIENT_SECRET}
  region: eastus
  vm_size: Standard_B2s
  spot_enabled: true

# GCP Configuration (if using GCP)
gcp:
  project_id: ${GCP_PROJECT_ID}
  credentials_file: /path/to/service-account-key.json
  region: us-central1
  zone: us-central1-a
  machine_type: n1-standard-2
  preemptible: true

# ZAP Configuration
zap_config:
  docker_image: ghcr.io/zaproxy/zaproxy:stable
  api_port: 8080
  api_key: null  # Set if ZAP requires API key
  automation_plan: kast/config/zap_automation_plan.yaml  # Path to automation plan
  report_name: zap_report.json
  timeout_minutes: 60
  poll_interval_seconds: 30
  ssh_timeout_seconds: 300
  ssh_retry_attempts: 5

# Cloud mode automation framework (default: true)
cloud:
  use_automation_framework: true  # Use YAML-based automation (recommended)

# Resource Tags/Labels
tags:
  Project: KAST
  ManagedBy: KAST-ZAP-Plugin
  Environment: security-scan
```

### 2. ZAP Automation Plan

Edit `kast/config/zap_automation_plan.yaml` to customize the scan:

```yaml
env:
  contexts:
    - name: "KAST Security Scan"
      urls:
        - "${TARGET_URL}"
      includePaths:
        - ".*"
      excludePaths: []
      authentication:
        method: "manual"
      sessionManagement:
        method: "cookie"

jobs:
  - type: spider
    parameters:
      maxDuration: 10
      maxDepth: 5
      maxChildren: 10
    
  - type: passiveScan-wait
    parameters:
      maxDuration: 5
  
  - type: activeScan
    parameters:
      policy: "Default Policy"
      maxRuleDurationInMins: 5
      maxScanDurationInMins: 30
  
  - type: report
    parameters:
      template: "traditional-json"
      reportDir: "/zap/reports"
      reportFile: "zap_report.json"
```

### 3. Environment Variables

Set credentials as environment variables for security:

```bash
# AWS
export AWS_ACCESS_KEY_ID="your_access_key"
export AWS_SECRET_ACCESS_KEY="your_secret_key"

# Azure
export AZURE_SUBSCRIPTION_ID="your_subscription_id"
export AZURE_TENANT_ID="your_tenant_id"
export AZURE_CLIENT_ID="your_client_id"
export AZURE_CLIENT_SECRET="your_client_secret"

# GCP
export GCP_PROJECT_ID="your_project_id"
```

## Usage

### Basic Scan

```bash
# Cloud mode (if configured as default)
python kast/main.py --target https://example.com --plugins zap

# Explicitly force cloud mode
# Edit zap_config.yaml: execution_mode: cloud
python kast/main.py --target https://example.com --plugins zap
```

### With Debug Output

```bash
python kast/main.py --target https://example.com --plugins zap --debug
```

### Custom Automation Plan

```bash
# Override automation plan path via CLI
python kast/main.py --target https://example.com --plugins zap \
  --config zap.zap_config.automation_plan=/path/to/custom_plan.yaml
```

### Disable Automation Framework

```bash
# Use direct API calls instead of automation framework
python kast/main.py --target https://example.com --plugins zap \
  --config zap.cloud.use_automation_framework=false
```

### Report Only Mode

```bash
python kast/main.py --target https://example.com --plugins zap --report-only
```

### Multiple Plugins

```bash
python kast/main.py --target https://example.com --plugins whatweb,testssl,zap
```

## How It Works

### Step-by-Step Process

1. **Configuration Loading**
   - Loads `zap_cloud_config.yaml`
   - Expands environment variables
   - Validates configuration

2. **SSH Key Generation**
   - Generates ephemeral RSA keypair
   - Private key stored in output directory
   - Public key used for instance access

3. **Infrastructure Provisioning**
   - Terraform prepares workspace
   - Copies provider-specific Terraform files
   - Creates `terraform.tfvars` with configuration
   - Runs `terraform init`, `plan`, and `apply`
   - Provisions:
     - VPC/VNet with subnet
     - Security groups/NSG (SSH, ZAP API access)
     - Spot/preemptible instance with Docker
     - Elastic/Static IP address

4. **SSH Connection**
   - Waits for instance to be ready
   - Establishes SSH connection with retry logic
   - Verifies instance readiness flag

5. **ZAP Container Deployment**
   - Uploads customized automation plan via SSH
   - Validates automation plan YAML structure
   - Starts ZAP Docker container
   - Mounts volumes for config and reports
   - Executes ZAP Automation Framework
   - **Note**: If automation plan is invalid or missing, scan fails (no fallback to API)

6. **Scan Monitoring**
   - Connects to ZAP API
   - Polls scan status periodically
   - Reports progress to KAST

7. **Results Collection**
   - Downloads JSON report via SSH/SFTP
   - Saves to KAST output directory

8. **Infrastructure Teardown**
   - Closes SSH connection
   - Runs `terraform destroy`
   - Removes all cloud resources
   - Cleans up Terraform workspace

9. **Post-Processing**
   - Parses ZAP alerts
   - Groups by risk level
   - Generates executive summary
   - Integrates with KAST report

## Troubleshooting

### Common Issues

#### 1. Terraform Not Found
```
Error: Terraform is not installed or not in PATH
```
**Solution**: Install Terraform and ensure it's in your PATH

#### 2. SSH Connection Timeout
```
Error: SSH connection failed
```
**Solutions**:
- Check security group allows SSH from your IP
- Verify instance is running and ready
- Increase `ssh_timeout_seconds` in config
- Check SSH key permissions (should be 600)

#### 3. ZAP Container Fails to Start
```
Error: Failed to start ZAP
```
**Solutions**:
- Verify Docker is installed on instance
- Check Docker image is accessible
- Review cloud-init logs on instance
- Increase instance size if out of memory

#### 4. Scan Timeout
```
Error: Scan timeout
```
**Solutions**:
- Increase `timeout_minutes` in config
- Reduce scan scope in automation plan
- Use more powerful instance type

#### 5. Infrastructure Provisioning Fails
```
Error: Infrastructure provisioning failed
```
**Solutions**:
- Verify cloud credentials are correct
- Check IAM/permissions
- Review Terraform logs in output directory
- Ensure quota limits not exceeded

### Debug Mode

Enable debug mode for detailed logging:

```bash
python kast/main.py --target https://example.com --plugins zap --debug
```

Debug output includes:
- Terraform commands and output
- SSH connection attempts
- ZAP API requests
- Scan progress updates

### Manual Cleanup

If infrastructure isn't properly torn down:

```bash
cd /path/to/output/dir/terraform_<provider>
terraform destroy -auto-approve
```

## Cost Considerations

### Estimated Costs (per scan)

**AWS** (t3.medium spot in us-east-1):
- Instance: ~$0.01-0.03/hour
- EIP: $0.005/hour
- Data transfer: minimal
- **Typical 1-hour scan: $0.02-0.05**

**Azure** (Standard_B2s spot in eastus):
- Instance: ~$0.01-0.04/hour
- Public IP: $0.005/hour
- **Typical 1-hour scan: $0.02-0.06**

**GCP** (n1-standard-2 preemptible in us-central1):
- Instance: ~$0.02-0.05/hour
- External IP: $0.004/hour
- **Typical 1-hour scan: $0.03-0.07**

### Cost Optimization

1. **Use Spot/Preemptible Instances**: Already configured by default
2. **Limit Scan Duration**: Set appropriate timeouts
3. **Scope Scans Properly**: Exclude unnecessary paths
4. **Cleanup on Failure**: Plugin attempts automatic cleanup
5. **Monitor Usage**: Set cloud provider billing alerts

## Security Considerations

### Best Practices

1. **Credentials Management**
   - Use environment variables for secrets
   - Never commit credentials to version control
   - Rotate credentials regularly
   - Use least-privilege IAM policies

2. **Network Security**
   - Security groups restrict access to SSH and ZAP API
   - Consider restricting source IP ranges
   - Use VPN or bastion host for production

3. **Data Handling**
   - Scan reports may contain sensitive findings
   - Secure output directory permissions
   - Delete SSH keys after use
   - Review reports before sharing

4. **Scan Targets**
   - Only scan authorized targets
   - Obtain permission for active scanning
   - Follow responsible disclosure practices
   - Respect rate limits and terms of service

## Advanced Configuration

### Automation Framework Customization

All ZAP modes now use the automation framework by default. Customize your scans by editing the automation plan:

#### Custom Automation Plans

Create custom automation plans for specific scenarios:

```yaml
# Authenticated scan
env:
  contexts:
    - name: "Authenticated Scan"
      urls:
        - "${TARGET_URL}"
      authentication:
        method: "form"
        parameters:
          loginUrl: "${TARGET_URL}/login"
          loginRequestData: "username={%username%}&password={%password%}"
```

#### Deeper Scans

```yaml
jobs:
  - type: spider
    parameters:
      maxDuration: 20  # Increased from default 10
      maxDepth: 10     # Increased from default 5
      
  - type: activeScan
    parameters:
      maxScanDurationInMins: 60  # Increased from default 30
      threadPerHost: 4            # Increased from default 2
```

#### Exclude Sensitive Paths

```yaml
env:
  contexts:
    - name: "Production Scan"
      excludePaths:
        - ".*logout.*"
        - ".*admin.*"
        - ".*delete.*"  # Protect against destructive actions
```

### Automation Plan Validation

The plugin validates automation plans before execution:

- ✅ Valid YAML syntax
- ✅ Required sections present (`env`, `jobs`)
- ✅ Each job has required fields
- ❌ Invalid plans cause scan to fail immediately

This ensures consistent, reliable scans across all environments.

### Multiple Scan Profiles

Maintain different configs for different environments:

```bash
# Development
cp zap_cloud_config_dev.yaml zap_cloud_config.yaml

# Production
cp zap_cloud_config_prod.yaml zap_cloud_config.yaml
```

### Custom Docker Images

Build custom ZAP images with additional plugins:

```yaml
zap_config:
  docker_image: myregistry/custom-zap:latest
```

## Integration with CI/CD

### GitLab CI Example

```yaml
security_scan:
  stage: security
  script:
    - pip install -r requirements.txt
    - python kast/main.py --target $TARGET_URL --plugins zap
  artifacts:
    paths:
      - output/
    expire_in: 30 days
  only:
    - schedules
```

### GitHub Actions Example

```yaml
name: Security Scan
on:
  schedule:
    - cron: '0 0 * * 0'  # Weekly

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run KAST with ZAP
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        run: |
          python kast/main.py --target ${{ secrets.TARGET_URL }} --plugins zap
      - name: Upload results
        uses: actions/upload-artifact@v2
        with:
          name: scan-results
          path: output/
```

## Related Documentation

- **[ZAP Multi-Mode Guide](ZAP_MULTI_MODE_GUIDE.md)**: Comprehensive guide to all ZAP modes (local, remote, cloud)
- **[ZAP Multi-Mode Implementation](ZAP_MULTI_MODE_IMPLEMENTATION.md)**: Technical implementation details
- **KAST Main Documentation**: General KAST usage and configuration

## Support

For issues and questions:
- Review this documentation and related guides
- Check KAST main documentation
- Enable debug mode for detailed logs
- Review cloud provider documentation
- Check ZAP documentation: https://www.zaproxy.org/docs/
- Check ZAP Automation Framework docs: https://www.zaproxy.org/docs/automate/automation-framework/

## License

This plugin is part of KAST and follows the same license.
