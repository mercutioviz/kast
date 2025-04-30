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
from pathlib import Path
from .processors import get_processor

# Configure logger
logger = logging.getLogger(__name__)

class DataProcessor:
    """
    Processes raw scan data from various tools and prepares it for report generation.
    This class handles the transformation and normalization of data from different adapters.
    """
    
    def __init__(self):
        self.processed_data = {}
        self.logger = logging.getLogger(self.__class__.__name__)

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
            self._process_category_tools(recon_results, processed_data["detailed_results"])
        
        # Process each tool's results from the 'vuln' category
        if "vuln" in scan_results:
            vuln_results = scan_results["vuln"]
            self._process_category_tools(vuln_results, processed_data["detailed_results"])
        
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
    
    def _process_category_tools(self, category_results: Dict[str, Any], detailed_results: Dict[str, Any]) -> None:
        """
        Process all tools within a category (recon or vuln)
        
        Args:
            category_results: Results for all tools in a category
            detailed_results: Dictionary to store processed results
        """
        for tool_name, tool_data in category_results.items():
            processor = get_processor(tool_name)
            if processor:
                logger.debug(f"Processing {tool_name} data")
                detailed_results[tool_name] = processor.process(tool_data)
            else:
                logger.warning(f"No processor available for {tool_name}")

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

    def _generate_summary(self, detailed_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a summary of all scan results"""
        # Debug the raw data structure
        import pprint
        self.logger.debug("Results raw data structure:")
        self.logger.debug(pprint.pformat(detailed_results, indent=2))

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

        # Process each tool's results and extract summaries
        for tool_name, tool_data in detailed_results.items():
            processor = get_processor(tool_name)
            if processor:
                # Get tool-specific summary
                tool_summary = processor.extract_summary(tool_data)
                summary["tools"][tool_name] = tool_summary
                
                # Update severity counts and total findings
                self._update_severity_counts(summary, tool_name, tool_data)
                
                # Add highlights based on tool-specific data
                self._add_tool_highlights(summary["highlights"], tool_name, tool_data, tool_summary)
            else:
                logger.warning(f"No processor available for summary of {tool_name}")
        
        return summary
    
    def _update_severity_counts(self, summary: Dict[str, Any], tool_name: str, tool_data: Dict[str, Any]) -> None:
        """
        Update severity counts in the summary based on tool data
        
        Args:
            summary: Summary dictionary to update
            tool_name: Name of the tool
            tool_data: Processed data from the tool
        """
        # Handle Nikto vulnerabilities - use pre-calculated counts
        if tool_name == "nikto":
            ### DEBUG
            logger.debug(f"Processing Nikto data: {tool_data}")
        
            if "severity_counts" in tool_data:
                # Use the pre-calculated severity counts
                for severity, count in tool_data["severity_counts"].items():
                    if severity in summary["severity"]:
                        summary["severity"][severity] += count
                
                # Add to total findings
                summary["total_findings"] += tool_data.get("all_vulnerabilities_count", 0)
            else:
                # Fall back to counting vulnerabilities in the list
                for vuln in tool_data.get("vulnerabilities", []):
                    severity = vuln.get("severity", "Info").lower()
                    if severity in summary["severity"]:
                        summary["severity"][severity] += 1
                        summary["total_findings"] += 1
        
        # Handle SSLScan vulnerabilities
        elif tool_name == "sslscan" and "vulnerabilities" in tool_data:
            for vuln in tool_data["vulnerabilities"]:
                severity = vuln.get("severity", "Info").lower()
                if severity in summary["severity"]:
                    summary["severity"][severity] += 1
                    summary["total_findings"] += 1
        
        # For WAFw00f, count each detected WAF as a finding
        elif tool_name == "wafw00f" and "findings" in tool_data:
            detected_wafs = [f for f in tool_data["findings"] if f.get("waf_detected", False)]
            summary["total_findings"] += len(detected_wafs)
        
        # For WhatWeb, count each URL scanned as a finding
        elif tool_name == "whatweb" and "findings" in tool_data:
            summary["total_findings"] += len(tool_data["findings"])
        
        # For other tools, just count findings if available
        elif "findings" in tool_data and isinstance(tool_data["findings"], list):
            summary["total_findings"] += len(tool_data["findings"])
    
    def _add_tool_highlights(self, highlights: List[str], tool_name: str, tool_data: Dict[str, Any], tool_summary: Dict[str, Any]) -> None:
        """
        Add tool-specific highlights to the summary
        
        Args:
            highlights: List of highlights to update
            tool_name: Name of the tool
            tool_data: Processed data from the tool
            tool_summary: Summary data from the tool
        """
        # Nikto highlights
        if tool_name == "nikto":
            high_vulns = [v for v in tool_data.get("vulnerabilities", []) if v.get("severity") in ["Critical", "High"]]
            if high_vulns:
                highlights.append(f"Found {len(high_vulns)} high/critical vulnerabilities")
        
        # SSLScan highlights
        elif tool_name == "sslscan":
            cert_info = tool_summary.get("cert_info", {})
            protocols = tool_summary.get("protocols", {})
            
            if cert_info.get("expired"):
                highlights.append("SSL certificate is expired")
            if cert_info.get("self_signed"):
                highlights.append("SSL certificate is self-signed")
            if protocols.get("ssl2") or protocols.get("ssl3"):
                highlights.append("Insecure SSL protocols detected")
        
        # WhatWeb highlights
        elif tool_name == "whatweb":
            technologies = tool_summary.get("technologies", [])
            interesting_techs = ["WordPress", "Drupal", "Joomla", "Apache", "Nginx", "IIS", "PHP"]
            
            for tech in technologies:
                if tech["name"] in interesting_techs:
                    version_info = f" {tech.get('version')}" if tech.get("version") else ""
                    highlights.append(f"Detected {tech['name']}{version_info}")
        
        # WAF detection highlights
        elif tool_name == "wafw00f":
            if tool_summary.get("detected"):
                highlights.append(f"WAF detected: {tool_summary.get('waf', 'Unknown')}")
            else:
                highlights.append("No WAF detected")
        
        # DNSEnum highlights
        elif tool_name == "dnsenum":
            if tool_summary.get("subdomains", 0) > 0:
                highlights.append(f"Found {tool_summary.get('subdomains')} subdomains")
        
        # theHarvester highlights
        elif tool_name == "theharvester":
            if tool_summary.get("emails", 0) > 0:
                highlights.append(f"Found {tool_summary.get('emails')} email addresses")
            if tool_summary.get("hosts", 0) > 0:
                highlights.append(f"Found {tool_summary.get('hosts')} additional hosts")
    
    def save_processed_data(self, processed_data: Dict[str, Any], output_path: str) -> bool:
        """
        Save processed data to a JSON file
        
        Args:
            processed_data: Processed scan data
            output_path: Path to save the processed data
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            output_dir = Path(output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w') as f:
                json.dump(processed_data, f, indent=2)
                
            logger.info(f"Processed data saved to {output_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving processed data: {str(e)}")
            return False


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