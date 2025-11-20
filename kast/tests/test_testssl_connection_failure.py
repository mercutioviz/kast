"""
Test for testssl plugin connection failure handling
"""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock
from kast.plugins.testssl_plugin import TestsslPlugin


class TestTestsslConnectionFailure(unittest.TestCase):
    """Test that testssl plugin properly handles connection failures"""

    def setUp(self):
        """Set up test fixtures"""
        self.cli_args = MagicMock()
        self.cli_args.verbose = False
        self.plugin = TestsslPlugin(self.cli_args)
        self.temp_dir = tempfile.mkdtemp()

    def test_connection_failure_handling(self):
        """Test that connection failures are properly handled and reported"""
        # Sample testssl output with connection failure (from the bug report)
        raw_output = {
            'Invocation': 'testssl -U -E -oJ /home/kali/kast_results/dentalassociates.com-20251120-215108/testssl.json dentalassociates.com',
            'at': 'kali:/usr/bin/openssl',
            'clientProblem1': [
                {
                    'finding': 'No engine or GOST support via engine with your /usr/bin/openssl',
                    'id': 'engine_problem',
                    'severity': 'WARN'
                }
            ],
            'openssl': 'OpenSSL 3.5.4 from Tue Sep 30 19:54:39 2025',
            'scanResult': [
                {
                    'finding': "Can't connect to '85.239.246.208:443' Make sure a firewall is not between you and your scanning target!",
                    'id': 'scanProblem',
                    'severity': 'FATAL'
                }
            ],
            'scanTime': 'Scan interrupted',
            'startTime': '1763675533',
            'version': '3.2.2 '
        }

        # Process the output
        result_path = self.plugin.post_process(raw_output, self.temp_dir)

        # Verify the processed file was created
        self.assertTrue(os.path.exists(result_path))

        # Load and verify the processed results
        with open(result_path, 'r') as f:
            processed = json.load(f)

        # Verify key fields are present
        self.assertEqual(processed['plugin-name'], 'testssl')
        self.assertEqual(processed['summary'], 'Unable to complete TLS scan.')
        self.assertIn('Unable to complete SSL/TLS scan', processed['details'])
        self.assertIn("Can't connect to '85.239.246.208:443'", processed['details'])
        self.assertIn('SSL/TLS scan could not be completed', processed['executive_summary'])
        self.assertEqual(processed['issues'], [])

        print(f"\n✓ Connection failure properly handled")
        print(f"  Summary: {processed['summary']}")
        print(f"  Details: {processed['details']}")
        print(f"  Executive Summary: {processed['executive_summary']}")

    def test_normal_scan_still_works(self):
        """Test that normal successful scans still work correctly"""
        # Sample successful testssl output
        raw_output = {
            'Invocation': 'testssl -U -E -oJ /tmp/testssl.json example.com',
            'scanResult': [
                {
                    'id': 'service',
                    'finding': 'HTTP',
                    'vulnerabilities': [
                        {
                            'id': 'heartbleed',
                            'finding': 'not vulnerable',
                            'severity': 'OK'
                        }
                    ],
                    'cipherTests': [
                        {
                            'id': 'tls1_2_strong',
                            'finding': 'offered',
                            'severity': 'OK'
                        }
                    ]
                }
            ]
        }

        # Process the output
        result_path = self.plugin.post_process(raw_output, self.temp_dir)

        # Verify the processed file was created
        self.assertTrue(os.path.exists(result_path))

        # Load and verify the processed results
        with open(result_path, 'r') as f:
            processed = json.load(f)

        # Verify normal processing occurred
        self.assertEqual(processed['plugin-name'], 'testssl')
        self.assertIn('No SSL/TLS vulnerabilities', processed['details'])
        self.assertIn('secure', processed['executive_summary'])

        print(f"\n✓ Normal scan processing still works")
        print(f"  Executive Summary: {processed['executive_summary']}")

    def tearDown(self):
        """Clean up test files"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)


if __name__ == '__main__':
    unittest.main()
