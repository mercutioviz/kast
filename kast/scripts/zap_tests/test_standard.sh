#!/usr/bin/env bash
# test_standard.sh — kast ZAP standard profile test
#
# Profile:  standard (~45 min)  [kast default]
# Spider:   Ajax spider (spiderClient) — requires browser in ZAP container
# Active:   yes, capped at 30 min
# Use case: regular development testing; the profile used by default kast scans

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

DEFAULT_ZAP_URL="http://localhost:8081"
DEFAULT_API_KEY="kast3zap"
DEFAULT_TIMEOUT=60
PROFILE_NAME="standard"
EST_TIME="~45 min"

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
    echo "NOTE: This is the default kast scan profile. It uses the Ajax spider"
    echo "      (spiderClient) and requires Firefox in the ZAP container."
    echo ""
    echo "Example:"
    echo "  $(basename "$0") -t https://example.com"
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
