#!/usr/bin/env python3
#
# kast/src/modules/adapters/wafw00f.py
#
# Description: Adapter for wafw00f Web Application Firewall detection results
#

from .base import ToolAdapter
import json
import logging
import os

class WAFw00fAdapter(ToolAdapter):
    """Adapter for wafw00f Web Application Firewall detection results."""
    
    def __init__(self):
        super().__init__('wafw00f', 'recon')
    
    def adapt(self, data):
        """
        Transform wafw00f data into template-friendly format.
        
        Args:
            data (dict/list): The raw wafw00f results
            
        Returns:
            dict: Transformed wafw00f results with organized WAF information
        """
        if not data:
            return {'detected': False, 'waf': None, 'details': {}}
        
        # Handle different possible data structures
        if isinstance(data, list):
            # If data is a list of detections
            if not data:
                return {'detected': False, 'waf': None, 'details': {}}
            
            # Use the first detection (usually there's only one)
            detection = data[0]
            return {
                'detected': True,
                'waf': detection.get('waf', 'Unknown WAF'),
                'details': detection
            }
        elif isinstance(data, dict):
            # If data is a dictionary with detection info
            if 'waf' in data:
                return {
                    'detected': True,
                    'waf': data.get('waf', 'Unknown WAF'),
                    'details': data
                }
            else:
                # Check if there's a nested structure
                for key, value in data.items():
                    if isinstance(value, dict) and 'waf' in value:
                        return {
                            'detected': True,
                            'waf': value.get('waf', 'Unknown WAF'),
                            'details': value
                        }
            
            # If no WAF info found in the dictionary
            return {'detected': False, 'waf': None, 'details': data}
        else:
            # Unexpected data format
            logging.warning(f"Unexpected wafw00f data format: {type(data)}")
            return {'detected': False, 'waf': None, 'details': {}}
