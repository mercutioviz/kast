#!/usr/bin/env python3
"""
Cleanup Orphaned Cloud Resources Script

Detects and removes orphaned KAST ZAP cloud infrastructure resources
that were left behind due to failed scans or incomplete cleanup.

Supports: AWS, Azure, GCP

Usage:
    # List all KAST resources
    python cleanup_orphaned_resources.py --list-all
    
    # List resources for specific scan
    python cleanup_orphaned_resources.py --scan-id kast-zap-355437ac
    
    # Cleanup specific instance
    python cleanup_orphaned_resources.py --instance-id i-06c57c296d5aef295
    
    # Interactive cleanup
    python cleanup_orphaned_resources.py --interactive
    
    # Cleanup all orphaned resources (dry-run)
    python cleanup_orphaned_resources.py --cleanup --dry-run
    
    # Cleanup for specific provider
    python cleanup_orphaned_resources.py --provider aws --cleanup
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
import json

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class CloudResource:
    """Represents a cloud resource"""
    
    def __init__(self, provider, resource_type, resource_id, name=None, 
                 region=None, state=None, tags=None, created_time=None, 
                 scan_id=None, associated_resources=None):
        self.provider = provider
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.name = name or resource_id
        self.region = region
        self.state = state
        self.tags = tags or {}
        self.created_time = created_time
        self.scan_id = scan_id
        self.associated_resources = associated_resources or []
        self.is_orphaned = False
        self.age_hours = None
        
        # Calculate age if created_time available
        if created_time:
            age_delta = datetime.now(created_time.tzinfo) - created_time
            self.age_hours = age_delta.total_seconds() / 3600
    
    def __str__(self):
        status = "ORPHANED" if self.is_orphaned else "TRACKED"
        age_str = f"{self.age_hours:.1f}h" if self.age_hours else "unknown"
        return (f"[{status}] {self.resource_type}\n"
                f"  ID: {self.resource_id}\n"
                f"  Name: {self.name}\n"
                f"  Region: {self.region}\n"
                f"  State: {self.state}\n"
                f"  Age: {age_str}\n"
                f"  Scan ID: {self.scan_id or 'N/A'}")


class CloudResourceScanner(ABC):
    """Abstract base class for cloud resource scanners"""
    
    def __init__(self, debug_callback=None):
        self.debug = debug_callback or (lambda x: print(f"  → {x}"))
        self.resources = []
    
    @abstractmethod
    def scan(self, scan_id=None, region=None):
        """
        Scan for KAST resources
        
        :param scan_id: Optional specific scan identifier
        :param region: Optional specific region
        :return: List of CloudResource objects
        """
        pass
    
    @abstractmethod
    def delete_resource(self, resource, dry_run=False):
        """
        Delete a specific resource
        
        :param resource: CloudResource to delete
        :param dry_run: If True, simulate but don't delete
        :return: True if successful
        """
        pass
    
    def is_kast_resource(self, tags, name):
        """
        Check if resource is a KAST resource based on tags/name
        
        :param tags: Dictionary of resource tags
        :param name: Resource name
        :return: True if KAST resource
        """
        # Check tags
        if tags:
            for key, value in tags.items():
                key_lower = key.lower()
                value_lower = str(value).lower() if value else ""
                
                if 'kast' in key_lower or 'kast' in value_lower:
                    return True
                if 'zap' in value_lower and 'scan' in value_lower:
                    return True
        
        # Check name pattern
        if name:
            name_lower = name.lower()
            if name_lower.startswith('kast-zap-'):
                return True
            if 'kast' in name_lower and 'zap' in name_lower:
                return True
        
        return False
    
    def extract_scan_id(self, tags, name):
        """
        Extract scan identifier from tags or name
        
        :param tags: Dictionary of resource tags
        :param name: Resource name
        :return: Scan ID or None
        """
        # Check tags first
        if tags:
            for key, value in tags.items():
                if key.lower() in ['scan_identifier', 'scanidentifier', 'scan-id']:
                    return str(value)
        
        # Extract from name (pattern: kast-zap-XXXXXXXX)
        if name and name.startswith('kast-zap-'):
            return name
        
        return None


class AWSResourceScanner(CloudResourceScanner):
    """Scanner for AWS resources"""
    
    def __init__(self, debug_callback=None):
        super().__init__(debug_callback)
        self.ec2_client = None
        self.region = None
    
    def _get_ec2_client(self, region='us-east-1'):
        """Get or create EC2 client"""
        try:
            import boto3
            if self.ec2_client is None or self.region != region:
                self.ec2_client = boto3.client('ec2', region_name=region)
                self.region = region
            return self.ec2_client
        except ImportError:
            self.debug("ERROR: boto3 not installed. Install with: pip install boto3")
            return None
        except Exception as e:
            self.debug(f"ERROR: Failed to create AWS client: {e}")
            return None
    
    def scan(self, scan_id=None, region='us-east-1'):
        """Scan AWS for KAST resources"""
        self.debug(f"Scanning AWS region: {region}")
        
        ec2 = self._get_ec2_client(region)
        if not ec2:
            return []
        
        resources = []
        
        # Scan EC2 instances
        try:
            filters = []
            if scan_id:
                # Filter by scan identifier tag or name
                filters.append({'Name': 'tag:scan_identifier', 'Values': [scan_id]})
            
            response = ec2.describe_instances(Filters=filters) if filters else ec2.describe_instances()
            
            for reservation in response.get('Reservations', []):
                for instance in reservation.get('Instances', []):
                    instance_id = instance.get('InstanceId')
                    
                    # Convert tags
                    tags = {}
                    for tag in instance.get('Tags', []):
                        tags[tag['Key']] = tag['Value']
                    
                    # Check if KAST resource
                    instance_name = tags.get('Name', instance_id)
                    if not self.is_kast_resource(tags, instance_name) and not scan_id:
                        continue
                    
                    # Create resource object
                    resource = CloudResource(
                        provider='aws',
                        resource_type='EC2 Instance',
                        resource_id=instance_id,
                        name=instance_name,
                        region=region,
                        state=instance['State']['Name'],
                        tags=tags,
                        created_time=instance.get('LaunchTime'),
                        scan_id=self.extract_scan_id(tags, instance_name)
                    )
                    
                    # Get associated resources
                    security_groups = [sg['GroupId'] for sg in instance.get('SecurityGroups', [])]
                    vpc_id = instance.get('VpcId')
                    
                    resource.associated_resources = []
                    if security_groups:
                        resource.associated_resources.extend([
                            {'type': 'SecurityGroup', 'id': sg} for sg in security_groups
                        ])
                    if vpc_id:
                        resource.associated_resources.append({'type': 'VPC', 'id': vpc_id})
                    
                    resources.append(resource)
                    self.debug(f"Found instance: {instance_id} ({instance_name})")
        
        except Exception as e:
            self.debug(f"Error scanning EC2 instances: {e}")
        
        # Scan Security Groups
        try:
            filters = []
            if scan_id:
                filters.append({'Name': 'tag:scan_identifier', 'Values': [scan_id]})
            
            response = ec2.describe_security_groups(Filters=filters) if filters else ec2.describe_security_groups()
            
            for sg in response.get('SecurityGroups', []):
                sg_id = sg.get('GroupId')
                sg_name = sg.get('GroupName')
                
                # Convert tags
                tags = {}
                for tag in sg.get('Tags', []):
                    tags[tag['Key']] = tag['Value']
                
                # Check if KAST resource
                if not self.is_kast_resource(tags, sg_name) and not scan_id:
                    continue
                
                # Skip default security groups
                if sg_name == 'default':
                    continue
                
                resource = CloudResource(
                    provider='aws',
                    resource_type='Security Group',
                    resource_id=sg_id,
                    name=sg_name,
                    region=region,
                    tags=tags,
                    scan_id=self.extract_scan_id(tags, sg_name)
                )
                
                resource.associated_resources.append({'type': 'VPC', 'id': sg.get('VpcId')})
                
                resources.append(resource)
                self.debug(f"Found security group: {sg_id} ({sg_name})")
        
        except Exception as e:
            self.debug(f"Error scanning security groups: {e}")
        
        self.resources = resources
        return resources
    
    def delete_resource(self, resource, dry_run=False):
        """Delete AWS resource"""
        ec2 = self._get_ec2_client(resource.region)
        if not ec2:
            return False
        
        try:
            if resource.resource_type == 'EC2 Instance':
                if dry_run:
                    self.debug(f"[DRY-RUN] Would terminate instance: {resource.resource_id}")
                    return True
                
                self.debug(f"Terminating instance: {resource.resource_id}")
                ec2.terminate_instances(InstanceIds=[resource.resource_id])
                
                # Wait for termination
                self.debug("Waiting for instance to terminate...")
                waiter = ec2.get_waiter('instance_terminated')
                waiter.wait(InstanceIds=[resource.resource_id])
                
                return True
            
            elif resource.resource_type == 'Security Group':
                if dry_run:
                    self.debug(f"[DRY-RUN] Would delete security group: {resource.resource_id}")
                    return True
                
                self.debug(f"Deleting security group: {resource.resource_id}")
                ec2.delete_security_group(GroupId=resource.resource_id)
                return True
            
            else:
                self.debug(f"Unknown resource type: {resource.resource_type}")
                return False
        
        except Exception as e:
            self.debug(f"Error deleting resource: {e}")
            return False


class AzureResourceScanner(CloudResourceScanner):
    """Scanner for Azure resources (placeholder)"""
    
    def scan(self, scan_id=None, region=None):
        self.debug("Azure scanning not yet implemented")
        return []
    
    def delete_resource(self, resource, dry_run=False):
        self.debug("Azure resource deletion not yet implemented")
        return False


class GCPResourceScanner(CloudResourceScanner):
    """Scanner for GCP resources (placeholder)"""
    
    def scan(self, scan_id=None, region=None):
        self.debug("GCP scanning not yet implemented")
        return []
    
    def delete_resource(self, resource, dry_run=False):
        self.debug("GCP resource deletion not yet implemented")
        return False


def print_header(message):
    """Print formatted header"""
    print("\n" + "=" * 70)
    print(f"  {message}")
    print("=" * 70 + "\n")


def print_section(message):
    """Print section header"""
    print(f"\n{'─' * 70}")
    print(f"  {message}")
    print(f"{'─' * 70}")


def print_success(message):
    """Print success message"""
    print(f"\n✓ {message}")


def print_error(message):
    """Print error message"""
    print(f"\n✗ ERROR: {message}")


def print_warning(message):
    """Print warning message"""
    print(f"\n⚠ WARNING: {message}")


def print_info(message):
    """Print info message"""
    print(f"  → {message}")


def check_for_state_files(scan_id):
    """
    Check if local state files exist for a scan
    
    :param scan_id: Scan identifier
    :return: Path to state file or None
    """
    test_output_dir = Path(__file__).parent.parent.parent / "test_output"
    
    if not test_output_dir.exists():
        return None
    
    # Search for state files containing the scan_id
    for state_file in test_output_dir.rglob("infrastructure_state.txt"):
        try:
            with open(state_file, 'r') as f:
                content = f.read()
                if scan_id in content:
                    return state_file
        except:
            continue
    
    return None


def mark_orphaned_resources(resources):
    """
    Mark resources as orphaned if no local state file exists
    
    :param resources: List of CloudResource objects
    """
    for resource in resources:
        if resource.scan_id:
            state_file = check_for_state_files(resource.scan_id)
            resource.is_orphaned = (state_file is None)
        else:
            # No scan_id means we can't correlate
            resource.is_orphaned = True


def display_resources(resources, show_all=False):
    """Display resources in formatted output"""
    if not resources:
        print_info("No KAST resources found")
        return
    
    # Group by provider
    by_provider = {}
    for resource in resources:
        if show_all or resource.is_orphaned:
            provider = resource.provider.upper()
            if provider not in by_provider:
                by_provider[provider] = []
            by_provider[provider].append(resource)
    
    # Display
    total_count = 0
    orphaned_count = 0
    
    for provider, provider_resources in by_provider.items():
        print_section(f"{provider} Resources ({len(provider_resources)})")
        
        for resource in provider_resources:
            print(f"\n{resource}")
            
            # Show associated resources
            if resource.associated_resources:
                print("  Associated:")
                for assoc in resource.associated_resources:
                    print(f"    - {assoc['type']}: {assoc['id']}")
            
            total_count += 1
            if resource.is_orphaned:
                orphaned_count += 1
    
    # Summary
    print_section("Summary")
    print_info(f"Total resources: {total_count}")
    print_info(f"Orphaned resources: {orphaned_count}")
    print_info(f"Tracked resources: {total_count - orphaned_count}")


def cleanup_resources(resources, dry_run=False, interactive=False):
    """
    Cleanup resources
    
    :param resources: List of CloudResource objects
    :param dry_run: If True, simulate but don't delete
    :param interactive: If True, prompt before each deletion
    :return: Count of successful deletions
    """
    # Filter to orphaned only
    orphaned = [r for r in resources if r.is_orphaned]
    
    if not orphaned:
        print_info("No orphaned resources to clean up")
        return 0
    
    print_header(f"Cleanup: {len(orphaned)} Orphaned Resource(s)")
    
    if dry_run:
        print_warning("DRY-RUN MODE - No resources will be deleted")
    
    # Create scanners
    scanners = {
        'aws': AWSResourceScanner(debug_callback=print_info),
        'azure': AzureResourceScanner(debug_callback=print_info),
        'gcp': GCPResourceScanner(debug_callback=print_info)
    }
    
    success_count = 0
    failed_count = 0
    skipped_count = 0
    
    for i, resource in enumerate(orphaned, 1):
        print_section(f"Resource {i}/{len(orphaned)}")
        print(f"\n{resource}")
        
        if interactive and not dry_run:
            response = input(f"\nDelete this resource? (yes/no/quit): ").strip().lower()
            if response == 'quit':
                print_info("Cleanup cancelled by user")
                break
            elif response not in ['yes', 'y']:
                print_info("Skipped")
                skipped_count += 1
                continue
        
        # Delete resource
        scanner = scanners.get(resource.provider)
        if scanner:
            if scanner.delete_resource(resource, dry_run=dry_run):
                success_count += 1
                print_success(f"{'Would delete' if dry_run else 'Deleted'}: {resource.resource_id}")
            else:
                failed_count += 1
                print_error(f"Failed to delete: {resource.resource_id}")
        else:
            print_warning(f"No scanner for provider: {resource.provider}")
            skipped_count += 1
    
    # Summary
    print_header("Cleanup Complete")
    print_info(f"Successful: {success_count}")
    if failed_count > 0:
        print_info(f"Failed: {failed_count}")
    if skipped_count > 0:
        print_info(f"Skipped: {skipped_count}")
    
    return success_count


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Detect and cleanup orphaned KAST cloud resources',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # List all KAST resources
  python cleanup_orphaned_resources.py --list-all
  
  # List resources for specific scan
  python cleanup_orphaned_resources.py --scan-id kast-zap-355437ac
  
  # Cleanup specific instance (dry-run)
  python cleanup_orphaned_resources.py --instance-id i-06c57c296d5aef295 --dry-run
  
  # Interactive cleanup
  python cleanup_orphaned_resources.py --interactive
  
  # Cleanup all orphaned resources
  python cleanup_orphaned_resources.py --cleanup
        '''
    )
    
    parser.add_argument(
        '--list-all',
        action='store_true',
        help='List all KAST resources (including tracked ones)'
    )
    parser.add_argument(
        '--scan-id',
        help='Filter by specific scan identifier (e.g., kast-zap-355437ac)'
    )
    parser.add_argument(
        '--instance-id',
        help='Filter by specific instance ID'
    )
    parser.add_argument(
        '--provider',
        choices=['aws', 'azure', 'gcp'],
        help='Scan specific cloud provider'
    )
    parser.add_argument(
        '--region',
        default='us-east-1',
        help='AWS region to scan (default: us-east-1)'
    )
    parser.add_argument(
        '--cleanup',
        action='store_true',
        help='Perform cleanup of orphaned resources'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be deleted without actually deleting'
    )
    parser.add_argument(
        '--interactive',
        action='store_true',
        help='Prompt before deleting each resource'
    )
    parser.add_argument(
        '--export',
        help='Export resource list to JSON file'
    )
    
    args = parser.parse_args()
    
    # Determine mode
    if not any([args.list_all, args.scan_id, args.instance_id, args.cleanup]):
        # Default: list orphaned resources
        args.list_all = False
    
    print_header("KAST Orphaned Resources Cleanup Tool")
    
    # Create scanners based on provider
    providers = [args.provider] if args.provider else ['aws']  # Default to AWS
    all_resources = []
    
    for provider in providers:
        print_section(f"Scanning {provider.upper()}")
        
        if provider == 'aws':
            scanner = AWSResourceScanner(debug_callback=print_info)
            resources = scanner.scan(scan_id=args.scan_id, region=args.region)
        elif provider == 'azure':
            scanner = AzureResourceScanner(debug_callback=print_info)
            resources = scanner.scan(scan_id=args.scan_id)
        elif provider == 'gcp':
            scanner = GCPResourceScanner(debug_callback=print_info)
            resources = scanner.scan(scan_id=args.scan_id)
        else:
            print_error(f"Unknown provider: {provider}")
            continue
        
        # Filter by instance ID if specified
        if args.instance_id:
            resources = [r for r in resources if r.resource_id == args.instance_id]
        
        all_resources.extend(resources)
    
    if not all_resources:
        print_info("No KAST resources found")
        sys.exit(0)
    
    # Mark orphaned resources
    print_section("Checking for Orphaned Resources")
    mark_orphaned_resources(all_resources)
    
    orphaned_count = sum(1 for r in all_resources if r.is_orphaned)
    print_info(f"Found {len(all_resources)} total resources")
    print_info(f"Identified {orphaned_count} orphaned resources")
    
    # Display resources
    print_header("Resource Inventory")
    display_resources(all_resources, show_all=args.list_all)
    
    # Export if requested
    if args.export:
        try:
            export_data = []
            for resource in all_resources:
                export_data.append({
                    'provider': resource.provider,
                    'type': resource.resource_type,
                    'id': resource.resource_id,
                    'name': resource.name,
                    'region': resource.region,
                    'state': resource.state,
                    'scan_id': resource.scan_id,
                    'is_orphaned': resource.is_orphaned,
                    'age_hours': resource.age_hours,
                    'tags': resource.tags
                })
            
            with open(args.export, 'w') as f:
                json.dump(export_data, f, indent=2, default=str)
            
            print_success(f"Exported to: {args.export}")
        except Exception as e:
            print_error(f"Failed to export: {e}")
    
    # Cleanup if requested
    if args.cleanup:
        if orphaned_count == 0:
            print_info("No orphaned resources to clean up")
            sys.exit(0)
        
        # Confirm before proceeding (unless dry-run or interactive)
        if not args.dry_run and not args.interactive:
            print_warning(f"About to delete {orphaned_count} orphaned resource(s)")
            response = input("Are you sure? (yes/no): ").strip().lower()
            if response not in ['yes', 'y']:
                print_info("Cleanup cancelled")
                sys.exit(0)
        
        success_count = cleanup_resources(
            all_resources,
            dry_run=args.dry_run,
            interactive=args.interactive
        )
        
        sys.exit(0 if success_count > 0 or args.dry_run else 1)
    
    sys.exit(0)


if __name__ == '__main__':
    main()
