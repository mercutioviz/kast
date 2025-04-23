# src/modules/reporting/processors/dnsenum_processor.py
from typing import Dict, Any, List
from .base_processor import BaseDataProcessor

class DNSEnumProcessor(BaseDataProcessor):
    """Process DNSenum scan results"""
    
    def process(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process DNSenum scan results"""
        # Debug the raw data structure
        import pprint
        self.logger.debug("DNSenum raw data structure:")
        self.logger.debug(pprint.pformat(raw_data, indent=2))

        processed_data = {
            "title": "DNSenum Results",
            "description": "DNS enumeration information",
            "nameservers": [],
            "mx_records": [],
            "a_records": [],
            "subdomains": []
        }
        
        if not raw_data:
            return processed_data
            
        try:
            if "nameservers" in raw_data:
                processed_data["nameservers"] = raw_data["nameservers"]
                
            if "mx_records" in raw_data:
                processed_data["mx_records"] = raw_data["mx_records"]
                
            if "a_records" in raw_data:
                processed_data["a_records"] = raw_data["a_records"]
                
            if "subdomains" in raw_data:
                processed_data["subdomains"] = raw_data["subdomains"]
        except Exception as e:
            self.logger.error(f"Error processing DNSenum data: {str(e)}")
            
        return processed_data
    
    def extract_summary(self, processed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract summary information from DNSenum results"""
        nameservers = processed_data.get("nameservers", [])
        mx_records = processed_data.get("mx_records", [])
        a_records = processed_data.get("a_records", [])
        subdomains = processed_data.get("subdomains", [])
        
        return {
            "nameservers": len(nameservers),
            "mx_records": len(mx_records),
            "a_records": len(a_records),
            "subdomains": len(subdomains),
            "total": len(nameservers) + len(mx_records) + len(a_records) + len(subdomains)
        }
    