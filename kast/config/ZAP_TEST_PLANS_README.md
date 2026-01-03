# ZAP Automation Test Plans

This directory contains predefined ZAP automation framework test plans optimized for different scanning scenarios.

## Available Profiles

### 1. Quick Profile (`zap_automation_quick.yaml`)
**Duration**: ~20 minutes  
**Use Case**: CI/CD pipelines, rapid feedback

**Configuration**:
- Spider: 5 minutes, depth 3, 2 threads
- Passive Scan: 5 alerts per rule
- Active Scan: 15 minutes, 2 threads per host

**When to Use**:
- ✅ Pull request security checks
- ✅ Pre-commit hooks
- ✅ Developer quick scans
- ✅ Rapid iteration during development

**Trade-offs**: May miss deeper vulnerabilities in exchange for speed

---

### 2. Standard Profile (`zap_automation_standard.yaml`) - DEFAULT
**Duration**: ~45 minutes  
**Use Case**: Regular development security testing

**Configuration**:
- Spider: 10 minutes, depth 5, 2 threads
- Passive Scan: 10 alerts per rule
- Active Scan: 30 minutes, 2 threads per host

**When to Use**:
- ✅ Regular security testing
- ✅ Feature branch scans
- ✅ Staging environment assessments
- ✅ Balanced coverage and speed

**Trade-offs**: Best balance between thoroughness and time

---

### 3. Thorough Profile (`zap_automation_thorough.yaml`)
**Duration**: ~90 minutes  
**Use Case**: Pre-production assessments, major releases

**Configuration**:
- Spider: 20 minutes, depth 10, 4 threads
- Passive Scan: 20 alerts per rule, tags enabled
- Active Scan: 60 minutes, 4 threads per host

**When to Use**:
- ✅ Pre-production security gate
- ✅ Major release assessments
- ✅ Quarterly security audits
- ✅ High-risk feature deployment

**Trade-offs**: Comprehensive but time-consuming

---

### 4. API Profile (`zap_automation_api.yaml`)
**Duration**: ~30 minutes  
**Use Case**: REST APIs, microservices, headless applications

**Configuration**:
- Spider: 3 minutes, depth 2, 2 threads (minimal)
- Passive Scan: 10 alerts per rule
- Active Scan: 25 minutes, 3 threads per host

**Special Features**:
- No HTML form processing
- Optimized for JSON/REST patterns
- Query parameter injection enabled
- Matches versioned API paths (`/api/*`, `/v[0-9]+/*`)

**When to Use**:
- ✅ REST API security testing
- ✅ Microservices assessment
- ✅ GraphQL endpoints
- ✅ Headless backend services

**Note**: For best results, provide OpenAPI/Swagger specification

---

### 5. Passive Profile (`zap_automation_passive.yaml`)
**Duration**: ~15 minutes  
**Use Case**: Production monitoring (SAFE for production)

**Configuration**:
- Spider: 10 minutes, depth 5, 1 thread (gentle)
- Passive Scan: 10 alerts per rule
- Active Scan: **NONE** (no injection attacks)

**When to Use**:
- ✅ Production environment monitoring
- ✅ Live site security checks
- ✅ Compliance scanning
- ✅ Safe baseline assessments

**Safety**: No attack payloads sent, only observes responses

---

## Usage Examples

### CLI Shortcut (Recommended)

```bash
# Quick scan for CI/CD
python kast/main.py --target https://example.com --plugins zap --zap-profile quick

# Standard scan (default behavior)
python kast/main.py --target https://example.com --plugins zap --zap-profile standard

# Thorough scan for pre-production
python kast/main.py --target https://example.com --plugins zap --zap-profile thorough

# API-focused scan
python kast/main.py --target https://api.example.com --plugins zap --zap-profile api

# Passive scan safe for production
python kast/main.py --target https://prod.example.com --plugins zap --zap-profile passive
```

### Direct Path Override

```bash
python kast/main.py --target https://example.com --plugins zap \
  --set zap.zap_config.automation_plan=kast/config/zap_automation_thorough.yaml
```

### Config File

```yaml
# In kast_config.yaml or ~/.config/kast/config.yaml
plugins:
  zap:
    zap_config:
      automation_plan: "kast/config/zap_automation_api.yaml"
```

### Environment-Based Selection

```yaml
# In zap_config.yaml
zap_config:
  automation_plan: "kast/config/zap_automation_${SCAN_PROFILE}.yaml"
```

Then set environment variable:
```bash
export SCAN_PROFILE=thorough
python kast/main.py --target https://example.com --plugins zap
```

---

## Comparison Table

| Profile | Duration | Spider | Active Scan | Threads | Best For |
|---------|----------|--------|-------------|---------|----------|
| **quick** | 20 min | 5min/d3 | 15 min | 2 | CI/CD |
| **standard** | 45 min | 10min/d5 | 30 min | 2 | Development |
| **thorough** | 90 min | 20min/d10 | 60 min | 4 | Pre-production |
| **api** | 30 min | 3min/d2 | 25 min | 3 | REST APIs |
| **passive** | 15 min | 10min/d5 | None | 1 | Production |

*d = depth*

---

## Customizing Test Plans

### Option 1: Edit Existing Plan

```bash
# Copy a profile to start
cp kast/config/zap_automation_standard.yaml kast/config/zap_automation_custom.yaml

# Edit parameters
nano kast/config/zap_automation_custom.yaml

# Use your custom plan
python kast/main.py --target https://example.com --plugins zap \
  --set zap.zap_config.automation_plan=kast/config/zap_automation_custom.yaml
```

### Option 2: Create Project-Specific Plan

```bash
# Create project config directory
mkdir -p .kast/

# Create custom plan
cp kast/config/zap_automation_standard.yaml .kast/zap_custom.yaml
# Edit .kast/zap_custom.yaml

# Reference in project config
cat > kast_config.yaml << EOF
plugins:
  zap:
    zap_config:
      automation_plan: ".kast/zap_custom.yaml"
EOF
```

### Common Customizations

**Increase Spider Depth:**
```yaml
jobs:
  - type: "spiderClient"
    parameters:
      maxDepth: 15  # Default varies by profile
```

**Adjust Active Scan Duration:**
```yaml
jobs:
  - type: "activeScan"
    parameters:
      maxScanDurationInMins: 120  # 2 hours
```

**Add URL Exclusions:**
```yaml
env:
  contexts:
    - name: "target-context"
      excludePaths:
        - ".*logout.*"
        - ".*delete.*"
        - ".*admin/dangerous-action.*"
```

**Configure Spider Threading:**
```yaml
jobs:
  - type: "spiderClient"
    parameters:
      threadCount: 8  # More threads = faster but more aggressive
```

---

## Validation

All test plans are automatically validated when loaded:

✅ Valid YAML syntax  
✅ Required sections present (`env`, `jobs`)  
✅ Each job has required `type` field  
✅ Target URL placeholder `${TARGET_URL}` present  

If validation fails, the scan will abort with a clear error message.

---

## Best Practices

### Development Workflow
1. Start with **quick** profile during active development
2. Use **standard** profile for feature branch merges
3. Run **thorough** profile before production deployment

### CI/CD Integration
```yaml
# .gitlab-ci.yml example
security_scan:
  script:
    - python kast/main.py --target $CI_ENVIRONMENT_URL --plugins zap --zap-profile quick
  only:
    - merge_requests
```

### Production Monitoring
```bash
# Cron job for weekly production scans (safe)
0 2 * * 0 python kast/main.py --target https://prod.example.com --plugins zap --zap-profile passive
```

### API Testing
```bash
# Best results with OpenAPI spec
python kast/main.py --target https://api.example.com --plugins zap --zap-profile api \
  --set zap.openapi_spec=/path/to/swagger.json
```

---

## Troubleshooting

### Plan Not Found
```
Error: Automation plan not found: kast/config/zap_automation_quick.yaml
```

**Solution**: Ensure you're running from project root, or use absolute path

### Invalid YAML Syntax
```
Error: Invalid automation plan YAML
```

**Solution**: Validate YAML syntax at https://www.yamllint.com/

### Target URL Not Substituted
```
Error: ${TARGET_URL} not replaced in plan
```

**Solution**: Ensure target is passed with `-t` or `--target` flag

---

## Support

For detailed documentation, see:
- `kast/docs/ZAP_MULTI_MODE_GUIDE.md` - Complete ZAP plugin guide
- `kast/docs/ZAP_MULTI_MODE_IMPLEMENTATION.md` - Technical implementation details
- ZAP Automation Framework: https://www.zaproxy.org/docs/desktop/addons/automation-framework/

For issues or questions, use `/reportbug` in the KAST CLI.
