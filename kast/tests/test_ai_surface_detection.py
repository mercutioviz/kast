"""
Tests for the AI Surface Detection plugin (C7 rename from ai_chatbot_detection).
Covers chatbot detection (existing) and AI search/RAG detection (new).
"""

import json
import os
import tempfile
import unittest

from kast.plugins.ai_surface_detection_plugin import AiSurfaceDetectionPlugin


class MinimalArgs:
    verbose = False
    mode = "passive"


class TestAiSurfaceDetectionAvailability(unittest.TestCase):
    """Plugin is always available since it's analysis-only."""

    def test_is_available(self):
        plugin = AiSurfaceDetectionPlugin(MinimalArgs())
        self.assertTrue(plugin.is_available())

    def test_metadata(self):
        plugin = AiSurfaceDetectionPlugin(MinimalArgs())
        meta = plugin.get_metadata()
        self.assertEqual(meta["name"], "ai_surface_detection")
        self.assertEqual(meta["scan_type"], "passive")
        self.assertIn("AI", meta["display_name"])


class TestRunNoData(unittest.TestCase):
    """When no prior plugin output exists, detections should be empty."""

    def test_run_empty_output_dir(self):
        plugin = AiSurfaceDetectionPlugin(MinimalArgs())
        with tempfile.TemporaryDirectory() as tmpdir:
            result = plugin.run("https://example.com", tmpdir, False)
            self.assertEqual(result["disposition"], "success")
            self.assertEqual(result["results"]["detections"], [])

    def test_run_disabled(self):
        plugin = AiSurfaceDetectionPlugin(MinimalArgs())
        plugin.enabled = False
        with tempfile.TemporaryDirectory() as tmpdir:
            result = plugin.run("https://example.com", tmpdir, False)
            self.assertEqual(result["disposition"], "success")
            self.assertEqual(result["results"]["detections"], [])


class TestKatanaChatbotAnalysis(unittest.TestCase):
    """Test chatbot detection from katana output."""

    def _make_plugin(self):
        return AiSurfaceDetectionPlugin(MinimalArgs())

    def test_chatbot_url_detected_in_katana_txt(self):
        plugin = self._make_plugin()
        with tempfile.TemporaryDirectory() as tmpdir:
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


class TestKatanaSearchAnalysis(unittest.TestCase):
    """Test AI search / RAG detection from katana output."""

    def _make_plugin(self):
        return AiSurfaceDetectionPlugin(MinimalArgs())

    def test_algolia_script_detected_in_katana_processed(self):
        plugin = self._make_plugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            processed = {
                "findings": {
                    "urls": [
                        "https://example.com/page1",
                        "https://cdn.jsdelivr.net/npm/algoliasearch@4/dist/algoliasearch.umd.js",
                        "https://example.com/products",
                    ]
                }
            }
            with open(os.path.join(tmpdir, "katana_processed.json"), "w") as f:
                json.dump(processed, f)
            result = plugin.run("https://example.com", tmpdir, False)
            detections = result["results"]["detections"]
            self.assertTrue(len(detections) >= 1)
            algolia_found = any("Algolia" in d["platform"] for d in detections)
            self.assertTrue(algolia_found, "Expected to find Algolia AI Search indicator")

    def test_semantic_search_url_detected(self):
        plugin = self._make_plugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "katana.txt"), "w") as f:
                f.write("https://example.com/api/semantic-search\n")
            result = plugin.run("https://example.com", tmpdir, False)
            detections = result["results"]["detections"]
            self.assertTrue(len(detections) >= 1)
            self.assertTrue(any(d.get("detection_type") == "ai_search" for d in detections))

    def test_rag_query_url_detected(self):
        plugin = self._make_plugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "katana.txt"), "w") as f:
                f.write("https://example.com/rag-query\n")
            result = plugin.run("https://example.com", tmpdir, False)
            detections = result["results"]["detections"]
            self.assertTrue(len(detections) >= 1)
            self.assertTrue(any(d.get("detection_type") == "ai_search" for d in detections))


class TestWhatWebAnalysis(unittest.TestCase):
    """Test detection from whatweb output."""

    def _make_plugin(self):
        return AiSurfaceDetectionPlugin(MinimalArgs())

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

    def test_algolia_detected_in_whatweb(self):
        plugin = self._make_plugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            processed = {
                "findings": {
                    "results": [
                        {
                            "plugins": {
                                "Algolia": {"version": ["4.0"]},
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
            self.assertTrue(any("Algolia" in d["platform"] for d in detections))
            self.assertTrue(any(d.get("detection_type") == "ai_search" for d in detections))

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
        return AiSurfaceDetectionPlugin(MinimalArgs())

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

    def test_algolia_sdk_detected_in_scripts(self):
        """AI search/RAG pattern: Algolia SDK loaded as external script."""
        plugin = self._make_plugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            processed = {
                "findings": {
                    "disposition": "success",
                    "results": {
                        "scripts": [
                            {"url": "https://cdn.jsdelivr.net/npm/algoliasearch@4/dist/algoliasearch.umd.js",
                             "hostname": "cdn.jsdelivr.net", "origin": "https://cdn.jsdelivr.net",
                             "is_same_origin": False},
                        ],
                        "unique_origins": ["https://cdn.jsdelivr.net"],
                    }
                }
            }
            with open(os.path.join(tmpdir, "script_detection_processed.json"), "w") as f:
                json.dump(processed, f)
            result = plugin.run("https://example.com", tmpdir, False)
            detections = result["results"]["detections"]
            self.assertTrue(len(detections) >= 1)
            self.assertTrue(any("Algolia" in d["platform"] for d in detections))
            self.assertTrue(any(d.get("detection_type") == "ai_search" for d in detections))

    def test_real_format_no_ai_scripts(self):
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
                        ],
                        "unique_origins": ["https://cdn.example.com"],
                    }
                }
            }
            with open(os.path.join(tmpdir, "script_detection_processed.json"), "w") as f:
                json.dump(processed, f)
            result = plugin.run("https://www.example.com", tmpdir, False)
            self.assertEqual(result["results"]["detections"], [])

    def test_legacy_format_external_script_drift(self):
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
    def test_filter_high_only(self):
        plugin = AiSurfaceDetectionPlugin(MinimalArgs())
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
        plugin = AiSurfaceDetectionPlugin(MinimalArgs())
        plugin.confidence_threshold = "medium"
        detections = [
            {"platform": "A", "confidence": "low", "source": "x", "evidence": "e", "description": "d"},
            {"platform": "B", "confidence": "medium", "source": "x", "evidence": "e", "description": "d"},
            {"platform": "C", "confidence": "high", "source": "x", "evidence": "e", "description": "d"},
        ]
        filtered = plugin._apply_confidence_filter(detections)
        self.assertEqual(len(filtered), 2)


class TestPostProcess(unittest.TestCase):
    def test_post_process_chatbot_detection(self):
        plugin = AiSurfaceDetectionPlugin(MinimalArgs())
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
                        "detection_type": "chatbot",
                    }
                ]
            })
            out_path = plugin.post_process(raw, tmpdir)
            self.assertTrue(os.path.isfile(out_path))
            with open(out_path) as f:
                data = json.load(f)
            self.assertEqual(data["plugin-name"], "ai_surface_detection")
            self.assertEqual(data["findings_count"], 1)
            self.assertIn("Drift", data["executive_summary"])
            self.assertIn("AI-CHATBOT-001", data["issues"])
            self.assertIn("custom_html", data)
            self.assertIn("custom_html_pdf", data)

    def test_post_process_search_detection_emits_ai_search_001(self):
        plugin = AiSurfaceDetectionPlugin(MinimalArgs())
        with tempfile.TemporaryDirectory() as tmpdir:
            raw = plugin.get_result_dict("success", {
                "target": "https://example.com",
                "detections": [
                    {
                        "platform": "Algolia AI Search",
                        "confidence": "high",
                        "source": "script_detection_external",
                        "evidence": "https://cdn.jsdelivr.net/npm/algoliasearch@4/dist/algoliasearch.umd.js",
                        "description": "AI-powered search-as-a-service platform",
                        "detection_type": "ai_search",
                    }
                ]
            })
            out_path = plugin.post_process(raw, tmpdir)
            with open(out_path) as f:
                data = json.load(f)
            self.assertIn("AI-SEARCH-001", data["issues"])
            self.assertNotIn("AI-CHATBOT-001", data["issues"])

    def test_post_process_no_detections(self):
        plugin = AiSurfaceDetectionPlugin(MinimalArgs())
        with tempfile.TemporaryDirectory() as tmpdir:
            raw = plugin.get_result_dict("success", {
                "target": "https://example.com",
                "detections": []
            })
            out_path = plugin.post_process(raw, tmpdir)
            with open(out_path) as f:
                data = json.load(f)
            self.assertEqual(data["findings_count"], 0)
            self.assertEqual(data["issues"], [])
            self.assertIn("No AI surface", data["executive_summary"])

    def test_post_process_multiple_chatbots_triggers_002(self):
        plugin = AiSurfaceDetectionPlugin(MinimalArgs())
        with tempfile.TemporaryDirectory() as tmpdir:
            raw = plugin.get_result_dict("success", {
                "target": "https://example.com",
                "detections": [
                    {"platform": "A", "confidence": "high", "source": "s", "evidence": "e",
                     "description": "d", "detection_type": "chatbot"},
                    {"platform": "B", "confidence": "high", "source": "s", "evidence": "e",
                     "description": "d", "detection_type": "chatbot"},
                    {"platform": "C", "confidence": "high", "source": "s", "evidence": "e",
                     "description": "d", "detection_type": "chatbot"},
                ]
            })
            out_path = plugin.post_process(raw, tmpdir)
            with open(out_path) as f:
                data = json.load(f)
            self.assertIn("AI-CHATBOT-001", data["issues"])
            self.assertIn("AI-CHATBOT-002", data["issues"])

    def test_post_process_mixed_detection_types(self):
        """Both chatbot and search detections → both issue IDs emitted."""
        plugin = AiSurfaceDetectionPlugin(MinimalArgs())
        with tempfile.TemporaryDirectory() as tmpdir:
            raw = plugin.get_result_dict("success", {
                "target": "https://example.com",
                "detections": [
                    {"platform": "Drift", "confidence": "high", "source": "s", "evidence": "e",
                     "description": "d", "detection_type": "chatbot"},
                    {"platform": "Algolia AI Search", "confidence": "high", "source": "s", "evidence": "e",
                     "description": "d", "detection_type": "ai_search"},
                ]
            })
            out_path = plugin.post_process(raw, tmpdir)
            with open(out_path) as f:
                data = json.load(f)
            self.assertIn("AI-CHATBOT-001", data["issues"])
            self.assertIn("AI-SEARCH-001", data["issues"])


class TestDeduplication(unittest.TestCase):
    def test_duplicates_removed(self):
        plugin = AiSurfaceDetectionPlugin(MinimalArgs())
        with tempfile.TemporaryDirectory() as tmpdir:
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
    def test_dependencies_declared(self):
        plugin = AiSurfaceDetectionPlugin(MinimalArgs())
        self.assertIsInstance(plugin.dependencies, list)
        dep_names = [d["plugin"] for d in plugin.dependencies]
        self.assertIn("katana", dep_names)
        self.assertIn("whatweb", dep_names)
        self.assertIn("script_detection", dep_names)

    def test_dependencies_satisfied_allows_run(self):
        plugin = AiSurfaceDetectionPlugin(MinimalArgs())
        previous = {
            "katana": {"disposition": "success"},
            "whatweb": {"disposition": "success"},
            "script_detection": {"disposition": "success"},
        }
        ok, reason = plugin.check_dependencies(previous)
        self.assertTrue(ok)

    def test_dependencies_missing_blocks_run(self):
        plugin = AiSurfaceDetectionPlugin(MinimalArgs())
        previous = {"katana": {"disposition": "success"}}
        ok, reason = plugin.check_dependencies(previous)
        self.assertFalse(ok)
        self.assertIn("whatweb", reason)


class TestDryRun(unittest.TestCase):
    def test_dry_run_info(self):
        plugin = AiSurfaceDetectionPlugin(MinimalArgs())
        info = plugin.get_dry_run_info("https://example.com", "/tmp/out")
        self.assertIn("description", info)
        self.assertIn("operations", info)
        self.assertTrue(len(info["operations"]) > 0)
