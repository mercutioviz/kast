"""
Helper functions for configuration testing

This module provides utilities to simplify config testing for KAST plugins.
"""
import tempfile
import yaml
import os
import shutil
from pathlib import Path


def create_test_config_file(plugin_configs, global_config=None):
    """
    Create a temporary YAML config file for testing.
    
    Args:
        plugin_configs: Dict like {"plugin_name": {"key": "value"}}
        global_config: Optional dict for global settings
    
    Returns:
        Tuple of (config_path, temp_dir) - caller should clean up temp_dir
    
    Example:
        config_path, temp_dir = create_test_config_file({
            "testssl": {"timeout": 600, "test_ciphers": False}
        })
        # ... use config_path ...
        shutil.rmtree(temp_dir)
    """
    temp_dir = tempfile.mkdtemp()
    config_path = os.path.join(temp_dir, "test_config.yaml")
    
    config_data = {
        "kast": {"config_version": "1.0"},
        "plugins": plugin_configs
    }
    
    if global_config:
        config_data["global"] = global_config
    
    with open(config_path, 'w') as f:
        yaml.dump(config_data, f)
    
    return config_path, temp_dir


def assert_config_values(plugin, expected_values):
    """
    Assert plugin loaded expected config values.
    
    Args:
        plugin: Plugin instance
        expected_values: Dict of {attr_name: expected_value}
    
    Raises:
        AssertionError: If any value doesn't match
    
    Example:
        assert_config_values(plugin, {
            "timeout": 600,
            "test_ciphers": False
        })
    """
    errors = []
    
    for attr, expected in expected_values.items():
        actual = getattr(plugin, attr, None)
        if actual != expected:
            errors.append(f"{attr}: expected {expected}, got {actual}")
    
    if errors:
        raise AssertionError("Config value mismatches:\n  " + "\n  ".join(errors))


def verify_schema_completeness(schema, plugin_name="unknown"):
    """
    Verify a plugin schema has all required fields and follows best practices.
    
    Args:
        schema: Plugin config_schema dict
        plugin_name: Name of plugin (for error messages)
    
    Returns:
        List of error messages (empty if valid)
    
    Example:
        errors = verify_schema_completeness(plugin.config_schema, "testssl")
        if errors:
            print("Schema issues:", errors)
    """
    errors = []
    
    if not isinstance(schema, dict):
        errors.append(f"{plugin_name}: Schema is not a dictionary")
        return errors
    
    # Check top-level required fields
    if schema.get("type") != "object":
        errors.append(f"{plugin_name}: Schema type must be 'object'")
    
    if "title" not in schema:
        errors.append(f"{plugin_name}: Schema missing 'title'")
    
    if "description" not in schema:
        errors.append(f"{plugin_name}: Schema missing 'description'")
    
    if "properties" not in schema:
        errors.append(f"{plugin_name}: Schema missing 'properties'")
        return errors
    
    # Check each property
    properties = schema["properties"]
    if not properties:
        errors.append(f"{plugin_name}: Schema has no properties defined")
    
    for key, prop in properties.items():
        prop_path = f"{plugin_name}.{key}"
        
        # Required fields for each property
        if "default" not in prop:
            errors.append(f"{prop_path}: Missing 'default' value")
        
        if "type" not in prop:
            errors.append(f"{prop_path}: Missing 'type' definition")
        
        if "description" not in prop:
            errors.append(f"{prop_path}: Missing 'description'")
        
        # Type-specific validation
        prop_type = prop.get("type")
        
        if prop_type in ["integer", "number"]:
            # Numeric types should have constraints
            if "minimum" not in prop and "maximum" not in prop:
                errors.append(f"{prop_path}: Numeric type should have min/max constraints")
            
            # Verify default is within constraints
            default = prop.get("default")
            if default is not None:
                minimum = prop.get("minimum")
                maximum = prop.get("maximum")
                
                if minimum is not None and default < minimum:
                    errors.append(f"{prop_path}: Default {default} below minimum {minimum}")
                
                if maximum is not None and default > maximum:
                    errors.append(f"{prop_path}: Default {default} above maximum {maximum}")
        
        elif prop_type == "array":
            # Array types should specify items
            if "items" not in prop:
                errors.append(f"{prop_path}: Array type should define 'items'")
        
        elif isinstance(prop_type, list):
            # Nullable types (e.g., ["integer", "null"])
            if "null" not in prop_type:
                errors.append(f"{prop_path}: Type list should include 'null' for nullable fields")
    
    return errors


def verify_type_match(value, json_schema_type):
    """
    Verify a value matches a JSON Schema type specification.
    
    Args:
        value: The value to check
        json_schema_type: JSON Schema type (string or list of strings)
    
    Returns:
        Tuple of (is_valid, error_message)
    
    Example:
        is_valid, error = verify_type_match(300, "integer")
        assert is_valid
        
        is_valid, error = verify_type_match("test", "integer")
        assert not is_valid
    """
    # Handle list of allowed types (e.g., ["integer", "null"])
    if isinstance(json_schema_type, list):
        for schema_type in json_schema_type:
            is_valid, _ = verify_type_match(value, schema_type)
            if is_valid:
                return True, None
        return False, f"Value {value} doesn't match any of types {json_schema_type}"
    
    # Handle null
    if json_schema_type == "null":
        if value is None:
            return True, None
        return False, f"Expected null, got {type(value).__name__}"
    
    # Type mapping
    type_map = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict
    }
    
    expected_python_type = type_map.get(json_schema_type)
    if expected_python_type is None:
        return False, f"Unknown JSON Schema type: {json_schema_type}"
    
    if isinstance(value, expected_python_type):
        return True, None
    
    return False, f"Expected {json_schema_type}, got {type(value).__name__}"


def extract_cli_command(plugin):
    """
    Extract the CLI command that would be executed by a plugin.
    
    Args:
        plugin: Plugin instance
    
    Returns:
        Command string or None if not available
    
    Example:
        command = extract_cli_command(plugin)
        assert "testssl" in command
        assert "-U" in command
    """
    # Try common attribute names
    if hasattr(plugin, 'command_executed'):
        cmd = plugin.command_executed
        if isinstance(cmd, dict):
            # Some plugins store multiple commands
            return cmd
        return cmd
    
    return None


def count_config_properties(schema):
    """
    Count the number of configuration properties in a schema.
    
    Args:
        schema: Plugin config_schema dict
    
    Returns:
        Integer count of properties
    """
    if not isinstance(schema, dict):
        return 0
    
    properties = schema.get("properties", {})
    return len(properties)


def get_schema_defaults(schema):
    """
    Extract all default values from a schema.
    
    Args:
        schema: Plugin config_schema dict
    
    Returns:
        Dict of {property_name: default_value}
    
    Example:
        defaults = get_schema_defaults(plugin.config_schema)
        assert defaults["timeout"] == 300
    """
    defaults = {}
    
    if not isinstance(schema, dict):
        return defaults
    
    properties = schema.get("properties", {})
    for key, prop in properties.items():
        if "default" in prop:
            defaults[key] = prop["default"]
    
    return defaults


def validate_config_against_schema(config_values, schema):
    """
    Validate configuration values against a schema.
    
    Args:
        config_values: Dict of configuration values to validate
        schema: Plugin config_schema dict
    
    Returns:
        List of validation error messages (empty if valid)
    
    Example:
        errors = validate_config_against_schema(
            {"timeout": 5000},  # Over maximum
            plugin.config_schema
        )
        assert len(errors) > 0
    """
    errors = []
    
    if not isinstance(schema, dict):
        return ["Schema is not a dictionary"]
    
    properties = schema.get("properties", {})
    
    for key, value in config_values.items():
        if key not in properties:
            errors.append(f"Unknown config key: {key}")
            continue
        
        prop = properties[key]
        prop_type = prop.get("type")
        
        # Type validation
        is_valid, error = verify_type_match(value, prop_type)
        if not is_valid:
            errors.append(f"{key}: {error}")
            continue
        
        # Numeric constraint validation
        if prop_type in ["integer", "number"] and value is not None:
            minimum = prop.get("minimum")
            maximum = prop.get("maximum")
            
            if minimum is not None and value < minimum:
                errors.append(f"{key}: Value {value} below minimum {minimum}")
            
            if maximum is not None and value > maximum:
                errors.append(f"{key}: Value {value} above maximum {maximum}")
    
    return errors
