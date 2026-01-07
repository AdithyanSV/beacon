# Quick Start Guide

## Starting the Application

### Option 1: Using the Startup Script (Recommended)

Simply run:
```bash
./start.sh
```

The script automatically:
- ✅ Checks and creates virtual environment
- ✅ Installs dependencies
- ✅ Configures Bluetooth
- ✅ Starts the application

### Option 2: Manual Start

If you prefer manual control:
```bash
source venv/bin/activate
cd backend
python main.py
```

## First Time Setup

If this is your first time running the application:

1. **Run the Bluetooth setup script** (one-time, requires sudo):
   ```bash
   sudo bash setup_bluetooth.sh
   ```

2. **Start the application**:
   ```bash
   ./start.sh
   ```

3. **Open your browser**:
   ```
   http://localhost:5000
   ```

## Troubleshooting

### Script Permission Error

If you get "Permission denied":
```bash
chmod +x start.sh
./start.sh
```

### Virtual Environment Not Found

The script will create it automatically, but if you need to create it manually:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Bluetooth Permission Error

If you get Bluetooth permission errors:
```bash
sudo usermod -a -G bluetooth $USER
# Then logout and login again, or run:
newgrp bluetooth
```

### Dependencies Not Installed

The script installs them automatically, but to reinstall:
```bash
source venv/bin/activate
pip install -r requirements.txt
```

## Stopping the Application

Press `Ctrl+C` in the terminal where the application is running.

## Running on Multiple Devices

1. Start the application on Device A:
   ```bash
   ./start.sh
   ```

2. Start the application on Device B (on another machine):
   ```bash
   ./start.sh
   ```

3. Both devices should discover each other automatically within 10-30 seconds.

## Files Created

- `start.sh` - Linux/Unix startup script
- `start.bat` - Windows startup script (limited support)
- `setup_bluetooth.sh` - One-time Bluetooth setup (requires sudo)
