#!/usr/bin/env python3
"""
Test for related_sites plugin target filtering functionality.

This test verifies that the plugin correctly filters out the original target
from the discovered subdomains to avoid duplication in results.
"""

import unittest
import sys
import os
from unittest.mock import Mock

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from kast.plugins.related_sites_plugin import RelatedSitesPlugin


class TestRelatedSitesFiltering(unittest.TestCase):
    """Test cases for target domain filtering in related_sites plugin."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create mock CLI args
        self.mock_args = Mock()
        self.mock_args.verbose = False
        self.mock_args.httpx_rate_limit = None
        
        # Create plugin instance
        self.plugin = RelatedSitesPlugin(self.mock_args)
    
    def test_normalize_hostname_basic(self):
        """Test basic hostname normalization."""
        # Test basic domain
        result = self.plugin._normalize_hostname("www.example.com")
        self.assertEqual(result, "www.example.com")
        
        # Test uppercase conversion
        result = self.plugin._normalize_hostname("WWW.EXAMPLE.COM")
        self.assertEqual(result, "www.example.com")
        
        # Test mixed case
        result = self.plugin._normalize_hostname("WwW.ExAmPlE.cOm")
        self.assertEqual(result, "www.example.com")
    
    def test_normalize_hostname_with_protocol(self):
        """Test hostname normalization with protocol prefixes."""
        # HTTP protocol
        result = self.plugin._normalize_hostname("http://www.example.com")
        self.assertEqual(result, "www.example.com")
        
        # HTTPS protocol
        result = self.plugin._normalize_hostname("https://www.example.com")
        self.assertEqual(result, "www.example.com")
        
        # With path
        result = self.plugin._normalize_hostname("https://www.example.com/path")
        self.assertEqual(result, "www.example.com/path")
    
    def test_normalize_hostname_with_port(self):
        """Test hostname normalization with port numbers."""
        # Standard HTTP port
        result = self.plugin._normalize_hostname("www.example.com:80")
        self.assertEqual(result, "www.example.com")
        
        # Standard HTTPS port
        result = self.plugin._normalize_hostname("www.example.com:443")
        self.assertEqual(result, "www.example.com")
        
        # Custom port
        result = self.plugin._normalize_hostname("www.example.com:8080")
        self.assertEqual(result, "www.example.com")
    
    def test_normalize_hostname_with_protocol_and_port(self):
        """Test hostname normalization with both protocol and port."""
        result = self.plugin._normalize_hostname("https://www.example.com:8443")
        self.assertEqual(result, "www.example.com")
        
        result = self.plugin._normalize_hostname("http://www.example.com:8080")
        self.assertEqual(result, "www.example.com")
    
    def test_normalize_hostname_with_trailing_slash(self):
        """Test hostname normalization with trailing slashes."""
        result = self.plugin._normalize_hostname("www.example.com/")
        self.assertEqual(result, "www.example.com")
        
        result = self.plugin._normalize_hostname("https://www.example.com:8080/")
        self.assertEqual(result, "www.example.com")
    
    def test_filtering_exact_match(self):
        """Test that exact matches are filtered correctly."""
        target = "www.example.com"
        subdomains = [
            "www.example.com",  # Should be filtered
            "mail.example.com",
            "api.example.com"
        ]
        
        target_normalized = self.plugin._normalize_hostname(target)
        filtered = [s for s in subdomains 
                   if self.plugin._normalize_hostname(s) != target_normalized]
        
        self.assertEqual(len(filtered), 2)
        self.assertNotIn("www.example.com", filtered)
        self.assertIn("mail.example.com", filtered)
        self.assertIn("api.example.com", filtered)
    
    def test_filtering_case_insensitive(self):
        """Test that filtering is case-insensitive."""
        target = "www.example.com"
        subdomains = [
            "WWW.EXAMPLE.COM",  # Should be filtered (same as target, different case)
            "www.Example.Com",  # Should be filtered (same as target, different case)
            "mail.example.com",
            "API.EXAMPLE.COM"
        ]
        
        target_normalized = self.plugin._normalize_hostname(target)
        filtered = [s for s in subdomains 
                   if self.plugin._normalize_hostname(s) != target_normalized]
        
        self.assertEqual(len(filtered), 2)
        self.assertIn("mail.example.com", filtered)
        self.assertIn("API.EXAMPLE.COM", filtered)
    
    def test_filtering_with_protocol(self):
        """Test that filtering works with protocol prefixes."""
        target = "www.example.com"
        subdomains = [
            "http://www.example.com",  # Should be filtered
            "https://www.example.com", # Should be filtered
            "mail.example.com",
            "http://api.example.com"
        ]
        
        target_normalized = self.plugin._normalize_hostname(target)
        filtered = [s for s in subdomains 
                   if self.plugin._normalize_hostname(s) != target_normalized]
        
        self.assertEqual(len(filtered), 2)
        self.assertIn("mail.example.com", filtered)
        self.assertIn("http://api.example.com", filtered)
    
    def test_filtering_with_ports(self):
        """Test that filtering works with port numbers."""
        target = "www.example.com"
        subdomains = [
            "www.example.com:80",    # Should be filtered
            "www.example.com:443",   # Should be filtered
            "www.example.com:8080",  # Should be filtered
            "mail.example.com:8080",
            "api.example.com"
        ]
        
        target_normalized = self.plugin._normalize_hostname(target)
        filtered = [s for s in subdomains 
                   if self.plugin._normalize_hostname(s) != target_normalized]
        
        self.assertEqual(len(filtered), 2)
        self.assertIn("mail.example.com:8080", filtered)
        self.assertIn("api.example.com", filtered)
    
    def test_filtering_no_duplicates(self):
        """Test that filtering works when target is not in list."""
        target = "www.example.com"
        subdomains = [
            "mail.example.com",
            "api.example.com",
            "admin.example.com"
        ]
        
        target_normalized = self.plugin._normalize_hostname(target)
        filtered = [s for s in subdomains 
                   if self.plugin._normalize_hostname(s) != target_normalized]
        
        self.assertEqual(len(filtered), 3)
        self.assertEqual(set(filtered), set(subdomains))
    
    def test_filtering_apex_domain(self):
        """Test filtering when target is apex domain."""
        target = "example.com"
        subdomains = [
            "example.com",      # Should be filtered
            "www.example.com",
            "mail.example.com"
        ]
        
        target_normalized = self.plugin._normalize_hostname(target)
        filtered = [s for s in subdomains 
                   if self.plugin._normalize_hostname(s) != target_normalized]
        
        self.assertEqual(len(filtered), 2)
        self.assertNotIn("example.com", filtered)
        self.assertIn("www.example.com", filtered)
        self.assertIn("mail.example.com", filtered)


def run_tests():
    """Run the test suite."""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestRelatedSitesFiltering)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(run_tests())
