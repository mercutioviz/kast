#!/usr/bin/env python3

import os
from datetime import datetime
from rich.progress import Progress

from src.modules.utils.validators import extract_domain
from src.modules.utils.logger import get_module_logger
from src.modules.vuln_scan.nikto_scanner import run_nikto

# Module-specific logger
logger = get_module_logger(__name__)

def create_results_dir(target):
    """Create a results directory for the current scan"""
    domain = extract_domain(target)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    results_dir = os.path.join(base_dir, "results", f"{domain}-{timestamp}")
    os.makedirs(results_dir, exist_ok=True)
    return results_dir

def run_scan(target, output_dir=None, use_browser=True, nikto_type="basic", custom_nikto_options=None, dry_run=False):
    """Run vulnerability scanning modules"""
    if not output_dir:
        output_dir = create_results_dir(target)
    
    vuln_dir = os.path.join(output_dir, 'vuln')
    os.makedirs(vuln_dir, exist_ok=True)
    
    results = {}
    
    with Progress() as progress:
        total_tasks = 1  # Just Nikto for now
        task = progress.add_task("[cyan]Running vulnerability scans...", total=total_tasks)
        
        # Run Nikto
        logger.info(f"Running Nikto web vulnerability scanner ({nikto_type} scan)")
        results['nikto'] = run_nikto(
            target, 
            vuln_dir, 
            scan_type=nikto_type,
            custom_options=custom_nikto_options,
            dry_run=dry_run
        )
        progress.update(task, advance=1)
    
    if dry_run:
        logger.info("[DRY RUN] Vulnerability scanning dry run completed. No actual scans were performed.")
    else:
        logger.info(f"Vulnerability scanning completed! Results saved to {vuln_dir}")
    
    return results, vuln_dir
