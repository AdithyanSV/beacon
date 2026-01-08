# Bluetooth Mesh Broadcast Application - Technical Documentation

## Executive Summary

This is a **Bluetooth Low Energy (BLE) mesh networking application** that enables peer-to-peer message broadcasting between up to 5 devices without requiring internet connectivity or a central server. The application implements a decentralized mesh topology where messages automatically propagate through connected devices using BLE GATT (Generic Attribute Profile) services.

---

## Technology Stack

### Core Technologies

#### **Programming Language**
- **Python 3.10+** - Primary language
- **Asyncio** - Asynchronous I/O framework for concurrent operations
- **Type Hints** - Static typing support for better code quality

#### **Bluetooth Stack**
- **BlueZ 5.x** - Linux Bluetooth protocol stack (system dependency)
- **Bleak 0.21.1** - Python BLE client library (asyncio-native)
- **Bless 0.2.5** - Python BLE GATT server library (peripheral mode)
- **dbus-next 0.2.3** - D-Bus protocol implementation (required by Bless)

#### **Data & Protocol**
- **Pydantic 2.5.2** - Data validation and serialization
- **JSON** - Message format (UTF-8 encoded)
- **TTLCache (cachetools 5.3.2)** - Time-based message deduplication cache

#### **System & Monitoring**
- **psutil 5.9.6** - System resource monitoring (CPU, memory)
- **python-dotenv 1.0.0** - Environment variable management

#### **Testing Framework**
- **pytest 7.4.3** - Testing framework
- **pytest-asyncio 0.23.2** - Async test support
- **pytest-cov 4.1.0** - Code coverage

#### **Platform**
- **Ubuntu 22.04** - Target platform
- **Linux Kernel 6.8+** - Bluetooth subsystem support

---

## Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ Terminal CLI │  │  Web Server  │  │   Config   │       │
│  │  (main_cli)  │  │   (main.py)  │  │            │       │
│  └──────┬───────┘  └──────┬───────┘  └─────┬──────┘       │
└─────────┼─────────────────┼────────────────┼──────────────┘
          │                 │                 │
┌─────────▼─────────────────▼─────────────────▼──────────────┐
│                  Core Application Layer                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   Message    │  │  Bluetooth   │  │   GATT       │    │
│  │   Handler    │  │   Manager    │  │   Server     │    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘    │
│         │                 │                  │             │
│  ┌──────▼─────────────────▼──────────────────▼───────┐    │
│  │         Message Router (Mesh Logic)               │    │
│  │  - Deduplication (TTL Cache)                     │    │
│  │  - TTL-based forwarding                          │    │
│  │  - Loop prevention                               │    │
│  └──────────────────────────────────────────────────┘    │
└───────────────────────────────────────────────────────────┘
          │                 │                  │
┌─────────▼─────────────────▼──────────────────▼──────────────┐
│              Bluetooth Abstraction Layer                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   Discovery  │  │  Connection  │  │  Advertising  │    │
│  │   Service    │  │    Pool      │  │              │    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘    │
└─────────┼─────────────────┼─────────────────┼──────────────┘
          │                 │                  │
┌─────────▼─────────────────▼──────────────────▼──────────────┐
│              BLE Protocol Stack (BlueZ/Bleak/Bless)          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   GATT       │  │   BLE        │  │   D-Bus      │     │
│  │   Client     │  │   Scanner    │  │   Backend    │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
└─────────┼─────────────────┼─────────────────┼───────────────┘
          │                 │                  │
┌─────────▼─────────────────▼──────────────────▼──────────────┐
│                    Linux Bluetooth Hardware                 │
│                    (HCI, L2CAP, ATT/GATT)                    │
└──────────────────────────────────────────────────────────────┘
```

### Design Patterns

1. **Event-Driven Architecture** - Callback-based component communication
2. **Dual-Mode Operation** - Both GATT client (outgoing) and GATT server (incoming)
3. **Connection Pooling** - Centralized connection state management
4. **Message Routing** - Mesh topology with TTL-based forwarding
5. **Rate Limiting** - Multi-level rate limiting (per-connection, per-device, global)

---

## Core Components

### 1. **BluetoothManager** (`bluetooth/manager.py`)

**Purpose**: Manages BLE client connections (outgoing connections to peers)

**Key Responsibilities**:
- Initialize BLE adapter
- Scan for devices advertising the service UUID
- Establish and maintain BLE connections
- Send/receive data via GATT characteristics
- Connection lifecycle management (connect, disconnect, heartbeat)

**Technical Details**:
- Uses **Bleak** library for BLE client operations
- Maintains connection dictionary: `Dict[str, PeerConnection]`
- Implements connection state machine (connecting → connected → disconnected)
- Heartbeat mechanism to detect dead connections
- Thread-safe with `asyncio.Lock()` for concurrent access

**Connection Flow**:
```
1. Discover device (via scanner)
2. Create BleakClient instance
3. Connect to device (with timeout)
4. Discover services/characteristics
5. Subscribe to notifications (if available)
6. Add to connection pool
7. Start heartbeat monitoring
```

### 2. **BLEGATTServer** (`bluetooth/gatt_server.py`)

**Purpose**: Hosts BLE GATT service (incoming connections from peers)

**Key Responsibilities**:
- Advertise custom service UUID (`12345678-1234-5678-1234-56789abcdef0`)
- Accept incoming BLE connections
- Handle read/write requests on characteristics
- Broadcast notifications to connected clients
- Manage client connection lifecycle

**Technical Details**:
- Uses **Bless** library for GATT server functionality
- Implements custom service with characteristic UUID (`12345678-1234-5678-1234-56789abcdef1`)
- Characteristic properties: READ, WRITE, NOTIFY
- D-Bus backend for BlueZ integration
- Thread-safe client tracking

**GATT Service Structure**:
```
Service UUID: 12345678-1234-5678-1234-56789abcdef0
└── Characteristic UUID: 12345678-1234-5678-1234-56789abcdef1
    ├── Properties: READ, WRITE, NOTIFY
    ├── Permissions: READABLE, WRITABLE
    └── Value: Message data (JSON bytes)
```

### 3. **DeviceDiscovery** (`bluetooth/discovery.py`)

**Purpose**: Continuously scan for devices running the application

**Key Responsibilities**:
- Periodic BLE scanning with adaptive intervals
- Filter devices by service UUID
- Track discovered devices (app devices vs. all devices)
- Auto-connect to discovered app devices
- Network state detection (no devices, moderate activity, stable)

**Technical Details**:
- Uses **BleakScanner** for device discovery
- Adaptive scanning intervals:
  - Initial: 5 seconds
  - Moderate: 15 seconds
  - Stable: 30 seconds
  - No devices: 10 seconds
- State machine: `IDLE → SCANNING → PROCESSING → IDLE`
- Network state: `UNKNOWN → DISCOVERING → STABLE → EMPTY`
- Device tracking with RSSI (signal strength)

### 4. **MessageHandler** (`messaging/handler.py`)

**Purpose**: Central coordinator for all message operations

**Key Responsibilities**:
- Create messages from user input
- Validate message content (size, format, sanitization)
- Coordinate with router for forwarding decisions
- Rate limiting enforcement
- Message statistics tracking

**Technical Details**:
- Integrates: `MessageSanitizer`, `MessageProtocol`, `MeshRouter`
- Rate limiting at 3 levels:
  - Per connection: 10 messages/minute
  - Per device: 30 messages/minute
  - Global: 100 messages/minute
- Message validation pipeline:
  ```
  Input → Sanitize → Validate Size → Check Rate Limits → Create Message → Route
  ```

### 5. **MeshRouter** (`messaging/router.py`)

**Purpose**: Implements mesh routing logic with deduplication

**Key Responsibilities**:
- Message deduplication (prevent loops)
- TTL-based forwarding (max 3 hops)
- Determine forwarding targets
- Cache management (LRU + TTL)

**Technical Details**:
- Uses **TTLCache** for message deduplication
  - Cache size: 100 messages
  - TTL: 300 seconds (5 minutes)
- Thread-safe cache wrapper (`ThreadSafeCache`)
- Routing algorithm:
  ```
  1. Check if message already seen (cache lookup)
  2. If duplicate → drop
  3. If TTL expired → drop
  4. Decrement TTL
  5. Determine forwarding targets (all connected except source)
  6. Add to cache
  7. Return forwarding list
  ```

### 6. **ConnectionPool** (`bluetooth/connection_pool.py`)

**Purpose**: Centralized connection state management

**Key Responsibilities**:
- Track active connections
- Enforce connection limits (max 4 concurrent)
- Connection statistics (bytes sent/received, message counts)
- Connection lifecycle events

**Technical Details**:
- Maintains connection metadata:
  - Connection timestamp
  - Bytes/messages sent/received
  - Connection state
- Thread-safe with `asyncio.Lock()`
- Integration point for both `BluetoothManager` and `BLEGATTServer`

### 7. **MessageProtocol** (`messaging/protocol.py`)

**Purpose**: Defines message structure and serialization

**Message Structure**:
```python
{
    "message_id": "uuid-v4",
    "sender_id": "device-mac-address",
    "sender_name": "optional-name",
    "content": "message text",
    "timestamp": 1234567890.123,
    "ttl": 3,
    "type": "MESSAGE" | "HEARTBEAT" | "SYSTEM"
}
```

**Serialization**:
- JSON encoding (UTF-8)
- Max size: 500 bytes
- Max content length: 450 characters

---

## Data Flow

### Message Sending Flow

```
User Input (CLI)
    ↓
TerminalUI.parse_command()
    ↓
Application._handle_send()
    ↓
MessageHandler.create_message()
    ├── MessageSanitizer.sanitize()
    ├── Validate size/rate limits
    └── MessageProtocol.create()
    ↓
MessageHandler.send_message()
    ├── MeshRouter.route_message()
    └── Determine targets (all connected devices)
    ↓
Parallel Send Operations:
    ├── BluetoothManager.send_data() → BLE Client connections
    └── BLEGATTServer.broadcast_message() → GATT server clients
    ↓
ConnectionPool.record_message_sent()
```

### Message Receiving Flow

```
BLE Connection (Client or Server)
    ↓
BluetoothManager._on_characteristic_notification()
    OR
BLEGATTServer._handle_write_request()
    ↓
Application._on_bluetooth_message()
    OR
Application._on_gatt_message_received()
    ↓
MessageHandler.receive_message()
    ├── MessageProtocol.parse()
    ├── MeshRouter.should_forward()
    │   ├── Check cache (deduplication)
    │   ├── Check TTL
    │   └── Determine forwarding targets
    └── Return (message, forward_to)
    ↓
If forward_to is not empty:
    ├── MessageHandler.prepare_for_forwarding()
    │   └── Decrement TTL, update seen_by
    └── Forward to targets:
        ├── BluetoothManager.send_data() → Other BLE clients
        └── BLEGATTServer.send_notification() → Other GATT clients
    ↓
Application._on_message_received()
    ↓
TerminalUI.print_message()
```

### Device Discovery Flow

```
DeviceDiscovery.start()
    ↓
Periodic Scan Loop (adaptive interval)
    ↓
BleakScanner.scan()
    ↓
Filter by Service UUID
    ↓
Application._on_app_device_found()
    ↓
Check ConnectionPool.available_slots
    ↓
If slots available:
    └── BluetoothManager.connect_to_device()
        ├── Create BleakClient
        ├── Connect with timeout
        ├── Discover services
        ├── Subscribe to notifications
        └── Add to ConnectionPool
```

---

## Mesh Networking Protocol

### Topology

- **Decentralized Mesh**: No central coordinator
- **Peer-to-Peer**: Each device can connect to up to 4 others
- **Bidirectional**: Both client and server roles simultaneously
- **Maximum Devices**: 5 (due to BLE connection limits)

### Message Propagation

1. **Origin**: User sends message on Device A
2. **First Hop**: Device A sends to all connected devices (B, C)
3. **Second Hop**: Devices B and C forward to their connected devices (excluding source)
4. **Third Hop**: If TTL > 0, continue forwarding
5. **Termination**: Message stops when TTL reaches 0 or all devices have seen it

### Deduplication Strategy

- **Message ID**: UUID v4 for each message
- **Cache Key**: `message_id + sender_id`
- **TTL Cache**: Messages expire after 5 minutes
- **Seen-By Tracking**: Prevents forwarding back to source

### TTL (Time-To-Live)

- **Default**: 3 hops
- **Decremented**: On each forward
- **Purpose**: Prevent infinite loops in mesh
- **Trade-off**: Limits network diameter but ensures termination

---

## Concurrency Model

### Asyncio Event Loop

- **Single Event Loop**: All operations run in one asyncio event loop
- **No Threading**: Pure async/await (no async/sync mixing)
- **Concurrent Tasks**: Multiple async tasks run concurrently:
  - GATT server
  - Bluetooth manager
  - Device discovery
  - Connection pool monitoring
  - Terminal input handling

### Thread Safety

- **Asyncio Locks**: `asyncio.Lock()` for async code
- **Threading Locks**: `threading.RLock()` for cache operations (TTLCache is thread-safe but wrapper adds safety)
- **No Race Conditions**: All shared state protected by locks

### Background Tasks

```python
# Example background tasks:
- DeviceDiscovery._scan_loop()      # Periodic scanning
- BluetoothManager._heartbeat_loop() # Connection health checks
- ConnectionPool._cleanup_loop()   # Stale connection cleanup
- TerminalUI._input_loop()          # User input handling
```

---

## Security & Reliability

### Input Sanitization

- **Character Filtering**: Only printable ASCII (32-126)
- **Unicode Support**: Optional (configurable)
- **Size Limits**: Max 450 characters, 500 bytes
- **Pattern Blocking**: Configurable block list

### Rate Limiting

- **Multi-Level**: Connection, device, and global limits
- **Sliding Window**: 60-second window
- **Automatic Cleanup**: Old entries removed automatically
- **Error Handling**: Returns retry-after time on limit exceeded

### Error Handling

- **Custom Exceptions**: Domain-specific error types
  - `BluetoothConnectionError`
  - `BluetoothTimeoutError`
  - `MessageValidationError`
  - `MessageRateLimitError`
- **Graceful Degradation**: Continues operation if non-critical components fail
- **Logging**: Comprehensive logging at all levels

### Resource Management

- **Connection Limits**: Max 4 concurrent peer connections
- **Memory Monitoring**: Optional resource monitor (psutil)
- **Cache Limits**: Max 100 messages in deduplication cache
- **Timeout Handling**: All operations have configurable timeouts

---

## Configuration System

### Configuration Classes

1. **BluetoothConfig**: Connection, discovery, heartbeat settings
2. **MessageConfig**: Size limits, TTL, rate limits, cache settings
3. **ResourceConfig**: Memory and connection limits
4. **SecurityConfig**: Rate limiting, sanitization flags
5. **LogConfig**: Logging levels and formats
6. **TerminalConfig**: UI display settings

### Environment Variables

All settings can be overridden via environment variables:
```bash
export MAX_CONCURRENT_CONNECTIONS=4
export MESSAGE_TTL=3
export MAX_MESSAGE_SIZE=500
export LOG_LEVEL=INFO
```

### Validation

- **Config.validate()**: Checks for logical inconsistencies
- **Startup Validation**: Runs before application starts
- **Type Safety**: Pydantic-style validation (planned)

---

## Performance Characteristics

### Latency

- **Connection Time**: ~2-5 seconds (BLE connection establishment)
- **Message Send**: ~50-200ms (depends on BLE stack)
- **Discovery**: 5-30 seconds (adaptive intervals)

### Throughput

- **Message Rate**: Limited by rate limiting (10-100 msg/min)
- **Concurrent Connections**: Max 4 peer connections
- **Network Diameter**: 3 hops (TTL limit)

### Resource Usage

- **Memory**: ~50-100 MB (typical)
- **CPU**: Low (<5% on idle, spikes during scanning)
- **Bluetooth**: Continuous scanning (adaptive intervals)

---

## Limitations & Constraints

### Hardware Limitations

1. **BLE Range**: ~10-30 meters (line of sight)
2. **Connection Limit**: Max 5 devices (BLE specification)
3. **Platform**: Ubuntu 22.04 only (BlueZ dependency)

### Protocol Limitations

1. **Message Size**: 500 bytes max
2. **Network Diameter**: 3 hops (TTL)
3. **No Persistence**: Messages are ephemeral
4. **No Encryption**: Messages sent in plaintext (BLE encryption at transport layer)

### Scalability

- **Not Designed For**: Large-scale networks (>5 devices)
- **Use Case**: Small local mesh networks
- **Alternative**: For larger networks, consider Bluetooth Mesh specification (not implemented)

---

## Testing Strategy

### Test Structure

- **Unit Tests**: Individual component testing
- **Integration Tests**: Component interaction testing
- **Mocking**: BLE operations mocked for testing

### Test Coverage

- Message protocol serialization/deserialization
- Router deduplication logic
- Rate limiting enforcement
- Connection pool management

---

## Future Enhancements

### Potential Improvements

1. **Encryption**: End-to-end message encryption
2. **Bluetooth Mesh**: Implement official Bluetooth Mesh spec
3. **Cross-Platform**: Support Windows/macOS
4. **Persistence**: Message history storage
5. **WebRTC Bridge**: Internet connectivity option
6. **Multi-Protocol**: Support other transport (Wi-Fi Direct, etc.)

---

## Conclusion

This application demonstrates a **sophisticated BLE mesh networking implementation** using modern Python async/await patterns. It successfully combines:

- **Dual-mode BLE operation** (client + server)
- **Mesh routing** with deduplication
- **Adaptive discovery** for efficient scanning
- **Rate limiting** for stability
- **Clean architecture** with separation of concerns

The codebase is well-structured, type-hinted, and follows Python best practices for async programming. It provides a solid foundation for small-scale mesh networking applications.
