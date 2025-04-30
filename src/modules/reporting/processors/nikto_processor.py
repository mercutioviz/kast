# src/modules/reporting/processors/nikto_processor.py
from typing import Dict, Any, List
from .base_processor import BaseDataProcessor

class NiktoProcessor(BaseDataProcessor):
    """Process Nikto scan results"""
    
    def process(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process Nikto scan results"""
        # Debug the raw data structure
        import pprint
        self.logger.debug("Nikto raw data structure:")
        self.logger.debug(pprint.pformat(raw_data, indent=2))

        processed_data = {
            "title": "Nikto Vulnerability Scan",
            "description": "Web server vulnerability scanner",
            "vulnerabilities": [],
            "all_vulnerabilities_count": 0,  # Track total count including info findings
            "severity_counts": {
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "info": 0
            }
        }
        
        if not raw_data:
            return processed_data
            
        try:
            if "vulnerabilities" in raw_data and isinstance(raw_data["vulnerabilities"], list):
                # Process and categorize vulnerabilities
                for vuln in raw_data["vulnerabilities"]:
                    # Extract CVE or OSVDB from references if available
                    reference_id = ""
                    references = vuln.get("references", "")
                    
                    if references:
                        # Try to extract CVE ID
                        if "CVE-" in references:
                            import re
                            cve_match = re.search(r'CVE-\d+-\d+', references)
                            if cve_match:
                                reference_id = cve_match.group(0)
                        # If no CVE, try OSVDB
                        elif "OSVDB-" in references or "OSVDB " in references:
                            import re
                            osvdb_match = re.search(r'OSVDB[-\s](\d+)', references)
                            if osvdb_match:
                                reference_id = f"OSVDB-{osvdb_match.group(1)}"
                    
                    # Determine severity based on ID, message, or references
                    severity = self._determine_nikto_severity(vuln)
                    
                    # Create processed vulnerability entry with all relevant fields
                    processed_vuln = {
                        "id": vuln.get("id", ""),
                        "method": vuln.get("method", "GET"),
                        "message": vuln.get("msg", ""),
                        "uri": vuln.get("url", "/"),
                        "reference_id": reference_id,
                        "references": references,
                        "severity": severity
                    }
                    
                    # Update severity counts for all findings
                    processed_data["all_vulnerabilities_count"] += 1
                    processed_data["severity_counts"][severity.lower()] += 1
                    
                    # Only add non-info vulnerabilities to the display list
                    if severity.lower() != "info":
                        processed_data["vulnerabilities"].append(processed_vuln)
                
                # Sort vulnerabilities by severity (High to Low)
                severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
                processed_data["vulnerabilities"].sort(
                    key=lambda x: severity_order.get(x["severity"].lower(), 999)
                )
        except Exception as e:
            self.logger.error(f"Error processing Nikto data: {str(e)}")
            
        return processed_data
    
    def _determine_nikto_severity(self, vulnerability: Dict[str, Any]) -> str:
        """Determine the severity of a Nikto vulnerability"""
        # Check ID first - some IDs have known severities
        vuln_id = vulnerability.get("id", "")
        msg = vulnerability.get("msg", "").lower()
        references = vulnerability.get("references", "").lower()
        
        # Debug the vulnerability being processed
        self.logger.debug(f"Processing Nikto vulnerability: ID={vuln_id}, msg={msg}")
        
        # Critical vulnerabilities
        if any(keyword in msg for keyword in ["remote code execution", "rce", "sql injection", "command injection", "arbitrary file upload"]):
            return "Critical"
            
        # High severity vulnerabilities
        if any(keyword in msg for keyword in ["xss", "cross-site scripting", "directory traversal", "path traversal", "information disclosure", "cve-"]):
            return "High"
            
        # Medium severity vulnerabilities
        if any(keyword in msg for keyword in [
            "clickjacking", "csrf", "cross-site request forgery", "weak password", "default credential",
            "strict-transport-security", "content-type-options", "secure flag", "httponly flag", "breach attack"
        ]):
            return "Medium"
            
        # Low severity vulnerabilities
        if any(keyword in msg for keyword in ["missing header", "cookie without", "outdated", "deprecated", "x-powered-by"]):
            return "Low"
            
        # Special cases based on ID
        if vuln_id in ["999970", "999103", "999961", "95", "999966", "999972"]:
            return "Medium"  # Security headers and cookie issues
            
        # Default to Info
        return "Info"
    
    def extract_summary(self, processed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract summary information from Nikto results"""
        # Use the pre-calculated counts that include info findings
        return {
            "total": processed_data.get("all_vulnerabilities_count", 0),
            "severity": processed_data.get("severity_counts", {
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "info": 0
            })
        }