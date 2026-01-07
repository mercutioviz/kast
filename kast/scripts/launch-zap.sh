#!/bin/sh
# OWASP ZAP Docker Launch Script (with NGINX Reverse Proxy)
#
# This script launches ZAP on internal port 8081, designed to work with NGINX reverse proxy.
# NGINX listens on external port 8080 and proxies to ZAP's internal port 8081.
#
# Architecture: Client :8080 → NGINX → ZAP :8081 (localhost only)
#
# Benefits:
# - Prevents ZAP proxy loop errors (Host header includes port)
# - Better security (ZAP not directly exposed)
# - Standard reverse proxy pattern
#
# Setup NGINX:
#   sudo apt-get install -y nginx
#   sudo cp kast/config/nginx/zap-proxy.conf /etc/nginx/sites-available/
#   sudo ln -sf /etc/nginx/sites-available/zap-proxy /etc/nginx/sites-enabled/
#   sudo rm -f /etc/nginx/sites-enabled/default
#   sudo nginx -t && sudo systemctl restart nginx
#
# Then run this script to start ZAP on port 8081
#
# For more information:
# - NGINX config: kast/config/nginx/zap-proxy.conf
# - Documentation: kast/config/nginx/README.md
# - Remote mode setup: kast/docs/ZAP_REMOTE_MODE_QUICK_START.md

sudo docker run -d \
  --name kast-zap \
  --restart unless-stopped \
  -u zap \
  -p 127.0.0.1:8081:8081 \
  -v /opt/zap/reports:/zap/reports:rw \
  -e TZ=UTC \
  --health-cmd="curl -f http://localhost:8081/JSON/core/view/version/?apikey=kast01 || exit 1" \
  --health-interval=30s \
  --health-timeout=10s \
  --health-retries=3 \
  --health-start-period=60s \
  ghcr.io/zaproxy/zaproxy:stable \
  zap.sh -daemon \
  -host 0.0.0.0 \
  -port 8081 \
  -config api.key=kast01 \
  -config api.addrs.addr.name=.* \
  -config api.addrs.addr.regex=true \
  -config api.filexfer=true \
  -config api.debug=true \
  -config api.disablekey=false
