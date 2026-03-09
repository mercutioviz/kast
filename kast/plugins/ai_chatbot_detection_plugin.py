"""
File: plugins/ai_chatbot_detection_plugin.py
Description: Analyzes output from passive plugins (katana, whatweb, script_detection)
             to detect indicators of agentic AI chatbots on the target website.
"""

import os
import re
import json
from datetime import datetime
from kast.plugins.base import KastPlugin


# ---------------------------------------------------------------------------
# Indicator databases
# ---------------------------------------------------------------------------

# Known AI / chatbot platform scripts and CDN patterns
AI_CHATBOT_SCRIPT_PATTERNS = [
    # Agentic / Conversational AI platforms
    (r"ada\.support|ada-embed|adasupport\.com", "Ada Support", "Agentic AI customer service platform"),
    (r"forethought\.ai|forethought-widget", "Forethought", "AI-powered customer support agent"),
    (r"ultimate\.ai|ultimate-widget", "Ultimate.ai", "AI-powered virtual agent platform"),
    (r"cognigy\.ai|cognigy-webchat", "Cognigy", "Conversational AI platform"),
    (r"kore\.ai|kore-widget|korebots", "Kore.ai", "Enterprise conversational AI"),
    (r"yellow\.ai|yellowmessenger|yellow-widget", "Yellow.ai", "Enterprise AI chatbot platform"),
    (r"haptik\.ai|haptik-sdk", "Haptik", "Conversational AI platform"),
    (r"verloop\.io|verloop-sdk", "Verloop", "Conversational AI for support"),
    (r"boost\.ai|boost-webchat", "Boost.ai", "Enterprise conversational AI"),
    (r"aisera\.com|aisera-widget", "Aisera", "AI service management chatbot"),
    (r"moveworks\.com|moveworks-widget", "Moveworks", "AI-powered IT service agent"),
    (r"kasisto\.com|kai-widget", "Kasisto KAI", "AI-powered banking chatbot"),
    (r"amelia\.ai|ipsoft\.com|amelia-widget", "Amelia/IPsoft", "Enterprise digital employee AI"),
    (r"inbenta\.com|inbenta-widget", "Inbenta", "AI-powered search and chatbot"),
    (r"netomi\.com|netomi-widget", "Netomi", "AI-first customer service"),
    (r"thankful\.ai|thankful-widget", "Thankful", "AI agent for customer service"),
    (r"laiye\.com|laiye-widget", "Laiye", "AI-powered chatbot platform"),
    (r"clinc\.com|clinc-widget", "Clinc", "Conversational AI for banking"),
    (r"passage\.ai|passageai", "Passage AI", "Conversational AI platform"),
    (r"replicant\.ai|replicant-widget", "Replicant", "AI-powered contact center agent"),
    (r"mavenoid\.com|mavenoid-widget", "Mavenoid", "AI-powered product support"),
    # Major cloud AI / chatbot services
    (r"watson-assistant|watson-chat|ibm\.com/assistant|wa-chat-app", "IBM Watson Assistant", "IBM cloud conversational AI"),
    (r"dialogflow|dialogflow\.cloud\.google|df-messenger", "Google Dialogflow", "Google conversational AI service"),
    (r"lex\.amazonaws|aws-lex-web-ui|connect\.amazonaws", "Amazon Lex / Connect", "AWS conversational AI"),
    (r"microsoft\.com/botframework|botframework\.com|webchat\.botframework|directline\.botframework", "Microsoft Bot Framework", "Azure Bot Service"),
    (r"cognitiveservices\.azure|azure-bot-service|healthbot\.microsoft", "Azure Bot Service", "Microsoft Azure conversational AI"),
    # Open-source / self-hosted chatbot frameworks
    (r"botpress\.com|botpress-webchat|inject\.js.*botpress", "Botpress", "Open-source chatbot platform"),
    (r"rasa\.com|rasa-widget|rasa-webchat", "Rasa", "Open-source conversational AI framework"),
    (r"chatwoot\.com|chatwoot-widget|chatwoot/sdk", "Chatwoot", "Open-source customer engagement"),
    # Popular live-chat / chatbot SaaS (AI-augmented)
    (r"drift\.com|drift-widget|driftt\.com|js\.driftt\.com", "Drift", "Conversational marketing / AI chatbot"),
    (r"intercom\.com|intercom-container|widget\.intercom\.io|intercomcdn", "Intercom", "AI-augmented customer messaging"),
    (r"zopim|zendesk.*chat|zdassets\.com.*chat|web-sdk.*zendesk|static\.zdassets\.com", "Zendesk Chat", "Zendesk AI-powered chat"),
    (r"livechat\.com|livechatinc\.com|cdn\.livechatinc", "LiveChat", "AI-augmented live chat"),
    (r"tidio\.co|code\.tidio\.co|tidio-chat", "Tidio", "AI chatbot and live chat"),
    (r"crisp\.chat|client\.crisp\.chat|crisp-widget", "Crisp", "Customer messaging with AI chatbot"),
    (r"freshchat|freshdesk\.com/widget|wchat\.freshchat", "Freshchat", "Freshworks AI-powered chat"),
    (r"tawk\.to|embed\.tawk\.to", "Tawk.to", "Live chat with AI features"),
    (r"hubspot.*chat|hubspot.*messages|conversations-visitor", "HubSpot Chat", "HubSpot conversational AI bot"),
    (r"kommunicate\.io|kommunicate-widget|widget\.kommunicate", "Kommunicate", "AI chatbot customer support"),
    (r"chatbot\.com|livechatinc\.com.*chatbot", "ChatBot.com", "AI chatbot platform"),
    (r"landbot\.io|landbot-widget", "Landbot", "No-code AI chatbot builder"),
    (r"manychat\.com|manychat-widget", "ManyChat", "AI-powered chat marketing"),
    (r"qualified\.com|qualified-widget", "Qualified", "AI-powered conversational sales"),
    (r"gorgias\.com|gorgias-chat", "Gorgias", "AI-augmented e-commerce helpdesk"),
    (r"helpscout\.com|beacon-v2|helpscout-beacon", "Help Scout Beacon", "AI-augmented help widget"),
    (r"olark\.com|olark-widget|static\.olark\.com", "Olark", "Live chat with AI co-pilot"),
    (r"smartsupp\.com|smartsupp-widget", "Smartsupp", "AI chatbot and live chat"),
    (r"collect\.chat|collectchat", "Collect.chat", "AI chatbot for lead generation"),
    (r"chatfuel\.com|chatfuel-widget", "Chatfuel", "AI chatbot platform"),
    (r"voiceflow\.com|voiceflow-widget", "Voiceflow", "Conversational AI design platform"),
    # OpenAI / LLM-powered chat widgets
    (r"openai\.com/chatgpt|chat\.openai|chatgpt-widget", "OpenAI ChatGPT Widget", "LLM-powered AI chat"),
    (r"anthropic\.com|claude-widget|claude-chat", "Anthropic Claude Widget", "LLM-powered AI chat"),
    (r"customgpt\.ai|customgpt-widget", "CustomGPT", "Custom GPT chatbot for websites"),
    (r"chatbase\.co|chatbase-widget", "Chatbase", "GPT-powered custom chatbot"),
    (r"dante-ai\.com|danteai", "Dante AI", "Custom AI chatbot builder"),
    (r"botsonic|writesonic.*chat", "Botsonic/Writesonic", "GPT-powered chatbot"),
    (r"botpress.*cloud|cdn\.botpress\.cloud", "Botpress Cloud", "AI-powered chatbot cloud"),
]

# URL path patterns that suggest chatbot / AI assistant endpoints
AI_CHATBOT_URL_PATTERNS = [
    (r"/chat[-_]?bot", "chatbot endpoint"),
    (r"/ai[-_]?chat", "AI chat endpoint"),
    (r"/ai[-_]?assistant", "AI assistant endpoint"),
    (r"/virtual[-_]?assistant", "virtual assistant endpoint"),
    (r"/virtual[-_]?agent", "virtual agent endpoint"),
    (r"/conversational[-_]?ai", "conversational AI endpoint"),
    (r"/chat[-_]?widget", "chat widget endpoint"),
    (r"/live[-_]?chat", "live chat endpoint"),
    (r"/support[-_]?chat", "support chat endpoint"),
    (r"/bot[-_]?api", "bot API endpoint"),
    (r"/chat[-_]?api", "chat API endpoint"),
    (r"/ask[-_]?ai", "ask AI endpoint"),
    (r"/ai[-_]?support", "AI support endpoint"),
    (r"/copilot", "copilot endpoint"),
    (r"/agent[-_]?chat", "agent chat endpoint"),
    (r"/helpbot", "helpbot endpoint"),
    (r"/chatgpt", "ChatGPT integration endpoint"),
    (r"/digital[-_]?assistant", "digital assistant endpoint"),
    (r"/smart[-_]?assistant", "smart assistant endpoint"),
    (r"/ai[-_]?concierge", "AI concierge endpoint"),
    (r"/webchat", "webchat endpoint"),
    (r"/messenger[-_]?bot", "messenger bot endpoint"),
]

# WhatWeb technology names that indicate chat / AI
WHATWEB_CHAT_INDICATORS = [
    "drift", "intercom", "zendesk", "zopim", "livechat", "tidio",
    "crisp", "freshchat", "tawk", "hubspot", "olark", "smartsupp",
    "chatbot", "botpress", "rasa", "dialogflow", "watson",
    "chatwoot", "kommunicate", "gorgias",
]

# Confidence level ordering
CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}


class AiChatbotDetectionPlugin(KastPlugin):
    """
    Analyzes data collected by passive plugins to detect indicators of
    agentic AI chatbot presence on the target website.

    This is an *analysis-only* plugin -- it runs no external tools.  Instead
    it reads processed-JSON output files from katana, whatweb, and
    script_detection, then searches for known chatbot / AI-assistant
    signatures in URLs, external scripts, and technology fingerprints.
    """

    priority = 70  # Run after katana (60), whatweb (15), script_detection (10)

    config_schema = {
        "type": "object",
        "title": "AI Chatbot Detection Configuration",
        "description": "Settings for detecting agentic AI chatbots from passive scan data",
        "properties": {
            "enabled": {
                "type": "boolean",
                "default": True,
                "description": "Enable or disable AI chatbot detection analysis"
            },
            "confidence_threshold": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "default": "low",
                "description": "Minimum confidence level to report (low includes URL-path-only hits)"
            }
        }
    }

    def __init__(self, cli_args, config_manager=None):
        self.name = "ai_chatbot_detection"
        self.display_name = "AI Chatbot Detection"
        self.description = "Detects indicators of agentic AI chatbots from passive scan data."
        self.website_url = "https://github.com/mercutioviz/kast"
        self.scan_type = "passive"
        self.output_type = "analysis"
        # Declare dependencies so the orchestrator waits for data-source
        # plugins to finish before running this analysis plugin (important
        # for --parallel mode).  condition=lambda r: True means "just wait
        # for the plugin to complete, regardless of its result".  If an
        # upstream plugin was filtered out or unavailable the chatbot plugin
        # still runs fine -- it gracefully handles missing files.
        self.dependencies = [
            {"plugin": "katana", "condition": lambda r: True},
            {"plugin": "whatweb", "condition": lambda r: True},
            {"plugin": "script_detection", "condition": lambda r: True},
        ]
        super().__init__(cli_args, config_manager)
        self._load_plugin_config()

    def _load_plugin_config(self):
        self.enabled = self.get_config("enabled", True)
        self.confidence_threshold = self.get_config("confidence_threshold", "low")

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    def is_available(self):
        return True

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self, target, output_dir, report_only):
        ts = datetime.utcnow().isoformat(timespec="milliseconds")

        if not self.enabled:
            return self.get_result_dict(
                "success", {"detections": [], "message": "Plugin disabled via config"}, timestamp=ts)

        detections = []
        detections.extend(self._analyze_katana(output_dir))
        detections.extend(self._analyze_whatweb(output_dir))
        detections.extend(self._analyze_script_detection(output_dir))

        # De-duplicate
        seen = set()
        unique = []
        for d in detections:
            key = (d["platform"], d["source"], d["evidence"])
            if key not in seen:
                seen.add(key)
                unique.append(d)

        unique = self._apply_confidence_filter(unique)
        self.debug(f"AI chatbot detection found {len(unique)} indicator(s)")

        return self.get_result_dict("success", {"target": target, "detections": unique}, timestamp=ts)

    # ------------------------------------------------------------------
    # Katana analysis
    # ------------------------------------------------------------------

    def _analyze_katana(self, output_dir):
        detections = []
        urls = []

        katana_proc = os.path.join(output_dir, "katana_processed.json")
        if os.path.isfile(katana_proc):
            try:
                with open(katana_proc) as f:
                    data = json.load(f)
                urls.extend(data.get("findings", {}).get("urls", []))
            except Exception as e:
                self.debug(f"Error reading katana_processed.json: {e}")

        katana_raw = os.path.join(output_dir, "katana.txt")
        if os.path.isfile(katana_raw):
            try:
                with open(katana_raw) as f:
                    urls.extend(line.strip() for line in f if line.strip())
            except Exception as e:
                self.debug(f"Error reading katana.txt: {e}")

        for url in urls:
            ul = url.lower()
            for pat, label in AI_CHATBOT_URL_PATTERNS:
                if re.search(pat, ul):
                    detections.append(dict(platform=label, confidence="medium",
                                           source="katana_url", evidence=url,
                                           description=f"URL path matches {label} pattern"))
                    break
            for pat, plat, desc in AI_CHATBOT_SCRIPT_PATTERNS:
                if re.search(pat, ul):
                    detections.append(dict(platform=plat, confidence="high",
                                           source="katana_url", evidence=url, description=desc))
                    break
        return detections

    # ------------------------------------------------------------------
    # WhatWeb analysis
    # ------------------------------------------------------------------

    def _analyze_whatweb(self, output_dir):
        detections = []
        path = os.path.join(output_dir, "whatweb_processed.json")
        if not os.path.isfile(path):
            return detections
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception:
            return detections

        findings = data.get("findings", {})
        results = findings.get("results", [])
        if not results and isinstance(findings, list):
            results = findings

        for entry in results:
            plugins = entry.get("plugins", {}) if isinstance(entry, dict) else {}
            for pname, pdata in plugins.items():
                pl = pname.lower()
                for ind in WHATWEB_CHAT_INDICATORS:
                    if ind in pl:
                        ver = ""
                        if isinstance(pdata, dict):
                            vl = pdata.get("version", [])
                            if vl:
                                ver = f" v{', '.join(vl)}"
                        detections.append(dict(
                            platform=f"{pname}{ver}", confidence="high",
                            source="whatweb_technology",
                            evidence=f"WhatWeb detected: {pname}{ver}",
                            description=f"Technology fingerprint matches '{ind}'"))
                        break
                # Check string values
                if isinstance(pdata, dict):
                    for s in pdata.get("string", []):
                        sl = s.lower() if isinstance(s, str) else ""
                        for pat, plat, desc in AI_CHATBOT_SCRIPT_PATTERNS:
                            if re.search(pat, sl):
                                detections.append(dict(
                                    platform=plat, confidence="high",
                                    source="whatweb_string",
                                    evidence=f"WhatWeb {pname}: {s}",
                                    description=desc))
                                break
        return detections

    # ------------------------------------------------------------------
    # Script detection analysis
    # ------------------------------------------------------------------

    def _analyze_script_detection(self, output_dir):
        detections = []
        path = os.path.join(output_dir, "script_detection_processed.json")
        if not os.path.isfile(path):
            return detections
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception:
            return detections

        findings = data.get("findings", {})

        # --- Real data format: findings.results.scripts[] ---
        # Each script object has: url, hostname, path, origin, is_same_origin, ...
        results = findings.get("results", {})
        if isinstance(results, dict):
            scripts_list = results.get("scripts", [])
            if isinstance(scripts_list, list):
                for script in scripts_list:
                    if not isinstance(script, dict):
                        continue
                    # Check the full URL
                    url = script.get("url", "")
                    ul = url.lower()
                    for pat, plat, desc in AI_CHATBOT_SCRIPT_PATTERNS:
                        if re.search(pat, ul):
                            detections.append(dict(
                                platform=plat, confidence="high",
                                source="script_detection_external",
                                evidence=url, description=desc))
                            break

            # Also scan unique_origins list for quick matches
            origins = results.get("unique_origins", [])
            if isinstance(origins, list):
                for origin in origins:
                    ol = origin.lower() if isinstance(origin, str) else ""
                    for pat, plat, desc in AI_CHATBOT_SCRIPT_PATTERNS:
                        if re.search(pat, ol):
                            # Only add if not already found via scripts[]
                            already = any(d["platform"] == plat and d["source"] == "script_detection_external"
                                          for d in detections)
                            if not already:
                                detections.append(dict(
                                    platform=plat, confidence="high",
                                    source="script_detection_origin",
                                    evidence=origin, description=desc))
                            break

        # --- Legacy / fallback format: findings.external_scripts[] ---
        scripts = findings.get("external_scripts", [])
        if isinstance(scripts, list):
            for script in scripts:
                src = script.get("src", "") if isinstance(script, dict) else str(script)
                sl = src.lower()
                for pat, plat, desc in AI_CHATBOT_SCRIPT_PATTERNS:
                    if re.search(pat, sl):
                        detections.append(dict(
                            platform=plat, confidence="high",
                            source="script_detection_external",
                            evidence=src, description=desc))
                        break

        # --- Legacy / fallback format: findings.inline_scripts[] ---
        inline = findings.get("inline_scripts", [])
        if isinstance(inline, list):
            for snip in inline:
                txt = snip.get("content", "") if isinstance(snip, dict) else str(snip)
                tl = txt.lower()[:2000]
                for pat, plat, desc in AI_CHATBOT_SCRIPT_PATTERNS:
                    if re.search(pat, tl):
                        short = txt[:200].replace("\n", " ")
                        detections.append(dict(
                            platform=plat, confidence="high",
                            source="script_detection_inline",
                            evidence=f"Inline script snippet: {short}",
                            description=desc))
                        break
        return detections

    # ------------------------------------------------------------------
    # Confidence filter
    # ------------------------------------------------------------------

    def _apply_confidence_filter(self, detections):
        thresh = CONFIDENCE_ORDER.get(self.confidence_threshold, 0)
        return [d for d in detections if CONFIDENCE_ORDER.get(d.get("confidence", "low"), 0) >= thresh]

    # ------------------------------------------------------------------
    # Post-process
    # ------------------------------------------------------------------

    def post_process(self, raw_output, output_dir):
        """
        Post-process raw scan results into a standardized processed JSON file.

        :param raw_output: Result dict returned by run() via get_result_dict()
        :param output_dir: Directory to write processed JSON
        :return: Path to the processed JSON file
        """
        ts = raw_output.get("timestamp", datetime.utcnow().isoformat(timespec="milliseconds"))
        results_data = raw_output.get("results", {})
        target = results_data.get("target", "unknown")
        detections = results_data.get("detections", [])
        n = len(detections)

        # Build executive summary
        if n == 0:
            exec_summary = "No AI chatbot indicators were detected on the target website."
        else:
            platforms = sorted({d["platform"] for d in detections})
            exec_summary = (
                f"{n} AI chatbot indicator(s) detected on the target. "
                f"Platform(s) identified: {', '.join(platforms)}. "
                "Agentic AI chatbots can introduce security risks including prompt injection, "
                "data leakage, and expanded attack surface via third-party integrations."
            )

        # Map to issue registry
        registry_issues = []
        if n > 0:
            registry_issues.append("AI-CHATBOT-001")
        if n >= 3:
            registry_issues.append("AI-CHATBOT-002")

        # Build HTML widgets
        html = self._build_html(detections, target)
        html_pdf = self._build_html_pdf(detections, target)

        # Build summary / details strings
        summary = self._generate_summary(detections)
        if n > 0:
            detail_lines = [f"AI chatbot indicators found: {n}"]
            for d in detections:
                detail_lines.append(f"  - {d['platform']} ({d['confidence']}): {d['description']}")
            details = "\n".join(detail_lines)
        else:
            details = "No AI chatbot indicators detected."

        # Save processed JSON (standard KAST format)
        processed = {
            "plugin-name": self.name,
            "plugin-description": self.description,
            "plugin-display-name": self.display_name,
            "timestamp": ts,
            "target": target,
            "findings": {"detections": detections},
            "findings_count": n,
            "summary": summary,
            "details": details,
            "issues": registry_issues,
            "executive_summary": exec_summary,
            "custom_html": html,
            "custom_html_pdf": html_pdf,
        }

        out_path = os.path.join(output_dir, f"{self.name}_processed.json")
        try:
            with open(out_path, "w") as f:
                json.dump(processed, f, indent=2)
            self.debug(f"Processed JSON written to {out_path}")
        except Exception as e:
            self.debug(f"Error writing processed JSON: {e}")

        return out_path

    # ------------------------------------------------------------------
    # Summary generation
    # ------------------------------------------------------------------

    def _generate_summary(self, detections):
        """Generate a short text summary of detections for the processed output."""
        n = len(detections)
        if n == 0:
            return "No AI chatbot indicators detected."
        platforms = sorted({d["platform"] for d in detections})
        high = sum(1 for d in detections if d.get("confidence") == "high")
        medium = sum(1 for d in detections if d.get("confidence") == "medium")
        low = sum(1 for d in detections if d.get("confidence") == "low")
        parts = []
        if high:
            parts.append(f"{high} high")
        if medium:
            parts.append(f"{medium} medium")
        if low:
            parts.append(f"{low} low")
        conf_str = ", ".join(parts) if parts else "unknown"
        return (
            f"Detected {n} AI chatbot indicator(s) ({conf_str} confidence). "
            f"Platform(s): {', '.join(platforms)}."
        )

    # ------------------------------------------------------------------
    # HTML generation
    # ------------------------------------------------------------------

    def _build_html(self, detections, target):
        if not detections:
            return "<p>No AI chatbot indicators detected.</p>"
        rows = []
        for d in detections:
            conf_class = {"high": "danger", "medium": "warning", "low": "info"}.get(d["confidence"], "info")
            rows.append(
                f'<tr><td>{d["platform"]}</td>'
                f'<td><span class="badge badge-{conf_class}">{d["confidence"]}</span></td>'
                f'<td>{d["source"]}</td>'
                f'<td style="word-break:break-all;max-width:400px">{d["evidence"]}</td>'
                f'<td>{d["description"]}</td></tr>'
            )
        return (
            '<div class="ai-chatbot-results">'
            f'<p><strong>{len(detections)}</strong> AI chatbot indicator(s) detected.</p>'
            '<table class="table table-striped table-sm">'
            '<thead><tr><th>Platform</th><th>Confidence</th><th>Source</th>'
            '<th>Evidence</th><th>Description</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>'
        )

    def _build_html_pdf(self, detections, target):
        if not detections:
            return "<p>No AI chatbot indicators detected.</p>"
        rows = []
        for d in detections:
            rows.append(
                f'<tr><td>{d["platform"]}</td>'
                f'<td>{d["confidence"]}</td>'
                f'<td>{d["source"]}</td>'
                f'<td>{d["description"]}</td></tr>'
            )
        return (
            f'<p><strong>{len(detections)}</strong> AI chatbot indicator(s) detected.</p>'
            '<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;width:100%">'
            '<tr><th>Platform</th><th>Confidence</th><th>Source</th><th>Description</th></tr>'
            f'{"".join(rows)}</table>'
        )

    # ------------------------------------------------------------------
    # Dry run
    # ------------------------------------------------------------------

    def get_dry_run_info(self, target, output_dir):
        return {
            "description": self.description,
            "operations": [
                "Read katana_processed.json / katana.txt for chatbot URL indicators",
                "Read whatweb_processed.json for chatbot technology fingerprints",
                "Read script_detection_processed.json for chatbot script indicators",
                f"Filter results by confidence >= {self.confidence_threshold}",
            ]
        }