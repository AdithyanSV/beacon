#!/bin/bash
# Bluetooth Setup Script for Mesh Broadcast Application
# Run with: sudo bash setup_bluetooth.sh

echo "=========================================="
echo "Bluetooth Mesh Broadcast - Setup Script"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use: sudo bash setup_bluetooth.sh)"
    exit 1
fi

# Get the actual user (not root)
ACTUAL_USER=${SUDO_USER:-$USER}
echo "Setting up Bluetooth for user: $ACTUAL_USER"
echo ""

# 1. Add user to bluetooth group
echo "Step 1: Adding user to bluetooth group..."
usermod -a -G bluetooth $ACTUAL_USER
echo "✓ User added to bluetooth group"
echo ""

# 2. Ensure bluetooth service is running
echo "Step 2: Ensuring Bluetooth service is running..."
systemctl enable bluetooth
systemctl start bluetooth
echo "✓ Bluetooth service enabled and started"
echo ""

# 3. Configure Bluetooth adapter
echo "Step 3: Configuring Bluetooth adapter..."
bluetoothctl << EOF
power on
discoverable on
pairable on
agent on
default-agent
EOF
echo "✓ Bluetooth adapter configured"
echo ""

# 4. Check adapter status
echo "Step 4: Checking Bluetooth adapter status..."
echo ""
hciconfig -a
echo ""

# 5. Show current configuration
echo "Step 5: Current Bluetooth configuration:"
bluetoothctl show
echo ""

echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "IMPORTANT: You need to either:"
echo "  1. Log out and log back in, OR"
echo "  2. Run 'newgrp bluetooth' in your terminal"
echo ""
echo "Then restart the application:"
echo "  cd /home/$ACTUAL_USER/Desktop/Final\\ Proj/bluetooth-mesh-broadcast"
echo "  source venv/bin/activate"
echo "  cd backend"
echo "  python main.py"
echo ""
echo "Access the UI at: http://localhost:5000"
echo "=========================================="
