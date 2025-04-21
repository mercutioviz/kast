#!/usr/bin/env python3
#
# kast/src/modules/adapters/sslscan.py
#
# Description: Adapter for SSLScan SSL/TLS configuration results
#

from .base import ToolAdapter

class SSLScanAdapter(ToolAdapter):
    """Adapter for SSLScan SSL/TLS configuration results."""
    
    def __init__(self):
        super().__init__('sslscan', 'recon')
    
    def adapt(self, data):
        """
        Transform SSLScan data into template-friendly format.
        
        Args:
            data (dict): The raw SSLScan results
            
        Returns:
            dict: Transformed SSLScan results with organized certificate and cipher information
        """
        if not data:
            return {}
            
        # This structure may need adjustment based on the actual SSLScan JSON format
        adapted_data = {
            'certificate': {},
            'ciphers': [],
            'protocols': []
        }
        
        # Extract certificate information
        if 'certificate' in data:
            adapted_data['certificate'] = {
                'subject': data['certificate'].get('subject', ''),
                'issuer': data['certificate'].get('issuer', ''),
                'valid_from': data['certificate'].get('valid_from', ''),
                'valid_to': data['certificate'].get('valid_to', ''),
                'fingerprint': data['certificate'].get('fingerprint', '')
            }
        
        # Extract cipher information
        if 'ciphers' in data and isinstance(data['ciphers'], list):
            for cipher in data['ciphers']:
                adapted_data['ciphers'].append({
                    'name': cipher.get('name', ''),
                    'strength': cipher.get('strength', ''),
                    'bits': cipher.get('bits', '')
                })
        
        # Extract protocol information
        if 'protocols' in data and isinstance(data['protocols'], list):
            adapted_data['protocols'] = data['protocols']
        
        return adapted_data
