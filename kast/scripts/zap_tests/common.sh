#!/usr/bin/env bash
# Shared helpers for kast ZAP test scripts.
# Source this file; do not execute it directly.

# ── colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ── print_banner ─────────────────────────────────────────────────────────────
# Usage: print_banner "Quick" "~20 min" "$TARGET" "$ZAP_URL" "$OUTPUT_DIR" "$TIMEOUT"
print_banner() {
    local profile="$1" est_time="$2" target="$3" zap_url="$4" output_dir="$5" timeout="$6"
    echo ""
    echo -e "${BOLD}╔══════════════════════════════════════════════════╗${RESET}"
    printf "${BOLD}║  kast ZAP Test — %-30s  ║${RESET}\n" "${profile} profile"
    echo -e "${BOLD}╚══════════════════════════════════════════════════╝${RESET}"
    echo -e "  Target:      ${CYAN}${target}${RESET}"
    echo -e "  ZAP URL:     ${zap_url}"
    echo -e "  Output:      ${output_dir}"
    echo -e "  Timeout:     ${timeout} min  (est. ${est_time})"
    echo ""
}

# ── check_zap_connectivity ───────────────────────────────────────────────────
# Usage: check_zap_connectivity "$ZAP_URL" "$API_KEY"
# Returns 0 on success, exits 1 on failure.
check_zap_connectivity() {
    local zap_url="$1" api_key="$2"
    echo -e "${BOLD}[1/2] Checking ZAP connectivity...${RESET}"

    local response
    response=$(curl -sf --max-time 10 \
        "${zap_url}/JSON/core/view/version/?apikey=${api_key}" 2>/dev/null) || true

    if [[ -z "$response" ]]; then
        echo -e "${RED}ERROR: No response from ZAP at ${zap_url}${RESET}"
        echo "       Verify ZAP is running and the URL/port are correct."
        exit 1
    fi

    local version
    version=$(echo "$response" \
        | python3 -c "import json,sys; print(json.load(sys.stdin)['version'])" 2>/dev/null) || true

    if [[ -z "$version" ]]; then
        echo -e "${RED}ERROR: ZAP responded but version could not be parsed.${RESET}"
        echo "       Raw response: ${response}"
        exit 1
    fi

    echo -e "  ${GREEN}✓${RESET} Connected to ZAP v${version} at ${zap_url}"
}

# ── reset_zap_session ────────────────────────────────────────────────────────
# Kept for backwards compatibility; kast now calls newSession internally during
# provision(), so this is a no-op stub. Test scripts no longer call it.
reset_zap_session() {
    :
}

# ── print_results ────────────────────────────────────────────────────────────
# Usage: print_results "$OUTPUT_DIR"
print_results() {
    local output_dir="$1"
    echo ""
    echo -e "${BOLD}Results written to: ${CYAN}${output_dir}${RESET}"
    if [[ -d "$output_dir" ]]; then
        echo ""
        ls -lh "${output_dir}/" 2>/dev/null | grep -v "^total" | \
            awk '{printf "  %-40s %s\n", $NF, $5}'
    fi
    echo ""
}

# ── parse_common_args ────────────────────────────────────────────────────────
# Sets: TARGET, ZAP_URL, API_KEY, TIMEOUT
# Requires caller to set DEFAULT_ZAP_URL, DEFAULT_API_KEY, DEFAULT_TIMEOUT, PROFILE_NAME
# Usage: parse_common_args "$@"
parse_common_args() {
    while getopts ":t:u:k:T:h" opt; do
        case $opt in
            t) TARGET="$OPTARG" ;;
            u) ZAP_URL="$OPTARG" ;;
            k) API_KEY="$OPTARG" ;;
            T) TIMEOUT="$OPTARG" ;;
            h) _usage; exit 0 ;;
            :) echo -e "${RED}ERROR: Option -${OPTARG} requires an argument.${RESET}"; _usage; exit 1 ;;
            \?) echo -e "${RED}ERROR: Unknown option -${OPTARG}.${RESET}"; _usage; exit 1 ;;
        esac
    done

    if [[ -z "${TARGET:-}" ]]; then
        echo -e "${RED}ERROR: Target (-t) is required.${RESET}"
        echo ""
        _usage
        exit 1
    fi
}
