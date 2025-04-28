# src/modules/reporting/processors/wafw00f_processor.py
from typing import Dict, Any, List
from .base_processor import BaseDataProcessor

class Wafw00fProcessor(BaseDataProcessor):
    """Process wafw00f scan results"""
    
    def process(self, raw_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process wafw00f scan results"""
        # Debug the raw data structure
        import pprint
        self.logger.debug("wafw00f raw data structure:")
        self.logger.debug(pprint.pformat(raw_data, indent=2))
        
        processed_data = {
            "title": "WAF Detection Results",
            "description": "Web Application Firewall detection",
            "findings": []
        }
        
        if not raw_data:
            return processed_data
            
        try:
            # Filter out "Generic" WAF if there are other WAFs detected
            detected_wafs = [item for item in raw_data if item.get('detected', False)]
            
            # Check if we have multiple WAFs and one is Generic
            non_generic_wafs = [waf for waf in detected_wafs if waf.get('firewall') != 'Generic']
            
            # If we have non-generic WAFs, use those; otherwise use all detected WAFs
            wafs_to_use = non_generic_wafs if non_generic_wafs and len(detected_wafs) > 1 else detected_wafs
            
            for waf in wafs_to_use:
                processed_data["findings"].append({
                    "target": waf.get("url", "Unknown"),
                    "waf_detected": waf.get("detected", False),
                    "waf_name": waf.get("firewall", "Unknown"),
                    "manufacturer": waf.get("manufacturer", "Unknown")
                })
                
        except Exception as e:
            self.logger.error(f"Error processing wafw00f data: {str(e)}")
        
        self.logger.debug(f"Processed wafw00f data: {processed_data}")
        return processed_data
    
    def extract_summary(self, processed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract summary information from wafw00f results"""
        findings = processed_data.get("findings", [])
        
        waf_detected = any(finding.get("waf_detected", False) for finding in findings)
        
        # If multiple WAFs detected, join their names
        waf_names = [finding.get("waf_name", "Unknown") for finding in findings if finding.get("waf_detected")]
        waf_name = ", ".join(waf_names) if waf_names else "None"
        
        return {
            "detected": waf_detected,
            "waf": waf_name
        }