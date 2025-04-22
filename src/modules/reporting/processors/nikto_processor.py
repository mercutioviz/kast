# src/modules/reporting/processors/nikto_processor.py
from typing import Dict, Any, List
from .base_processor import BaseDataProcessor

class NiktoProcessor(BaseDataProcessor):
    """Process Nikto scan results"""
    
    def process(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process Nikto scan results"""
        processed_data = {
            "title": "Nikto Vulnerability Scan",
            "description": "Web server vulnerability scanner",
            "vulnerabilities": []
        }
        
        if not raw_data:
            return processed_data
            
        try:
            if "vulnerabilities" in raw_data and isinstance(raw_data["vulnerabilities"], list):
                # Process and categorize vulnerabilities by severity
                for vuln in raw_data["vulnerabilities"]:
                    # Determine severity based on OSVDB ID or description keywords
                    severity = self._determine_nikto_severity(vuln)
                    
                    processed_vuln = {
                        "id": vuln.get("id", ""),
                        "osvdb": vuln.get("osvdb", ""),
                        "description": vuln.get("description", ""),
                        "severity": severity
                    }
                    processed_data["vulnerabilities"].append(processed_vuln)
                
                # Sort vulnerabilities by severity (High to Low)
                severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Info": 4}
                processed_data["vulnerabilities"].sort(
                    key=lambda x: severity_order.get(x["severity"], 999)
                )
        except Exception as e:
            self.logger.error(f"Error processing Nikto data: {str(e)}")
            
        return processed_data
    
    def _determine_nikto_severity(self, vulnerability: Dict[str, Any]) -> str:
        """Determine the severity of a Nikto vulnerability"""
        description = vulnerability.get("description", "").lower()
        
        # Critical vulnerabilities
        if any(keyword in description for keyword in ["remote code execution", "rce", "sql injection", "command injection"]):
            return "Critical"
            
        # High severity vulnerabilities
        if any(keyword in description for keyword in ["xss", "cross-site scripting", "directory traversal", "path traversal", "information disclosure"]):
            return "High"
            
        # Medium severity vulnerabilities
        if any(keyword in description for keyword in ["clickjacking", "csrf", "cross-site request forgery", "weak password"]):
            return "Medium"
            
        # Low severity vulnerabilities
        if any(keyword in description for keyword in ["missing header", "cookie without", "outdated"]):
            return "Low"
            
        # Default to Info
        return "Info"
    
    def extract_summary(self, processed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract summary information from Nikto results"""
        vulnerabilities = processed_data.get("vulnerabilities", [])
        
        # Count vulnerabilities by severity
        severity_counts = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "info": 0
        }
        
        for vuln in vulnerabilities:
            severity = vuln.get("severity", "Info").lower()
            if severity in severity_counts:
                severity_counts[severity] += 1
        
        return len(vulnerabilities)