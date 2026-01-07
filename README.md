# Bluetooth Mesh Broadcast Application

A terminal-based application for Ubuntu 22.04 that enables mesh network broadcasting of messages between up to 5 devices using Bluetooth Low Energy (BLE).

## Features

- **Mesh Networking**: Messages automatically propagate through connected devices
- **Terminal Interface**: Simple, efficient CLI for interaction
- **BLE GATT Server**: Hosts service for device discovery and message exchange
- **Pure Asyncio**: Single event loop, no async/sync mixing
- **Auto-Discovery**: Automatically finds and connects to other app devices

## Requirements

### Hardware
- Ubuntu 22.04 Desktop
- Bluetooth adapter (built-in or USB, BLE 4.0+ supported)
- Minimum 2GB RAM
- 500MB disk space

### Software
- Python 3.10 or higher
- BlueZ 5.x

## Quick Start

1. **One-time setup** (if not already done):
   ```bash
   sudo bash setup_bluetooth.sh
   ```

2. **Start the application**:
   ```bash
   ./start.sh
   ```

That's it! The application will start in your terminal.

## Installation

### 1. System Dependencies

```bash
sudo apt update
sudo apt install bluetooth bluez libbluetooth-dev python3-dev python3-pip python3-venv
```

Or run the setup script:
```bash
sudo bash setup_bluetooth.sh
```

### 2. Project Setup

The startup script (`start.sh`) will automatically:
- Create virtual environment if needed
- Install all dependencies
- Configure Bluetooth

If you prefer manual setup:

```bash
cd bluetooth-mesh-broadcast
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Bluetooth Configuration

The startup script handles this automatically, but if you need to configure manually:

```bash
sudo systemctl start bluetooth
sudo systemctl enable bluetooth
bluetoothctl power on
bluetoothctl discoverable on
```

## Usage

### Quick Start (Recommended)

Simply run the startup script:

```bash
./start.sh
```

### Manual Start

If you prefer to start manually:

```bash
source venv/bin/activate
cd backend
python main_cli.py
```

## Commands

Once the application is running, you can use these commands:

| Command | Description |
|---------|-------------|
| `send <message>` | Broadcast a message to the mesh |
| `list` | Show connected and discovered devices |
| `scan` | Force an immediate device scan |
| `connect <address>` | Connect to a device by address |
| `disconnect <address>` | Disconnect from a device |
| `status` | Show system status |
| `stats` | Show message statistics |
| `clear` | Clear the screen |
| `help` | Show help message |
| `quit` | Exit the application |

### Command Aliases

- `send` / `s`
- `list` / `ls` / `devices`
- `scan` / `discover`
- `connect` / `c`
- `disconnect` / `dc`
- `status` / `st`
- `quit` / `exit` / `q`

## Architecture

```
┌─────────────────────────────────────────┐
│        Terminal Interface (CLI)         │
│   stdin -> CommandParser -> actions     │
│   stdout <- status, messages, logs      │
└──────────────────┬──────────────────────┘
                   │
┌──────────────────▼──────────────────────┐
│           Application Core              │
│   - Initialize components               │
│   - Wire up callbacks                   │
│   - Coordinate message flow             │
└──────────────────┬──────────────────────┘
                   │
     ┌─────────────┼─────────────┐
     │             │             │
┌────▼────┐  ┌─────▼─────┐  ┌────▼────┐
│ Message │  │ Bluetooth │  │  GATT   │
│ Handler │  │  Manager  │  │ Server  │
└─────────┘  └───────────┘  └─────────┘
                   │
         ┌────────▼────────┐
         │  BLE Hardware   │
         └─────────────────┘
```

## Project Structure

```
bluetooth-mesh-broadcast/
├── backend/
│   ├── main_cli.py              # Application entry point
│   ├── config.py                # Configuration settings
│   ├── cli/
│   │   ├── terminal.py          # Terminal UI
│   │   └── commands.py          # Command parser
│   ├── bluetooth/
│   │   ├── manager.py           # BLE connection manager
│   │   ├── discovery.py         # Device discovery
│   │   ├── gatt_server.py       # GATT server (bless)
│   │   ├── connection_pool.py   # Connection management
│   │   └── constants.py         # UUIDs, constants
│   ├── messaging/
│   │   ├── handler.py           # Message handling
│   │   ├── protocol.py          # Message structure
│   │   ├── router.py            # Mesh routing
│   │   └── sanitizer.py         # Input sanitization
│   ├── utils/
│   │   └── logger.py            # Logging utilities
│   └── exceptions/
│       ├── bluetooth_errors.py  # Bluetooth exceptions
│       └── message_errors.py    # Message exceptions
├── tests/
│   └── ...                      # Test files
├── requirements.txt             # Python dependencies
├── start.sh                     # Startup script
├── setup_bluetooth.sh           # Bluetooth setup
└── README.md                    # This file
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

### Environment Variables

```bash
# Bluetooth
export CONNECTION_TIMEOUT=30
export MAX_CONCURRENT_CONNECTIONS=4

# Messages
export MAX_MESSAGE_SIZE=500
export MESSAGE_TTL=3

# Logging
export LOG_LEVEL=INFO
export SHOW_DEBUG=false
```

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

### Device discovery issues

1. Check that GATT server is running (shown in `status` command)
2. Ensure both devices have the same service UUID
3. Try forcing a scan with the `scan` command

## Known Limitations

1. Maximum 5 devices due to Bluetooth connection limits
2. Bluetooth range ~10-30 meters (line of sight)
3. Messages are ephemeral (not persisted)
4. Ubuntu 22.04 only (not cross-platform)

## License

MIT License - See LICENSE file for details.
