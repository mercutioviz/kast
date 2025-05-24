# KAST Plugin Development Guide

## Overview

KAST (Kali Automated Scan Tool) is a modular Python-based framework for automating web application security scanning tools. This guide explains how to create new plugins to extend KAST's functionality.

## Plugin Architecture

KAST uses a plugin-based architecture where each security tool is wrapped in a plugin class that inherits from a base plugin class. This allows for consistent interfaces while accommodating the unique features of each tool.

### Directory Structure

/opt/kast/kast/ ├── plugins/ │ ├── init.py │ ├── base.py # Base plugin class │ ├── wafw00f_plugin.py # Example plugin │ └── your_plugin.py # Your new plugin

## Creating a New Plugin

### Step 1: Create a new Python file

Create a new file in the `plugins` directory named after your tool (e.g., `nikto_plugin.py`).

### Step 2: Import the base plugin class

python from .base import BasePlugin

### Step 3: Define your plugin class

python class YourToolPlugin(BasePlugin): def init(self): super().init( name=“your_tool_name”, description=“Description of what your tool does”, binary_name=“binary_command”, # The actual command to run version_flag=“–version” # Flag to check version )

### Step 4: Implement required methods

At minimum, you need to implement these methods:

#### `build_command`

Constructs the command line to execute the tool:

python def build_command(self, target, options=None): cmd = [self.binary_name]

# Add target cmd.extend(["-target", target]) # Add any tool-specific options if options: for key, value in options.items(): if key == "custom_option": cmd.extend(["--option", value]) return cmd

#### `parse_output`

Processes the raw output from the tool:

python def parse_output(self, output, output_format=“json”): # Parse the tool’s output # Return structured data

try: if output_format == "json": return json.loads(output) else: # Custom parsing logic return {"parsed_data": output} except Exception as e: self.error(f"Failed to parse output: {str(e)}") return {"error": str(e), "raw_output": output}

#### `post_process`

Performs additional processing on the parsed output:

I’ll help you create a README.md file for creating plugins for your KAST tool. First, let me examine the existing plugin structure to better understand how plugins work in your system.

Based on the directory structure and the wafw00f_plugin.py code snippet you’ve shared, I can see that KAST uses a plugin architecture with a base class that individual scanner plugins inherit from. Let me create a comprehensive README.md for plugin development.

Before I do that, let me help you with the immediate task of modifying the post_process method to handle the “generic” WAF detection case:

python

Copy Code
def post_process(self, raw_output, output_dir):
    import json
    import os
    from datetime import datetime

    # If raw_output is a file path, load it
    if isinstance(raw_output, str) and os.path.isfile(raw_output):
        with open(raw_output, "r") as f:
            findings = json.load(f)
    elif isinstance(raw_output, dict):
        findings = raw_output
    else:
        # Try to parse string as JSON, fallback to empty dict
        try:
            findings = json.loads(raw_output)
        except Exception:
            findings = {}

    self.debug(f"{self.name} raw findings:\n {pformat(findings)}")
    
    # Process WAF findings - remove "Generic" if multiple WAFs are detected
    if findings and 'results' in findings and isinstance(findings['results'], list):
        waf_results = findings['results']
        if len(waf_results) > 1:
            # Check if any result has "Generic" firewall
            generic_indices = [i for i, result in enumerate(waf_results) 
                              if result.get('firewall') == 'Generic']
            
            # Remove Generic entries if other WAFs are detected
            if generic_indices:
                for index in sorted(generic_indices, reverse=True):
                    self.debug(f"Removing Generic WAF detection at index {index}")
                    findings['results'].pop(index)
    
    #summary = self._generate_summary(findings)  # Implement this as needed
    summary = None

    processed = {
        "plugin-name": self.name,
        "plugin-description": self.description,
        "timestamp": datetime.now().isoformat(),
        "findings": findings if findings else {},
        "summary": summary if summary else f"{self.name} did not produce any findings"
    }

    processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
    with open(processed_path, "w") as f:
        json.dump(processed, f, indent=2)
    return processed_path
Now, let me create a README.md file for plugin development:

markdown

Copy Code
# KAST Plugin Development Guide

## Overview

KAST (Kali Automated Scan Tool) is a modular Python-based framework for automating web application security scanning tools. This guide explains how to create new plugins to extend KAST's functionality.

## Plugin Architecture

KAST uses a plugin-based architecture where each security tool is wrapped in a plugin class that inherits from a base plugin class. This allows for consistent interfaces while accommodating the unique features of each tool.

### Directory Structure
/opt/kast/kast/ ├── plugins/ │ ├── init.py │ ├── base.py # Base plugin class │ ├── wafw00f_plugin.py # Example plugin │ └── your_plugin.py # Your new plugin


Copy Code
## Creating a New Plugin

### Step 1: Create a new Python file

Create a new file in the `plugins` directory named after your tool (e.g., `nikto_plugin.py`).

### Step 2: Import the base plugin class
python from .base import BasePlugin


Copy Code
### Step 3: Define your plugin class
python class YourToolPlugin(BasePlugin): def init(self): super().init( name=“your_tool_name”, description=“Description of what your tool does”, binary_name=“binary_command”, # The actual command to run version_flag=“–version” # Flag to check version )


Copy Code
### Step 4: Implement required methods

At minimum, you need to implement these methods:

#### `build_command`

Constructs the command line to execute the tool:
python def build_command(self, target, options=None): cmd = [self.binary_name]

# Add target cmd.extend(["-target", target]) # Add any tool-specific options if options: for key, value in options.items(): if key == "custom_option": cmd.extend(["--option", value]) return cmd

Copy Code
#### `parse_output`

Processes the raw output from the tool:
python def parse_output(self, output, output_format=“json”): # Parse the tool’s output # Return structured data

try: if output_format == "json": return json.loads(output) else: # Custom parsing logic return {"parsed_data": output} except Exception as e: self.error(f"Failed to parse output: {str(e)}") return {"error": str(e), "raw_output": output}

Copy Code
#### `post_process`

Performs additional processing on the parsed output:
python def post_process(self, raw_output, output_dir): import json import os from datetime import datetime

# Process the findings # Generate summary information # Save processed results processed = { "plugin-name": self.name, "plugin-description": self.description, "timestamp": datetime.now().isoformat(), "findings": processed_findings, "summary": summary } processed_path = os.path.join(output_dir, f"{self.name}_processed.json") with open(processed_path, "w") as f: json.dump(processed, f, indent=2) return processed_path

## Example: WAFw00f Plugin

The WAFw00f plugin demonstrates how to integrate a web application firewall detection tool:

python class Wafw00fPlugin(BasePlugin): def init(self): super().init( name=“wafw00f”, description=“WAF detection tool”, binary_name=“wafw00f”, version_flag=“-v” )

def build_command(self, target, options=None): cmd = [self.binary_name] # Add format option for JSON output cmd.extend(["-o", "json"]) # Add target URL cmd.append(target) return cmd # Other methods...

## Advanced Features

### Debugging

Use the built-in logging methods:

python self.debug(“Detailed information”) self.info(“General information”) self.warning(“Warning message”) self.error(“Error message”)

### Handling Tool-Specific Options

Your plugin can accept custom options through the `options` parameter:

python def build_command(self, target, options=None): cmd = [self.binary_name]

if options and "timeout" in options: cmd.extend(["--timeout", str(options["timeout"])]) # Add more options as needed return cmd

### Data Processing Examples

#### Filtering Results

Example: Filter out false positives
filtered_results = [result for result in results if result.get(“confidence”, 0) > 70]


Copy Code
#### Enhancing Results
python

Example: Add severity ratings
for finding in findings: if “critical” in finding[“description”].lower(): finding[“severity”] = “Critical” elif “high” in finding[“description”].lower(): finding[“severity”] = “High” # etc.

## Testing Your Plugin

1. Place your plugin in the `plugins` directory
2. Import it in `plugins/__init__.py`
3. Run a test scan with your plugin:

bash python -m kast.main --plugin your_plugin --target https://example.com

## Best Practices

1. **Error Handling**: Always handle exceptions gracefully
2. **Documentation**: Add docstrings to your methods
3. **Validation**: Validate inputs before passing to the tool
4. **Resource Management**: Clean up temporary files and processes
5. **Consistent Output**: Follow the established output format

## Contributing

When contributing plugins to KAST:

1. Follow the coding style of existing plugins
2. Include comprehensive documentation
3. Add appropriate error handling
4. Test thoroughly with various inputs
5. Submit a pull request with a clear description of your plugin's functionality


