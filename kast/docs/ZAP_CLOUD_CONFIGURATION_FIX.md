# ZAP Cloud Configuration Fix

## Problem Summary

The ZAP cloud infrastructure had two critical issues:

1. **Container Not Starting**: The Terraform cloud-init script only pulled the ZAP Docker image but never started the container
2. **Proxy Loop Issue**: When the container was manually started, external API requests were being treated as proxy traffic, causing ZAP to attempt to proxy requests to itself, resulting in timeouts

## Root Cause

### Issue 1: Missing Container Start Command
The original cloud-init script ended after pulling the Docker image:
```bash
# Pull ZAP Docker image
docker pull ${var.zap_docker_image}

# Create a ready flag
touch /tmp/zap-ready
```

This meant users had to manually SSH into the instance and start ZAP themselves.

### Issue 2: Proxy Mode Confusion
ZAP runs both a proxy server and an API server on port 8080 by default. When accessed via the public IP, ZAP was treating API requests (e.g., `/JSON/core/view/version/`) as proxy traffic and attempting to forward them to the public IP address, creating an infinite loop:

```
External Request → ZAP:8080 → ZAP thinks it's proxy traffic → Tries to proxy to 34.220.15.173:8080 → Loops back to itself → Timeout
```

## Solution Implemented

### 1. Added ZAP API Key Variable
Added a new variable to `variables.tf` for secure API key management:

```hcl
variable "zap_api_key" {
  description = "ZAP API key for authentication"
  type        = string
  default     = "kast01"
  sensitive   = true
}
```

### 2. Updated Cloud-Init Script
The cloud-init script in `main.tf` now:

1. **Starts the ZAP container automatically** with proper configuration
2. **Configures API-only mode** by binding the proxy to localhost only
3. **Adds health checks** for monitoring
4. **Implements restart policy** for resilience
5. **Logs all setup steps** to `/var/log/zap-setup.log`
6. **Waits for ZAP to be ready** before marking setup complete

### 3. ZAP Container Configuration

The key configuration parameters:

```bash
docker run -d \
  --name kast-zap \
  --restart unless-stopped \
  -u zap \
  -p 8080:8080 \
  -v /opt/zap/reports:/zap/reports:rw \
  -e TZ=UTC \
  --health-cmd="curl -f http://localhost:8080/JSON/core/view/version/?apikey=${var.zap_api_key} || exit 1" \
  --health-interval=30s \
  --health-timeout=10s \
  --health-retries=3 \
  --health-start-period=60s \
  ${var.zap_docker_image} \
  zap.sh -daemon \
  -host 0.0.0.0 \
  -port 8080 \
  -config api.key=${var.zap_api_key} \
  -config api.addrs.addr.name=.* \
  -config api.addrs.addr.regex=true \
  -config api.disablekey=false \
  -config proxy.ip=127.0.0.1 \
  -config proxy.port=8081
```

**Critical Settings Explained:**

- `-host 0.0.0.0`: ZAP API listens on all interfaces (external access)
- `-port 8080`: API port
- `-config api.key=<key>`: Sets API key for authentication
- `-config api.addrs.addr.name=.*`: Allow API access from any IP
- `-config proxy.ip=127.0.0.1`: **KEY FIX** - Proxy only listens on localhost
- `-config proxy.port=8081`: Proxy on different port than API
- `--restart unless-stopped`: Auto-restart on failures
- `--health-cmd`: Docker health check using API

## How It Fixes the Proxy Loop

By setting `-config proxy.ip=127.0.0.1`, the proxy component only listens on localhost:8081, while the API listens on 0.0.0.0:8080. This means:

1. External requests to `public-ip:8080` → Go to API (correct)
2. Proxy traffic (if needed) → Only accessible via `localhost:8081` (not exposed)
3. No confusion between API and proxy traffic

## Files Modified

1. **kast/terraform/aws/variables.tf**
   - Added `zap_api_key` variable with sensitive flag

2. **kast/terraform/aws/main.tf**
   - Rewrote cloud-init script to start ZAP container
   - Added comprehensive logging
   - Added health checks and monitoring
   - Added startup verification loop
   - Added error handling

## Testing the Fix

### Deploy New Infrastructure

```bash
cd /opt/kast
python3 kast/scripts/test_infrastructure_provision.py aws
```

### Verify ZAP is Running

Once deployed, the output will show the public IP. Wait 2-3 minutes for cloud-init to complete, then:

```bash
# Get the public IP from the Terraform output
PUBLIC_IP="<ip-from-output>"

# Test API access
curl -X GET "http://${PUBLIC_IP}:8080/JSON/core/view/version/?apikey=kast01"
```

**Expected Response:**
```json
{"version":"2.17.0"}
```

### Check Setup Logs (if needed)

```bash
# SSH into the instance
ssh -i test_output/infra_test_aws_<timestamp>/test_ssh_key ubuntu@${PUBLIC_IP}

# View setup logs
cat /var/log/zap-setup.log

# Check container status
docker ps --filter name=kast-zap

# Check container health
docker inspect kast-zap --format='{{.State.Health.Status}}'

# View ZAP logs
docker logs kast-zap
```

## Troubleshooting

### If API Still Times Out

1. **Check security group rules:**
   ```bash
   aws ec2 describe-security-groups --region <region> --filters "Name=group-name,Values=*kast-zap*"
   ```

2. **Check container is running:**
   ```bash
   ssh ubuntu@${PUBLIC_IP} "docker ps --filter name=kast-zap"
   ```

3. **Test from inside the instance:**
   ```bash
   ssh ubuntu@${PUBLIC_IP} "curl http://localhost:8080/JSON/core/view/version/?apikey=kast01"
   ```

4. **Check setup logs:**
   ```bash
   ssh ubuntu@${PUBLIC_IP} "cat /var/log/zap-setup.log"
   ```

### If Container Won't Start

Check the setup log for errors:
```bash
ssh ubuntu@${PUBLIC_IP} "tail -100 /var/log/zap-setup.log"
```

Common issues:
- Docker image pull failed (network issues)
- Insufficient memory (use larger instance type)
- Port conflicts (shouldn't happen with clean setup)

## Backward Compatibility

**Breaking Changes:**
- Existing infrastructure will need to be destroyed and recreated to get the new configuration
- The `zap_api_key` variable is now required (defaults to "kast01" if not specified)

**Migration Path:**
```bash
# Destroy old infrastructure
cd /opt/kast
python3 kast/scripts/test_infrastructure_teardown.py aws

# Deploy new infrastructure
python3 kast/scripts/test_infrastructure_provision.py aws
```

## Security Considerations

1. **API Key**: The default API key "kast01" should be changed in production
2. **IP Restrictions**: Consider restricting the security group ingress rules to specific IPs
3. **Sensitive Variable**: The `zap_api_key` is marked as sensitive to prevent exposure in logs

## Performance Notes

- **Startup Time**: Initial setup takes 2-3 minutes (Docker install + image pull + container start)
- **Health Check**: Container will show as "healthy" after ZAP API responds successfully
- **Auto-Restart**: Container will automatically restart if ZAP crashes

## Docker Installation Method Update (Jan 2, 2026)

### Issue
The original cloud-init script used manual apt repository configuration for Docker installation, which occasionally failed due to package version conflicts:

```
E: Failed to fetch https://download.docker.com/linux/ubuntu/.../containerd.io_2.2.1-1...
404 Not Found
```

This occurred when Docker removed or updated specific package versions in their repository.

### Solution
Updated to use Docker's official installation script (`get.docker.com`), which:
- Automatically handles version selection and compatibility
- More reliable across different Ubuntu versions
- Maintained by Docker and always up-to-date
- Simpler and more maintainable code

### Changes Made
```bash
# Old method (manual apt repository):
apt-get install -y ca-certificates curl gnupg lsb-release
mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=...] https://download.docker.com/linux/ubuntu ..." | tee /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# New method (official script):
curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
sh /tmp/get-docker.sh
rm /tmp/get-docker.sh
```

Added validation to ensure Docker installed successfully:
```bash
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker installation failed"
    exit 1
fi
```

## Future Improvements

1. Add Terraform output for ZAP API URL
2. Add CloudWatch logs integration
3. Add option to use pre-built AMI with Docker pre-installed
4. Add support for custom ZAP configurations
5. Add automated health monitoring and alerting

## References

- ZAP Docker Documentation: https://www.zaproxy.org/docs/docker/
- ZAP API Documentation: https://www.zaproxy.org/docs/api/
- Terraform AWS Provider: https://registry.terraform.io/providers/hashicorp/aws/latest/docs
