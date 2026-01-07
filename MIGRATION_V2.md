# Migration to Version 2.0 - Pure Asyncio Architecture

## Summary of Changes

This document summarizes the major architectural changes made to fix the critical issues identified in the code analysis.

## Problem Summary (Before)

1. **No GATT Server**: The app used `bleak` which is client-only. Devices couldn't accept incoming BLE connections.
2. **Eventlet + Asyncio Conflict**: Mixing eventlet (for Flask-SocketIO) with native asyncio (for bleak) caused race conditions.
3. **Discovery Not Triggering Connections**: Callbacks weren't executing properly due to threading issues.
4. **Duplicate Device Detection**: Same device logged 50+ times per scan due to RSSI update callbacks.
5. **Disconnected Components**: ConnectionPool and BluetoothManager had separate state tracking.

## Solution Summary (After)

### 1. Added BLE GATT Server (`bluetooth/gatt_server.py`)

New module using the `bless` library to host a GATT server:

```python
from bluetooth.gatt_server import BLEGATTServer

server = BLEGATTServer()
await server.start()  # Now hosting SERVICE_UUID
```

This allows other devices to:
- Discover this device via the service UUID
- Connect TO this device
- Write messages to the characteristic
- Subscribe to notifications

### 2. Replaced Flask/Eventlet with Pure Asyncio (`web/async_server.py`)

- Removed Flask, Flask-SocketIO, eventlet
- Added aiohttp + python-socketio (async mode)
- Single event loop for all async operations

**Old dependencies:**
```
Flask==3.0.0
Flask-SocketIO==5.3.6
eventlet==0.34.2
```

**New dependencies:**
```
aiohttp==3.9.1
aiohttp-cors==0.7.0
python-socketio[asyncio]==5.10.0
bless==0.2.5
```

### 3. Single Event Loop Architecture (`main.py`)

All components now run in one asyncio event loop:

```python
async def main():
    app = Application()
    await app.initialize()
    await app.start()  # All components in same loop
```

No more threading between:
- Web server
- BLE discovery
- GATT server
- Message handling

### 4. Fixed Discovery Deduplication (`bluetooth/discovery.py`)

Deduplication now happens IN the scan callback:

```python
async def detection_callback(device, advertisement_data):
    # Skip if already seen in this scan
    if address in self._current_scan_devices:
        return
    self._current_scan_devices.add(address)
    # Only process new devices...
```

Before: "Found 52 devices" (same 4 devices, 52 RSSI updates)
After: "Found 4 unique devices, 2 new"

### 5. Unified Connection Management

BluetoothManager now has integrated connection tracking:
- Single `_connections` dict
- `connection_count` and `available_slots` properties
- No separate ConnectionPool state to sync

## File Changes

### New Files
- `backend/bluetooth/gatt_server.py` - BLE GATT server implementation
- `backend/web/async_server.py` - Async web server with aiohttp
- `tests/test_integration.py` - Comprehensive integration tests
- `MIGRATION_V2.md` - This file

### Modified Files
- `backend/main.py` - Complete rewrite for async architecture
- `backend/config.py` - Updated for aiohttp async mode
- `backend/bluetooth/manager.py` - Simplified, integrated connection tracking
- `backend/bluetooth/discovery.py` - Fixed deduplication in callback
- `backend/bluetooth/__init__.py` - Export new GATT server
- `backend/web/__init__.py` - Export async server functions
- `backend/utils/websocket_log_handler.py` - Async-compatible logging
- `requirements.txt` - New async dependencies
- `start.sh` - Updated for new architecture

### Unchanged Files
- `backend/messaging/*` - Message handling logic unchanged
- `backend/bluetooth/constants.py` - Constants unchanged
- `backend/bluetooth/connection_pool.py` - Still available but not primary
- `frontend/*` - No frontend changes needed

## How to Run

```bash
cd bluetooth-mesh-broadcast
./start.sh
```

Or manually:

```bash
source venv/bin/activate
pip install -r requirements.txt
cd backend
python main.py
```

## Testing

```bash
source venv/bin/activate
pytest tests/ -v
```

All 54 tests pass.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                  Single asyncio Event Loop                   │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ GATT Server  │  │  BLE Client  │  │  WebSocket/HTTP  │   │
│  │   (bless)    │  │   (bleak)    │  │    (aiohttp)     │   │
│  │              │  │              │  │                  │   │
│  │ - Host UUID  │  │ - Scan       │  │ - Serve UI       │   │
│  │ - Accept     │  │ - Connect    │  │ - Socket.IO      │   │
│  │   writes     │  │ - Send data  │  │ - API endpoints  │   │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘   │
│         │                  │                   │             │
│         └──────────────────┼───────────────────┘             │
│                            ▼                                 │
│              ┌─────────────────────────┐                     │
│              │    Message Handler      │                     │
│              │  (routing, dedup, TTL)  │                     │
│              └─────────────────────────┘                     │
└─────────────────────────────────────────────────────────────┘
```

## Next Steps

1. Test with two physical devices running the app
2. Verify GATT server is discoverable (`bluetoothctl scan on`)
3. Test message exchange between devices
4. Performance tuning based on real-world usage
