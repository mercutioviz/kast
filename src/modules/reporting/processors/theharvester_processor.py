# src/modules/reporting/processors/theharvester_processor.py
from typing import Dict, Any, List
from .base_processor import BaseDataProcessor

class TheHarvesterProcessor(BaseDataProcessor):
    """Process theHarvester scan results"""
    
    def process(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process theHarvester scan results"""
        # Debug the raw data structure
        import pprint
        self.logger.debug("theHarvester raw data structure:")
        self.logger.debug(pprint.pformat(raw_data, indent=2))

        processed_data = {
            "title": "theHarvester Results",
            "description": "Email, subdomain and host information gathering",
            "emails": [],
            "hosts": [],
            "ips": []
        }
        
        if not raw_data:
            return processed_data
            
        try:
            if "emails" in raw_data:
                processed_data["emails"] = raw_data["emails"]
                
            if "hosts" in raw_data:
                processed_data["hosts"] = raw_data["hosts"]
                
            if "ips" in raw_data:
                processed_data["ips"] = raw_data["ips"]
        except Exception as e:
            self.logger.error(f"Error processing theHarvester data: {str(e)}")
            
        return processed_data
    
    def extract_summary(self, processed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract summary information from theHarvester results"""
        emails = processed_data.get("emails", [])
        hosts = processed_data.get("hosts", [])
        ips = processed_data.get("ips", [])
        
        return {
            "emails": len(emails),
            "hosts": len(hosts),
            "ips": len(ips),
            "total": len(emails) + len(hosts) + len(ips)
        }