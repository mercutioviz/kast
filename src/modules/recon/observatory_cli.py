#!/usr/bin/env python3

import os
import json
import subprocess
import time
from datetime import datetime
from src.modules.utils.validators import normalize_url, extract_domain
from src.modules.utils.logger import get_module_logger
from src.modules.utils.json_utils import load_json_file, save_json

# Module-specific logger
logger = get_module_logger(__name__)

def run_mozilla_observatory(target, output_dir, dry_run=False):
    """
    Run Mozilla Observatory scan using the mdn-http-observatory npm package
    
    Args:
        target (str): The target URL or domain
        output_dir (str): Directory to save results
        dry_run (bool): If True, only show what would be done
        
    Returns:
        dict: Scan results
    """
    logger.info("Running Mozilla Observatory scan for HTTP security analysis")
    
    # Ensure target is a domain (without protocol)
    domain = extract_domain(target)
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Define output files
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_output = os.path.join(output_dir, f'observatory_{timestamp}.json')
    txt_output = os.path.join(output_dir, f'observatory_{timestamp}.txt')
    summary_output = os.path.join(output_dir, f'observatory_summary_{timestamp}.json')
    
    # Command to run the observatory CLI tool
    command = ['observatory', domain, '--format=json', '--rescan']
    
    if dry_run:
        logger.info(f"[DRY RUN] Would execute: {' '.join(command)} > {json_output}")
        return {
            "dry_run": True,
            "command": ' '.join(command),
            "output_file": json_output
        }
    
    try:
        # Start time for tracking scan duration
        start_time = time.time()
        
        # Run the observatory command
        logger.info(f"Executing: {' '.join(command)}")
        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False  # Don't raise exception on non-zero exit
        )
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Check if the process completed successfully
        if process.returncode != 0:
            logger.warning(f"Observatory exited with code {process.returncode}")
            logger.warning(f"Stderr: {process.stderr}")
            
            # Save stderr to text file for debugging
            with open(txt_output, 'w') as f:
                f.write(f"Command: {' '.join(command)}\n")
                f.write(f"Return code: {process.returncode}\n")
                f.write(f"Stderr: {process.stderr}\n")
                f.write(f"Stdout: {process.stdout}\n")
            
            logger.info(f"Debug output saved to {txt_output}")
        
        # Save stdout as JSON
        try:
            observatory_data = json.loads(process.stdout)
            with open(json_output, 'w') as f:
                json.dump(observatory_data, f, indent=2)
            
            logger.info(f"Observatory scan completed in {duration:.1f} seconds. Results saved to {json_output}")
            
            # Create a summary of the results
            summary = create_observatory_summary(observatory_data, domain, duration)
            
            # Save the summary
            save_json(summary, summary_output)
            logger.info(f"Observatory summary saved to {summary_output}")
            
            return {
                "raw_results": observatory_data,
                "summary": summary,
                "output_file": json_output,
                "summary_file": summary_output,
                "duration": duration
            }
        except json.JSONDecodeError:
            logger.error("Failed to parse Observatory output as JSON")
            
            # Save raw output for debugging
            with open(txt_output, 'w') as f:
                f.write(process.stdout)
            
            logger.info(f"Raw output saved to {txt_output}")
            
            return {
                "error": "Failed to parse Observatory output as JSON",
                "debug_file": txt_output,
                "duration": duration
            }
        
    except Exception as e:
        logger.error(f"Error running Observatory: {str(e)}")
        return {
            "error": str(e)
        }

def create_observatory_summary(observatory_data, target, duration):
    """
    Create a summary of Mozilla Observatory scan results
    
    Args:
        observatory_data (dict): The raw Observatory results
        target (str): The target that was scanned
        duration (float): The scan duration in seconds
        
    Returns:
        dict: A summary of the scan results
    """
    try:
        # Initialize summary
        summary = {
            "target": target,
            "duration": f"{duration:.1f} seconds",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "tests": []
        }
        
        # Extract score and grade
        if "score" in observatory_data:
            summary["score"] = observatory_data["score"]
        
        if "grade" in observatory_data:
            summary["grade"] = observatory_data["grade"]
        
        # Extract test results
        if "tests" in observatory_data:
            for test_name, test_data in observatory_data["tests"].items():
                test_summary = {
                    "name": test_name,
                    "score_modifier": test_data.get("score_modifier", 0),
                    "score_description": test_data.get("score_description", ""),
                    "pass": test_data.get("pass", False)
                }
                
                summary["tests"].append(test_summary)
        
        return summary
    
    except Exception as e:
        logger.error(f"Error creating Observatory summary: {str(e)}")
        return {
            "error": f"Failed to create summary: {str(e)}",
            "target": target,
            "duration": f"{duration:.1f} seconds",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
