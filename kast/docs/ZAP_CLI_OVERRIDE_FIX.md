# ZAP CLI Override Fix

## Issue
ZAP remote mode CLI arguments (`--set zap.execution_mode=remote`) were not being recognized when a non-existent config file was specified with `--config`. The plugin would fall back to auto-discovery mode and attempt to use Docker instead of the remote instance.

## Root Cause
In `ConfigManager.load()`, when a config file path was provided via `--config` but the file didn't exist, the method would log a warning and return `False` immediately, **without parsing CLI overrides**. This meant all `--set` arguments were ignored.

```python
# OLD CODE (BUGGY):
if config_file:
    config_path = Path(config_file).expanduser()
    if config_path.exists():
        # ... load file ...
    else:
        self.logger.warning(f"Config file not found: {config_path}")
        return False  # <-- EARLY RETURN, CLI overrides never parsed!

# Parse CLI overrides (--set arguments)
if self.cli_args and hasattr(self.cli_args, 'set') and self.cli_args.set:
    self._parse_cli_overrides(self.cli_args.set)  # <-- NEVER REACHED
```

## Fix
Modified `ConfigManager.load()` to **always** parse CLI overrides, regardless of whether a config file exists or not. CLI overrides should work standalone.

```python
# NEW CODE (FIXED):
if config_file:
    config_path = Path(config_file).expanduser()
    if config_path.exists():
        # ... load file ...
    else:
        self.logger.warning(f"Config file not found: {config_path}")
        # DON'T return early - still need to parse CLI overrides

# IMPORTANT: Always parse CLI overrides, even if config file not found
# CLI overrides have highest priority and should work standalone
if self.cli_args and hasattr(self.cli_args, 'set') and self.cli_args.set:
    self._parse_cli_overrides(self.cli_args.set)
    self.logger.debug(f"Parsed {len(self.cli_overrides)} plugin CLI override(s)")
```

## Impact
- CLI overrides (`--set`) now work even when:
  - No config file is specified
  - A non-existent config file is specified with `--config`
  - An invalid config file path is provided
- This maintains the documented priority order:
  1. CLI overrides (highest)
  2. CLI arguments
  3. Project config
  4. User config
  5. System config
  6. Plugin defaults (lowest)

## Testing
Run the test script:
```bash
python3 /opt/kast/test_cli_override_fix.py
```

Test with actual ZAP command:
```bash
kast -t example.com -m active \
  --config /tmp/nonexistent.yaml \
  --set zap.execution_mode=remote \
  --set zap.remote.api_url=http://localhost:8080 \
  --set zap.remote.api_key=kast-local \
  --run-only zap -v
```

Expected: ZAP should use remote mode, not attempt to start Docker container.

## Files Modified
- `kast/config_manager.py`: Fixed `load()` method to always parse CLI overrides

## Date
2026-01-10
