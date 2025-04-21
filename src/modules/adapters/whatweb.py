#!/usr/bin/env python3
#
# kast/src/modules/adapters/whatweb.py
#
# Description: Adapter for WhatWeb web technology detection results
#

from .base import ToolAdapter
import os

class WhatWebAdapter(ToolAdapter):
    """Adapter for WhatWeb web technology detection results."""
    
    def __init__(self):
        super().__init__('whatweb', 'recon')
    
    def adapt(self, data):
        """
        Transform WhatWeb data into template-friendly format.
        
        Args:
            data (list/dict): The raw WhatWeb scan results
            
        Returns:
            list: Transformed WhatWeb results with organized technology information
        """
        if not data:
            return []
            
        adapted_data = []
        
        # Handle different data formats
        if isinstance(data, dict):
            # If it's a single entry
            entry = self._process_whatweb_entry(data)
            if entry:
                adapted_data.append(entry)
        elif isinstance(data, list):
            # If it's a list of entries
            for item in data:
                entry = self._process_whatweb_entry(item)
                if entry:
                    adapted_data.append(entry)
        
        return adapted_data

    def _process_whatweb_entry(self, entry):
        """Process a single WhatWeb entry"""
        if not entry or not isinstance(entry, dict):
            return None
            
        target = entry.get('target', '')
        technologies = []
        
        # Extract plugins/technologies
        plugins = entry.get('plugins', {})
        if plugins and isinstance(plugins, dict):
            for name, details in plugins.items():
                tech = {
                    'name': name,
                    'details': []
                }
                
                # Extract version if available
                if 'version' in details:
                    if isinstance(details['version'], list):
                        tech['details'].append(f"Version: {', '.join(details['version'])}")
                    else:
                        tech['details'].append(f"Version: {details['version']}")
                
                # Extract other details
                for key, value in details.items():
                    if key != 'version':
                        if isinstance(value, list):
                            tech['details'].append(f"{key}: {', '.join(str(v) for v in value)}")
                        else:
                            tech['details'].append(f"{key}: {value}")
                
                technologies.append(tech)
        
        # If no plugins section, try to extract other useful information
        if not technologies:
            for key, value in entry.items():
                if key not in ['target', 'http_status', 'plugins']:
                    tech = {
                        'name': key,
                        'details': [str(value)]
                    }
                    technologies.append(tech)
        
        return {
            'target': target,
            'technologies': technologies
        }