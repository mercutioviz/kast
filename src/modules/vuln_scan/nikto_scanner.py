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

def run_nikto(target, output_dir, scan_type="basic", custom_options=None, dry_run=False):
    """
    Run Nikto web server scanner with different scan types
    
    Args:
        target (str): The target URL or domain
        output_dir (str): Directory to save results
        scan_type (str): Type of scan - "basic", "quick", "thorough", or "custom"
        custom_options (list): List of custom Nikto options (for scan_type="custom")
        dry_run (bool): If True, only show what would be done
        
    Returns:
        dict: Scan results
    """
    logger.info(f"Running Nikto scan ({scan_type}) for {target}")
    
    # Ensure target has a scheme
    target = normalize_url(target)
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Define output files
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_output = os.path.join(output_dir, f'nikto_{scan_type}_{timestamp}.json')
    txt_output = os.path.join(output_dir, f'nikto_{scan_type}_{timestamp}.txt')
    summary_output = os.path.join(output_dir, f'nikto_summary_{scan_type}_{timestamp}.json')
    
    # Base command
    command = ['nikto', '-h', target, '-o', json_output, '-Format', 'json']
    
    # Add scan type specific options
    if scan_type == "quick":
        # Quick scan: Limited test types, faster execution
        command.extend(['-Tuning', '23bc', '-maxtime', '600'])
        logger.info("Using quick scan settings: Limited tests, 10 minute max")
    elif scan_type == "thorough":
        # Thorough scan: All test types, comprehensive
        command.extend(['-Tuning', 'x', '-maxtime', '3600'])
        logger.info("Using thorough scan settings: All tests, 1 hour max")
    elif scan_type == "custom" and custom_options:
        # Custom scan: User-provided options
        command.extend(custom_options)
        logger.info(f"Using custom scan settings: {' '.join(custom_options)}")
    else:
        # Basic scan: Default settings
        command.extend(['-maxtime', '1800'])
        logger.info("Using basic scan settings: Default tests, 30 minute max")
    
    if dry_run:
        logger.info(f"[DRY RUN] Would execute: {' '.join(command)}")
        return {
            "dry_run": True,
            "command": ' '.join(command),
            "output_file": json_output,
            "scan_type": scan_type
        }
    
    try:
        # Start time for tracking scan duration
        start_time = time.time()
        
        # Run Nikto
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
            logger.warning(f"Nikto exited with code {process.returncode}")
            logger.warning(f"Stderr: {process.stderr}")
            
            # Save stderr to text file for debugging
            with open(txt_output, 'w') as f:
                f.write(f"Command: {' '.join(command)}\n")
                f.write(f"Return code: {process.returncode}\n")
                f.write(f"Stderr: {process.stderr}\n")
                f.write(f"Stdout: {process.stdout}\n")
            
            logger.info(f"Debug output saved to {txt_output}")
        
        # Check if the JSON output file was created
        if os.path.exists(json_output) and os.path.getsize(json_output) > 0:
            logger.info(f"Nikto scan completed in {duration:.1f} seconds. Results saved to {json_output}")
            
            # Load and parse the JSON results
            nikto_data = load_json_file(json_output)
            
            if nikto_data:
                # Create a summary of the results
                summary = create_nikto_summary(nikto_data, target, scan_type, duration)
                
                # Save the summary
                save_json(summary, summary_output)
                logger.info(f"Nikto summary saved to {summary_output}")
                
                return {
                    "raw_results": nikto_data,
                    "summary": summary,
                    "output_file": json_output,
                    "summary_file": summary_output,
                    "scan_type": scan_type,
                    "duration": duration
                }
            else:
                logger.error("Failed to parse Nikto JSON output")
        else:
            logger.error(f"Nikto did not create a valid JSON output file at {json_output}")
            
            # Try to save stdout as JSON
            try:
                with open(json_output, 'w') as f:
                    f.write(process.stdout)
                
                # Try to parse it
                nikto_data = load_json_file(json_output)
                
                if nikto_data:
                    logger.info(f"Successfully parsed Nikto output from stdout")
                    
                    # Create a summary of the results
                    summary = create_nikto_summary(nikto_data, target, scan_type, duration)
                    
                    # Save the summary
                    save_json(summary, summary_output)
                    logger.info(f"Nikto summary saved to {summary_output}")
                    
                    return {
                        "raw_results": nikto_data,
                        "summary": summary,
                        "output_file": json_output,
                        "summary_file": summary_output,
                        "scan_type": scan_type,
                        "duration": duration
                    }
            except Exception as e:
                logger.error(f"Error saving or parsing stdout as JSON: {e}")
        
        # If we get here, something went wrong
        return {
            "error": f"Nikto scan failed or produced invalid output (exit code: {process.returncode})",
            "debug_file": txt_output,
            "scan_type": scan_type,
            "duration": duration
        }
        
    except Exception as e:
        logger.error(f"Error running Nikto: {str(e)}")
        return {
            "error": str(e),
            "scan_type": scan_type
        }

def create_nikto_summary(nikto_data, target, scan_type, duration):
    """
    Create a summary of Nikto scan results
    
    Args:
        nikto_data (dict): The raw Nikto results
        target (str): The target that was scanned
        scan_type (str): The type of scan performed
        duration (float): The scan duration in seconds
        
    Returns:
        dict: A summary of the scan results
    """
    try:
        # Initialize summary
        summary = {
            "target": target,
            "scan_type": scan_type,
            "duration": f"{duration:.1f} seconds",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "vulnerabilities": {
                "high": 0,
                "medium": 0,
                "low": 0,
                "info": 0
            },
            "findings": []
        }
        
        # Extract scan details
        if "details" in nikto_data:
            if "host" in nikto_data["details"]:
                summary["host_details"] = nikto_data["details"]["host"]
            if "stats" in nikto_data["details"]:
                summary["statistics"] = nikto_data["details"]["stats"]
        
        # Process vulnerabilities
        if "vulnerabilities" in nikto_data:
            for vuln in nikto_data["vulnerabilities"]:
                # Determine severity (Nikto doesn't provide severity, so we'll estimate)
                severity = estimate_severity(vuln)
                
                # Increment counter
                summary["vulnerabilities"][severity] += 1
                
                # Add to findings list
                finding = {
                    "id": vuln.get("id", "unknown"),
                    "severity": severity,
                    "method": vuln.get("method", ""),
                    "url": vuln.get("url", ""),
                    "message": vuln.get("msg", ""),  # Fix: Use "msg" field from Nikto output
                    "osvdb": vuln.get("osvdb", "")
                }
                
                summary["findings"].append(finding)
        
        # Add total count
        total = sum(summary["vulnerabilities"].values())
        summary["total_findings"] = total
        
        return summary
    
    except Exception as e:
        logger.error(f"Error creating Nikto summary: {str(e)}")
        return {
            "error": f"Failed to create summary: {str(e)}",
            "target": target,
            "scan_type": scan_type,
            "duration": f"{duration:.1f} seconds",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

def estimate_severity(vulnerability):
    """
    Estimate the severity of a vulnerability based on its characteristics
    
    Args:
        vulnerability (dict): The vulnerability data from Nikto
        
    Returns:
        str: Estimated severity - "high", "medium", "low", or "info"
    """
    # Get the message and references
    message = vulnerability.get("msg", "").lower()
    references = vulnerability.get("references", "").lower()
    vuln_id = vulnerability.get("id", "")
    
    # Check for CVE references first
    if references and "cve-" in references:
        return "high"
    
    # Keywords that might indicate high severity
    high_keywords = [
        "remote code execution", "rce", "sql injection", "command injection",
        "arbitrary code", "xss", "cross site scripting", "csrf", "directory traversal",
        "path traversal", "buffer overflow", "privilege escalation", "authentication bypass"
    ]
    
    # Keywords that might indicate medium severity
    medium_keywords = [
        "information disclosure", "information leakage", "default password",
        "default credential", "misconfiguration", "sensitive data", "weak password",
        "insecure configuration", "outdated", "deprecated", "breach attack",
        "strict-transport-security", "content-type-options", "secure flag", "httponly flag"
    ]
    
    # Keywords that might indicate low severity
    low_keywords = [
        "version disclosure", "server type", "banner", "header", "cookie",
        "missing header", "clickjacking", "cacheable", "autocomplete", "x-powered-by"
    ]
    
    # Check for high severity indicators
    for keyword in high_keywords:
        if keyword in message or keyword in references:
            return "high"
    
    # Check for medium severity indicators
    for keyword in medium_keywords:
        if keyword in message or keyword in references:
            return "medium"
    
    # Check for low severity indicators
    for keyword in low_keywords:
        if keyword in message or keyword in references:
            return "low"
    
    # Special cases based on ID
    if vuln_id in ["999970", "999103", "999961", "95", "999966", "999972"]:
        return "medium"  # Security headers and cookie issues
    
    # Default to info
    return "info"

# Test function for direct execution
def main():
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Run Nikto web server scanner")
    parser.add_argument("target", help="Target URL or domain")
    parser.add_argument("-o", "--output", default="/tmp/nikto_results", help="Output directory")
    parser.add_argument("-t", "--type", choices=["basic", "quick", "thorough", "custom"], default="basic", help="Scan type")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser.add_argument("--custom-options", nargs="+", help="Custom Nikto options (for custom scan type)")
    
    args = parser.parse_args()
    
    # Create output directory
    os.makedirs(args.output, exist_ok=True)
    
    # Run the scan
    results = run_nikto(
        args.target,
        args.output,
        scan_type=args.type,
        custom_options=args.custom_options,
        dry_run=args.dry_run
    )
    
    # Print results summary
    if "dry_run" in results and results["dry_run"]:
        print(f"Dry run completed. Would have executed: {results['command']}")
    elif "error" in results:
        print(f"Error: {results['error']}")
    else:
        print(f"Scan completed successfully!")
        print(f"Output file: {results['output_file']}")
        print(f"Summary file: {results.get('summary_file', 'N/A')}")
        
        if "summary" in results:
            summary = results["summary"]
            print("\nSummary:")
            print(f"Target: {summary['target']}")
            print(f"Scan type: {summary['scan_type']}")
            print(f"Duration: {summary['duration']}")
            print(f"Total findings: {summary.get('total_findings', 0)}")
            
            vulns = summary.get("vulnerabilities", {})
            print(f"High severity: {vulns.get('high', 0)}")
            print(f"Medium severity: {vulns.get('medium', 0)}")
            print(f"Low severity: {vulns.get('low', 0)}")
            print(f"Informational: {vulns.get('info', 0)}")

if __name__ == "__main__":
    main()
