#!/usr/bin/env python3
#
# kast/src/modules/adapters/nikto.py
#
# Description: Adapter for Nikto vulnerability scanner results
#

from .base import ToolAdapter
import logging
import os
import glob
import json

class NiktoAdapter(ToolAdapter):
    """Adapter for Nikto vulnerability scanner results."""
    
    def __init__(self):
        super().__init__('nikto', 'vuln')
    
    def load_data(self, results_dir):
        """
        Load Nikto data from the quick scan JSON file.
        
        Args:
            results_dir (str): Path to the results directory
            
        Returns:
            list: The loaded Nikto scan results
        """
        # Try both naming patterns: with and without underscore
        patterns = [
            os.path.join(results_dir, self.result_subdir, f'{self.tool_name}_thorough_*.json')
        ]
        
        files = []
        for pattern in patterns:
            files.extend(glob.glob(pattern))
        
        if not files:
            logging.warning(f"No Nikto scan results found in {os.path.join(results_dir, self.result_subdir)}")
            return None
        
        logging.info(f"Found Nikto scan results: {files}")
        logging.info(f"Loading Nikto data from {files[0]}")
        try:
            with open(files[0], 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading Nikto data: {e}")
            return None
    
    def adapt(self, data):
        """
        Transform Nikto data into template-friendly format.
        
        Args:
            data (list/dict): The raw Nikto scan results
            
        Returns:
            list: Transformed Nikto findings with severity information
        """
        if not data:
            return []
        
        adapted_data = []
        
        # Handle different data formats
        if isinstance(data, dict):
            # If it's a dictionary with scan results
            if 'vulnerabilities' in data:
                # Format 1: Direct vulnerabilities list
                for vuln in data['vulnerabilities']:
                    adapted_data.append(self._process_vulnerability(vuln))
            elif 'scan' in data and isinstance(data['scan'], dict):
                # Format 2: Nested scan results
                for host, host_data in data['scan'].items():
                    if 'vulnerabilities' in host_data:
                        for vuln in host_data['vulnerabilities']:
                            adapted_data.append(self._process_vulnerability(vuln))
            else:
                # Format 3: Simple list of findings
                for finding in data:
                    if isinstance(finding, dict):
                        adapted_data.append(self._process_vulnerability(finding))
        elif isinstance(data, list):
            # If it's a list of findings
            for finding in data:
                adapted_data.append(self._process_vulnerability(finding))
        
        return adapted_data

    def _process_vulnerability(self, vuln):
        """Process a single vulnerability entry"""
        if not isinstance(vuln, dict):
            return {
                'id': 'unknown',
                'osvdb': '',
                'message': str(vuln),
                'uri': '',
                'severity': 'info'
            }
        
        # Extract basic information
        finding = {
            'id': vuln.get('id', ''),
            'osvdb': vuln.get('osvdb', ''),
            'message': vuln.get('message', ''),
            'uri': vuln.get('uri', vuln.get('url', '')),
            'severity': self._determine_severity(vuln)
        }
        
        return finding
    
    def _determine_severity(self, finding):
        """
        Determine the severity of a Nikto finding based on its content.
        
        Args:
            finding (dict): A Nikto finding
            
        Returns:
            str: Severity level ('high', 'medium', 'low', or 'info')
        """
        # Check OSVDB reference first
        osvdb = finding.get('osvdb', '')
        if osvdb:
            # These are example mappings - you would need to expand this with actual OSVDB references
            high_risk_osvdb = ['11771', '877', '12613', '838']
            medium_risk_osvdb = ['3268', '5646', '576']
            low_risk_osvdb = ['13648', '3092', '3093']
            
            if osvdb in high_risk_osvdb:
                return 'high'
            elif osvdb in medium_risk_osvdb:
                return 'medium'
            elif osvdb in low_risk_osvdb:
                return 'low'
        
        # If no OSVDB match, check message content
        message = finding.get('message', '').lower()
        if any(word in message for word in ['critical', 'high', 'xss', 'sql injection', 'remote code']):
            return 'high'
        elif any(word in message for word in ['medium', 'moderate', 'csrf', 'directory listing']):
            return 'medium'
        elif any(word in message for word in ['low', 'information disclosure']):
            return 'low'
        else:
            return 'info'