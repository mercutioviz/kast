#!/usr/bin/env python3
#
# kast/src/modules/adapters/base.py
#
# Description: Base adapter class for transforming tool results into template-friendly format
#

import os
import glob
import json
import logging

class ToolAdapter:
    """Base class for tool result adapters."""
    
    def __init__(self, tool_name, result_subdir=None):
        """
        Initialize the adapter.
        
        Args:
            tool_name (str): Name of the tool (used in filename patterns)
            result_subdir (str, optional): Subdirectory where results are stored (e.g., 'recon', 'vuln')
        """
        self.tool_name = tool_name
        self.result_subdir = result_subdir
    
    def load_data(self, results_dir):
        """
        Load data from results directory.
        
        Args:
            results_dir (str): Path to the results directory
            
        Returns:
            dict/list: The loaded JSON data, or None if no file found
        """
        search_path = results_dir
        if self.result_subdir:
            search_path = os.path.join(results_dir, self.result_subdir)
        
        # Try both naming patterns: with and without underscore
        patterns = [
            os.path.join(search_path, f'{self.tool_name}.json'),
            os.path.join(search_path, f'{self.tool_name}_*.json')
        ]
        
        files = []
        for pattern in patterns:
            files.extend(glob.glob(pattern))
        
        if not files:
            logging.warning(f"No result files found for {self.tool_name} in {search_path}")
            return None
        
        try:
            with open(files[0], 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading {self.tool_name} data: {e}")
            return None
    
    def adapt(self, data):
        """
        Transform tool data into template-friendly format.
        
        Args:
            data (dict/list): The raw data from the tool
            
        Returns:
            dict/list: Transformed data ready for the template
        """
        raise NotImplementedError("Subclasses must implement adapt()")
    
    def get_template_variable(self):
        """
        Return the variable name to use in the template.
        
        Returns:
            str: Variable name for the template
        """
        return f"{self.tool_name}_results"
