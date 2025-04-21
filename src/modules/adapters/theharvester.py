#!/usr/bin/env python3
#
# kast/src/modules/adapters/theharvester.py
#
# Description: Adapter for theHarvester information gathering results
#

from .base import ToolAdapter
import os

class TheHarvesterAdapter(ToolAdapter):
    """Adapter for theHarvester information gathering results."""
    
    def __init__(self):
        super().__init__('theharvester', 'recon')
    
    def adapt(self, data):
        """
        Transform theHarvester data into template-friendly format.
        
        Args:
            data (dict): The raw theHarvester results
            
        Returns:
            dict: Transformed theHarvester results with organized sections
        """
        if not data:
            return {}
            
        adapted_data = {
            'emails': data.get('emails', []),
            'hosts': data.get('hosts', []),
            'ips': data.get('ips', []),
            'additional': []
        }
        
        # Add any other sections that might be present
        for key, value in data.items():
            if key not in ['emails', 'hosts', 'ips'] and isinstance(value, list) and value:
                adapted_data['additional'].append({
                    'name': key,
                    'items': value
                })
        
        return adapted_data
