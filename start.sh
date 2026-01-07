#!/bin/bash
# Bluetooth Mesh Broadcast Application - Startup Script
# Terminal CLI Edition
# Run with: ./start.sh

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo -e "${CYAN}"
echo "=========================================="
echo "Bluetooth Mesh Broadcast Application"
echo "Terminal CLI Edition"
echo "=========================================="
echo -e "${NC}"

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
else
    # Activate virtual environment
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Check if dependencies need updating
if ! python -c "import bleak" 2>/dev/null; then
    echo -e "${YELLOW}Dependencies not installed or need updating...${NC}"
    pip install --upgrade pip
    pip install -r requirements.txt
    echo -e "${GREEN}✓ Dependencies installed${NC}"
    echo ""
fi

# Check for bless library (GATT server)
if ! python -c "import bless" 2>/dev/null; then
    echo -e "${YELLOW}Installing bless library for GATT server support...${NC}"
    pip install bless
    echo -e "${GREEN}✓ bless installed${NC}"
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
    echo -e "${YELLOW}  Then logout and login again${NC}"
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
echo -e "${CYAN}"
echo "=========================================="
echo "Starting Terminal Application..."
echo "=========================================="
echo -e "${NC}"
echo -e "${GREEN}Type 'help' for available commands${NC}"
echo -e "${GREEN}Press Ctrl+C to stop${NC}"
echo ""

# Run the CLI application
python main_cli.py
