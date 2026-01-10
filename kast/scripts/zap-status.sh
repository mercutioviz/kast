
#!/usr/bin/env bash
#
# zap-status.sh
# Show a consolidated status view for a running OWASP ZAP daemon.
#
# Options:
#   --zapurl   Base URL of the ZAP API (default: http://localhost:8080)
#   --apikey   ZAP API key             (default: kast-local)
#
# Dependencies: curl
# Optional:     jq (for pretty-printing JSON)
#
# References:
# - ZAP API reference (core/ascan/spider/ajaxSpider/alert/pscan) https://www.zaproxy.org/docs/api/
# - Client/JS spider control (scan/status/stop)                  https://www.zaproxy.org/docs/desktop/addons/client-side-integration/spider-api/
#
set -euo pipefail

# -------- Defaults --------
ZAPURL_DEFAULT="http://localhost:8080"
APIKEY_DEFAULT="kast-local"

ZAPURL="$ZAPURL_DEFAULT"
APIKEY="$APIKEY_DEFAULT"

# -------- Parse CLI --------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --zapurl)
      ZAPURL="${2:-}"; shift 2;;
    --apikey)
      APIKEY="${2:-}"; shift 2;;
    --help|-h)
      cat <<EOF
Usage: $(basename "$0") [--zapurl URL] [--apikey KEY]

Defaults:
  --zapurl  ${ZAPURL_DEFAULT}
  --apikey  ${APIKEY_DEFAULT}
EOF
      exit 0;;
    *)
      echo "Unknown option: $1" >&2; exit 1;;
  esac
done

# -------- Helpers --------
have_jq=0
if command -v jq >/dev/null 2>&1; then
  have_jq=1
fi

api() {
  # $1: path (e.g., /JSON/core/view/version/)
  # Remaining args are query string pairs "name=value"
  local path="$1"; shift
  local qs="apikey=${APIKEY}"
  for kv in "$@"; do
    qs="${qs}&${kv}"
  done
  curl -sS "${ZAPURL}${path}?${qs}"
}

print_json() {
  if [[ $have_jq -eq 1 ]]; then
    jq -r "$1"
  else
    cat
  fi
}

hr() { printf '%*s\n' "${COLUMNS:-80}" '' | tr ' ' '='; }

title() {
  echo
  hr
  echo "== $1 =="
  hr
}

# -------- Sections --------

section_version() {
  title "ZAP Version & API"
  api "/JSON/core/view/version/" \
  | { [[ $have_jq -eq 1 ]] && jq -r '.version' || cat; } \
  | sed 's/^/Version: /'
  echo "API Base: ${ZAPURL}"
}

section_sites_urls() {
  title "Sites & URLs Seen"
  echo "- Sites:"
  api "/JSON/core/view/sites/" \
  | { [[ $have_jq -eq 1 ]] && jq -r '.sites[]' || cat; }

  echo "- Number of URLs:"
  api "/JSON/core/view/numberOfUrls/" \
  | { [[ $have_jq -eq 1 ]] && jq -r '.numberOfUrls' || cat; }

  echo "- Sample URLs (first 20):"
  api "/JSON/core/view/urls/" \
  | { [[ $have_jq -eq 1 ]] && jq -r '.urls[:20][]' || cat; }
}

section_alerts() {
  title "Alerts Summary"
  api "/JSON/alert/view/alertsSummary/" \
  | {
      if [[ $have_jq -eq 1 ]]; then
        jq -r '
        to_entries[]
        | "\(.key): High=\(.value.High), Medium=\(.value.Medium), Low=\(.value.Low), Informational=\(.value.Informational)"
        '
      else
        cat
      fi
    }

  echo "- Total alerts:"
  api "/JSON/core/view/numberOfAlerts/" \
  | { [[ $have_jq -eq 1 ]] && jq -r '.numberOfAlerts' || cat; }
}

section_active_scans() {
  title "Active Scans (ascan)"
  scans_json="$(api "/JSON/ascan/view/scans/")"
  if [[ $have_jq -eq 1 ]]; then
    echo "$scans_json" \
    | jq -r '
      .scans[]
      | "ScanId=\(.id) | Target=\(.url) | State=\(.state) | Progress=\(.progress)%"
      ' 2>/dev/null || echo "No active scan records."
  else
    echo "$scans_json"
  fi

  # Show per-scan plugin progress for the most recent scan (if any)
  if [[ $have_jq -eq 1 ]]; then
    last_id="$(echo "$scans_json" | jq -r '.scans|last|.id' 2>/dev/null || true)"
    if [[ -n "$last_id" && "$last_id" != "null" ]]; then
      echo
      echo "- Detail: Plugin progress for ScanId=${last_id}"

      progress_json="$(api "/JSON/ascan/view/scanProgress/" "scanId=${last_id}")"

      # Prefer column if present for alignment.
      if command -v column >/dev/null 2>&1; then
        echo "$progress_json" \
        | jq -r '
            # 1) If the root has scanProgress, use it; else use root.
            (if has("scanProgress") then .scanProgress else . end)
            # 2) If it is an array, take element [1] (the object); else use it as-is.
            | (if type=="array" then .[1] else . end)
            # 3) Navigate to HostProcess (if missing, use empty list to avoid errors).
            | .HostProcess // []
            # 4) Iterate each HostProcess entry and format Plugin fields by index.
            | .[]
            | .Plugin as $p
            | [
                ("ID=" + ($p[1] // "n/a")),
                ("Name=" + ($p[0] // "n/a")),
                ("Track=" + ($p[2] // "n/a")),
                ("State=" + ($p[3] // "n/a")),
                ("Requests=" + ($p[4] // "0")),
                ("C5=" + ($p[5] // "0")),
                ("C6=" + ($p[6] // "0"))
              ]
            | @tsv
          ' \
        | column -t -s $'\t'
      else
        echo "$progress_json" \
        | jq -r '
            (if has("scanProgress") then .scanProgress else . end)
            | (if type=="array" then .[1] else . end)
            | .HostProcess // []
            | .[]
            | .Plugin as $p
            | "ID=\($p[1] // "n/a") | Name=\($p[0] // "n/a") | Track=\($p[2] // "n/a") | State=\($p[3] // "n/a") | Requests=\($p[4] // "0") | C5=\($p[5] // "0") | C6=\($p[6] // "0")"
          '
      fi
    fi
  fi
}

section_spider() {
  title "Spider Scans"
  spider_json="$(api "/JSON/spider/view/scans/")"
  if [[ $have_jq -eq 1 ]]; then
    echo "$spider_json" \
    | jq -r '.scans[] | "ScanId=\(.scan) | Started=\(.startTime) | Status=\(.status)"' 2>/dev/null || echo "No spider scans."
    # If there is a last scan, show status and a few results
    last_id="$(echo "$spider_json" | jq -r '.scans|last|.scan' 2>/dev/null || true)"
    if [[ -n "$last_id" && "$last_id" != "null" ]]; then
      echo
      echo "- Spider status for ScanId=${last_id}:"
      api "/JSON/spider/view/status/" "scanId=${last_id}" \
      | jq -r '.status'
      echo "- Spider results (first 20):"
      api "/JSON/spider/view/results/" "scanId=${last_id}" \
      | jq -r '.results[:20][]'
    fi
  else
    echo "$spider_json"
  fi
}

section_ajax_spider() {
  title "AJAX Spider Scans"
  ajax_json="$(api "/JSON/ajaxSpider/view/scans/")"
  if [[ $have_jq -eq 1 ]]; then
    echo "$ajax_json" \
    | jq -r '.scans[] | "Started=\(.start) | Status=\(.status)"' 2>/dev/null || echo "No AJAX spider scans."
    echo "- Current AJAX spider status:"
    api "/JSON/ajaxSpider/view/status/" \
    | jq -r '.status'
    echo "- AJAX spider results (first 20):"
    api "/JSON/ajaxSpider/view/results/" "start=0" "count=20" \
    | jq -r '.results[]'
  else
    echo "$ajax_json"
    api "/JSON/ajaxSpider/view/status/"
    api "/JSON/ajaxSpider/view/results/" "start=0" "count=20"
  fi
}

section_pscan() {
  title "Passive Scanner Queue"
  api "/JSON/pscan/view/recordsToScan/" \
  | { [[ $have_jq -eq 1 ]] && jq -r '.recordsToScan' || cat; } \
  | sed 's/^/Records waiting: /'
}

# -------- Run --------
section_version
section_sites_urls
section_alerts
section_active_scans
section_spider
section_ajax_spider
section_pscan

echo
echo "Done."
