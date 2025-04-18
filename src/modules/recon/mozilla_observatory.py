#!/usr/bin/env python3

import os
import json
import subprocess
import time
from src.modules.utils.validators import extract_domain
from src.modules.utils.logger import get_module_logger
from src.modules.utils.json_utils import load_json_file, save_json

# Module-specific logger
logger = get_module_logger(__name__)

def run_mozilla_observatory(target, output_dir, dry_run=False):
    """Run Mozilla Observatory scan for web security analysis"""
    logger.info("Running Mozilla Observatory scan for web security analysis")
    
    domain = extract_domain(target)
    output_file = os.path.join(output_dir, 'mozilla_observatory.json')
    raw_output_file = os.path.join(output_dir, 'mozilla_observatory_raw.txt')
    
    # Use the new command: mdn-http-observatory
    command = [
        'mdn-http-observatory-scan',
        domain
    ]
    
    if dry_run:
        logger.info(f"[DRY RUN] Would execute: {' '.join(command)}")
        return {
            "dry_run": True,
            "command": ' '.join(command),
            "output_file": output_file
        }
    
    try:
        # Run the command and capture output
        logger.info(f"Executing: {' '.join(command)}")
        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False  # Don't raise exception on non-zero exit
        )
        
        # Save raw output for debugging
        with open(raw_output_file, 'w') as f:
            f.write(f"Command: {' '.join(command)}\n")
            f.write(f"Return code: {process.returncode}\n")
            f.write(f"Stderr: {process.stderr}\n")
            f.write(f"Stdout: {process.stdout}\n")
        
        # Check if the process completed successfully
        if process.returncode != 0:
            logger.warning(f"Mozilla Observatory exited with code {process.returncode}")
            logger.warning(f"Stderr: {process.stderr}")
            logger.info(f"Raw output saved to {raw_output_file}")
            
            return {
                "error": f"Mozilla Observatory scan failed with exit code {process.returncode}",
                "raw_output_file": raw_output_file
            }
        
        # Try to parse the JSON output from stdout
        try:
            observatory_data = json.loads(process.stdout)
            
            # Save the parsed JSON
            save_json(observatory_data, output_file)
            logger.info(f"Mozilla Observatory scan completed. Results saved to {output_file}")
            
            # Create a summary of the results
            summary = create_observatory_summary(observatory_data, domain)
            
            return {
                "raw_results": observatory_data,
                "summary": summary,
                "output_file": output_file
            }
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing Mozilla Observatory JSON output: {e}")
            logger.info(f"Raw output saved to {raw_output_file}")
            
            return {
                "error": f"Failed to parse Mozilla Observatory output: {e}",
                "raw_output_file": raw_output_file
            }
            
    except Exception as e:
        logger.error(f"Error with Mozilla Observatory scan: {str(e)}")
        return {
            "error": str(e)
        }

def create_observatory_summary(data, domain):
    """
    Create a summary of Mozilla Observatory scan results

    Args:
        data (dict): The raw Observatory results
        domain (str): The domain that was scanned
        
    Returns:
        dict: A summary of the scan results
    """
    summary = {
        "domain": domain,
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # Extract the grade and score
    if "grade" in data:
        summary["grade"] = data["grade"]
    
    if "score" in data:
        summary["score"] = data["score"]
    
    # Extract test results
    if "tests" in data:
        tests_summary = []
        for test_name, test_data in data["tests"].items():
            test_summary = {
                "name": test_name,
                "pass": test_data.get("pass", False),
                "score_modifier": test_data.get("score_modifier", 0),
                "result": test_data.get("result", "unknown")
            }
            tests_summary.append(test_summary)
        
        summary["tests"] = tests_summary
    
    # Count passed and failed tests
    passed_tests = 0
    failed_tests = 0
    
    if "tests" in summary:
        for test in summary["tests"]:
            if test["pass"]:
                passed_tests += 1
            else:
                failed_tests += 1
    
    summary["passed_tests"] = passed_tests
    summary["failed_tests"] = failed_tests
    summary["total_tests"] = passed_tests + failed_tests
    
    return summary

# Test function for direct execution
def main():
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Run Mozilla Observatory scan")
    parser.add_argument("target", help="Target domain")
    parser.add_argument("-o", "--output", default="/tmp/observatory_results", help="Output directory")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    
    args = parser.parse_args()
    
    # Create output directory
    os.makedirs(args.output, exist_ok=True)
    
    # Run the scan
    results = run_mozilla_observatory(args.target, args.output, args.dry_run)
    
    # Print results summary
    if "dry_run" in results and results["dry_run"]:
        print(f"Dry run completed. Would have executed: {results['command']}")
    elif "error" in results:
        print(f"Error: {results['error']}")
        if "raw_output_file" in results:
            print(f"See {results['raw_output_file']} for details")
    else:
        print(f"Scan completed successfully!")
        print(f"Output file: {results['output_file']}")
        
        if "summary" in results:
            summary = results["summary"]
            print("\nSummary:")
            print(f"Domain: {summary['domain']}")
            print(f"Grade: {summary.get('grade', 'N/A')}")
            print(f"Score: {summary.get('score', 'N/A')}")
            print(f"Passed tests: {summary.get('passed_tests', 0)}")
            print(f"Failed tests: {summary.get('failed_tests', 0)}")
            print(f"Total tests: {summary.get('total_tests', 0)}")

if __name__ == "__main__":
    main()
