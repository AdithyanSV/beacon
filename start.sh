#!/bin/bash
# Bluetooth Mesh Broadcast Application - Startup Script
# Run with: ./start.sh

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "Bluetooth Mesh Broadcast Application"
echo "=========================================="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Virtual environment not found. Creating it...${NC}"
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
    echo ""
    
    echo "Installing dependencies..."
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    echo -e "${GREEN}✓ Dependencies installed${NC}"
    echo ""
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Check if dependencies are installed
if ! python -c "import flask" 2>/dev/null; then
    echo -e "${YELLOW}Dependencies not installed. Installing...${NC}"
    pip install --upgrade pip
    pip install -r requirements.txt
    echo -e "${GREEN}✓ Dependencies installed${NC}"
    echo ""
fi

# Check Bluetooth service
echo "Checking Bluetooth service..."
if ! systemctl is-active --quiet bluetooth; then
    echo -e "${YELLOW}Bluetooth service is not running. Attempting to start...${NC}"
    if systemctl start bluetooth 2>/dev/null; then
        echo -e "${GREEN}✓ Bluetooth service started${NC}"
    else
        echo -e "${RED}⚠ Could not start Bluetooth service. You may need to run: sudo systemctl start bluetooth${NC}"
    fi
    echo ""
fi

# Check if user is in bluetooth group
if ! groups | grep -q bluetooth; then
    echo -e "${YELLOW}⚠ Warning: You may not be in the bluetooth group.${NC}"
    echo -e "${YELLOW}  If you encounter permission errors, run:${NC}"
    echo -e "${YELLOW}  sudo usermod -a -G bluetooth \$USER${NC}"
    echo -e "${YELLOW}  Then logout and login again, or run: newgrp bluetooth${NC}"
    echo ""
fi

# Try to enable Bluetooth discoverable mode (non-blocking)
echo "Configuring Bluetooth..."
bluetoothctl power on 2>/dev/null || true
bluetoothctl discoverable on 2>/dev/null || true
echo -e "${GREEN}✓ Bluetooth configured${NC}"
echo ""

# Change to backend directory
cd backend

# Start the application
echo "=========================================="
echo "Starting Application..."
echo "=========================================="
echo ""
echo -e "${GREEN}Application will be available at: http://localhost:5000${NC}"
echo -e "${GREEN}Press Ctrl+C to stop${NC}"
echo ""

# Run the application
python main.py
