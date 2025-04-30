#!/usr/bin/env python3
#
# kast/src/modules/reporting/report_generator.py
#
# Description: Report generation module for KAST scan results
#

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Union
from jinja2 import Environment, FileSystemLoader

# Import the data processor
from src.modules.reporting.data_processor import process_scan_data

# Configure logger
logger = logging.getLogger(__name__)

class ReportGenerator:
    """
    Generates HTML reports from processed scan data.
    This class handles the rendering of templates and creation of report files.
    """
    
    def __init__(self, template_dir: str = None):
        """
        Initialize the report generator with template directory.
        
        Args:
            template_dir: Directory containing report templates
        """
        if template_dir is None:
            # Default to the templates directory in the project
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            template_dir = os.path.join(base_dir, "templates")
        
        self.template_dir = template_dir
        self.env = Environment(loader=FileSystemLoader(template_dir))
        logger.debug(f"Initialized ReportGenerator with template directory: {template_dir}")

    def generate_report(self, scan_results: Dict[str, Any], output_file: str, target: str = None) -> str:
        """
        Generate an HTML report from scan results.
        
        Args:
            scan_results: Dictionary containing results from various scanning tools
            output_file: Path where the report will be saved
            target: Optional target name to include in the report
            
        Returns:
            Path to the generated report file
        """
        try:
            # Process the scan data
            processed_data = process_scan_data(scan_results)
            
            # Override target if provided
            if target:
                processed_data['metadata']['target'] = target
                
            # Debug logging
            logger.debug(f"Processed data keys: {list(processed_data.keys())}")
            logger.debug(f"Summary keys: {list(processed_data['summary'].keys())}")
            if 'tools' in processed_data['summary']:
                logger.debug(f"Summary tools keys: {list(processed_data['summary']['tools'].keys())}")
            logger.debug(f"Detailed results keys: {list(processed_data['detailed_results'].keys())}")
            
            # Debug the raw data structure
            import pprint
            logger.debug("Processed data raw data structure:")
            logger.debug(pprint.pformat(processed_data, indent=2))

            # Render the template
            template = self.env.get_template("report_template.html")
            report_html = template.render(
                title=f"KAST Scan Report - {processed_data['metadata'].get('target', 'Unknown Target')}",
                timestamp=processed_data['metadata'].get('timestamp', datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                target=processed_data['metadata'].get('target', 'Unknown'),
                summary=processed_data['summary'],
                detailed_results=processed_data['detailed_results']
            )
            
            # Ensure the output directory exists
            os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
            
            # Write the report to file
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report_html)
                
            logger.info(f"Report generated successfully: {output_file}")
            return output_file
            
        except Exception as e:
            logger.error(f"Error generating report: {str(e)}")
            raise

    def get_template_variables(self, template_name: str) -> List[str]:
        """
        Get a list of variables used in a template.
        Useful for debugging template rendering issues.
        
        Args:
            template_name: Name of the template file
            
        Returns:
            List of variable names used in the template
        """
        try:
            template_source = self.env.loader.get_source(self.env, template_name)[0]
            parsed_content = self.env.parse(template_source)
            return list(self.env.meta.find_undeclared_variables(parsed_content))
        except Exception as e:
            logger.error(f"Error getting template variables: {str(e)}")
            return []

# Module-level function for easier use
def generate_html_report(scan_results: Dict[str, Any], output_file: str, target: str = None, template_dir: str = None) -> str:
    """
    Generate an HTML report from scan results.
    This is a convenience function for external use.
    
    Args:
        scan_results: Dictionary containing results from various scanning tools
        output_file: Path where the report will be saved
        target: Optional target name to include in the report
        template_dir: Optional directory containing report templates
        
    Returns:
        Path to the generated report file
    """
    generator = ReportGenerator(template_dir)
    return generator.generate_report(scan_results, output_file, target)
    
# Get a proper filename
def get_report_filename(output_dir):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_filename = f"kast_report_{timestamp}.html"
    report_dir = os.path.join(output_dir, "report")
    os.makedirs(report_dir, exist_ok=True)
    return os.path.join(report_dir, report_filename)