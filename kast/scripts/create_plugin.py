#!/usr/bin/env python3
"""
File: scripts/create_plugin.py
Description: Helper script to create new KAST plugins from templates or existing plugins.

Usage:
    python kast/scripts/create_plugin.py --name <tool_name> [options]
    python kast/scripts/create_plugin.py --interactive

Examples:
    # Create from template (default)
    python kast/scripts/create_plugin.py --name nmap --display-name "Nmap Port Scanner"
    
    # Create based on existing plugin
    python kast/scripts/create_plugin.py --name nikto --based-on whatweb
    
    # Interactive mode
    python kast/scripts/create_plugin.py --interactive
"""

import argparse
import os
import sys
import shutil
import re
from pathlib import Path
from datetime import datetime, UTC

# Add parent directory to path for imports
script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))


class PluginCreator:
    """Helper class to create new KAST plugins."""
    
    def __init__(self):
        self.plugins_dir = project_root / "kast" / "plugins"
        self.tests_dir = project_root / "kast" / "tests"
        self.template_plugin = self.plugins_dir / "template_plugin.py"
        
    def get_available_plugins(self):
        """Get list of available plugins to use as templates."""
        plugins = []
        for file in self.plugins_dir.glob("*_plugin.py"):
            if file.name != "template_plugin.py" and file.name != "__init__.py":
                plugins.append(file.stem.replace("_plugin", ""))
        return sorted(plugins)
    
    def validate_tool_exists(self, tool_name):
        """Check if the tool exists in PATH."""
        return shutil.which(tool_name) is not None
    
    def get_plugin_info_interactive(self):
        """Interactively gather plugin information from user."""
        print("\n=== KAST Plugin Creator - Interactive Mode ===\n")
        
        # Tool name (required)
        while True:
            name = input("Tool name (e.g., nmap, nikto): ").strip().lower()
            if name and re.match(r'^[a-z0-9_]+$', name):
                break
            print("  Error: Tool name must contain only lowercase letters, numbers, and underscores.")
        
        # Check if tool exists in PATH
        tool_in_path = self.validate_tool_exists(name)
        if tool_in_path:
            print(f"  ✓ Tool '{name}' found in PATH")
        else:
            print(f"  ⚠ Warning: Tool '{name}' not found in PATH")
            proceed = input("  Continue anyway? (y/n): ").strip().lower()
            if proceed != 'y':
                print("Aborted.")
                sys.exit(0)
        
        # Display name
        default_display = name.replace("_", " ").title()
        display_name = input(f"Display name [{default_display}]: ").strip() or default_display
        
        # Description
        description = input("Short description: ").strip() or f"{display_name} security scanner"
        
        # Website URL
        website_url = input("Website URL (optional): ").strip() or f"https://example.com/{name}"
        
        # Scan type
        print("\nScan type:")
        print("  1. passive - Read-only, no active probing")
        print("  2. active - Sends requests, may trigger alerts")
        scan_type_choice = input("Select [1/2] (default: 1): ").strip() or "1"
        scan_type = "passive" if scan_type_choice == "1" else "active"
        
        # Output type
        print("\nOutput type:")
        print("  1. file - Tool writes to output file")
        print("  2. stdout - Tool writes to stdout/stderr")
        output_type_choice = input("Select [1/2] (default: 1): ").strip() or "1"
        output_type = "file" if output_type_choice == "1" else "stdout"
        
        # Priority
        priority = input("Priority (10-90, lower runs first) [50]: ").strip() or "50"
        try:
            priority = int(priority)
        except ValueError:
            priority = 50
        
        # Base template
        print("\nBase template:")
        print("  0. template (clean slate with minimal boilerplate)")
        available_plugins = self.get_available_plugins()
        for idx, plugin in enumerate(available_plugins, 1):
            print(f"  {idx}. {plugin} (copy from existing plugin)")
        
        base_choice = input(f"Select [0-{len(available_plugins)}] (default: 0): ").strip() or "0"
        try:
            base_idx = int(base_choice)
            if base_idx == 0:
                based_on = "template"
            elif 1 <= base_idx <= len(available_plugins):
                based_on = available_plugins[base_idx - 1]
            else:
                based_on = "template"
        except ValueError:
            based_on = "template"
        
        print(f"\n  Selected base: {based_on}")
        
        return {
            "name": name,
            "display_name": display_name,
            "description": description,
            "website_url": website_url,
            "scan_type": scan_type,
            "output_type": output_type,
            "priority": priority,
            "based_on": based_on
        }
    
    def create_plugin(self, info):
        """Create a new plugin file based on the provided information."""
        plugin_name = f"{info['name']}_plugin.py"
        plugin_path = self.plugins_dir / plugin_name
        
        # Check if plugin already exists
        if plugin_path.exists():
            print(f"\n✗ Error: Plugin '{plugin_name}' already exists at {plugin_path}")
            return None
        
        # Determine source template
        if info['based_on'] == 'template':
            source_file = self.template_plugin
        else:
            source_file = self.plugins_dir / f"{info['based_on']}_plugin.py"
            if not source_file.exists():
                print(f"\n✗ Error: Source plugin '{info['based_on']}' not found")
                return None
        
        # Read source template
        with open(source_file, 'r') as f:
            content = f.read()
        
        # Perform replacements
        content = self._perform_replacements(content, info)
        
        # Add creation header
        creation_header = f'''"""
File: plugins/{plugin_name}
Description: KAST plugin for {info['display_name']}
Created: {datetime.now(UTC).strftime('%Y-%m-%d')} using create_plugin.py
Based on: {info['based_on']}

TODO: Customize the following sections:
  1. Command structure in run() method
  2. Output parsing in post_process() method
  3. Issue extraction logic
  4. Executive summary generation
  5. Update _generate_summary() if needed
"""

'''
        
        # Replace the original file header
        content = re.sub(r'^"""[\s\S]*?"""', creation_header.rstrip(), content, count=1)
        
        # Write new plugin file
        with open(plugin_path, 'w') as f:
            f.write(content)
        
        print(f"\n✓ Created plugin: {plugin_path}")
        return plugin_path
    
    def _perform_replacements(self, content, info):
        """Perform string replacements to customize the plugin."""
        class_name = ''.join(word.capitalize() for word in info['name'].split('_')) + 'Plugin'
        
        replacements = {
            # Class name
            r'class TemplatePlugin\(KastPlugin\):': f'class {class_name}(KastPlugin):',
            r'class \w+Plugin\(KastPlugin\):': f'class {class_name}(KastPlugin):',
            
            # Basic attributes
            r'self\.name = "[^"]*"': f'self.name = "{info["name"]}"',
            r'self\.display_name = "[^"]*"': f'self.display_name = "{info["display_name"]}"',
            r'self\.description = "[^"]*"': f'self.description = "{info["description"]}"',
            r'self\.website_url = "[^"]*"': f'self.website_url = "{info["website_url"]}"',
            r'self\.scan_type = "[^"]*"': f'self.scan_type = "{info["scan_type"]}"',
            r'self\.output_type = "[^"]*"': f'self.output_type = "{info["output_type"]}"',
            r'priority = \d+': f'priority = {info["priority"]}',
            
            # Tool name in commands and comments
            r'"toolname"': f'"{info["name"]}"',
            r'toolname': info["name"],
            
            # File paths
            r'f"{self\.name}\.json"': f'f"{{self.name}}.json"',
        }
        
        for pattern, replacement in replacements.items():
            content = re.sub(pattern, replacement, content)
        
        return content
    
    def create_test_file(self, plugin_name):
        """Create a basic unit test skeleton for the plugin."""
        test_name = f"test_{plugin_name}_plugin.py"
        test_path = self.tests_dir / test_name
        
        if test_path.exists():
            print(f"  ⚠ Test file already exists: {test_path}")
            return None
        
        class_name = ''.join(word.capitalize() for word in plugin_name.split('_')) + 'Plugin'
        
        test_content = f'''"""
File: tests/{test_name}
Description: Unit tests for {plugin_name} plugin
Created: {datetime.now(UTC).strftime('%Y-%m-%d')}
"""

import unittest
import os
import json
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock
from kast.plugins.{plugin_name}_plugin import {class_name}


class Test{class_name}(unittest.TestCase):
    """Test suite for {class_name}."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_cli_args = Mock()
        self.mock_cli_args.verbose = False
        self.plugin = {class_name}(self.mock_cli_args)
        self.test_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_plugin_initialization(self):
        """Test plugin initializes with correct attributes."""
        self.assertEqual(self.plugin.name, "{plugin_name}")
        self.assertIsNotNone(self.plugin.display_name)
        self.assertIsNotNone(self.plugin.description)
        self.assertIn(self.plugin.scan_type, ["passive", "active"])
        self.assertIn(self.plugin.output_type, ["file", "stdout"])
    
    def test_is_available(self):
        """Test tool availability check."""
        # This will depend on whether the tool is installed
        result = self.plugin.is_available()
        self.assertIsInstance(result, bool)
    
    @patch('subprocess.run')
    def test_run_success(self, mock_run):
        """Test successful plugin execution."""
        # TODO: Implement based on tool's output format
        pass
    
    @patch('subprocess.run')
    def test_run_failure(self, mock_run):
        """Test plugin handles execution failures."""
        # TODO: Implement failure scenarios
        pass
    
    def test_post_process(self):
        """Test post-processing of plugin output."""
        # TODO: Create sample output and test processing
        pass
    
    def test_report_only_mode(self):
        """Test plugin behavior in report-only mode."""
        result = self.plugin.run("https://example.com", self.test_dir, report_only=True)
        self.assertIsInstance(result, dict)
        self.assertIn("disposition", result)


if __name__ == '__main__':
    unittest.main()
'''
        
        with open(test_path, 'w') as f:
            f.write(test_content)
        
        print(f"✓ Created test file: {test_path}")
        return test_path
    
    def generate_checklist(self, info):
        """Generate a checklist of customization tasks."""
        print("\n" + "="*70)
        print("CUSTOMIZATION CHECKLIST")
        print("="*70)
        print("\nPlease review and customize the following sections:\n")
        
        checklist = [
            "[ ] Update is_available() to check for tool installation",
            "[ ] Customize command structure in run() method",
            "[ ] Implement command flags and options for your tool",
            "[ ] Handle tool-specific error conditions",
            "[ ] Implement output parsing in post_process()",
            "[ ] Define issue extraction logic (map to issue_registry.json if applicable)",
            "[ ] Create meaningful executive summary",
            "[ ] Update _generate_summary() with tool-specific logic",
            "[ ] Add tool-specific helper methods as needed",
            "[ ] Write unit tests in test file",
            "[ ] Test plugin with real tool output",
            "[ ] Update plugin documentation in docstrings",
        ]
        
        for item in checklist:
            print(f"  {item}")
        
        if info['based_on'] != 'template':
            print(f"\n⚠ NOTE: Based on '{info['based_on']}' plugin - remove tool-specific logic!")
            print("  Review sections marked with tool name and adapt to your needs.")
        
        print("\n" + "="*70)
    
    def open_in_editor(self, file_path):
        """Attempt to open the file in the user's editor."""
        try:
            # Try VSCode first
            if shutil.which('code'):
                os.system(f'code {file_path}')
                return True
            # Try other common editors
            for editor in ['nano', 'vim', 'vi']:
                if shutil.which(editor):
                    os.system(f'{editor} {file_path}')
                    return True
        except Exception:
            pass
        return False


def main():
    """Main entry point for the plugin creator."""
    parser = argparse.ArgumentParser(
        description='Create new KAST plugins from templates or existing plugins.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Interactive mode (recommended for first-time users)
  %(prog)s --interactive
  
  # Create from template
  %(prog)s --name nmap --display-name "Nmap Port Scanner" --description "Port scanning tool"
  
  # Create based on existing plugin
  %(prog)s --name nikto --based-on whatweb --scan-type active
  
  # Quick create with minimal options
  %(prog)s --name gobuster
        '''
    )
    
    parser.add_argument('--name', help='Tool name (lowercase, underscores allowed)')
    parser.add_argument('--display-name', help='Human-readable display name')
    parser.add_argument('--description', help='Short description of the tool')
    parser.add_argument('--website-url', help='Tool website URL')
    parser.add_argument('--scan-type', choices=['passive', 'active'], default='passive',
                       help='Scan type (default: passive)')
    parser.add_argument('--output-type', choices=['file', 'stdout'], default='file',
                       help='Output type (default: file)')
    parser.add_argument('--priority', type=int, default=50,
                       help='Execution priority (10-90, lower runs first, default: 50)')
    parser.add_argument('--based-on', default='template',
                       help='Base template to use (template or existing plugin name)')
    parser.add_argument('--interactive', '-i', action='store_true',
                       help='Interactive mode - prompt for all options')
    parser.add_argument('--no-test', action='store_true',
                       help='Skip creating test file')
    parser.add_argument('--no-open', action='store_true',
                       help='Do not open file in editor after creation')
    
    args = parser.parse_args()
    
    creator = PluginCreator()
    
    # Interactive mode
    if args.interactive:
        info = creator.get_plugin_info_interactive()
    else:
        # Validate required arguments
        if not args.name:
            parser.error("--name is required (or use --interactive)")
        
        # Validate tool name format
        if not re.match(r'^[a-z0-9_]+$', args.name):
            parser.error("Tool name must contain only lowercase letters, numbers, and underscores")
        
        # Build info dict from arguments
        info = {
            'name': args.name,
            'display_name': args.display_name or args.name.replace('_', ' ').title(),
            'description': args.description or f"{args.name} security scanner",
            'website_url': args.website_url or f"https://example.com/{args.name}",
            'scan_type': args.scan_type,
            'output_type': args.output_type,
            'priority': args.priority,
            'based_on': args.based_on
        }
        
        # Validate based_on
        if info['based_on'] != 'template':
            available = creator.get_available_plugins()
            if info['based_on'] not in available:
                print(f"\n✗ Error: Plugin '{info['based_on']}' not found.")
                print(f"Available plugins: {', '.join(available)}")
                sys.exit(1)
    
    # Create the plugin
    plugin_path = creator.create_plugin(info)
    if not plugin_path:
        sys.exit(1)
    
    # Create test file
    if not args.no_test:
        creator.create_test_file(info['name'])
    
    # Generate checklist
    creator.generate_checklist(info)
    
    # Open in editor
    if not args.no_open:
        print("\nAttempting to open file in editor...")
        if creator.open_in_editor(plugin_path):
            print("✓ File opened in editor")
        else:
            print(f"⚠ Could not auto-open file. Please open manually: {plugin_path}")
    
    print("\n✓ Plugin creation complete!")
    print(f"\nNext steps:")
    print(f"  1. Review and customize: {plugin_path}")
    print(f"  2. Implement tests: {creator.tests_dir / f'test_{info['name']}_plugin.py'}")


if __name__ == '__main__':
    main()
