# src/modules/reporting/processors/sslscan_processor.py
from typing import Dict, Any, List
import logging
from .base_processor import BaseDataProcessor

class SSLScanProcessor(BaseDataProcessor):
    """Process SSLScan results"""
    
    def process(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process SSLScan results"""
        # Debug the raw data structure
        import pprint
        self.logger.debug("SSLScan raw data structure:")
        self.logger.debug(pprint.pformat(raw_data, indent=2))
        
        processed_data = {
            "title": "SSLScan Results",
            "description": "SSL/TLS configuration analysis",
            "certificate": {},
            "ciphers": [],
            "protocols": {},
            "vulnerabilities": []
        }
        
        if not raw_data:
            return processed_data
            
        try:
            # Process certificate information
            if "certificate" in raw_data:
                processed_data["certificate"] = raw_data["certificate"]
                
            # Process cipher information
            if "ciphers" in raw_data and isinstance(raw_data["ciphers"], list):
                processed_data["ciphers"] = raw_data["ciphers"]
                
            # Process protocol information
            if "protocols" in raw_data and isinstance(raw_data["protocols"], dict):
                processed_data["protocols"] = raw_data["protocols"]
                
            # Extract vulnerabilities from the data
            vulnerabilities = []
            if "heartbleed" in raw_data and raw_data["heartbleed"]:
                vulnerabilities.append({
                    "name": "Heartbleed",
                    "severity": "High",
                    "description": "Server is vulnerable to the Heartbleed attack (CVE-2014-0160)"
                })
                
            if "poodle" in raw_data and raw_data["poodle"]:
                vulnerabilities.append({
                    "name": "POODLE",
                    "severity": "Medium",
                    "description": "Server is vulnerable to the POODLE attack (CVE-2014-3566)"
                })
                
            processed_data["vulnerabilities"] = vulnerabilities
        except Exception as e:
            self.logger.error(f"Error processing SSLScan data: {str(e)}")
            
        return processed_data
    
    def extract_summary(self, processed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract summary information from SSLScan results"""
        ssl_vulns = processed_data.get("vulnerabilities", [])
        protocols_data = processed_data.get("protocols", {})
        ciphers_data = processed_data.get("ciphers", [])
        cert_data = processed_data.get("certificate", {})
        
        # Format protocol information
        protocol_support = {}
        enabled_protocols = []
        
        # Map protocol keys to their display names
        protocol_display_names = {
            "SSLv2": "SSLv2",
            "SSLv3": "SSLv3", 
            "TLSv1.0": "TLSv1.0",
            "TLSv1.1": "TLSv1.1",
            "TLSv1.2": "TLSv1.2",
            "TLSv1.3": "TLSv1.3"
        }
        
        # Process protocol information
        if isinstance(protocols_data, dict):
            for protocol, enabled in protocols_data.items():
                display_name = protocol_display_names.get(protocol, protocol)
                if enabled:
                    enabled_protocols.append(display_name)
        
        return {
            "vulnerabilities": len(ssl_vulns),
            "has_issues": len(ssl_vulns) > 0,
            "ciphers": len(ciphers_data),
            "enabled_protocols": enabled_protocols,
            "cert_info": {
                "issuer": cert_data.get("issuer", "Unknown"),
                "subject": cert_data.get("subject", "Unknown"),
                "not_before": cert_data.get("not_before", "Unknown"),
                "not_after": cert_data.get("not_after", "Unknown")
            }
        }