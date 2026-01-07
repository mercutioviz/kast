# ZAP Plugin Testing Plan

## Overview

This document provides a comprehensive, step-by-step testing plan for the OWASP ZAP multi-mode plugin. The plugin supports three execution modes:
- **Local Mode**: Docker-based local scanning
- **Remote Mode**: Existing ZAP instance connectivity
- **Cloud Mode**: Ephemeral cloud infrastructure (AWS/Azure/GCP)

## Testing Goals

1. Verify each provider mode works independently
2. Confirm auto-discovery logic functions correctly
3. Validate backward compatibility with legacy configurations
4. Ensure proper error handling and cleanup
5. Test integration with KAST reporting system
6. Benchmark performance across modes

---

## Prerequisites

### General Requirements

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Verify KAST installation
python kast/main.py --help

# 3. Prepare test targets
# Safe testing targets:
# - http://testphp.vulnweb.com (intentionally vulnerable test site)
# - https://httpbin.org/html (safe API testing endpoint)
# - Your own test server
```

### Mode-Specific Prerequisites

#### Local Mode Setup
```bash
# Verify Docker installation
docker --version

# Pull ZAP Docker image
docker pull ghcr.io/zaproxy/zaproxy:stable

# Verify image
docker images | grep zaproxy
```

#### Remote Mode Setup
```bash
# Start a test ZAP instance
docker run -d --name zap-test \
  -p 8080:8080 \
  ghcr.io/zaproxy/zaproxy:stable \
  zap.sh -daemon -port 8080 \
  -config api.key=test-key \
  -config api.addrs.addr.name=.* \
  -config api.filexfer=true \
  -config api.addrs.addr.regex=true

# Verify ZAP is running
curl http://localhost:8080/JSON/core/view/version/?apikey=test-key
```

#### Cloud Mode Setup
```bash
# Install Terraform
terraform --version  # Should be >= 1.0

# AWS Setup
export AWS_ACCESS_KEY_ID="your_access_key"
export AWS_SECRET_ACCESS_KEY="your_secret_key"
export AWS_DEFAULT_REGION="us-east-1"

# Verify AWS credentials
aws sts get-caller-identity

# Azure Setup (optional)
export ARM_SUBSCRIPTION_ID="your_subscription_id"
export ARM_TENANT_ID="your_tenant_id"
export ARM_CLIENT_ID="your_client_id"
export ARM_CLIENT_SECRET="your_client_secret"

# GCP Setup (optional)
export GOOGLE_CREDENTIALS="path/to/service-account.json"
export GOOGLE_PROJECT="your_project_id"
```

---

## Phase 1: Local Mode Testing

### Test 1.1: Basic Local Scan with Auto-Start

**Objective**: Verify local mode can automatically start a ZAP container and perform a scan

**Prerequisites**: 
- Docker installed and running
- No existing ZAP containers

**Steps**:
```bash
# 1. Clean environment
docker stop $(docker ps -q --filter ancestor=ghcr.io/zaproxy/zaproxy) 2>/dev/null || true
docker rm $(docker ps -a -q --filter ancestor=ghcr.io/zaproxy/zaproxy) 2>/dev/null || true

# 2. Ensure config is set to local or auto mode
# Edit kast/config/zap_config.yaml:
# execution_mode: local  # or auto

# 3. Run scan with debug output
python kast/main.py \
  --target http://testphp.vulnweb.com \
  --run-only zap \
  --output-dir test_output/local_autostart \
  --debug

# 4. Check container status
docker ps | grep zaproxy
```

**Expected Results**:
- ✅ Debug message: "Starting local ZAP container: kast-zap-local"
- ✅ Debug message: "ZAP container started successfully"
- ✅ Debug message: "ZAP API ready"
- ✅ Scan completes without errors
- ✅ HTML report generated in `test_output/local_autostart/`
- ✅ Container remains running (default: `cleanup_on_completion: false`)
- ✅ Report includes mode info: "provider_mode: local"

**Success Criteria**:
- Exit code: 0
- Report file exists
- Container still running: `docker ps | grep kast-zap-local`

---

### Test 1.2: Local Scan with Container Reuse

**Objective**: Verify local mode can detect and reuse an existing container

**Prerequisites**: 
- ZAP container running from Test 1.1

**Steps**:
```bash
# 1. Verify container is running
docker ps | grep kast-zap-local

# 2. Run another scan
python kast/main.py \
  --target https://httpbin.org/html \
  --run-only zap \
  --output-dir test_output/local_reuse \
  --debug

# 3. Check that no new container was created
docker ps -a | grep kast-zap-local | wc -l  # Should be 1
```

**Expected Results**:
- ✅ Debug message: "Found running ZAP container: kast-zap-local"
- ✅ Debug message: "Using existing ZAP container"
- ✅ Scan starts faster (~10-15 seconds vs 30-45 seconds)
- ✅ No new container created
- ✅ Report generated successfully

**Success Criteria**:
- Only one container exists
- Scan completes in < 1 minute
- Report generated

---

### Test 1.3: Local Scan with Cleanup Enabled

**Objective**: Verify container cleanup functionality

**Prerequisites**:
- Clean environment (no ZAP containers)

**Steps**:
```bash
# 1. Clean environment
docker stop kast-zap-local 2>/dev/null || true
docker rm kast-zap-local 2>/dev/null || true

# 2. Edit config to enable cleanup
# kast/config/zap_config.yaml:
# local:
#   cleanup_on_completion: true

# 3. Run scan
python kast/main.py \
  --target http://testphp.vulnweb.com \
  --run-only zap \
  --output-dir test_output/local_cleanup \
  --debug

# 4. Check container status immediately after
docker ps -a | grep kast-zap-local
```

**Expected Results**:
- ✅ Container starts successfully
- ✅ Scan completes
- ✅ Debug message: "Stopping container: kast-zap-local"
- ✅ Container is stopped and removed
- ✅ No container exists after scan

**Success Criteria**:
- `docker ps -a | grep kast-zap-local` returns nothing
- Report generated successfully
- Exit code: 0

---

### Test 1.4: Local Mode Error Handling

**Objective**: Verify graceful error handling when Docker is unavailable

**Prerequisites**:
- Ability to stop Docker service (requires sudo)

**Steps**:
```bash
# 1. Stop Docker
sudo systemctl stop docker

# 2. Attempt scan
python kast/main.py \
  --target http://testphp.vulnweb.com \
  --run-only zap \
  --output-dir test_output/local_error \
  --debug

# 3. Restore Docker
sudo systemctl start docker
```

**Expected Results**:
- ✅ Error message: "Docker not available"
- ✅ Plugin fails gracefully (no crash)
- ✅ Clear error message in output
- ✅ No hanging processes

**Success Criteria**:
- Exit code: non-zero
- Error message displayed
- No system crash or hang

---

## Phase 2: Remote Mode Testing

### Test 2.1: Remote Mode with Environment Variables

**Objective**: Verify remote mode connects to existing ZAP instance using environment variables

**Prerequisites**:
- ZAP instance running on localhost:8080

**Steps**:
```bash
# 1. Ensure ZAP test instance is running
docker ps | grep zap-test || docker start zap-test

# 2. Set environment variables
export KAST_ZAP_URL="http://localhost:8080"
export KAST_ZAP_API_KEY="test-key"

# 3. Run scan
python kast/main.py \
  --target http://testphp.vulnweb.com \
  --run-only zap \
  --output-dir test_output/remote_env \
  --debug

# 4. Cleanup
unset KAST_ZAP_URL
unset KAST_ZAP_API_KEY
```

**Expected Results**:
- ✅ Debug message: "Connecting to remote ZAP instance..."
- ✅ Debug message: "Connecting to http://localhost:8080"
- ✅ Debug message: "Remote mode: Will use API-based scanning"
- ✅ No provisioning delay (scan starts immediately)
- ✅ Scan completes in < 1 minute
- ✅ Report shows mode: "remote"

**Success Criteria**:
- Total scan time < 2 minutes
- No local container created
- Report generated with remote mode indicated

---

### Test 2.2: Remote Mode with Config File

**Objective**: Verify remote mode using configuration file settings

**Prerequisites**:
- ZAP test instance running

**Steps**:
```bash
# 1. Edit kast/config/zap_config.yaml:
# execution_mode: remote
# remote:
#   api_url: "http://localhost:8080"
#   api_key: "test-key"
#   timeout_seconds: 30

# 2. Ensure no environment variables are set
unset KAST_ZAP_URL
unset KAST_ZAP_API_KEY

# 3. Run scan
python kast/main.py \
  --target https://httpbin.org/html \
  --run-only zap \
  --output-dir test_output/remote_config \
  --debug
```

**Expected Results**:
- ✅ Config file settings used
- ✅ Connection successful
- ✅ Scan completes
- ✅ Report generated

**Success Criteria**:
- Scan completes without errors
- Report shows correct mode

---

### Test 2.3: Remote Mode Error - Invalid URL

**Objective**: Verify error handling for unreachable ZAP instance

**Steps**:
```bash
# 1. Set invalid URL
export KAST_ZAP_URL="http://localhost:9999"  # Wrong port
export KAST_ZAP_API_KEY="test-key"

# 2. Attempt scan
python kast/main.py \
  --target http://testphp.vulnweb.com \
  --run-only zap \
  --output-dir test_output/remote_error \
  --debug

# 3. Cleanup
unset KAST_ZAP_URL
unset KAST_ZAP_API_KEY
```

**Expected Results**:
- ✅ Error message: "Cannot connect to http://localhost:9999"
- ✅ Plugin fails gracefully
- ✅ Clear error message
- ✅ No hanging connections

**Success Criteria**:
- Exit code: non-zero
- Meaningful error message
- No system hang

---

## Phase 3: Cloud Mode Testing

### Test 3.1: Cloud Mode - AWS Full End-to-End

**Objective**: Verify complete cloud provisioning workflow with AWS

**Prerequisites**:
- AWS credentials configured
- Terraform installed
- Budget: ~$0.10-0.20 for test (spot instance for ~10-15 minutes)

**Steps**:
```bash
# 1. Verify AWS credentials
aws sts get-caller-identity

# 2. Edit kast/config/zap_config.yaml:
# execution_mode: cloud
# cloud:
#   cloud_provider: aws
#   aws:
#     region: us-east-1
#     instance_type: t3.medium

# 3. Run scan (will take 5-10 minutes)
time python kast/main.py \
  --target http://testphp.vulnweb.com \
  --run-only zap \
  --output-dir test_output/cloud_aws \
  --debug 2>&1 | tee cloud_aws_test.log

# 4. Verify cleanup in AWS Console
# - Check EC2 instances: none should remain
# - Check VPCs: none with "kast" tag should remain
# - Check Security Groups: none should remain
```

**Expected Results**:
- ✅ Debug: "Generating SSH keypair..."
- ✅ Debug: "Initializing Terraform..."
- ✅ Debug: "Applying Terraform configuration..."
- ✅ Debug: "Infrastructure provisioned - Instance IP: X.X.X.X"
- ✅ Debug: "SSH connection established"
- ✅ Debug: "Starting ZAP container on remote instance..."
- ✅ Debug: "ZAP API ready"
- ✅ Scan completes
- ✅ Debug: "Report downloaded to..."
- ✅ Debug: "Running Terraform destroy..."
- ✅ Debug: "Infrastructure destroyed successfully"
- ✅ Debug: "Temporary files cleaned up"

**Success Criteria**:
- Total time: 5-15 minutes
- Exit code: 0
- Report generated
- AWS Console shows no leftover resources
- Temp directory cleaned: check `/tmp/kast_zap_*` (should not exist)

**Verification Checklist**:
```bash
# After test completes, verify cleanup:
# 1. Check for temp directories
ls -la /tmp/ | grep kast_zap

# 2. Check Terraform state
ls test_output/cloud_aws/terraform_workspace/

# 3. Check AWS resources (via CLI)
aws ec2 describe-instances --filters "Name=tag:Project,Values=KAST" --query 'Reservations[*].Instances[*].[InstanceId,State.Name]'
aws ec2 describe-vpcs --filters "Name=tag:Project,Values=KAST" --query 'Vpcs[*].[VpcId]'
```

---

### Test 3.2: Cloud Mode - Backward Compatibility

**Objective**: Verify legacy cloud configuration still works

**Prerequisites**:
- AWS credentials configured
- Legacy config file: `kast/config/zap_cloud_config.yaml`

**Steps**:
```bash
# 1. Verify legacy config exists
cat kast/config/zap_cloud_config.yaml

# 2. The plugin should auto-detect and use legacy config
# No config changes needed

# 3. Run scan
python kast/main.py \
  --target http://testphp.vulnweb.com \
  --run-only zap \
  --output-dir test_output/cloud_legacy \
  --debug 2>&1 | tee cloud_legacy_test.log
```

**Expected Results**:
- ✅ Plugin detects legacy config
- ✅ Debug message about using legacy configuration
- ✅ All cloud functionality works
- ✅ Scan completes successfully
- ✅ Cleanup runs properly

**Success Criteria**:
- Works identically to Test 3.1
- No errors related to configuration format
- Backward compatibility maintained

---

### Test 3.3: Cloud Mode - Error Recovery and Cleanup

**Objective**: Verify infrastructure cleanup occurs even when scan fails

**Prerequisites**:
- AWS credentials configured

**Steps**:
```bash
# 1. Use an invalid target URL to force scan failure
python kast/main.py \
  --target http://invalid-nonexistent-domain-12345.com \
  --run-only zap \
  --output-dir test_output/cloud_error \
  --debug 2>&1 | tee cloud_error_test.log

# 2. Verify cleanup in AWS Console
# Check that no resources remain
```

**Expected Results**:
- ✅ Infrastructure provisions successfully
- ✅ Scan fails (expected - invalid target)
- ✅ Cleanup still runs
- ✅ Debug: "Running Terraform destroy..."
- ✅ All AWS resources cleaned up

**Success Criteria**:
- Exit code: non-zero (scan failed)
- AWS Console shows no leftover resources
- Terraform destroy completed successfully

---

### Test 3.4: Cloud Mode - Azure (Optional)

**Objective**: Verify multi-cloud support with Azure

**Prerequisites**:
- Azure credentials configured
- Budget: ~$0.10-0.20 for test

**Steps**:
```bash
# 1. Set Azure credentials
export ARM_SUBSCRIPTION_ID="your_subscription"
export ARM_TENANT_ID="your_tenant"
export ARM_CLIENT_ID="your_client"
export ARM_CLIENT_SECRET="your_secret"

# 2. Edit config for Azure
# cloud:
#   cloud_provider: azure
#   azure:
#     location: eastus
#     vm_size: Standard_B2s

# 3. Run scan
python kast/main.py \
  --target http://testphp.vulnweb.com \
  --run-only zap \
  --output-dir test_output/cloud_azure \
  --debug 2>&1 | tee cloud_azure_test.log
```

**Expected Results**:
- Similar to AWS test (Test 3.1)
- Azure-specific resources created and cleaned up

**Success Criteria**:
- Scan completes
- Azure Portal shows no leftover resources

---

## Phase 4: Auto-Discovery Testing

### Test 4.1: Auto-Discovery - Remote Priority

**Objective**: Verify remote mode takes priority when KAST_ZAP_URL is set

**Prerequisites**:
- ZAP test instance running
- Docker available

**Steps**:
```bash
# 1. Set config to auto mode
# execution_mode: auto

# 2. Set environment variable
export KAST_ZAP_URL="http://localhost:8080"
export KAST_ZAP_API_KEY="test-key"

# 3. Run scan
python kast/main.py \
  --target http://testphp.vulnweb.com \
  --run-only zap \
  --output-dir test_output/auto_remote \
  --debug

# 4. Cleanup
unset KAST_ZAP_URL
unset KAST_ZAP_API_KEY
```

**Expected Results**:
- ✅ Auto-discovery selects remote mode
- ✅ Debug: "Auto-discovery: Using remote provider (KAST_ZAP_URL set)"
- ✅ Connects to localhost:8080
- ✅ No local container created

**Success Criteria**:
- Remote mode used (not local)
- Report indicates mode: "remote"

---

### Test 4.2: Auto-Discovery - Local Fallback

**Objective**: Verify local mode selected when Docker available and no env var

**Prerequisites**:
- Docker available
- No KAST_ZAP_URL environment variable

**Steps**:
```bash
# 1. Ensure no environment variable
unset KAST_ZAP_URL

# 2. Config set to auto
# execution_mode: auto

# 3. Run scan
python kast/main.py \
  --target http://testphp.vulnweb.com \
  --run-only zap \
  --output-dir test_output/auto_local \
  --debug
```

**Expected Results**:
- ✅ Auto-discovery selects local mode
- ✅ Debug: "Auto-discovery: Using local provider (Docker available)"
- ✅ Local container created or reused

**Success Criteria**:
- Local mode used
- Report indicates mode: "local"

---

## Phase 5: Integration Testing

### Test 5.1: Report Content Verification

**Objective**: Verify reports include correct mode information and findings

**Steps**:
```bash
# 1. Run scans in each mode
python kast/main.py --target http://testphp.vulnweb.com --run-only zap --output-dir test_output/report_local --debug
export KAST_ZAP_URL="http://localhost:8080"
python kast/main.py --target http://testphp.vulnweb.com --run-only zap --output-dir test_output/report_remote --debug
unset KAST_ZAP_URL

# 2. Inspect HTML reports
ls test_output/report_*/kast_report_*.html

# 3. Check for mode information
grep -i "mode" test_output/report_local/kast_report_*.html
grep -i "mode" test_output/report_remote/kast_report_*.html

# 4. Verify ZAP findings section exists
grep -i "zap" test_output/report_local/kast_report_*.html
```

**Expected Results**:
- ✅ Report contains plugin name: "OWASP ZAP"
- ✅ Report shows execution mode (local/remote/cloud)
- ✅ Executive summary includes ZAP findings
- ✅ Vulnerability details formatted correctly
- ✅ Risk ratings visible (High/Medium/Low)

**Success Criteria**:
- All reports generated successfully
- Mode correctly identified in each report
- ZAP findings present and well-formatted

---

### Test 5.2: Multi-Plugin Integration

**Objective**: Verify ZAP works alongside other KAST plugins

**Steps**:
```bash
# Run multiple plugins together
python kast/main.py \
  --target http://testphp.vulnweb.com \
  --run-only whatweb,testssl,zap \
  --output-dir test_output/multi_plugin \
  --debug

# Verify report contains all plugin results
grep -E "(whatweb|testssl|zap)" test_output/multi_plugin/kast_report_*.html
```

**Expected Results**:
- ✅ All plugins execute successfully
- ✅ Single consolidated HTML report
- ✅ Each plugin's section clearly labeled
- ✅ Executive summary includes all findings
- ✅ No plugin interference or conflicts

**Success Criteria**:
- Exit code: 0
- Report contains results from all plugins
- Execution completes without errors

---

### Test 5.3: Report-Only Mode

**Objective**: Verify ZAP plugin respects report-only mode

**Steps**:
```bash
# Create a mock results file from previous scan
cp test_output/report_local/zap_results.json test_output/report_only_input/

# Run in report-only mode
python kast/main.py \
  --target http://testphp.vulnweb.com \
  --run-only zap \
  --output-dir test_output/report_only \
  --report-only \
  --debug
```

**Expected Results**:
- ✅ No actual scanning performed
- ✅ Report generated from existing data
- ✅ Debug message: "Running in report-only mode"
- ✅ Fast execution (< 10 seconds)

**Success Criteria**:
- No ZAP instance launched
- Report generated successfully
- Execution time minimal

---

## Phase 6: Performance Testing

### Test 6.1: Performance Comparison

**Objective**: Benchmark performance across all modes

**Steps**:
```bash
# Test local mode (first run - cold start)
time python kast/main.py \
  --target http://testphp.vulnweb.com \
  --run-only zap \
  --output-dir test_output/perf_local_cold \
  --debug

# Test local mode (warm - container exists)
time python kast/main.py \
  --target http://testphp.vulnweb.com \
  --run-only zap \
  --output-dir test_output/perf_local_warm \
  --debug

# Test remote mode
export KAST_ZAP_URL="http://localhost:8080"
time python kast/main.py \
  --target http://testphp.vulnweb.com \
  --run-only zap \
  --output-dir test_output/perf_remote \
  --debug
unset KAST_ZAP_URL

# Cloud mode timing (if testing cloud)
# time python kast/main.py --target ... --run-only zap --debug
```

**Expected Performance**:
- **Local (cold)**: 1-2 minutes (container startup)
- **Local (warm)**: 30-60 seconds (container reuse)
- **Remote**: 10-30 seconds (no provisioning)
- **Cloud**: 5-15 minutes (infrastructure provisioning)

**Success Criteria**:
- Performance matches expected ranges
- Warm starts significantly faster than cold
- Remote mode fastest provisioning

---

### Test 6.2: Scan Duration Comparison

**Objective**: Compare actual scan times (excluding provisioning)

**Steps**:
```bash
# Monitor scan duration in debug logs
# Look for timestamps between "Starting scan" and "Scan complete"

# Extract timing from logs
grep -E "(Starting|complete)" test_output/*/debug.log
```

**Expected Results**:
- Similar scan durations across modes (for same target)
- Variation < 20% between modes
- Scan quality consistent

**Success Criteria**:
- Scan times comparable
- All modes find similar vulnerabilities

---

## Phase 7: Error Handling & Edge Cases

### Test 7.1: Network Timeout Handling

**Objective**: Verify graceful handling of network timeouts

**Steps**:
```bash
# Use a target that times out
python kast/main.py \
  --target http://10.255.255.1 \
  --run-only zap \
  --output-dir test_output/timeout \
  --debug
```

**Expected Results**:
- ✅ Timeout detected
- ✅ Error message displayed
- ✅ Plugin fails gracefully
- ✅ Cleanup still runs

**Success Criteria**:
- No hanging processes
- Clear timeout error
- Resources cleaned up

---

### Test 7.2: Invalid Target URL

**Objective**: Verify handling of invalid/malformed URLs

**Steps**:
```bash
# Test various invalid URLs
python kast/main.py --target "not-a-url" --run-only zap --output-dir test_output/invalid1 --debug
python kast/main.py --target "ftp://example.com" --run-only zap --output-dir test_output/invalid2 --debug
python kast/main.py --target "" --run-only zap --output-dir test_output/invalid3 --debug
```

**Expected Results**:
- ✅ Validation error displayed
- ✅ Clear error message
- ✅ No provisioning attempted
- ✅ Plugin fails early

**Success Criteria**:
- Early validation
- Meaningful error messages
- Fast failure (< 5 seconds)

---

### Test 7.3: Interrupted Scan Cleanup

**Objective**: Verify cleanup when scan is interrupted (Ctrl+C)

**Steps**:
```bash
# Start a scan
python kast/main.py \
  --target http://testphp.vulnweb.com \
  --run-only zap \
  --output-dir test_output/interrupted \
  --debug &

PID=$!
sleep 30  # Let it provision

# Interrupt the scan
kill -INT $PID

# Wait and check cleanup
sleep 10

# For local: check container still exists (cleanup_on_completion=false)
docker ps | grep kast-zap-local

# For cloud: manually verify AWS resources were cleaned up
```

**Expected Results**:
- ✅ Graceful shutdown initiated
- ✅ Cleanup attempts to run
- ✅ Resources handled appropriately

**Success Criteria**:
- No zombie processes
- Reasonable cleanup attempt
- System remains stable

---

## Phase 8: Security & Configuration Testing

### Test 8.1: API Key Security

**Objective**: Verify API keys are handled securely

**Steps**:
```bash
# Check that API keys don't leak in logs
python kast/main.py \
  --target http://testphp.vulnweb.com \
  --run-only zap \
  --output-dir test_output/security \
  --debug 2>&1 | tee security_test.log

# Search for API key in logs
grep -i "test-key" security_test.log
grep -i "api.key" security_test.log
```

**Expected Results**:
- ✅ API keys not printed in debug output
- ✅ Sensitive data masked or omitted
- ✅ Config files have appropriate permissions

**Success Criteria**:
- No cleartext API keys in logs
- No sensitive data exposure

---

### Test 8.2: SSH Key Security (Cloud Mode)

**Objective**: Verify SSH keys are ephemeral and cleaned up

**Steps**:
```bash
# Run cloud scan
python kast/main.py \
  --target http://testphp.vulnweb.com \
  --run-only zap \
  --output-dir test_output/ssh_security \
  --debug 2>&1 | tee ssh_test.log

# Check for leftover SSH keys
ls -la /tmp/ | grep kast_zap
find /tmp -name "zap_key*" 2>/dev/null
```

**Expected Results**:
- ✅ SSH keys generated in temp directory
- ✅ Keys have correct permissions (600)
- ✅ Keys deleted after scan
- ✅ No keys left in filesystem

**Success Criteria**:
- No leftover SSH keys
- Temp directory cleaned up

---

## Test Execution Checklist

Use this checklist to track your testing progress:

### Phase 1: Local Mode
- [ ] Test 1.1: Basic auto-start
- [ ] Test 1.2: Container reuse
- [ ] Test 1.3: Cleanup enabled
- [ ] Test 1.4: Error handling

### Phase 2: Remote Mode
- [ ] Test 2.1: Environment variables
- [ ] Test 2.2: Config file
- [ ] Test 2.3: Invalid URL error

### Phase 3: Cloud Mode
- [ ] Test 3.1: AWS E2E
- [ ] Test 3.2: Backward compatibility
- [ ] Test 3.3: Error recovery
- [ ] Test 3.4: Azure/GCP (optional)

### Phase 4: Auto-Discovery
- [ ] Test 4.1: Remote priority
- [ ] Test 4.2: Local fallback

### Phase 5: Integration
- [ ] Test 5.1: Report content
- [ ] Test 5.2: Multi-plugin
- [ ] Test 5.3: Report-only mode

### Phase 6: Performance
- [ ] Test 6.1: Mode comparison
- [ ] Test 6.2: Scan duration

### Phase 7: Error Handling
- [ ] Test 7.1: Network timeout
- [ ] Test 7.2: Invalid URL
- [ ] Test 7.3: Interrupted scan

### Phase 8: Security
- [ ] Test 8.1: API key security
- [ ] Test 8.2: SSH key security

---

## Quick Test Script

For rapid validation, use this quick test script:

```bash
#!/bin/bash
# quick_test.sh - Run essential tests

set -e

echo "=== ZAP Plugin Quick Test Suite ==="

# Setup
export TEST_TARGET="http://testphp.vulnweb.com"
export TEST_OUTPUT="test_output/quick"

# Test 1: Local Mode
echo "Testing Local Mode..."
python kast/main.py --target $TEST_TARGET --run-only zap --output-dir ${TEST_OUTPUT}_local --debug
echo "✓ Local mode passed"

# Test 2: Remote Mode
echo "Testing Remote Mode..."
export KAST_ZAP_URL="http://localhost:8080"
export KAST_ZAP_API_KEY="test-key"
python kast/main.py --target $TEST_TARGET --run-only zap --output-dir ${TEST_OUTPUT}_remote --debug
unset KAST_ZAP_URL
unset KAST_ZAP_API_KEY
echo "✓ Remote mode passed"

# Test 3: Auto-discovery
echo "Testing Auto-discovery..."
python kast/main.py --target $TEST_TARGET --run-only zap --output-dir ${TEST_OUTPUT}_auto --debug
echo "✓ Auto-discovery passed"

echo ""
echo "=== Quick Test Complete ==="
echo "All essential tests passed!"
```

---

## Troubleshooting Guide

### Common Issues

#### Issue: "Docker not available"
**Solution**: 
```bash
sudo systemctl start docker
docker ps  # Verify Docker is running
```

#### Issue: "Cannot connect to remote ZAP"
**Solution**:
```bash
# Verify ZAP is running
curl http://localhost:8080/JSON/core/view/version/?apikey=test-key

# Check firewall
sudo ufw status
```

#### Issue: "Terraform not found"
**Solution**:
```bash
# Install Terraform
wget https://releases.hashicorp.com/terraform/1.6.0/terraform_1.6.0_linux_amd64.zip
unzip terraform_1.6.0_linux_amd64.zip
sudo mv terraform /usr/local/bin/
terraform --version
```

#### Issue: Cloud resources not cleaning up
**Solution**:
```bash
# Manual cleanup for AWS
cd test_output/cloud_aws/terraform_workspace
terraform destroy -auto-approve

# Check for leftover resources
aws ec2 describe-instances --filters "Name=tag:Project,Values=KAST"
```

#### Issue: Container port conflict
**Solution**:
```bash
# Find process using port 8080
sudo lsof -i :8080

# Stop conflicting container
docker stop $(docker ps -q --filter publish=8080)
```

---

## Test Reporting

### Create Test Report

After completing tests, create a summary report:

```bash
# Generate test summary
cat > test_summary.md << EOF
# ZAP Plugin Test Results

Date: $(date)
Tester: $(whoami)

## Test Summary

| Phase | Tests | Passed | Failed | Skipped |
|-------|-------|--------|--------|---------|
| Local Mode | 4 | X | X | X |
| Remote Mode | 3 | X | X | X |
| Cloud Mode | 4 | X | X | X |
| Auto-Discovery | 2 | X | X | X |
| Integration | 3 | X | X | X |
| Performance | 2 | X | X | X |
| Error Handling | 3 | X | X | X |
| Security | 2 | X | X | X |

## Issues Found

1. [Issue description]
2. [Issue description]

## Recommendations

1. [Recommendation]
2. [Recommendation]

EOF
```

---

## Continuous Testing

For ongoing validation, consider setting up automated testing:

```bash
# Create a CI/CD test script
#!/bin/bash
# ci_test.sh

# Run only fast, reliable tests
python kast/main.py --target http://testphp.vulnweb.com --run-only zap --output-dir ci_test --debug

# Verify report generated
if [ -f ci_test/kast_report_*.html ]; then
    echo "✓ CI test passed"
    exit 0
else
    echo "✗ CI test failed"
    exit 1
fi
```

---

## Conclusion

This comprehensive testing plan covers:
- ✅ All three execution modes (local, remote, cloud)
- ✅ Auto-discovery functionality
- ✅ Error handling and edge cases
- ✅ Integration with KAST reporting
- ✅ Performance benchmarking
- ✅ Security considerations

Follow this plan systematically to ensure the ZAP plugin works correctly across all scenarios. Start with local mode (fastest and easiest), progress to remote mode, and finally test cloud mode if cloud credentials are available.

**Estimated Total Testing Time**: 
- Local + Remote + Integration: 1-2 hours
- Cloud Mode: +2-3 hours (if testing)
- Complete testing: 3-5 hours

Good luck with your testing!
