# Terminal Issues Fixed

## Issues Found from Terminal Monitoring

### 1. KeyError: 'Device' Still Appearing
**Problem**: The error was still showing in logs:
```
10:43:31 [ERROR] dbus_fast.message_bus: A message handler raised an exception: 'Device'
Traceback (most recent call last):
  ...
KeyError: 'Device'
```

**Root Cause**: The logging filter wasn't catching the `dbus_fast.message_bus` sublogger specifically. The error was being logged at ERROR level by the `dbus_fast.message_bus` logger, which is a child logger of `dbus_fast`.

**Fix**: 
- Added specific filter for `dbus_fast.message_bus` logger
- Enhanced the filter to catch multiple forms of the error message:
  - `"A message handler raised an exception: 'Device'"`
  - `"KeyError: 'Device'"`
  - Any message containing both "Device" and "KeyError"

**File Modified**: `backend/utils/logger.py`

### 2. Dashboard Not Appearing
**Problem**: Dashboard might fail silently without showing errors.

**Root Cause**: 
- Dashboard errors were only logged if `SHOW_DEBUG` was enabled
- Silent failures made it hard to diagnose dashboard issues
- No visibility into why dashboard wasn't updating

**Fix**:
- Added error counting to track consecutive failures
- Log warnings after 5 consecutive failures (to avoid spam)
- Better error messages when stats handler is not set
- Improved exception handling with traceback in debug mode

**File Modified**: `backend/cli/terminal.py`

### 3. Dashboard Callback Errors Causing Spam
**Problem**: Dashboard callback errors were being printed every time, causing spam.

**Fix**:
- Modified `_safe_callback` to suppress errors from dashboard stats callback
- Dashboard loop now handles its own errors with rate limiting

**File Modified**: `backend/cli/terminal.py`

## Changes Made

### `backend/utils/logger.py`

1. **Enhanced Error Filter**:
   ```python
   # Added specific sublogger filters
   logging.getLogger('dbus_fast.message_bus').addFilter(error_filter)
   logging.getLogger('dbus-fast.message_bus').addFilter(error_filter)
   
   # Enhanced filter to catch multiple error message forms
   if ('Device' in message and 'KeyError' in message) or \
      ("A message handler raised an exception: 'Device'" in message) or \
      ("KeyError: 'Device'" in message):
       return False
   ```

### `backend/cli/terminal.py`

1. **Improved Dashboard Error Handling**:
   - Added error counting to prevent spam
   - Logs warnings after multiple consecutive failures
   - Better visibility into dashboard issues
   - Handles missing stats handler gracefully

2. **Enhanced Callback Safety**:
   - Suppresses dashboard callback errors to avoid spam
   - Other callbacks still show errors normally

## Testing

To verify the fixes:

1. **Test Error Suppression**:
   ```bash
   ./start.sh
   ```
   - Should NOT see `KeyError: 'Device'` in logs
   - Other errors should still appear

2. **Test Dashboard**:
   - Dashboard should appear after ~1 second
   - If it fails, you'll see warnings after 5 consecutive failures
   - Check that stats are updating every 2 seconds

3. **Test Error Visibility**:
   - Enable debug mode to see detailed error traces
   - Check that legitimate errors still appear

## Expected Behavior

1. **No KeyError: 'Device' messages** - These are now properly filtered
2. **Dashboard appears** - Should show within 1-2 seconds of startup
3. **Error visibility** - Legitimate errors still appear, filtered errors don't
4. **Dashboard updates** - Updates every 2 seconds without errors

## Debug Mode

To enable detailed error logging for dashboard:
```python
# In config.py or environment
Config.terminal.SHOW_DEBUG = True
```

This will show:
- Detailed tracebacks for dashboard errors
- Debug messages from various components
- More verbose error information
