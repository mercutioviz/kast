#!/usr/bin/env python3

import os
from datetime import datetime
from rich.progress import Progress

from src.modules.utils.validators import extract_domain
from src.modules.utils.logger import setup_logger, get_module_logger
from src.modules.recon.passive_recon import run_whatweb, run_theharvester
from src.modules.recon.dns_recon import run_dnsenum
from src.modules.recon.ssl_recon import run_sslscan, run_ssllabs
from src.modules.recon.security_headers import run_securityheaders
from src.modules.recon.mozilla_observatory import run_mozilla_observatory
from src.modules.recon.web_recon import browser_recon
from src.modules.recon.wafw00f_scan import run_wafw00f

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

def run_recon(target, output_dir=None, use_browser=True, use_online_services=True, dry_run=False):
    """Run all reconnaissance modules"""
    if not output_dir:
        output_dir = create_results_dir(target)
    
    # Set up the logger
    main_logger = setup_logger(target, output_dir)
    
    if dry_run:
        logger.info("[DRY RUN] This is a dry run. No actual scanning will be performed.")
    
    recon_dir = os.path.join(output_dir, 'recon')
    os.makedirs(recon_dir, exist_ok=True)
    
    results = {}
    
    with Progress() as progress:
        total_tasks = 5  # Basic tools
        if use_browser:
            total_tasks += 1
        if use_online_services:
            total_tasks += 3  # SSL Labs, SecurityHeaders, Mozilla Observatory
        
        task = progress.add_task("[cyan]Running reconnaissance...", total=total_tasks)
        
        # Run WhatWeb
        #logger.info("Running WhatWeb for technology detection")
        results['whatweb'] = run_whatweb(target, recon_dir, dry_run=dry_run)
        progress.update(task, advance=1)
        
        # Run theHarvester
        #logger.info("Running theHarvester for email and subdomain enumeration")
        #results['theharvester'] = run_theharvester(target, recon_dir, dry_run=dry_run)
        #progress.update(task, advance=1)
        
        # Run DNSenum
        #logger.info("\nRunning DNSenum for DNS enumeration")
        results['dnsenum'] = run_dnsenum(target, recon_dir, dry_run=dry_run)
        progress.update(task, advance=1)
        
        # Run SSLScan
        #logger.info("\nRunning SSLScan for SSL/TLS configuration analysis")
        results['sslscan'] = run_sslscan(target, recon_dir, dry_run=dry_run)
        progress.update(task, advance=1)
        
        # Run wafw00f
        #logger.info("\nRunning wafw00f to detect Web Application Firewalls")
        results['wafw00f'] = run_wafw00f(target, recon_dir, dry_run=dry_run)
        progress.update(task, advance=1)
        
        # Run browser-based recon if enabled
        if use_browser and target.startswith(('http://', 'https://')):
            #logger.info("\nRunning browser-based reconnaissance")
            results['browser'] = browser_recon(target, recon_dir, dry_run=dry_run)
            progress.update(task, advance=1)
        
        # Run online services if enabled
        if use_online_services:
            # Run SSL Labs
            #logger.info("\nRunning SSL Labs scan for comprehensive SSL/TLS analysis")
            results['ssllabs'] = run_ssllabs(target, recon_dir, dry_run=dry_run)
            progress.update(task, advance=1)
            
            ### Circle back to securityheaders.com if there's valid reason to do so ###
            # Run SecurityHeaders.io
            #logger.info("Running SecurityHeaders.io scan for HTTP security headers analysis")
            #results['securityheaders'] = run_securityheaders(target, recon_dir, dry_run=dry_run)
            #progress.update(task, advance=1)
            
            ### Circle back to observatory if there's valid reason to do so ###
            # Run Mozilla Observatory
            logger.info("\nRunning Mozilla Observatory scan for web security analysis")
            results['mozilla_observatory'] = run_mozilla_observatory(target, recon_dir, dry_run=dry_run)
            progress.update(task, advance=1)
    
    if dry_run:
        logger.info("[DRY RUN] Reconnaissance dry run completed. No actual scans were performed.")
    else:
        logger.info(f"Reconnaissance completed! Results saved to {recon_dir}")
    
    return results, recon_dir
