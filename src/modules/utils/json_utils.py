#!/usr/bin/env python3

import os
import json
import re
from src.modules.utils.logger import get_module_logger

# Module-specific logger
logger = get_module_logger(__name__)

def robust_json_parse(content, output_dir=None, debug_filename=None):
    """
    Robustly parse potentially malformed JSON content
    
    Args:
        content (str): The JSON content to parse
        output_dir (str, optional): Directory to save debug files
        debug_filename (str, optional): Filename for debug output
        
    Returns:
        dict/list: Parsed JSON data or None if parsing fails
    """
    # Try to parse the JSON directly
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        logger.warning(f"Initial JSON parsing failed: {e}. Attempting to clean the data.")
        
        # Try to clean the JSON data
        # 1. Remove any non-JSON prefix/suffix
        content = content.strip()
        if content.startswith('[') and content.endswith(']'):
            # It's an array, keep it as is
            pass
        elif content.startswith('{') and content.endswith('}'):
            # It's an object, keep it as is
            pass
        else:
            # Try to find JSON object or array
            json_obj_match = re.search(r'(\{.*\})', content, re.DOTALL)
            json_arr_match = re.search(r'(\[.*\])', content, re.DOTALL)
            
            if json_obj_match:
                content = json_obj_match.group(1)
            elif json_arr_match:
                content = json_arr_match.group(1)
        
        # 2. Fix common JSON issues
        # Replace invalid escape sequences
        content = content.replace('\\"', '"').replace('\\\'', '\'')
        
        # 3. Try to parse again
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # 4. Last resort: try to parse line by line (for multiple JSON objects)
            try:
                lines = content.split('\n')
                json_data = []
                for line in lines:
                    line = line.strip()
                    if line and (line.startswith('{') or line.startswith('[')):
                        try:
                            obj = json.loads(line)
                            json_data.append(obj)
                        except:
                            pass
                
                if json_data:
                    return json_data
                else:
                    raise ValueError("Could not parse any JSON objects")
            except Exception as e2:
                logger.error(f"All JSON parsing attempts failed: {e2}")
                
                # Save the problematic content to a debug file if output_dir is provided
                if output_dir and debug_filename:
                    debug_file = os.path.join(output_dir, debug_filename)
                    try:
                        with open(debug_file, 'w') as f:
                            f.write(content)
                        logger.error(f"Saved problematic content to {debug_file}")
                    except Exception as e3:
                        logger.error(f"Failed to save debug file: {e3}")
                
                return None

def save_json(data, filepath):
    """
    Safely save JSON data to a file
    
    Args:
        data (dict/list): The data to save
        filepath (str): Path to the output file
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving JSON to {filepath}: {e}")
        return False

def load_json_file(filepath):
    """
    Load and parse a JSON file with robust error handling
    
    Args:
        filepath (str): Path to the JSON file
        
    Returns:
        dict/list: Parsed JSON data or None if parsing fails
    """
    try:
        if not os.path.exists(filepath):
            logger.error(f"JSON file not found: {filepath}")
            return None
            
        with open(filepath, 'r') as f:
            content = f.read()
            
        return robust_json_parse(content, os.path.dirname(filepath), f"debug_{os.path.basename(filepath)}")
    except Exception as e:
        logger.error(f"Error loading JSON file {filepath}: {e}")
        return None
