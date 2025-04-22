#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# src/modules/reporting/data_processor.py
#
# Description: This module processes raw scan data from various tools and prepares it for report generation.
# This class handles the transformation and normalization of data from different adapters.

import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Union

# Configure logger
logger = logging.getLogger(__name__)

class DataProcessor:
    """
    Processes raw scan data from various tools and prepares it for report generation.
    This class handles the transformation and normalization of data from different adapters.
    """
    
    def __init__(self):
        self.processed_data = {}

    def process_scan_results(self, scan_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process all scan results and prepare them for report generation.
        
        Args:
            scan_results: Dictionary containing results from various scanning tools
            
        Returns:
            Dictionary with processed and normalized data ready for report generation
        """
        logger.debug(f"Processing scan results with tools: {list(scan_results.keys())}")
        
        # Add these lines to see the nested structure
        if 'recon' in scan_results:
            logger.debug(f"Recon tools: {list(scan_results['recon'].keys())}")
        if 'vuln' in scan_results:
            logger.debug(f"Vuln tools: {list(scan_results['vuln'].keys())}")
        
        processed_data = {
            "metadata": self._process_metadata(scan_results.get("metadata", {})),
            "summary": {},
            "detailed_results": {}
        }
        
        # Process each tool's results from the 'recon' category
        if "recon" in scan_results:
            recon_results = scan_results["recon"]
            
            if "whatweb" in recon_results:
                logger.debug(f"Processing whatweb data from recon")
                processed_data["detailed_results"]["whatweb"] = self._process_whatweb_data(recon_results["whatweb"])
                
            if "theharvester" in recon_results:
                logger.debug(f"Processing theharvester data from recon")
                processed_data["detailed_results"]["theharvester"] = self._process_harvester_data(recon_results["theharvester"])
                
            if "dnsenum" in recon_results:
                logger.debug(f"Processing dnsenum data from recon")
                processed_data["detailed_results"]["dnsenum"] = self._process_dnsenum_data(recon_results["dnsenum"])
                
            if "sslscan" in recon_results:
                logger.debug(f"Processing sslscan data from recon")
                processed_data["detailed_results"]["sslscan"] = self._process_sslscan_data(recon_results["sslscan"])
                
            if "wafw00f" in recon_results:
                logger.debug(f"Processing wafw00f data from recon")
                processed_data["detailed_results"]["wafw00f"] = self._process_wafw00f_data(recon_results["wafw00f"])
        
        # Process each tool's results from the 'vuln' category
        if "vuln" in scan_results:
            vuln_results = scan_results["vuln"]
            
            if "nikto" in vuln_results:
                logger.debug(f"Processing nikto data from vuln")
                processed_data["detailed_results"]["nikto"] = self._process_nikto_data(vuln_results["nikto"])
        
        # Extract metadata from scan_results if available
        if "target" in scan_results:
            processed_data["metadata"]["target"] = scan_results["target"]
        if "timestamp" in scan_results:
            processed_data["metadata"]["timestamp"] = scan_results["timestamp"]
        if "duration" in scan_results:
            processed_data["metadata"]["duration"] = scan_results["duration"]
        
        # Generate summary after processing all detailed results
        logger.debug(f"Generating summary from detailed results with keys: {list(processed_data['detailed_results'].keys())}")
        processed_data["summary"] = self._generate_summary(processed_data["detailed_results"])
        
        # Log the final structure
        logger.debug(f"Summary tools keys: {list(processed_data['summary']['tools'].keys()) if 'tools' in processed_data['summary'] else 'No tools in summary'}")
        
        return processed_data

    def _process_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Process and enhance metadata information"""
        processed_metadata = metadata.copy()
        
        # Add timestamp if not present
        if "timestamp" not in processed_metadata:
            processed_metadata["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
        # Format duration if present
        if "duration" in processed_metadata and isinstance(processed_metadata["duration"], (int, float)):
            minutes, seconds = divmod(processed_metadata["duration"], 60)
            processed_metadata["formatted_duration"] = f"{int(minutes)}m {int(seconds)}s"
            
        return processed_metadata
        
    def _process_whatweb_data(self, whatweb_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process WhatWeb scan results"""
        processed_data = {
            "title": "WhatWeb Results",
            "description": "Web technology identification",
            "findings": []
        }
        
        if not whatweb_data:
            return processed_data
            
        try:
            for target, details in whatweb_data.items():
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
            logger.error(f"Error processing WhatWeb data: {str(e)}")
            
        return processed_data

    def _process_harvester_data(self, harvester_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process theHarvester scan results"""
        processed_data = {
            "title": "theHarvester Results",
            "description": "Email, subdomain and host information gathering",
            "emails": [],
            "hosts": [],
            "ips": []
        }
        
        if not harvester_data:
            return processed_data
            
        try:
            if "emails" in harvester_data:
                processed_data["emails"] = harvester_data["emails"]
                
            if "hosts" in harvester_data:
                processed_data["hosts"] = harvester_data["hosts"]
                
            if "ips" in harvester_data:
                processed_data["ips"] = harvester_data["ips"]
        except Exception as e:
            logger.error(f"Error processing theHarvester data: {str(e)}")
            
        return processed_data
        
    def _process_dnsenum_data(self, dnsenum_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process DNSenum scan results"""
        processed_data = {
            "title": "DNSenum Results",
            "description": "DNS enumeration information",
            "nameservers": [],
            "mx_records": [],
            "a_records": [],
            "subdomains": []
        }
        
        if not dnsenum_data:
            return processed_data
            
        try:
            if "nameservers" in dnsenum_data:
                processed_data["nameservers"] = dnsenum_data["nameservers"]
                
            if "mx_records" in dnsenum_data:
                processed_data["mx_records"] = dnsenum_data["mx_records"]
                
            if "a_records" in dnsenum_data:
                processed_data["a_records"] = dnsenum_data["a_records"]
                
            if "subdomains" in dnsenum_data:
                processed_data["subdomains"] = dnsenum_data["subdomains"]
        except Exception as e:
            logger.error(f"Error processing DNSenum data: {str(e)}")
            
        return processed_data

    def _process_sslscan_data(self, sslscan_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process SSLScan results"""

        ### DEBUGGING ###
        # Print the entire structure with formatting
        import pprint
        logger.debug("SSLScan raw data structure:")
        logger.debug(pprint.pformat(sslscan_data, indent=2))
    
        processed_data = {
            "title": "SSLScan Results",
            "description": "SSL/TLS configuration analysis",
            "certificates": [],
            "ciphers": [],
            "protocols": [],
            "vulnerabilities": []
        }
        
        if not sslscan_data:
            return processed_data
            
        try:
            if "certificates" in sslscan_data:
                processed_data["certificates"] = sslscan_data["certificates"]
                
            if "ciphers" in sslscan_data:
                processed_data["ciphers"] = sslscan_data["ciphers"]
                
            if "protocols" in sslscan_data:
                processed_data["protocols"] = sslscan_data["protocols"]
                
            # Extract vulnerabilities from the data
            vulnerabilities = []
            if "heartbleed" in sslscan_data and sslscan_data["heartbleed"]:
                vulnerabilities.append({
                    "name": "Heartbleed",
                    "severity": "High",
                    "description": "Server is vulnerable to the Heartbleed attack (CVE-2014-0160)"
                })
                
            if "poodle" in sslscan_data and sslscan_data["poodle"]:
                vulnerabilities.append({
                    "name": "POODLE",
                    "severity": "Medium",
                    "description": "Server is vulnerable to the POODLE attack (CVE-2014-3566)"
                })
                
            processed_data["vulnerabilities"] = vulnerabilities
        except Exception as e:
            logger.error(f"Error processing SSLScan data: {str(e)}")
            
        return processed_data
        
    def _process_wafw00f_data(self, wafw00f_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process wafw00f scan results"""
        logger.debug(f"Raw wafw00f data: {wafw00f_data}")

        processed_data = {
            "title": "WAF Detection Results",
            "description": "Web Application Firewall detection",
            "findings": []
        }
        
        if not wafw00f_data:
            return processed_data
            
        try:
            if "waf" in wafw00f_data:
                waf_info = wafw00f_data["waf"]
                if waf_info:
                    processed_data["findings"].append({
                        "target": wafw00f_data.get("target", "Unknown"),
                        "waf_detected": True,
                        "waf_name": waf_info
                    })
                else:
                    processed_data["findings"].append({
                        "target": wafw00f_data.get("target", "Unknown"),
                        "waf_detected": False,
                        "waf_name": "None detected"
                    })
        except Exception as e:
            logger.error(f"Error processing wafw00f data: {str(e)}")

        logger.debug(f"Processed wafw00f data: {processed_data}") 
        return processed_data

    def _process_nikto_data(self, nikto_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process Nikto scan results"""
        processed_data = {
            "title": "Nikto Vulnerability Scan",
            "description": "Web server vulnerability scanner",
            "vulnerabilities": []
        }
        
        if not nikto_data:
            return processed_data
            
        try:
            if "vulnerabilities" in nikto_data and isinstance(nikto_data["vulnerabilities"], list):
                # Process and categorize vulnerabilities by severity
                for vuln in nikto_data["vulnerabilities"]:
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
            logger.error(f"Error processing Nikto data: {str(e)}")
            
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

    def _generate_summary(self, detailed_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a summary of all scan results"""
        summary = {
            "total_findings": 0,
            "tools_run": len(detailed_results),
            "severity": {
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "info": 0
            },
            "tools": {},
            "highlights": []
        }

        # Process Nikto results
        if "nikto" in detailed_results:
            nikto_data = detailed_results["nikto"]
            logger.debug(f"nikto data type: {type(nikto_data)}")
            nikto_vulns = nikto_data.get("vulnerabilities", [])

            # Simple count for Nikto
            summary["tools"]["nikto"] = len(nikto_vulns)

            for vuln in nikto_vulns:
                severity = vuln.get("severity", "Info").lower()
                if severity in summary["severity"]:
                    summary["severity"][severity] += 1
                    summary["total_findings"] += 1

            high_vulns = [v for v in nikto_vulns if v.get("severity") in ["Critical", "High"]]
            if high_vulns:
                summary["highlights"].append(f"Found {len(high_vulns)} high/critical vulnerabilities")

        # Process SSLScan results
        if "sslscan" in detailed_results:
            ssl_data = detailed_results["sslscan"]
            logger.debug(f"sslscan data type: {type(ssl_data)}")

            ssl_vulns = ssl_data.get("vulnerabilities", [])
            protocols_data = ssl_data.get("protocols")
            certs_data = ssl_data.get("certificates") or []

            logger.debug(f"sslscan protocols_data type: {type(protocols_data)}")

            versions = ["SSLv2", "SSLv3", "TLSv1.0", "TLSv1.1", "TLSv1.2", "TLSv1.3"]

            protocol_support = {}
            if isinstance(protocols_data, list):
                # fallback in case of misstructured data
                logger.warning("Expected dict for protocols_data, got list. Skipping protocol summary.")
            elif isinstance(protocols_data, str):
                logger.warning("Expected dict for protocols_data, got string. Skipping protocol summary.")
            elif isinstance(protocols_data, dict):
                protocol_support = {
                    v.lower().replace(".", ""): protocols_data.get(v, False)
                    for v in versions
                }
            else:
                logger.warning(f"Unknown type for protocols_data: {type(protocols_data)}")

            summary["tools"]["sslscan"] = {
                "vulnerabilities": len(ssl_vulns),
                "has_issues": len(ssl_vulns) > 0,
                "protocols": protocol_support,
                "cert_info": {
                    "expired": any(c.get("expired", False) for c in certs_data),
                    "self_signed": any(c.get("self_signed", False) for c in certs_data)
                }
            }

            for vuln in ssl_vulns:
                severity = vuln.get("severity", "Info").lower()
                if severity in summary["severity"]:
                    summary["severity"][severity] += 1
                    summary["total_findings"] += 1

            if summary["tools"]["sslscan"]["cert_info"]["expired"]:
                summary["highlights"].append("SSL certificate is expired")
            if summary["tools"]["sslscan"]["cert_info"]["self_signed"]:
                summary["highlights"].append("SSL certificate is self-signed")
            if summary["tools"]["sslscan"]["protocols"].get("ssl2") or summary["tools"]["sslscan"]["protocols"].get("ssl3"):
                summary["highlights"].append("Insecure SSL protocols detected")

        # Process WhatWeb results
        if "whatweb" in detailed_results:
            ww_data = detailed_results["whatweb"]
            logger.debug(f"whatweb data type: {type(ww_data)}")

            findings = ww_data.get("findings", [])
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

            summary["tools"]["whatweb"] = {
                "count": len(findings),
                "technologies": technologies[:10]
            }

            interesting_techs = ["WordPress", "Drupal", "Joomla", "Apache", "Nginx", "IIS", "PHP"]
            for tech in technologies:
                if tech["name"] in interesting_techs:
                    version_info = f" {tech.get('version')}" if tech.get("version") else ""
                    summary["highlights"].append(f"Detected {tech['name']}{version_info}")

        # Process WAF detection results
        if "wafw00f" in detailed_results:
            waf_data = detailed_results["wafw00f"]
            logger.debug(f"Generating summary for wafw00f: {waf_data}")

            findings = waf_data.get("findings", [])
            logger.debug(f"WAF findings type: {type(findings)}")

            waf_detected = any(finding.get("waf_detected", False) for finding in findings)
            waf_name = next((finding.get("waf_name", "Unknown") for finding in findings if finding.get("waf_detected")), "None")

            summary["tools"]["wafw00f"] = {
                "detected": waf_detected,
                "waf": waf_name
            }

            if waf_detected:
                summary["highlights"].append(f"WAF detected: {waf_name}")
            else:
                summary["highlights"].append("No WAF detected")

        # Process DNS enumeration results
        if "dnsenum" in detailed_results:
            dns_data = detailed_results["dnsenum"]
            nameservers = dns_data.get("nameservers", [])
            mx_records = dns_data.get("mx_records", [])
            a_records = dns_data.get("a_records", [])
            subdomains = dns_data.get("subdomains", [])

            summary["tools"]["dnsenum"] = {
                "nameservers": len(nameservers),
                "mx_records": len(mx_records),
                "a_records": len(a_records),
                "subdomains": len(subdomains),
                "total": len(nameservers) + len(mx_records) + len(a_records) + len(subdomains)
            }

            if subdomains:
                summary["highlights"].append(f"Found {len(subdomains)} subdomains")

        # Process theHarvester results
        if "theharvester" in detailed_results:
            harvester_data = detailed_results["theharvester"]
            emails = harvester_data.get("emails", [])
            hosts = harvester_data.get("hosts", [])
            ips = harvester_data.get("ips", [])

            summary["tools"]["theharvester"] = {
                "emails": len(emails),
                "hosts": len(hosts),
                "ips": len(ips),
                "total": len(emails) + len(hosts) + len(ips)
            }

            if emails:
                summary["highlights"].append(f"Found {len(emails)} email addresses")
            if hosts:
                summary["highlights"].append(f"Found {len(hosts)} additional hosts")

        return summary

# Helper functions that can be used outside the class
def process_scan_data(scan_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process scan results using the DataProcessor class.
    This is a convenience function for external use.
    
    Args:
        scan_results: Dictionary containing results from various scanning tools
        
    Returns:
        Dictionary with processed data ready for report generation
    """
    processor = DataProcessor()
    return processor.process_scan_results(scan_results)

