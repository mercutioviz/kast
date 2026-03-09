"""
Tests for the AI Chatbot Detection plugin.
"""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock

from kast.plugins.ai_chatbot_detection_plugin import AiChatbotDetectionPlugin


class MinimalArgs:
    verbose = False
    mode = "passive"


class TestAiChatbotDetectionAvailability(unittest.TestCase):
    """Plugin is always available since it's analysis-only."""

    def test_is_available(self):
        plugin = AiChatbotDetectionPlugin(MinimalArgs())
        self.assertTrue(plugin.is_available())

    def test_metadata(self):
        plugin = AiChatbotDetectionPlugin(MinimalArgs())
        meta = plugin.get_metadata()
        self.assertEqual(meta["name"], "ai_chatbot_detection")
        self.assertEqual(meta["scan_type"], "passive")
        self.assertIn("AI", meta["display_name"])


class TestRunNoData(unittest.TestCase):
    """When no prior plugin output exists, detections should be empty."""

    def test_run_empty_output_dir(self):
        plugin = AiChatbotDetectionPlugin(MinimalArgs())
        with tempfile.TemporaryDirectory() as tmpdir:
            result = plugin.run("https://example.com", tmpdir, False)
            self.assertEqual(result["disposition"], "success")
            self.assertEqual(result["results"]["detections"], [])

    def test_run_disabled(self):
        plugin = AiChatbotDetectionPlugin(MinimalArgs())
        plugin.enabled = False
        with tempfile.TemporaryDirectory() as tmpdir:
            result = plugin.run("https://example.com", tmpdir, False)
            self.assertEqual(result["disposition"], "success")
            self.assertEqual(result["results"]["detections"], [])


class TestKatanaAnalysis(unittest.TestCase):
    """Test detection from katana output."""

    def _make_plugin(self):
        return AiChatbotDetectionPlugin(MinimalArgs())

    def test_chatbot_url_detected_in_katana_txt(self):
        plugin = self._make_plugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write a katana.txt with a chatbot URL
            with open(os.path.join(tmpdir, "katana.txt"), "w") as f:
                f.write("https://example.com/page1\n")
                f.write("https://example.com/ai-chat\n")
                f.write("https://example.com/about\n")
            result = plugin.run("https://example.com", tmpdir, False)
            detections = result["results"]["detections"]
            self.assertTrue(len(detections) >= 1)
            platforms = [d["source"] for d in detections]
            self.assertIn("katana_url", platforms)

    def test_chatbot_script_url_in_katana_processed(self):
        plugin = self._make_plugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            processed = {
                "findings": {
                    "urls": [
                        "https://example.com/page1",
                        "https://js.driftt.com/include/12345/widget.js",
                        "https://example.com/contact",
                    ]
                }
            }
            with open(os.path.join(tmpdir, "katana_processed.json"), "w") as f:
                json.dump(processed, f)
            result = plugin.run("https://example.com", tmpdir, False)
            detections = result["results"]["detections"]
            self.assertTrue(len(detections) >= 1)
            drift_found = any("Drift" in d["platform"] for d in detections)
            self.assertTrue(drift_found, "Expected to find Drift chatbot indicator")

    def test_no_false_positive_on_clean_urls(self):
        plugin = self._make_plugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "katana.txt"), "w") as f:
                f.write("https://example.com/index.html\n")
                f.write("https://example.com/about\n")
                f.write("https://example.com/contact\n")
            result = plugin.run("https://example.com", tmpdir, False)
            self.assertEqual(result["results"]["detections"], [])


class TestWhatWebAnalysis(unittest.TestCase):
    """Test detection from whatweb output."""

    def _make_plugin(self):
        return AiChatbotDetectionPlugin(MinimalArgs())

    def test_intercom_detected_in_whatweb(self):
        plugin = self._make_plugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            processed = {
                "findings": {
                    "results": [
                        {
                            "plugins": {
                                "Intercom": {"version": ["3.0"]},
                                "jQuery": {"version": ["3.6.0"]},
                            }
                        }
                    ]
                }
            }
            with open(os.path.join(tmpdir, "whatweb_processed.json"), "w") as f:
                json.dump(processed, f)
            result = plugin.run("https://example.com", tmpdir, False)
            detections = result["results"]["detections"]
            self.assertTrue(len(detections) >= 1)
            self.assertTrue(any("Intercom" in d["platform"] for d in detections))

    def test_whatweb_string_match(self):
        plugin = self._make_plugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            processed = {
                "findings": {
                    "results": [
                        {
                            "plugins": {
                                "Script": {
                                    "string": ["https://widget.intercom.io/widget/abc123"]
                                }
                            }
                        }
                    ]
                }
            }
            with open(os.path.join(tmpdir, "whatweb_processed.json"), "w") as f:
                json.dump(processed, f)
            result = plugin.run("https://example.com", tmpdir, False)
            detections = result["results"]["detections"]
            self.assertTrue(len(detections) >= 1)


class TestScriptDetectionAnalysis(unittest.TestCase):
    """Test detection from script_detection output."""

    def _make_plugin(self):
        return AiChatbotDetectionPlugin(MinimalArgs())

    def test_real_format_scripts_list_qualified(self):
        """Test with real script_detection data format: findings.results.scripts[]"""
        plugin = self._make_plugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            processed = {
                "findings": {
                    "name": "script_detection",
                    "timestamp": "2026-03-08T20:34:10.007",
                    "disposition": "success",
                    "results": {
                        "target_url": "https://www.example.com",
                        "target_origin": "https://www.example.com",
                        "total_scripts": 5,
                        "scripts_analyzed": 5,
                        "scripts": [
                            {"url": "https://www.example.com/main.js", "hostname": "www.example.com",
                             "path": "/main.js", "origin": "https://www.example.com", "is_same_origin": True},
                            {"url": "https://js.qualified.com/qualified.js?token=abc123", "hostname": "js.qualified.com",
                             "path": "/qualified.js", "origin": "https://js.qualified.com", "is_same_origin": False},
                            {"url": "https://cdn.example.com/jquery.min.js", "hostname": "cdn.example.com",
                             "path": "/jquery.min.js", "origin": "https://cdn.example.com", "is_same_origin": False},
                        ],
                        "unique_origins": [
                            "https://www.example.com",
                            "https://js.qualified.com",
                            "https://cdn.example.com",
                        ],
                    }
                }
            }
            with open(os.path.join(tmpdir, "script_detection_processed.json"), "w") as f:
                json.dump(processed, f)
            result = plugin.run("https://www.example.com", tmpdir, False)
            detections = result["results"]["detections"]
            self.assertTrue(len(detections) >= 1, "Expected at least 1 detection for Qualified")
            self.assertTrue(any("Qualified" in d["platform"] for d in detections))
            # Should not duplicate from both scripts[] and unique_origins[]
            qualified_count = sum(1 for d in detections if "Qualified" in d["platform"])
            self.assertEqual(qualified_count, 1, "Qualified should appear once, not duplicated")

    def test_real_format_scripts_list_drift(self):
        """Test with real format: drift detected from scripts[] URL."""
        plugin = self._make_plugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            processed = {
                "findings": {
                    "name": "script_detection",
                    "disposition": "success",
                    "results": {
                        "scripts": [
                            {"url": "https://js.driftt.com/include/12345/drift.js", "hostname": "js.driftt.com",
                             "origin": "https://js.driftt.com", "is_same_origin": False},
                        ],
                        "unique_origins": ["https://js.driftt.com"],
                    }
                }
            }
            with open(os.path.join(tmpdir, "script_detection_processed.json"), "w") as f:
                json.dump(processed, f)
            result = plugin.run("https://example.com", tmpdir, False)
            detections = result["results"]["detections"]
            self.assertTrue(len(detections) >= 1)
            self.assertTrue(any("Drift" in d["platform"] for d in detections))

    def test_real_format_no_chatbot_scripts(self):
        """Test with real format: no chatbot scripts present."""
        plugin = self._make_plugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            processed = {
                "findings": {
                    "name": "script_detection",
                    "disposition": "success",
                    "results": {
                        "scripts": [
                            {"url": "https://cdn.example.com/jquery.min.js", "hostname": "cdn.example.com",
                             "origin": "https://cdn.example.com", "is_same_origin": False},
                            {"url": "https://www.example.com/app.js", "hostname": "www.example.com",
                             "origin": "https://www.example.com", "is_same_origin": True},
                        ],
                        "unique_origins": ["https://cdn.example.com", "https://www.example.com"],
                    }
                }
            }
            with open(os.path.join(tmpdir, "script_detection_processed.json"), "w") as f:
                json.dump(processed, f)
            result = plugin.run("https://www.example.com", tmpdir, False)
            detections = result["results"]["detections"]
            self.assertEqual(len(detections), 0, "No chatbot scripts should be detected")

    def test_legacy_format_external_script_drift(self):
        """Test legacy fallback format: findings.external_scripts[]"""
        plugin = self._make_plugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            processed = {
                "findings": {
                    "external_scripts": [
                        {"src": "https://js.driftt.com/include/12345/drift.js"},
                        {"src": "https://cdn.example.com/jquery.min.js"},
                    ]
                }
            }
            with open(os.path.join(tmpdir, "script_detection_processed.json"), "w") as f:
                json.dump(processed, f)
            result = plugin.run("https://example.com", tmpdir, False)
            detections = result["results"]["detections"]
            self.assertTrue(len(detections) >= 1)
            self.assertTrue(any("Drift" in d["platform"] for d in detections))

    def test_legacy_format_inline_script_tidio(self):
        """Test legacy fallback format: findings.inline_scripts[]"""
        plugin = self._make_plugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            processed = {
                "findings": {
                    "external_scripts": [],
                    "inline_scripts": [
                        {"content": "window.tidioChatCode = 'abc123'; // tidio.co init"}
                    ]
                }
            }
            with open(os.path.join(tmpdir, "script_detection_processed.json"), "w") as f:
                json.dump(processed, f)
            result = plugin.run("https://example.com", tmpdir, False)
            detections = result["results"]["detections"]
            self.assertTrue(len(detections) >= 1)
            self.assertTrue(any("Tidio" in d["platform"] for d in detections))


class TestConfidenceFilter(unittest.TestCase):
    """Test confidence-based filtering."""

    def test_filter_high_only(self):
        plugin = AiChatbotDetectionPlugin(MinimalArgs())
        plugin.confidence_threshold = "high"
        detections = [
            {"platform": "A", "confidence": "low", "source": "x", "evidence": "e", "description": "d"},
            {"platform": "B", "confidence": "medium", "source": "x", "evidence": "e", "description": "d"},
            {"platform": "C", "confidence": "high", "source": "x", "evidence": "e", "description": "d"},
        ]
        filtered = plugin._apply_confidence_filter(detections)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["platform"], "C")

    def test_filter_medium_and_above(self):
        plugin = AiChatbotDetectionPlugin(MinimalArgs())
        plugin.confidence_threshold = "medium"
        detections = [
            {"platform": "A", "confidence": "low", "source": "x", "evidence": "e", "description": "d"},
            {"platform": "B", "confidence": "medium", "source": "x", "evidence": "e", "description": "d"},
            {"platform": "C", "confidence": "high", "source": "x", "evidence": "e", "description": "d"},
        ]
        filtered = plugin._apply_confidence_filter(detections)
        self.assertEqual(len(filtered), 2)


class TestPostProcess(unittest.TestCase):
    """Test the post_process method produces valid output."""

    def test_post_process_with_detections(self):
        plugin = AiChatbotDetectionPlugin(MinimalArgs())
        with tempfile.TemporaryDirectory() as tmpdir:
            raw = plugin.get_result_dict("success", {
                "target": "https://example.com",
                "detections": [
                    {
                        "platform": "Drift",
                        "confidence": "high",
                        "source": "katana_url",
                        "evidence": "https://js.driftt.com/widget.js",
                        "description": "Conversational marketing / AI chatbot",
                    }
                ]
            })
            out_path = plugin.post_process(raw, tmpdir)
            self.assertTrue(os.path.isfile(out_path))
            with open(out_path) as f:
                data = json.load(f)
            self.assertEqual(data["plugin-name"], "ai_chatbot_detection")
            self.assertEqual(data["findings_count"], 1)
            self.assertIn("Drift", data["executive_summary"])
            self.assertIn("AI-CHATBOT-001", data["issues"])
            self.assertIn("custom_html", data)
            self.assertIn("custom_html_pdf", data)

    def test_post_process_no_detections(self):
        plugin = AiChatbotDetectionPlugin(MinimalArgs())
        with tempfile.TemporaryDirectory() as tmpdir:
            raw = plugin.get_result_dict("success", {
                "target": "https://example.com",
                "detections": []
            })
            out_path = plugin.post_process(raw, tmpdir)
            self.assertTrue(os.path.isfile(out_path))
            with open(out_path) as f:
                data = json.load(f)
            self.assertEqual(data["findings_count"], 0)
            self.assertEqual(data["issues"], [])
            self.assertIn("No AI chatbot", data["executive_summary"])

    def test_post_process_multiple_detections_triggers_002(self):
        plugin = AiChatbotDetectionPlugin(MinimalArgs())
        with tempfile.TemporaryDirectory() as tmpdir:
            raw = plugin.get_result_dict("success", {
                "target": "https://example.com",
                "detections": [
                    {"platform": "A", "confidence": "high", "source": "s", "evidence": "e", "description": "d"},
                    {"platform": "B", "confidence": "high", "source": "s", "evidence": "e", "description": "d"},
                    {"platform": "C", "confidence": "high", "source": "s", "evidence": "e", "description": "d"},
                ]
            })
            out_path = plugin.post_process(raw, tmpdir)
            with open(out_path) as f:
                data = json.load(f)
            self.assertIn("AI-CHATBOT-001", data["issues"])
            self.assertIn("AI-CHATBOT-002", data["issues"])


class TestDeduplication(unittest.TestCase):
    """Test that duplicate detections are removed."""

    def test_duplicates_removed(self):
        plugin = AiChatbotDetectionPlugin(MinimalArgs())
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write same drift URL in both katana.txt and katana_processed.json
            drift_url = "https://js.driftt.com/include/123/drift.js"
            with open(os.path.join(tmpdir, "katana.txt"), "w") as f:
                f.write(drift_url + "\n")
            processed = {"findings": {"urls": [drift_url]}}
            with open(os.path.join(tmpdir, "katana_processed.json"), "w") as f:
                json.dump(processed, f)
            result = plugin.run("https://example.com", tmpdir, False)
            detections = result["results"]["detections"]
            drift_count = sum(1 for d in detections if "Drift" in d["platform"])
            self.assertEqual(drift_count, 1, "Duplicate drift detection should be de-duped")


class TestDependencies(unittest.TestCase):
    """Test that dependencies are declared for parallel mode safety."""

    def test_dependencies_declared(self):
        plugin = AiChatbotDetectionPlugin(MinimalArgs())
        self.assertIsInstance(plugin.dependencies, list)
        dep_names = [d["plugin"] for d in plugin.dependencies]
        self.assertIn("katana", dep_names)
        self.assertIn("whatweb", dep_names)
        self.assertIn("script_detection", dep_names)

    def test_dependencies_satisfied_allows_run(self):
        plugin = AiChatbotDetectionPlugin(MinimalArgs())
        previous = {
            "katana": {"disposition": "success"},
            "whatweb": {"disposition": "success"},
            "script_detection": {"disposition": "success"},
        }
        ok, reason = plugin.check_dependencies(previous)
        self.assertTrue(ok)

    def test_dependencies_missing_blocks_run(self):
        plugin = AiChatbotDetectionPlugin(MinimalArgs())
        previous = {"katana": {"disposition": "success"}}
        ok, reason = plugin.check_dependencies(previous)
        self.assertFalse(ok)
        self.assertIn("whatweb", reason)


class TestDryRun(unittest.TestCase):
    """Test dry run info."""

    def test_dry_run_info(self):
        plugin = AiChatbotDetectionPlugin(MinimalArgs())
        info = plugin.get_dry_run_info("https://example.com", "/tmp/out")
        self.assertIn("description", info)
        self.assertIn("operations", info)
        self.assertTrue(len(info["operations"]) > 0)


if __name__ == "__main__":
    unittest.main()