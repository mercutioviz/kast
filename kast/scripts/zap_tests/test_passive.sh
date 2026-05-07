#!/usr/bin/env bash
# test_passive.sh — kast ZAP passive profile test
#
# Profile:  passive (~15 min)
# Spider:   Ajax spider (spiderClient) — requires browser in ZAP container
# Active:   NO — observation only, safe for production targets
# Use case: production monitoring; also the cheapest spiderClient smoke test

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

DEFAULT_ZAP_URL="http://localhost:8081"
DEFAULT_API_KEY="kast3zap"
DEFAULT_TIMEOUT=25
PROFILE_NAME="passive"
EST_TIME="~15 min"

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
    echo "NOTE: This profile uses the Ajax spider (spiderClient)."
    echo "      The ZAP container must have Firefox available."
    echo "      Use zaproxy/zap:stable, not zap:bare."
    echo ""
    echo "Example:"
    echo "  $(basename "$0") -t https://example.com"
}

parse_common_args "$@"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUTPUT_DIR="/tmp/kast-zap-${PROFILE_NAME}-${TIMESTAMP}"

print_banner "$PROFILE_NAME" "$EST_TIME" "$TARGET" "$ZAP_URL" "$OUTPUT_DIR" "$TIMEOUT"
echo -e "  ${YELLOW}Note:${RESET} Passive only — no attack payloads sent. Safe for production."
echo ""

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
