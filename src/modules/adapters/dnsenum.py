#!/usr/bin/env python3
#
# kast/src/modules/adapters/dnsenum.py
#
# Description: Adapter for DNSenum DNS enumeration results
#

from .base import ToolAdapter

class DNSenumAdapter(ToolAdapter):
    """Adapter for DNSenum DNS enumeration results."""
    
    def __init__(self):
        super().__init__('dnsenum', 'recon')
    
    def adapt(self, data):
        """
        Transform DNSenum data into template-friendly format.
        
        Args:
            data (dict): The raw DNSenum results
            
        Returns:
            dict: Transformed DNSenum results with organized DNS record sections
        """
        if not data:
            return {}
            
        return {
            'nameservers': data.get('nameservers', []),
            'mx_records': data.get('mx_records', []),
            'a_records': data.get('a_records', []),
            'other_records': data.get('other_records', [])
        }
