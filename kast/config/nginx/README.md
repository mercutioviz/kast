# NGINX Reverse Proxy for OWASP ZAP

## Overview

This directory contains NGINX configuration files used to run OWASP ZAP behind a reverse proxy. This setup solves critical issues with ZAP's proxy mode and API access when running in remote or cloud environments.

## The Problem

OWASP ZAP has a unique challenge: it functions as both:
1. **A web proxy** - Intercepts and analyzes HTTP/HTTPS traffic
2. **An API server** - Provides REST API for automation and control

When ZAP runs on the same port for both functions, it can confuse incoming API requests with proxy traffic, especially when:
- The `Host` header doesn't include a port number
- External clients connect to ZAP from different IP addresses
- ZAP attempts to determine if a request should be proxied or handled as an API call

This leads to **proxy loop errors**, where ZAP tries to proxy its own API requests, causing scans to fail or behave unpredictably.

## The Solution

By placing NGINX as a reverse proxy in front of ZAP, we create clear separation:

```
┌─────────────────────────────────────────────────────────┐
│  External Client (KAST Plugin)                          │
└────────────────┬────────────────────────────────────────┘
                 │ HTTP Requests to :8080
                 ▼
┌─────────────────────────────────────────────────────────┐
│  NGINX Reverse Proxy (:8080)                            │
│  - Accepts external connections                         │
│  - Rewrites Host header to include port                 │
│  - Sets X-Forwarded headers to localhost                │
│  - Manages timeouts and buffering                       │
└────────────────┬────────────────────────────────────────┘
                 │ Proxied to http://localhost:8081
                 ▼
┌─────────────────────────────────────────────────────────┐
│  OWASP ZAP Daemon (:8081)                               │
│  - Listens only on localhost:8081                       │
│  - Sees all requests as coming from 127.0.0.1           │
│  - Host header includes port (localhost:8081)           │
│  - No confusion between API and proxy requests          │
└─────────────────────────────────────────────────────────┘
```

## Key Benefits

1. **Prevents Proxy Loops**: ZAP receives requests with `Host: localhost:8081`, which it doesn't try to proxy
2. **Better Security**: ZAP only binds to localhost, not exposed directly to external networks
3. **Consistent Headers**: All requests appear to come from 127.0.0.1, preventing IP-based confusion
4. **Standard Pattern**: Uses well-established reverse proxy patterns familiar to DevOps teams
5. **Timeout Management**: NGINX handles long-running scan timeouts gracefully
6. **Better Streaming**: Disables buffering for real-time progress updates

## Files

- **`zap-proxy.conf`**: NGINX server configuration for ZAP reverse proxy
  - Used by `kast/scripts/launch-zap.sh` for manual/remote setups
  - Embedded in Terraform cloud infrastructure deployments
  - Can be installed directly on any system running ZAP

## Usage

### Manual Installation (Remote ZAP Instances)

If you're running ZAP manually and want to use the nginx proxy:

```bash
# Copy the config
sudo cp kast/config/nginx/zap-proxy.conf /etc/nginx/sites-available/

# Enable the site
sudo ln -sf /etc/nginx/sites-available/zap-proxy /etc/nginx/sites-enabled/

# Disable default site
sudo rm -f /etc/nginx/sites-enabled/default

# Test configuration
sudo nginx -t

# Restart nginx
sudo systemctl restart nginx
```

Then start ZAP on port 8081 (internal):
```bash
# Example using launch-zap.sh script
kast/scripts/launch-zap.sh
```

Connect to ZAP via: `http://your-server:8080` (NGINX port)

### Automated Installation (Cloud Mode)

When using KAST's cloud mode (`--plugins zap` with cloud provider), the nginx configuration is automatically installed via Terraform:
- **AWS**: See `kast/terraform/aws/main.tf`
- **Azure**: See `kast/terraform/azure/main.tf`
- **GCP**: See `kast/terraform/gcp/main.tf`

No manual configuration needed - it's all handled automatically.

### Docker-based Setup

See `kast/scripts/launch-zap.sh` for a working Docker-compose example that:
1. Starts ZAP container on `127.0.0.1:8081`
2. Assumes nginx is installed and configured
3. Makes ZAP accessible via `http://server:8080`

## Configuration Details

The nginx configuration includes these critical settings:

```nginx
# Force HTTP/1.1
proxy_http_version 1.1;

# Clear Connection header
proxy_set_header Connection "";

# CRITICAL: Include port in Host header
proxy_set_header Host localhost:8081;

# Make all requests appear local
proxy_set_header X-Real-IP 127.0.0.1;
proxy_set_header X-Forwarded-For 127.0.0.1;
proxy_set_header X-Forwarded-Proto http;
proxy_set_header X-Forwarded-Host localhost;

# Long timeouts for scans
proxy_connect_timeout 300s;
proxy_send_timeout 300s;
proxy_read_timeout 300s;

# Disable buffering for streaming
proxy_buffering off;
proxy_request_buffering off;
```

## Port Configuration

- **External Port (8080)**: NGINX listens here, accessible to KAST plugin and external clients
- **Internal Port (8081)**: ZAP listens here, only on localhost (not externally accessible)

This port separation is crucial for the solution to work correctly.

## Troubleshooting

### Issue: Connection Refused to Port 8080
**Solution**: Ensure nginx is installed and running:
```bash
sudo systemctl status nginx
sudo systemctl restart nginx
```

### Issue: Still Getting Proxy Loop Errors
**Solution**: Verify ZAP is using port 8081 and Host header includes port:
```bash
# Check ZAP is listening on 8081
netstat -tlnp | grep 8081

# Test nginx proxy (should include port)
curl -v http://localhost:8080/JSON/core/view/version/
# Look for "Host: localhost:8081" in the request
```

### Issue: Nginx Configuration Error
**Solution**: Test the configuration file:
```bash
sudo nginx -t
# Check error log
sudo tail -f /var/log/nginx/error.log
```

### Issue: ZAP Not Starting
**Solution**: Check if port 8081 is already in use:
```bash
sudo lsof -i :8081
# Kill any conflicting process or choose different port
```

## Related Documentation

- **[ZAP Remote Mode Quick Start](../../docs/ZAP_REMOTE_MODE_QUICK_START.md)**: How to configure KAST to use remote ZAP instances
- **[ZAP Cloud Plugin Guide](../../docs/ZAP_CLOUD_PLUGIN_GUIDE.md)**: Cloud deployment architecture and configuration
- **[launch-zap.sh](../../scripts/launch-zap.sh)**: Script demonstrating nginx + ZAP setup
- **[ZAP Documentation](https://www.zaproxy.org/docs/)**: Official OWASP ZAP documentation

## Contributing

When modifying the nginx configuration:
1. Test thoroughly with both API calls and proxy functionality
2. Verify in all three cloud providers (AWS, Azure, GCP)
3. Update this README if adding new configuration options
4. Ensure compatibility with different nginx versions (1.18+)
