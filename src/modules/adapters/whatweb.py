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
            data (list): The raw WhatWeb scan results
            
        Returns:
            list: Transformed WhatWeb results with organized technology information
        """
        if not data:
            return []
            
        adapted_data = []
        for entry in data:
            adapted_entry = {
                'target': entry.get('target', ''),
                'technologies': []
            }
            
            # Extract technologies
            for key, value in entry.items():
                if key != 'target' and isinstance(value, list):
                    adapted_entry['technologies'].append({
                        'name': key,
                        'details': value
                    })
            
            adapted_data.append(adapted_entry)
        
        return adapted_data
