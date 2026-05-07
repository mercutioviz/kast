#!/usr/bin/env bash
# test_quick.sh — kast ZAP quick profile test
#
# Profile:  quick (~20 min)
# Spider:   traditional spider (no browser required)
# Active:   yes, capped at 15 min
# Use case: CI/CD pipelines, fast sanity checks

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

DEFAULT_ZAP_URL="http://localhost:8081"
DEFAULT_API_KEY="kast3zap"
DEFAULT_TIMEOUT=35
PROFILE_NAME="quick"
EST_TIME="~20 min"

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
    echo "Example:"
    echo "  $(basename "$0") -t https://example.com"
    echo "  $(basename "$0") -t https://example.com -u http://192.168.1.10:8081 -k mykey -T 45"
}

parse_common_args "$@"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUTPUT_DIR="/tmp/kast-zap-${PROFILE_NAME}-${TIMESTAMP}"

print_banner "$PROFILE_NAME" "$EST_TIME" "$TARGET" "$ZAP_URL" "$OUTPUT_DIR" "$TIMEOUT"

check_zap_connectivity "$ZAP_URL" "$API_KEY"
reset_zap_session      "$ZAP_URL" "$API_KEY"

echo -e "${BOLD}[3/3] Running kast scan (${PROFILE_NAME} profile)...${RESET}"
echo "      kast will poll ZAP every 30 s and print progress."
echo ""

kast scan \
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
