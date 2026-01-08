# Log Preservation and Dashboard Fix

## Issues Fixed

### 1. Logs Disappearing
**Problem**: Logs were disappearing when the dashboard updated.

**Root Causes**:
- Dashboard was using `\033[J` which clears from cursor to end of screen
- Print methods were using `\r` (carriage return) which overwrites lines
- Dashboard updates were clearing all content below the dashboard area

**Solution**:
- Changed dashboard to only clear its own specific lines, not the entire screen
- Changed all print methods to use newlines (`\n`) instead of carriage returns (`\r`)
- This preserves logs that appear above or below the dashboard area

### 2. Dashboard Clearing Too Much
**Problem**: Dashboard was clearing the entire screen below it, wiping out logs.

**Solution**:
- Dashboard now only clears the exact number of lines it uses
- Uses `\033[K` to clear individual lines instead of `\033[J` to clear to end of screen
- Only clears a limited number of extra lines (25 max) to handle dashboard size changes

### 3. Stderr Filter Too Aggressive
**Problem**: Stderr filter might have been filtering legitimate logs.

**Solution**:
- Made filter more specific - requires BOTH error pattern AND file pattern to match
- Only filters `KeyError: 'Device'` when it's clearly from bleak/dbus-fast
- Preserves all other error output

## Changes Made

### `backend/cli/terminal.py`

1. **Dashboard Update Method**:
   - Changed from clearing entire screen (`\033[J`) to clearing only specific lines
   - Now clears each dashboard line individually
   - Limits clearing to dashboard area only

2. **Print Methods**:
   - Changed from `\r` (overwrite) to `\n` (newline) in:
     - `print_info()`
     - `print_warning()`
     - `print_error()`
     - `print_debug()`
     - `print_success()`
     - `print_message()`
     - `print_device_found()`
     - `print_device_connected()`
     - `print_device_disconnected()`

### `backend/utils/error_suppression.py`

1. **More Specific Filtering**:
   - Now requires both error pattern AND file pattern to match
   - Less likely to filter legitimate errors
   - Only filters `KeyError: 'Device'` when clearly from bleak/dbus-fast

### `backend/main_cli.py`

1. **Better Startup Messages**:
   - Added separator before dashboard starts
   - Clear indication that logs will be preserved

## How It Works Now

1. **Logs Above Dashboard**: 
   - Initialization logs, startup messages appear above dashboard
   - These are preserved and never cleared

2. **Dashboard Area**:
   - Fixed position starting at line 7 (after banner)
   - Only clears its own lines when updating
   - Doesn't affect content above or far below

3. **Logs Below Dashboard**:
   - User messages, device notifications, errors appear below dashboard
   - These accumulate and are preserved
   - Dashboard updates don't clear them

4. **Input Prompt**:
   - Always appears at the bottom
   - Dashboard updates don't interfere with input

## Testing

To verify logs are preserved:

1. **Start the application**:
   ```bash
   ./start.sh
   ```

2. **Check initialization logs**:
   - Should see `[INIT]` and `[OK]` messages above dashboard
   - These should remain visible

3. **Check runtime logs**:
   - Send a message: `send test`
   - Should see message appear below dashboard
   - Dashboard updates should not clear it

4. **Check error logs**:
   - Any errors should appear and remain visible
   - Not filtered unless they're the known non-fatal Device errors

## Known Limitations

1. **Terminal Scrollback**: If terminal has limited scrollback, very old logs may scroll out of view
2. **Very Long Logs**: Extremely long log messages might wrap and look messy
3. **Non-TTY**: Dashboard and log preservation only work in interactive terminals

## Future Improvements

1. Add log buffer to store recent logs
2. Add command to view recent logs (`logs` command)
3. Add option to disable dashboard for log-heavy debugging
4. Add log file output as backup
