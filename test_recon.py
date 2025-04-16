#!/usr/bin/env python3

import os
import sys
import argparse
from src.modules.utils.logger import setup_logger

def main():
    parser = argparse.ArgumentParser(description="Test individual KAST recon modules")
    parser.add_argument("module", choices=["whatweb", "theharvester", "dnsenum", "sslscan", 
                                          "ssllabs", "securityheaders", "mozilla", "wafw00f", "browser"],
                        help="Module to test")
    parser.add_argument("target", help="Target URL or IP address")
    parser.add_argument("--output", "-o", default="/tmp/kast-test", help="Output directory")
    
    args = parser.parse_args()
    
    # Create output directory
    os.makedirs(args.output, exist_ok=True)
    
    # Set up logger
    logger = setup_logger(args.target, args.output)
    
    # Import and run the selected module
    if args.module == "whatweb":
        from src.modules.recon.passive_recon import run_whatweb
        result = run_whatweb(args.target, args.output)
    elif args.module == "theharvester":
        from src.modules.recon.passive_recon import run_theharvester
        result = run_theharvester(args.target, args.output)
    elif args.module == "dnsenum":
        from src.modules.recon.dns_recon import run_dnsenum
        result = run_dnsenum(args.target, args.output)
    elif args.module == "sslscan":
        from src.modules.recon.ssl_recon import run_sslscan
        result = run_sslscan(args.target, args.output)
    elif args.module == "ssllabs":
        from src.modules.recon.ssl_recon import run_ssllabs
        result = run_ssllabs(args.target, args.output)
    elif args.module == "securityheaders":
        from src.modules.recon.security_headers import run_securityheaders
        result = run_securityheaders(args.target, args.output)
    elif args.module == "mozilla":
        from src.modules.recon.mozilla_observatory import run_mozilla_observatory
        result = run_mozilla_observatory(args.target, args.output)
    elif args.module == "wafw00f":
        from src.modules.recon.wafw00f_scan import run_wafw00f
        result = run_wafw00f(args.target, args.output)
    elif args.module == "browser":
        from src.modules.recon.web_recon import browser_recon
        result = browser_recon(args.target, args.output)
    
    print(f"\nResult: {result}")

if __name__ == "__main__":
    main()
