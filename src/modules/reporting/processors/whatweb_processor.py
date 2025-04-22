# src/modules/reporting/processors/whatweb_processor.py
from typing import Dict, Any, List
from .base_processor import BaseDataProcessor

class WhatWebProcessor(BaseDataProcessor):
    """Process WhatWeb scan results"""
    
    def process(self, raw_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process WhatWeb scan results"""

        # Debug the raw data structure
        import pprint
        self.logger.debug("WhatWeb raw data structure:")
        self.logger.debug(pprint.pformat(raw_data, indent=2))

        processed_data = {
            "title": "WhatWeb Results",
            "description": "Web technology identification",
            "findings": []
        }
        
        if not raw_data:
            return processed_data
            
        try:
            # Log the raw data structure for debugging
            self.logger.debug(f"WhatWeb raw data structure:")
            self.logger.debug(f"{raw_data}")
            
            # Process each entry in the list
            for entry in raw_data:
                target = entry.get("target", "Unknown")
                plugins = entry.get("plugins", {})
                
                finding = {
                    "target": target,
                    "http_status": entry.get("http_status", ""),
                    "technologies": []
                }
                
                for plugin_name, plugin_data in plugins.items():
                    tech = {"name": plugin_name}
                    
                    # Extract version if available
                    if isinstance(plugin_data, dict):
                        version_list = plugin_data.get("version", [])
                        if version_list and isinstance(version_list, list):
                            tech["version"] = version_list[0]
                        
                        # Extract other details
                        details = []
                        for key, value in plugin_data.items():
                            if isinstance(value, list) and value:
                                details.append(f"{key}: {', '.join(value)}")
                        
                        if details:
                            tech["details"] = details
                    
                    finding["technologies"].append(tech)
                
                processed_data["findings"].append(finding)
                
            self.logger.debug(f"Processed WhatWeb data: {processed_data}")
            
        except Exception as e:
            self.logger.error(f"Error processing WhatWeb data: {str(e)}")
            
        return processed_data
    
    def extract_summary(self, processed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract summary information from WhatWeb results"""
        findings = processed_data.get("findings", [])
        technologies = []
        
        for finding in findings:
            for tech in finding.get("technologies", []):
                tech_name = tech.get("name", "")
                tech_version = tech.get("version", "")
                if tech_name:
                    tech_info = {"name": tech_name}
                    if tech_version:
                        tech_info["version"] = tech_version
                    technologies.append(tech_info)
        
        return {
            "count": len(technologies),
            "technologies": technologies[:10]  # Limit to top 10 technologies
        }