# src/modules/reporting/processors/whatweb_processor.py
from typing import Dict, Any, List
from .base_processor import BaseDataProcessor

class WhatWebProcessor(BaseDataProcessor):
    """Process WhatWeb scan results"""
    
    def process(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process WhatWeb scan results"""
        processed_data = {
            "title": "WhatWeb Results",
            "description": "Web technology identification",
            "findings": []
        }
        
        if not raw_data:
            return processed_data
            
        try:
            for target, details in raw_data.items():
                if isinstance(details, dict):
                    plugins = details.get("plugins", {})
                    finding = {
                        "target": target,
                        "http_status": details.get("http_status", ""),
                        "technologies": []
                    }
                    
                    for plugin_name, plugin_data in plugins.items():
                        tech = {"name": plugin_name}
                        if isinstance(plugin_data, dict):
                            tech["version"] = plugin_data.get("version", [""])[0] if isinstance(plugin_data.get("version", []), list) else ""
                            tech["details"] = plugin_data
                        finding["technologies"].append(tech)
                    
                    processed_data["findings"].append(finding)
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
            "count": len(findings),
            "technologies": technologies[:10]  # Limit to top 10 technologies
        }