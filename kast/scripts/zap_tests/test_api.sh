#!/usr/bin/env bash
# test_api.sh — kast ZAP API profile test
#
# Profile:  api (~30 min)
# Spider:   Ajax spider (spiderClient), depth 2, paths /api/* and /v*/*
# Active:   yes, 25 min, addQueryParam=true, CSRF tokens disabled
# Use case: REST APIs and microservices

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

DEFAULT_ZAP_URL="http://localhost:8081"
DEFAULT_API_KEY="kast3zap"
DEFAULT_TIMEOUT=45
PROFILE_NAME="api"
EST_TIME="~30 min"

TARGET=""
ZAP_URL="$DEFAULT_ZAP_URL"
API_KEY="$DEFAULT_API_KEY"
TIMEOUT="$DEFAULT_TIMEOUT"

_usage() {
    echo "Usage: $(basename "$0") -t <target> [-u <zap_url>] [-k <api_key>] [-T <timeout_min>]"
    echo ""
    echo "  -t  Target URL to scan (required)"
    echo "  -u  ZAP API URL            (default: ${DEFAULT_ZAP_URL})"
    echo "  -k  ZAP API key            (default: ${DEFAULT_API_KEY})"
    echo "  -T  Scan timeout (minutes) (default: ${DEFAULT_TIMEOUT})"
    echo ""
    echo "NOTE: This profile scopes crawling to /api/* and /v*/* paths."
    echo "      Point -t at the API base URL, e.g. https://example.com"
    echo "      (not https://example.com/api/v1)."
    echo "      Requires Firefox in the ZAP container (spiderClient)."
    echo ""
    echo "Example:"
    echo "  $(basename "$0") -t https://example.com"
}

parse_common_args "$@"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUTPUT_DIR="/tmp/kast-zap-${PROFILE_NAME}-${TIMESTAMP}"

print_banner "$PROFILE_NAME" "$EST_TIME" "$TARGET" "$ZAP_URL" "$OUTPUT_DIR" "$TIMEOUT"
echo -e "  ${CYAN}Note:${RESET} Spider scoped to /api/* and /v[0-9]+/* paths."
echo ""

check_zap_connectivity "$ZAP_URL" "$API_KEY"

echo -e "${BOLD}[2/2] Running kast scan (${PROFILE_NAME} profile)...${RESET}"
echo "      kast will poll ZAP every 30 s and print progress."
echo ""

kast scan \
    -m active \
    --target   "$TARGET" \
    --zap-profile "$PROFILE_NAME" \
    --set "zap.execution_mode=remote" \
    --set "zap.remote.api_url=${ZAP_URL}" \
    --set "zap.remote.api_key=${API_KEY}" \
    --set "zap.zap_config.timeout_minutes=${TIMEOUT}" \
    --run-only zap \
    --format   both \
    -o         "$OUTPUT_DIR"

print_results "$OUTPUT_DIR"
