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
            "certificates": [],
            "ciphers": [],
            "protocols": [],
            "vulnerabilities": []
        }
        
        if not raw_data:
            return processed_data
            
        try:
            if "certificates" in raw_data:
                processed_data["certificates"] = raw_data["certificates"]
                
            if "ciphers" in raw_data:
                processed_data["ciphers"] = raw_data["ciphers"]
                
            if "protocols" in raw_data:
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
        protocols_data = processed_data.get("protocols")
        certs_data = processed_data.get("certificates") or []
        
        versions = ["SSLv2", "SSLv3", "TLSv1.0", "TLSv1.1", "TLSv1.2", "TLSv1.3"]
        
        protocol_support = {}
        if isinstance(protocols_data, list):
            # fallback in case of misstructured data
            self.logger.warning("Expected dict for protocols_data, got list. Skipping protocol summary.")
        elif isinstance(protocols_data, str):
            self.logger.warning("Expected dict for protocols_data, got string. Skipping protocol summary.")
        elif isinstance(protocols_data, dict):
            protocol_support = {
                v.lower().replace(".", ""): protocols_data.get(v, False)
                for v in versions
            }
        else:
            self.logger.warning(f"Unknown type for protocols_data: {type(protocols_data)}")
        
        return {
            "vulnerabilities": len(ssl_vulns),
            "has_issues": len(ssl_vulns) > 0,
            "protocols": protocol_support,
            "cert_info": {
                "expired": any(c.get("expired", False) for c in certs_data),
                "self_signed": any(c.get("self_signed", False) for c in certs_data)
            }
        }