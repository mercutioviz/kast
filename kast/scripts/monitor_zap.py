#!/usr/bin/env python3
"""
Interactive ZAP Scan Monitor with Auto-Discovery
Automatically finds ZAP URL from infrastructure state or accepts manual input

Usage:
    python kast/scripts/monitor_zap.py                    # Auto-discover ZAP URL
    python kast/scripts/monitor_zap.py --url URL          # Specify URL manually
    python kast/scripts/monitor_zap.py --once             # One-time status check
    python kast/scripts/monitor_zap.py --api-key KEY      # Custom API key
"""

import sys
import time
import argparse
from pathlib import Path
from datetime import datetime

# Add KAST to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import ZAPAPIClient directly
import importlib.util
spec = importlib.util.spec_from_file_location(
    "zap_api_client",
    Path(__file__).parent / "zap_api_client.py"
)
zap_api_client = importlib.util.module_from_spec(spec)
sys.modules['zap_api_client'] = zap_api_client
spec.loader.exec_module(zap_api_client)
ZAPAPIClient = zap_api_client.ZAPAPIClient


def find_latest_zap_infrastructure():
    """
    Scan for most recent ZAP infrastructure state file
    
    Returns:
        tuple: (zap_url, api_key, timestamp) or (None, None, None) if not found
    """
    # Directories to search
    search_dirs = [
        Path(__file__).parent.parent.parent / "test_output",
        Path(__file__).parent.parent.parent / "output"
    ]
    
    state_files = []
    
    # Find all infrastructure_state.txt files
    for search_dir in search_dirs:
        if search_dir.exists():
            for state_file in search_dir.rglob("infrastructure_state.txt"):
                state_files.append(state_file)
    
    if not state_files:
        return None, None, None
    
    # Parse state files and find most recent
    latest_state = None
    latest_timestamp = None
    
    for state_file in state_files:
        try:
            with open(state_file, 'r') as f:
                content = f.read()
            
            # Parse the state file
            zap_url = None
            timestamp = None
            api_key = None
            
            for line in content.split('\n'):
                if line.startswith('Timestamp:'):
                    timestamp = line.split(':', 1)[1].strip()
                elif 'zap_api_url:' in line:
                    zap_url = line.split(':', 1)[1].strip()
                    # Handle format "zap_api_url: http://..."
                    if zap_url.startswith('http'):
                        pass
                    else:
                        # Try to extract from full line
                        if 'http' in line:
                            zap_url = 'http' + line.split('http')[1].strip()
            
            # Extract API key from config (default to kast01)
            api_key = "kast01"
            
            if zap_url and timestamp:
                # Compare timestamps to find latest
                if latest_timestamp is None or timestamp > latest_timestamp:
                    latest_timestamp = timestamp
                    latest_state = (zap_url, api_key, timestamp)
        
        except Exception as e:
            print(f"Warning: Failed to parse {state_file}: {e}")
            continue
    
    return latest_state if latest_state else (None, None, None)


def print_header():
    """Print monitor header"""
    print("\n" + "="*70)
    print("  ZAP SCAN MONITOR")
    print("="*70)


def print_status(client, show_timestamp=True):
    """Print current scan status"""
    if show_timestamp:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Refreshing status...")
    
    print("\n" + "-"*70)
    
    # Get ZAP info
    info = client.get_zap_info()
    print(f"ZAP Version: {info.get('version', 'unknown')}")
    print(f"API URL: {client.api_url}")
    
    # Get scan status
    status = client.get_scan_status()
    if status:
        print(f"\n📊 Scan Progress:")
        
        # Spider progress
        spider_pct = status['spider_status']
        spider_bar = create_progress_bar(spider_pct)
        print(f"  Spider:      {spider_bar} {spider_pct}%")
        
        # Active scan progress
        ascan_pct = status['active_scan_status']
        ascan_bar = create_progress_bar(ascan_pct)
        print(f"  Active Scan: {ascan_bar} {ascan_pct}%")
        
        # Status
        in_progress = status['in_progress']
        status_icon = "🔄" if in_progress else "✅"
        status_text = "In Progress" if in_progress else "Completed"
        print(f"\n  Status: {status_icon} {status_text}")
        
        # Alerts
        alert_count = status['alert_count']
        print(f"  Alerts Found: {alert_count}")
    else:
        print("\n⚠️  Could not retrieve scan status")
    
    # Get alerts summary
    if 'alerts_summary' in info and info['alerts_summary']:
        print(f"\n🚨 Alerts by Risk:")
        summary = info['alerts_summary']
        risk_icons = {
            'High': '🔴',
            'Medium': '🟠',
            'Low': '🟡',
            'Informational': '🔵'
        }
        
        for risk in ['High', 'Medium', 'Low', 'Informational']:
            count = summary.get(risk, 0)
            if isinstance(count, str):
                try:
                    count = int(count)
                except:
                    count = 0
            
            if count > 0:
                icon = risk_icons.get(risk, '•')
                print(f"  {icon} {risk:15} {count:3} finding(s)")
    
    print("-"*70)


def create_progress_bar(percentage, width=30):
    """Create a text-based progress bar"""
    try:
        pct = int(percentage)
    except:
        pct = 0
    
    filled = int(width * pct / 100)
    bar = '█' * filled + '░' * (width - filled)
    return f"[{bar}]"


def show_alerts(client, limit=20):
    """Display recent alerts"""
    print("\n" + "="*70)
    print("RECENT ALERTS")
    print("="*70)
    
    alerts = client.get_alerts()
    
    if not alerts:
        print("\nNo alerts found yet.")
        return
    
    print(f"\nTotal: {len(alerts)} alert(s)")
    print(f"Showing: {min(limit, len(alerts))} most recent\n")
    
    risk_icons = {
        'High': '🔴',
        'Medium': '🟠',
        'Low': '🟡',
        'Informational': '🔵'
    }
    
    for i, alert in enumerate(alerts[:limit], 1):
        risk = alert.get('risk', 'Unknown')
        name = alert.get('name', 'Unknown')
        url = alert.get('url', 'N/A')
        
        icon = risk_icons.get(risk, '•')
        
        print(f"{i:2}. {icon} [{risk}] {name}")
        print(f"    URL: {url[:60]}{'...' if len(url) > 60 else ''}")
        
        if i < limit and i < len(alerts):
            print()


def generate_report(client):
    """Generate and save JSON report"""
    timestamp = int(time.time())
    output_file = f"zap_report_{timestamp}.json"
    
    print(f"\n📄 Generating report...")
    
    try:
        report_path = client.generate_report(output_file)
        print(f"✅ Report saved: {report_path}")
    except Exception as e:
        print(f"❌ Failed to generate report: {e}")


def show_menu():
    """Display interactive menu"""
    print("\n" + "="*70)
    print("OPTIONS")
    print("="*70)
    print("  [Enter]  - Refresh status")
    print("  [a]      - Show all alerts")
    print("  [r]      - Generate JSON report")
    print("  [h]      - Show this help menu")
    print("  [q]      - Quit")
    print("="*70)


def interactive_mode(client):
    """Run interactive monitoring loop"""
    print_header()
    print(f"\n✅ Connected to ZAP at {client.api_url}")
    
    show_menu()
    
    try:
        while True:
            print_status(client)
            
            try:
                choice = input("\nChoice (h for help): ").strip().lower()
            except EOFError:
                # Handle Ctrl+D
                print("\n")
                break
            
            if choice == 'q':
                print("\n👋 Exiting monitor...")
                break
            elif choice == 'a':
                show_alerts(client)
                input("\nPress Enter to continue...")
            elif choice == 'r':
                generate_report(client)
                input("\nPress Enter to continue...")
            elif choice == 'h':
                show_menu()
            elif choice == '':
                # Just refresh
                continue
            else:
                print(f"\n⚠️  Unknown option: '{choice}'. Press 'h' for help.")
                time.sleep(1)
    
    except KeyboardInterrupt:
        print("\n\n👋 Exiting monitor...")


def once_mode(client):
    """Run one-time status check"""
    print_header()
    print_status(client, show_timestamp=False)


def main():
    parser = argparse.ArgumentParser(
        description='Monitor OWASP ZAP scan status interactively',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                     # Auto-discover ZAP URL
  %(prog)s --url URL           # Specify URL manually
  %(prog)s --once              # One-time status check
  %(prog)s --api-key KEY       # Custom API key
        """
    )
    
    parser.add_argument(
        '--url',
        help='ZAP API URL (e.g., http://host:8080). Auto-discovered if not specified.'
    )
    parser.add_argument(
        '--api-key',
        default='kast01',
        help='ZAP API key (default: kast01)'
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='One-time status check (non-interactive)'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=30,
        help='API request timeout in seconds (default: 30)'
    )
    
    args = parser.parse_args()
    
    # Determine ZAP URL
    zap_url = args.url
    api_key = args.api_key
    
    if not zap_url:
        print("🔍 Auto-discovering ZAP infrastructure...")
        discovered_url, discovered_key, timestamp = find_latest_zap_infrastructure()
        
        if discovered_url:
            zap_url = discovered_url
            if discovered_key:
                api_key = discovered_key
            print(f"✅ Found ZAP at {zap_url} (deployed: {timestamp})")
        else:
            print("\n❌ No ZAP infrastructure found.")
            print("\nSearched in:")
            print("  - test_output/**/infrastructure_state.txt")
            print("  - output/**/infrastructure_state.txt")
            print("\nPlease specify URL manually with --url option")
            print("Example: python monitor_zap.py --url http://34.220.11.146:8080")
            sys.exit(1)
    
    # Create client
    client = ZAPAPIClient(
        api_url=zap_url,
        api_key=api_key,
        timeout=args.timeout,
        debug_callback=lambda msg: None  # Silent debug
    )
    
    # Test connection
    print(f"\n🔌 Connecting to {zap_url}...")
    if not client.check_connection():
        print(f"\n❌ Failed to connect to ZAP at {zap_url}")
        print("\nPossible issues:")
        print("  - ZAP is not running")
        print("  - URL is incorrect")
        print("  - Network/firewall blocking connection")
        print("  - API key is incorrect")
        sys.exit(1)
    
    # Run in selected mode
    if args.once:
        once_mode(client)
    else:
        interactive_mode(client)


if __name__ == "__main__":
    main()
