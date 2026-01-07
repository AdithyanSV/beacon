# Bluetooth Mesh Broadcast Application

A secure, optimized web-based application for Ubuntu 22.04 that enables mesh network broadcasting of messages between up to 5 devices using Bluetooth Low Energy (BLE).

## Features

- **Mesh Networking**: Messages automatically propagate through connected devices
- **Real-time UI**: WebSocket-based interface with instant updates
- **Security First**: Input sanitization, rate limiting, and origin validation
- **Optimized Performance**: Async architecture, LRU caching, adaptive discovery
- **Thread-Safe**: Proper locking mechanisms for concurrent operations

## Requirements

### Hardware
- Ubuntu 22.04 Desktop
- Bluetooth adapter (built-in or USB, BLE 4.0+ supported)
- Minimum 2GB RAM
- 500MB disk space

### Software
- Python 3.10 or higher
- BlueZ 5.x
- Modern web browser (Chrome, Firefox, Edge)

## Installation

### 1. System Dependencies

```bash
sudo apt update
sudo apt install bluetooth bluez libbluetooth-dev python3-dev python3-pip python3-venv
```

### 2. Project Setup

```bash
cd bluetooth-mesh-broadcast
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Bluetooth Configuration

```bash
sudo systemctl start bluetooth
sudo systemctl enable bluetooth
bluetoothctl power on
bluetoothctl discoverable on
```

## Usage

### Starting the Application

```bash
source venv/bin/activate
cd backend
python main.py
```

### Accessing the UI

Open your browser and navigate to:
```
http://localhost:5000
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Application Layer                      │
│  ┌───────────────────────────────────────────────────┐  │
│  │         Web UI (HTML/CSS/JavaScript)              │  │
│  └───────────────┬───────────────────────────────────┘  │
│                  │ WebSocket (with origin validation)    │
│  ┌───────────────▼───────────────────────────────────┐  │
│  │      Flask-SocketIO Server (Rate Limited)          │  │
│  └───────────────┬───────────────────────────────────┘  │
│                  │                                       │
│  ┌───────────────▼───────────────────────────────────┐  │
│  │    Message Handler (Validated & Sanitized)        │  │
│  └───────────────┬───────────────────────────────────┘  │
│                  │                                       │
│  ┌───────────────▼───────────────────────────────────┐  │
│  │    Mesh Router (Thread-Safe, LRU Cache)           │  │
│  └───────────────┬───────────────────────────────────┘  │
│                  │                                       │
│  ┌───────────────▼───────────────────────────────────┐  │
│  │    Bluetooth Manager (Bleak, Async)               │  │
│  └───────────────┬───────────────────────────────────┘  │
└──────────────────┼───────────────────────────────────────┘
                   │
         Bluetooth Hardware
```

## Project Structure

```
bluetooth-mesh-broadcast/
├── backend/
│   ├── main.py                 # Application entry point
│   ├── config.py               # Configuration settings
│   ├── bluetooth/
│   │   ├── manager.py          # Async Bluetooth Manager (Bleak)
│   │   ├── discovery.py        # Smart discovery with adaptive intervals
│   │   ├── connection_pool.py  # Connection pool management
│   │   └── constants.py        # UUIDs, constants
│   ├── messaging/
│   │   ├── handler.py          # Message Handler with validation
│   │   ├── protocol.py         # Message structure & validation
│   │   ├── router.py           # Mesh routing (thread-safe)
│   │   └── sanitizer.py        # Input sanitization
│   ├── web/
│   │   ├── server.py           # Flask + SocketIO setup
│   │   ├── handlers.py         # WebSocket handlers (rate limited)
│   │   └── security.py         # Origin validation, rate limiting
│   ├── utils/
│   │   ├── logger.py           # Structured logging
│   │   ├── resource_monitor.py # Memory/connection monitoring
│   │   └── helpers.py          # Utility functions
│   └── exceptions/
│       ├── bluetooth_errors.py # Bluetooth-specific exceptions
│       └── message_errors.py   # Message handling exceptions
├── frontend/
│   ├── index.html              # Main HTML page
│   ├── css/
│   │   └── style.css           # Styling
│   └── js/
│       ├── app.js              # Main application logic
│       ├── socket-handler.js   # Socket.IO client
│       ├── ui-controller.js    # UI updates
│       └── input-validator.js  # Client-side validation
├── tests/
│   └── ...                     # Test files
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## Configuration

Configuration can be modified via environment variables or directly in `backend/config.py`.

### Key Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `MAX_MESSAGE_SIZE` | 500 bytes | Maximum message size |
| `MAX_CONTENT_LENGTH` | 450 chars | Maximum message content length |
| `MESSAGE_TTL` | 3 | Message hop limit |
| `MAX_CONCURRENT_CONNECTIONS` | 4 | Maximum peer connections |
| `RATE_LIMIT_PER_CONNECTION` | 10/min | Messages per connection per minute |

## Security Features

1. **Input Sanitization**: All user inputs are sanitized to prevent XSS and injection attacks
2. **Rate Limiting**: Prevents message spam at connection, device, and global levels
3. **Origin Validation**: WebSocket connections validated against allowed origins
4. **Thread Safety**: Proper locking for all shared resources
5. **Resource Monitoring**: Automatic alerts for memory and connection limits

## API Reference

### WebSocket Events

#### Client → Server

| Event | Payload | Description |
|-------|---------|-------------|
| `send_message` | `{ content: string }` | Broadcast a message |
| `request_devices` | `{}` | Get connected devices |
| `request_messages` | `{}` | Get recent messages |

#### Server → Client

| Event | Payload | Description |
|-------|---------|-------------|
| `message_received` | Message object | New message received |
| `message_sent` | `{ message_id, success }` | Send confirmation |
| `devices_updated` | `{ devices, count }` | Device list updated |
| `error` | `{ message, code }` | Error notification |

## Troubleshooting

### Bluetooth not available

```bash
# Check Bluetooth status
systemctl status bluetooth

# Restart Bluetooth service
sudo systemctl restart bluetooth

# Check adapter
hciconfig -a
```

### Permission denied

```bash
# Add user to bluetooth group
sudo usermod -a -G bluetooth $USER

# Restart session or run
newgrp bluetooth
```

### Connection issues

1. Ensure devices are within Bluetooth range (~10-30 meters)
2. Check that both devices are running the application
3. Verify Bluetooth is discoverable: `bluetoothctl discoverable on`

## Known Limitations

1. Maximum 5 devices due to Bluetooth connection limits
2. Bluetooth range ~10-30 meters (line of sight)
3. Messages are ephemeral (not persisted)
4. Ubuntu 22.04 only (not cross-platform)

## License

MIT License - See LICENSE file for details.
# beacon
# beacon
