# OWASP ZAP Multi-Mode Plugin Guide

## Overview

The KAST ZAP plugin now supports three execution modes, making it significantly more versatile and efficient:

1. **Local Mode**: Uses local Docker ZAP container (fastest, zero cost)
2. **Remote Mode**: Connects to existing ZAP instance (flexible, shared resources)
3. **Cloud Mode**: Provisions ephemeral cloud infrastructure (isolated, production-ready)

The plugin intelligently selects the best available mode or can be configured explicitly.

## Architecture

```
┌─────────────────────────────────────────────┐
│          ZAP Plugin (Entry Point)           │
│  - Load config                              │
│  - Determine execution mode                 │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│      ZapProviderFactory (Auto-Discovery)    │
│  1. Check env vars (KAST_ZAP_URL)          │
│  2. Check local Docker availability         │
│  3. Fall back to cloud                      │
└──────────────────┬──────────────────────────┘
                   ↓
      ┌────────────┴────────────┐
      ↓            ↓             ↓
┌──────────┐ ┌──────────┐ ┌──────────┐
│  Local   │ │  Remote  │ │  Cloud   │
│ Provider │ │ Provider │ │ Provider │
└──────────┘ └──────────┘ └──────────┘
      ↓            ↓             ↓
┌─────────────────────────────────────────────┐
│         ZAP API Client (Common)             │
│  - Monitor scan progress                    │
│  - Download results                         │
│  - Generate reports                         │
└─────────────────────────────────────────────┘
```

## Quick Start

### 1. Local Mode (Recommended for Development)

**Prerequisites**: Docker installed

**Usage**:
```bash
# Auto mode will detect Docker and use local mode
python kast/main.py --target https://example.com --plugins zap --debug

# Or explicitly specify local mode in config
# Set execution_mode: local in zap_config.yaml
```

**Behavior**:
- Checks for running ZAP container
- Starts new container if needed (configurable)
- Keeps container running for reuse (faster subsequent scans)
- Uses mounted volumes for config/reports

**Advantages**:
- ✅ Fastest scan initiation (~30 seconds)
- ✅ Zero cost
- ✅ Container reuse across scans
- ✅ Good for development/testing

### 2. Remote Mode (Shared Infrastructure)

**Prerequisites**: ZAP instance URL and API key

**Setup**:
```bash
# Set environment variables
export KAST_ZAP_URL="http://zap.example.com:8080"
export KAST_ZAP_API_KEY="your-api-key"

# Run scan
python kast/main.py --target https://example.com --plugins zap --debug
```

**Behavior**:
- Connects to existing ZAP instance
- Uses direct API calls (not automation framework)
- No provisioning/cleanup needed

**Advantages**:
- ✅ Fast scan initiation (~10 seconds)
- ✅ Share ZAP instance across team
- ✅ Centralized management
- ✅ Good for CI/CD pipelines

### 3. Cloud Mode (Production Scans)

**Prerequisites**: Terraform, cloud credentials (AWS/Azure/GCP)

**Setup**:
```bash
# Configure cloud provider in zap_config.yaml
# execution_mode: cloud

# Set cloud credentials
export AWS_ACCESS_KEY_ID="your_key"
export AWS_SECRET_ACCESS_KEY="your_secret"

# Run scan
python kast/main.py --target https://example.com --plugins zap --debug
```

**Behavior**:
- Provisions ephemeral infrastructure
- Deploys ZAP container
- Runs scan
- Tears down infrastructure

**Advantages**:
- ✅ Complete isolation
- ✅ Production-grade scanning
- ✅ No local dependencies
- ✅ Cost-optimized (spot instances)

## Configuration

### New Configuration File: `zap_config.yaml`

```yaml
# Execution mode: auto, local, remote, cloud
execution_mode: auto

# Auto-discovery settings
auto_discovery:
  prefer_local: true
  check_env_vars: true

# Local mode settings
local:
  docker_image: "ghcr.io/zaproxy/zaproxy:stable"
  auto_start: true
  api_port: 8080
  api_key: "kast-local"
  container_name: "kast-zap-local"
  cleanup_on_completion: false  # Keep running for reuse

# Remote mode settings
remote:
  api_url: "${KAST_ZAP_URL}"
  api_key: "${KAST_ZAP_API_KEY}"
  timeout_seconds: 30

# Cloud mode settings (existing)
cloud:
  cloud_provider: aws
  aws:
    region: us-east-1
    instance_type: t3.medium
```

## Auto-Discovery Logic

When `execution_mode: auto` is set, the plugin follows this priority:

1. **Check for Remote ZAP**:
   - Look for `KAST_ZAP_URL` environment variable
   - If found, use Remote mode

2. **Check for Local Docker**:
   - Verify Docker is installed
   - Look for running ZAP container
   - If available, use Local mode

3. **Fall Back to Cloud**:
   - If neither above is available, use Cloud mode
   - Requires Terraform and cloud credentials

## Comparison Table

| Feature | Local Mode | Remote Mode | Cloud Mode |
|---------|------------|-------------|------------|
| **Setup Time** | ~30s | ~10s | ~5-10min |
| **Cost** | Free | Variable | $0.02-0.07/hr |
| **Isolation** | Low | Medium | High |
| **Reusability** | High | High | Low (ephemeral) |
| **Dependencies** | Docker | Network access | Terraform, Cloud |
| **Best For** | Development | CI/CD, Shared | Production, Isolated |

## Usage Examples

### Example 1: Development Workflow (Local)

```bash
# First run - starts container
python kast/main.py --target https://dev.example.com --plugins zap --debug
# Container: kast-zap-local started

# Subsequent runs - reuses container
python kast/main.py --target https://staging.example.com --plugins zap
# Container: kast-zap-local reused (much faster!)
```

### Example 2: CI/CD Pipeline (Remote)

```yaml
# .gitlab-ci.yml or .github/workflows/security.yml
env:
  KAST_ZAP_URL: "http://zap-server.internal:8080"
  KAST_ZAP_API_KEY: $ZAP_API_KEY  # From CI secrets

script:
  - python kast/main.py --target $DEPLOY_URL --plugins zap
```

### Example 3: Production Assessment (Cloud)

```bash
# Run isolated scan in cloud
python kast/main.py \
  --target https://production.example.com \
  --plugins zap \
  --debug

# Infrastructure provisioned → Scan → Auto-cleanup
```

### Example 4: Explicit Mode Selection

```bash
# Force local mode
# Edit zap_config.yaml: execution_mode: local
python kast/main.py --target https://example.com --plugins zap

# Force remote mode with inline config
export KAST_ZAP_URL="http://localhost:8080"
# Edit zap_config.yaml: execution_mode: remote
python kast/main.py --target https://example.com --plugins zap

# Force cloud mode
# Edit zap_config.yaml: execution_mode: cloud
python kast/main.py --target https://example.com --plugins zap
```

## Environment Variables

The plugin supports the following environment variables:

- `KAST_ZAP_URL`: Remote ZAP instance URL (e.g., `http://zap.example.com:8080`)
- `KAST_ZAP_API_KEY`: API key for remote ZAP authentication
- Cloud credentials (AWS/Azure/GCP) - see cloud config section

## Troubleshooting

### Local Mode Issues

**Problem**: "Docker not available"
```bash
# Solution: Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

**Problem**: "Port 8080 already in use"
```bash
# Solution: Change port in config
# Edit zap_config.yaml: local.api_port: 8081
```

**Problem**: Container won't start
```bash
# Check Docker logs
docker logs kast-zap-local

# Remove stale container
docker rm -f kast-zap-local
```

### Remote Mode Issues

**Problem**: "Cannot connect to remote ZAP"
```bash
# Solution: Verify URL and connectivity
curl http://your-zap-url:8080/JSON/core/view/version

# Check API key
export KAST_ZAP_API_KEY="correct-key"
```

**Problem**: "Connection timeout"
```bash
# Solution: Increase timeout in config
# Edit zap_config.yaml: remote.timeout_seconds: 60
```

### Cloud Mode Issues

See existing `ZAP_CLOUD_PLUGIN_GUIDE.md` for cloud-specific troubleshooting.

## Migration Guide

### From Legacy Cloud-Only Plugin

The new plugin is backward compatible. If you have existing `zap_cloud_config.yaml`:

1. Plugin automatically detects and adapts legacy config
2. Consider migrating to new `zap_config.yaml` format:

```bash
# Copy and adapt your config
cp kast/config/zap_cloud_config.yaml kast/config/zap_config.yaml

# Update structure (see configuration section above)
```

## Best Practices

### For Development
- Use **local mode** with `cleanup_on_completion: false`
- Container stays running between scans
- Fastest iteration cycle

### For CI/CD
- Use **remote mode** with shared ZAP instance
- Set `KAST_ZAP_URL` in CI secrets
- Consistent environment across builds

### For Production
- Use **cloud mode** for isolation
- Enable spot/preemptible instances for cost savings
- Set appropriate scan timeouts

### For Testing
- Use **auto mode** to adapt to environment
- Works locally (Docker) and in CI (remote) automatically

## Performance Comparison

Based on typical scan of a medium-sized web application:

| Mode | Provisioning | Scan Time | Total Time | Cost |
|------|--------------|-----------|------------|------|
| Local | 30s | 15min | 15.5min | $0 |
| Remote | 10s | 15min | 15.2min | $0* |
| Cloud | 8min | 15min | 25min | $0.05 |

\* Cost depends on remote instance hosting

## Advanced Configuration

### Custom Local Container

```yaml
local:
  docker_image: "your-registry/custom-zap:latest"
  # Mount custom scripts
  # Add custom addons
```

### Multiple Remote Instances

```yaml
# Use different remotes based on environment
remote:
  api_url: "${ZAP_URL_${ENVIRONMENT}}"  # ZAP_URL_DEV, ZAP_URL_STAGING
```

### Hybrid Approach

```yaml
# Development: Use local
# CI: Use remote (via env var)
# Production: Force cloud
execution_mode: auto  # Adapts automatically
```

## Security Considerations

### Local Mode
- Container has access to host network
- API key should be unique per project
- Consider network isolation for sensitive scans

### Remote Mode
- Use HTTPS with valid certificates in production
- Rotate API keys regularly
- Implement IP whitelisting on ZAP instance

### Cloud Mode
- Security groups restrict access to SSH + ZAP API
- Ephemeral instances minimize attack surface
- No persistent data after teardown

## Future Enhancements

Planned improvements:
- [ ] Kubernetes provider (deploy to K8s cluster)
- [ ] Result caching (avoid re-scanning unchanged resources)
- [ ] Parallel scanning (multiple targets simultaneously)
- [ ] Smart mode selection based on target complexity
- [ ] WebSocket support for real-time progress
- [ ] Integration with ZAP marketplace addons

## Support

For issues or questions:
1. Check troubleshooting section above
2. Review debug logs (`--debug` flag)
3. Consult ZAP documentation: https://www.zaproxy.org/docs/
4. Report KAST-specific issues using `/reportbug` command

## Summary

The multi-mode ZAP plugin provides flexibility for different scenarios:

- **Development**: Fast local scanning with Docker
- **CI/CD**: Shared remote instance for consistency  
- **Production**: Isolated cloud scanning for security

The auto-discovery mode makes it work seamlessly across environments without configuration changes.
