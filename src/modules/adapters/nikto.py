#!/usr/bin/env python3
#
# kast/src/modules/adapters/nikto.py
#
# Description: Adapter for Nikto vulnerability scanner results
#

from .base import ToolAdapter
import logging

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
        import os
        import glob
        import json
        
        pattern = os.path.join(results_dir, self.result_subdir, f'{self.tool_name}_quick_*.json')
        files = glob.glob(pattern)
        
        if not files:
            logging.warning(f"No Nikto quick scan results found at {pattern}")
            return None
        
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
            data (list): The raw Nikto scan results
            
        Returns:
            list: Transformed Nikto findings with severity information
        """
        if not data:
            return []
            
        adapted_data = []
        for finding in data:
            adapted_finding = {
                'id': finding.get('id', ''),
                'osvdb': finding.get('osvdb', ''),
                'message': finding.get('message', ''),
                'uri': finding.get('uri', ''),
                'severity': self._determine_severity(finding)
            }
            adapted_data.append(adapted_finding)
        
        return adapted_data
    
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
            # These are example mappings - you would need toexpand this with actual OSVDB references
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
