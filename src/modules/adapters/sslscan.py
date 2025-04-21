#!/usr/bin/env python3
#
# kast/src/modules/adapters/sslscan.py
#
# Description: Adapter for SSLScan SSL/TLS configuration results
#

from .base import ToolAdapter
import os

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
        
        # Initialize result structure
        result = {
            'certificate': {},
            'ciphers': [],
            'protocols': []
        }
        
        # Extract certificate information
        if 'certificate' in data and isinstance(data['certificate'], dict):
            cert = data['certificate']
            result['certificate'] = {
                'subject': cert.get('subject', ''),
                'issuer': cert.get('issuer', ''),
                'valid_from': cert.get('valid_from', ''),
                'valid_to': cert.get('valid_to', ''),
                'fingerprint': cert.get('fingerprint', '')
            }
        
        # Extract cipher information
        if 'ciphers' in data and isinstance(data['ciphers'], list):
            for cipher in data['ciphers']:
                if isinstance(cipher, dict):
                    result['ciphers'].append({
                        'name': cipher.get('name', ''),
                        'strength': cipher.get('strength', ''),
                        'bits': cipher.get('bits', '')
                    })
        
        # Extract protocol information
        if 'protocols' in data and isinstance(data['protocols'], list):
            result['protocols'] = data['protocols']
        elif 'protocols' in data and isinstance(data['protocols'], dict):
            # Handle case where protocols are in a dict
            for proto, enabled in data['protocols'].items():
                if enabled:
                    result['protocols'].append(proto)
        
        return result