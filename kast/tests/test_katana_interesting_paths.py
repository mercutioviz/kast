"""
File: tests/test_katana_interesting_paths.py
Description: Test katana's "Interesting Endpoints" classification.

The section is prospect-facing and headed "may warrant security review", so a
false positive costs more than a missed detection. These tests pin the cases
that were wrong on real scan data.
"""

import unittest
from unittest.mock import Mock

from kast.plugins.katana_plugin import KatanaPlugin


class InterestingPathsBase(unittest.TestCase):
    def setUp(self):
        cli_args = Mock()
        cli_args.verbose = False
        cli_args.target = "example.com"
        self.plugin = KatanaPlugin(cli_args)

    def categorize(self, *labels):
        """Return {label: category} for whatever matched."""
        found = self.plugin._find_interesting_paths(list(labels))
        return {label: cat for cat, paths in found.items() for label in paths}

    def assertCategory(self, label, category):
        self.assertEqual(self.categorize(label).get(label), category)

    def assertNotInteresting(self, label):
        self.assertIsNone(
            self.categorize(label).get(label),
            f"{label!r} should not be flagged as security-relevant",
        )


class TestObservedFalsePositives(InterestingPathsBase):
    """Every case here was produced by a real scan of donate.wbez.org."""

    def test_news_articles_under_a_health_section(self):
        """34 of these were reported as Debug / Diagnostics endpoints."""
        self.assertNotInteresting(
            "www.wbez.org/health/2026/03/02/health-care-illinois-prisons"
        )
        self.assertNotInteresting(
            "chicago.suntimes.com/health/2026/04/24/obamacare-health-insurance"
        )

    def test_news_articles_under_a_media_section(self):
        self.assertNotInteresting(
            "www.wbez.org/media/2025/07/18/chicago-public-media-ceo-responds"
        )

    def test_bundled_css_and_js_under_files(self):
        """16 build artifacts were reported as Upload / Storage."""
        self.assertNotInteresting("/files/wbez/css/css_6t2_ulF8lLeeyt.css")
        self.assertNotInteresting("/files/wbez/js/js_GqDCPsE4jeKrtTr.js")

    def test_rss_feed_is_not_storage(self):
        self.assertNotInteresting("www.wbez.org/rss/media/index.xml")

    def test_share_link_query_string_is_ignored(self):
        """?url=...%2Fadmin%2F is a share button, not an admin panel."""
        self.assertNotInteresting(
            "twitter.com/intent/tweet?url=https%3A%2F%2Fexample.com%2Fadmin%2F"
        )


class TestStillDetected(InterestingPathsBase):
    """Tightening must not blind the plugin to the real thing."""

    def test_admin_panels(self):
        self.assertCategory("/admin/", "Admin / CMS")
        self.assertCategory("/admin/users/42", "Admin / CMS")
        self.assertCategory("/wp-admin/edit.php", "Admin / CMS")

    def test_health_endpoints(self):
        self.assertCategory("/health", "Debug / Diagnostics")
        self.assertCategory("/actuator/health", "Debug / Diagnostics")
        self.assertCategory("/healthz", "Debug / Diagnostics")

    def test_api_endpoints(self):
        self.assertCategory("/api/v2/users", "API Endpoints")
        self.assertCategory("/graphql", "API Endpoints")

    def test_authentication(self):
        self.assertCategory("/login", "Authentication")
        self.assertCategory("/auth/oauth2/authorize", "Authentication")

    def test_exposed_config(self):
        self.assertCategory("/.env", "Config / Exposed Files")
        self.assertCategory("/.git/config", "Config / Exposed Files")
        self.assertCategory("/swagger/index.html", "Config / Exposed Files")
        self.assertCategory("/config.php", "Config / Exposed Files")

    def test_upload_directories(self):
        self.assertCategory("/uploads/avatar.png.php", "Upload / Storage")
        self.assertCategory("/private/export", "Upload / Storage")

    def test_detection_survives_on_a_sibling_host(self):
        """Host-qualified labels must classify on their path, not their host."""
        self.assertCategory("intranet.example.com/admin/", "Admin / CMS")


class TestSegmentMatching(InterestingPathsBase):
    """Matching is on whole segments, so a word inside another word is not a hit."""

    def test_substring_inside_a_longer_segment_does_not_match(self):
        self.assertNotInteresting("/administrative-law/overview")
        self.assertNotInteresting("/registered-trademarks")
        self.assertNotInteresting("/healthcare-costs")
        self.assertNotInteresting("/api-guidelines-for-partners")

    def test_exact_segment_still_matches(self):
        self.assertCategory("/administrator/index.php", "Admin / CMS")
        self.assertCategory("/register", "Authentication")


class TestDepthAndDateRules(InterestingPathsBase):
    def test_deep_diagnostics_paths_are_rejected(self):
        """A real /health endpoint is shallow; a deep one is a content section."""
        self.assertNotInteresting("/health/policy/research/papers/2024-review")

    def test_depth_limit_does_not_apply_to_api(self):
        self.assertCategory("/api/v1/tenants/9/users/42/sessions", "API Endpoints")

    def test_two_part_dates_are_suppressed(self):
        self.assertNotInteresting("www.example.com/media/2025/07/some-story")

    def test_a_year_alone_is_not_a_date_run(self):
        """/api/2024/report is still an API path; only Y/M(/D) runs suppress."""
        self.assertCategory("/api/2024/report", "API Endpoints")


class TestFirstMatchWins(InterestingPathsBase):
    def test_category_priority_is_stable(self):
        """A path matching two categories lands in the higher-priority one."""
        self.assertCategory("/admin/api/keys", "Admin / CMS")

    def test_each_url_is_reported_once(self):
        found = self.plugin._find_interesting_paths(["/admin/api/keys"])
        self.assertEqual(sum(len(v) for v in found.values()), 1)


class TestEmptyAndOddInput(InterestingPathsBase):
    def test_root_and_empty_labels(self):
        self.assertEqual(self.plugin._find_interesting_paths(["/", "host.tld/"]), {})

    def test_no_matches_returns_empty_dict(self):
        self.assertEqual(self.plugin._find_interesting_paths(["/about", "/contact"]), {})


if __name__ == "__main__":
    unittest.main()
