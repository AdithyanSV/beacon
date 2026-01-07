# Detailed Logging Setup - Complete Guide

## Overview

The application now has comprehensive logging that shows in both:
1. **Terminal/Console** - All logs printed to stdout
2. **Web Browser** - Real-time log streaming via WebSocket

## Log Levels

The application uses DEBUG level logging by default to show everything:
- **DEBUG**: Detailed diagnostic information
- **INFO**: General informational messages
- **WARNING**: Warning messages
- **ERROR**: Error messages

## What Gets Logged

### Discovery Process
- ✅ Every scan attempt
- ✅ Devices discovered (with address, name, RSSI)
- ✅ App device identification
- ✅ Connection attempts
- ✅ Connection results
- ✅ Service UUID verification

### Bluetooth Operations
- ✅ Adapter initialization
- ✅ Advertising start/stop
- ✅ Connection attempts
- ✅ Connection success/failure
- ✅ Message sending/receiving
- ✅ Service discovery

### Application Lifecycle
- ✅ Component initialization
- ✅ Service startup
- ✅ Error conditions
- ✅ State changes

## Viewing Logs

### In Terminal
All logs are printed to the terminal where you started the application:
```bash
./start.sh
```

You'll see logs like:
```
[INFO] 🔍 Starting BLE scan (timeout: 10.0s)
[INFO] 🆕 NEW DEVICE FOUND: AA:BB:CC:DD:EE:FF | Name: Device-1 | RSSI: -50 | App Device: False
[INFO] 🔌 Attempting to connect to device: AA:BB:CC:DD:EE:FF
[INFO] ✅ Successfully connected to AA:BB:CC:DD:EE:FF
```

### In Web Browser

1. **Open the application**: `http://localhost:5000`
2. **Look for the Logs Panel** at the bottom of the screen
3. **Click the toggle button** (up arrow) to expand the logs panel
4. **Watch logs in real-time** as they stream from the server

The logs panel shows:
- Timestamp
- Log level (DEBUG, INFO, WARNING, ERROR)
- Message
- Source file and line number

## Log Panel Controls

- **Toggle Button**: Expand/collapse the logs panel
- **Clear Button**: Clear all logs from the panel
- **Auto-scroll**: Automatically scrolls to show latest logs

## Understanding the Logs

### Discovery Logs

**Scan Starting**:
```
🔍 Starting BLE scan (timeout: 10.0s)
```
This means discovery is actively scanning for devices.

**Device Found**:
```
🆕 NEW DEVICE FOUND: AA:BB:CC:DD:EE:FF | Name: Device-1 | RSSI: -50 | App Device: False
```
- Address: Bluetooth MAC address
- Name: Device name (if available)
- RSSI: Signal strength (more negative = weaker signal)
- App Device: Whether it's running our app

**Connection Attempt**:
```
🔌 Attempting to connect to device: AA:BB:CC:DD:EE:FF
```
Connection is being attempted.

**Connection Success**:
```
✅ Successfully connected to AA:BB:CC:DD:EE:FF
✅ Service UUID verified for AA:BB:CC:DD:EE:FF - this is an app device
```

**Connection Failure**:
```
⚠️ Device AA:BB:CC:DD:EE:FF connected but doesn't have our service UUID
```
Device connected but may not be running our app.

### Common Issues in Logs

**No devices found**:
```
📡 BLE scan completed - Found 0 device(s) in callback
```
- Devices might not be in range
- Bluetooth might not be enabled
- Devices might not be discoverable

**Connection failures**:
```
Failed to connect to AA:BB:CC:DD:EE:FF: [error message]
```
- Device might be out of range
- Device might not accept connections
- Bluetooth permissions issue

**Discovery not running**:
If you don't see scan messages, discovery might not be started.
Check for:
```
✓ Device discovery started
Discovery scan loop started
```

## Debugging Tips

1. **Check if discovery is running**:
   - Look for "Discovery scan loop started" in logs
   - Look for periodic "Starting BLE scan" messages

2. **Check if devices are being found**:
   - Look for "NEW DEVICE FOUND" messages
   - Check RSSI values (should be -30 to -90 typically)

3. **Check connection attempts**:
   - Look for "Attempting to connect" messages
   - Check for success/failure messages

4. **Check service verification**:
   - Look for "Service UUID verified" messages
   - Check for warnings about missing service UUID

## Changing Log Level

To change log level, set environment variable:
```bash
export LOG_LEVEL=DEBUG  # Most verbose
export LOG_LEVEL=INFO   # Normal
export LOG_LEVEL=WARNING # Only warnings and errors
```

Or edit `backend/config.py`:
```python
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG")
```

## Log Format

Logs include:
- **Timestamp**: When the event occurred
- **Level**: DEBUG, INFO, WARNING, ERROR
- **Logger**: Which component logged it
- **Message**: What happened
- **Source**: File and line number (in browser)

## Next Steps

After reviewing logs:
1. Check if discovery is running
2. Check if devices are being found
3. Check if connections are being attempted
4. Check for any error messages
5. Share relevant log excerpts if issues persist
