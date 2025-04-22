# src/modules/reporting/processors/wafw00f_processor.py
from typing import Dict, Any, List
from .base_processor import BaseDataProcessor

class Wafw00fProcessor(BaseDataProcessor):
    """Process wafw00f scan results"""
    
    def process(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process wafw00f scan results"""
        self.logger.debug(f"Raw wafw00f data: {raw_data}")
        
        processed_data = {
            "title": "WAF Detection Results",
            "description": "Web Application Firewall detection",
            "findings": []
        }
        
        if not raw_data:
            return processed_data
            
        try:
            if "waf" in raw_data:
                waf_info = raw_data["waf"]
                if waf_info:
                    processed_data["findings"].append({
                        "target": raw_data.get("target", "Unknown"),
                        "waf_detected": True,
                        "waf_name": waf_info
                    })
                else:
                    processed_data["findings"].append({
                        "target": raw_data.get("target", "Unknown"),
                        "waf_detected": False,
                        "waf_name": "None detected"
                    })
        except Exception as e:
            self.logger.error(f"Error processing wafw00f data: {str(e)}")
        
        self.logger.debug(f"Processed wafw00f data: {processed_data}")
        return processed_data
    
    def extract_summary(self, processed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract summary information from wafw00f results"""
        findings = processed_data.get("findings", [])
        
        waf_detected = any(finding.get("waf_detected", False) for finding in findings)
        waf_name = next((finding.get("waf_name", "Unknown") for finding in findings if finding.get("waf_detected")), "None")
        
        return {
            "detected": waf_detected,
            "waf": waf_name
        }