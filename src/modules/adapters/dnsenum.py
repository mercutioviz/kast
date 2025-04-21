#!/usr/bin/env python3
#
# kast/src/modules/adapters/dnsenum.py
#
# Description: Adapter for DNSenum DNS enumeration results
#

from .base import ToolAdapter
import os

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
        
        # Initialize with empty lists for all expected record types
        result = {
            'nameservers': [],
            'mx_records': [],
            'a_records': [],
            'other_records': []
        }
        
        # Process nameservers
        if 'nameservers' in data and isinstance(data['nameservers'], list):
            result['nameservers'] = data['nameservers']
        
        # Process MX records
        if 'mx_records' in data and isinstance(data['mx_records'], list):
            result['mx_records'] = data['mx_records']
        
        # Process A records
        if 'a_records' in data and isinstance(data['a_records'], list):
            result['a_records'] = data['a_records']
        elif 'hosts' in data and isinstance(data['hosts'], list):
            # Some formats store A records under 'hosts'
            result['a_records'] = data['hosts']
        
        # Process other records
        if 'other_records' in data and isinstance(data['other_records'], list):
            result['other_records'] = data['other_records']
        
        # Try to extract records from alternative formats
        if not any(result.values()):
            # If we haven't found any records yet, try to extract from other formats
            for key, value in data.items():
                if isinstance(value, list) and key not in result:
                    if 'ns' in key.lower():
                        result['nameservers'] = value
                    elif 'mx' in key.lower():
                        result['mx_records'] = value
                    elif 'a' in key.lower() or 'host' in key.lower():
                        result['a_records'] = value
                    else:
                        result['other_records'].extend(value)
        
        return result