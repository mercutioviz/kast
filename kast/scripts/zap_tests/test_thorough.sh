#!/usr/bin/env bash
# test_thorough.sh — kast ZAP thorough profile test
#
# Profile:  thorough (~90 min)
# Spider:   Ajax spider (spiderClient), depth 10, 4 threads
# Active:   yes, capped at 60 min, 4 threads
# Use case: pre-production deep scans and major releases

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

DEFAULT_ZAP_URL="http://localhost:8081"
DEFAULT_API_KEY="kast3zap"
DEFAULT_TIMEOUT=110
PROFILE_NAME="thorough"
EST_TIME="~90 min"

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
    echo "NOTE: This is the longest profile — allow ~90 min plus margin."
    echo "      Use a dedicated test target (DVWA, Juice Shop, WebGoat) for"
    echo "      meaningful results. Requires Firefox in the ZAP container."
    echo ""
    echo "Example:"
    echo "  $(basename "$0") -t https://example.com"
    echo "  $(basename "$0") -t https://example.com -T 120"
}

parse_common_args "$@"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUTPUT_DIR="/tmp/kast-zap-${PROFILE_NAME}-${TIMESTAMP}"

print_banner "$PROFILE_NAME" "$EST_TIME" "$TARGET" "$ZAP_URL" "$OUTPUT_DIR" "$TIMEOUT"
echo -e "  ${YELLOW}Note:${RESET} Long-running scan. Do not interrupt once started."
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
