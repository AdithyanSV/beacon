"""
Integration Tests for Bluetooth Mesh Broadcast.

These tests verify the complete flow of the application including:
- GATT server hosting
- Device discovery
- Message exchange between devices

Note: These tests require actual Bluetooth hardware and should be run
with two or more devices. For CI/CD, use the mock tests instead.
"""

import pytest
import asyncio
import sys
import os
import time
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from bluetooth.gatt_server import BLEGATTServer, GATTServerConfig
from bluetooth.manager import BluetoothManager
from bluetooth.discovery import DeviceDiscovery
from bluetooth.constants import DeviceInfo, ConnectionState, BluetoothConstants
from messaging.handler import MessageHandler
from messaging.protocol import Message, MessageProtocol


class TestGATTServer:
    """Tests for the BLE GATT Server."""
    
    @pytest.fixture
    def server(self):
        """Create a GATT server instance."""
        return BLEGATTServer()
    
    def test_server_creation(self, server):
        """Test that server can be created."""
        assert server is not None
        assert not server.is_running
        assert server.service_uuid == BluetoothConstants.SERVICE_UUID
        assert server.characteristic_uuid == BluetoothConstants.CHARACTERISTIC_UUID
    
    def test_custom_config(self):
        """Test server with custom configuration."""
        config = GATTServerConfig(
            service_uuid="00001234-0000-1000-8000-00805f9b34fb",
            characteristic_uuid="00005678-0000-1000-8000-00805f9b34fb",
            service_name="TestService"
        )
        server = BLEGATTServer(config)
        assert server.service_uuid == config.service_uuid
        assert server.characteristic_uuid == config.characteristic_uuid
    
    def test_callback_setting(self, server):
        """Test callback can be set."""
        callback = MagicMock()
        server.set_message_received_callback(callback)
        assert server._on_message_received == callback
    
    @pytest.mark.asyncio
    async def test_server_start_stop(self, server):
        """Test server start and stop (requires Bluetooth hardware)."""
        # This test will fail without actual Bluetooth hardware
        # but it tests the interface
        try:
            success = await server.start()
            # If we get here with success, hardware is available
            if success:
                assert server.is_running
                await server.stop()
                assert not server.is_running
        except Exception as e:
            # Expected if no Bluetooth hardware
            pytest.skip(f"Bluetooth hardware not available: {e}")


class TestBluetoothManager:
    """Tests for the Bluetooth Manager."""
    
    @pytest.fixture
    def manager(self):
        """Create a Bluetooth manager instance."""
        return BluetoothManager()
    
    def test_manager_creation(self, manager):
        """Test that manager can be created."""
        assert manager is not None
        assert not manager.is_running
        assert manager._initialized == False
    
    @pytest.mark.asyncio
    async def test_manager_initialization(self, manager):
        """Test manager initialization (requires Bluetooth hardware)."""
        try:
            success = await manager.initialize()
            if success:
                assert manager._initialized
                assert manager.local_address is not None
        except Exception as e:
            pytest.skip(f"Bluetooth hardware not available: {e}")
    
    @pytest.mark.asyncio
    async def test_get_connected_devices_empty(self, manager):
        """Test getting connected devices when none are connected."""
        devices = await manager.get_connected_devices()
        assert devices == []
    
    @pytest.mark.asyncio
    async def test_connection_count(self, manager):
        """Test connection count property."""
        count = await manager.get_connection_count()
        assert count == 0


class TestDeviceDiscovery:
    """Tests for Device Discovery."""
    
    @pytest.fixture
    def discovery(self):
        """Create a discovery instance."""
        return DeviceDiscovery()
    
    def test_discovery_creation(self, discovery):
        """Test that discovery can be created."""
        assert discovery is not None
        assert discovery.state.name == "IDLE"
        assert discovery.network_state.name == "NO_DEVICES"
    
    def test_callback_setting(self, discovery):
        """Test callbacks can be set."""
        device_callback = MagicMock()
        app_callback = MagicMock()
        lost_callback = MagicMock()
        
        discovery.set_device_found_callback(device_callback)
        discovery.set_app_device_found_callback(app_callback)
        discovery.set_device_lost_callback(lost_callback)
        
        assert discovery._on_device_found == device_callback
        assert discovery._on_app_device_found == app_callback
        assert discovery._on_device_lost == lost_callback
    
    @pytest.mark.asyncio
    async def test_get_devices_empty(self, discovery):
        """Test getting devices when none discovered."""
        devices = await discovery.get_all_devices()
        assert devices == []
        
        app_devices = await discovery.get_app_devices()
        assert app_devices == []
    
    @pytest.mark.asyncio
    async def test_clear_cache(self, discovery):
        """Test clearing discovery cache."""
        await discovery.clear_cache()
        devices = await discovery.get_all_devices()
        assert devices == []


class TestMessageHandler:
    """Tests for Message Handler."""
    
    @pytest.fixture
    def handler(self):
        """Create a message handler instance."""
        return MessageHandler(local_device_id="test-device-001")
    
    def test_handler_creation(self, handler):
        """Test that handler can be created."""
        assert handler is not None
        assert handler.local_device_id == "test-device-001"
    
    @pytest.mark.asyncio
    async def test_create_message(self, handler):
        """Test creating a message."""
        message = await handler.create_message(
            content="Hello, World!",
            sender_name="Test User"
        )
        
        assert message is not None
        assert message.content == "Hello, World!"
        assert message.sender_name == "Test User"
        assert message.sender_id == "test-device-001"
    
    @pytest.mark.asyncio
    async def test_get_recent_messages(self, handler):
        """Test getting recent messages."""
        # Create and send a few messages (send_message adds to recent)
        for i in range(5):
            msg = await handler.create_message(
                content=f"Message {i}",
                sender_name="Test"
            )
            # send_message adds to recent messages buffer
            await handler.send_message(msg, [])
        
        # Get recent messages
        messages = await handler.get_recent_messages(10)
        assert len(messages) == 5
    
    @pytest.mark.asyncio
    async def test_clear_messages(self, handler):
        """Test clearing messages."""
        await handler.create_message(content="Test", sender_name="Test")
        await handler.clear_recent_messages()
        
        messages = await handler.get_recent_messages()
        assert len(messages) == 0


class TestEndToEndFlow:
    """
    End-to-end integration tests.
    
    These tests simulate the complete flow of message exchange
    between two "devices" (mocked for testing without hardware).
    """
    
    @pytest.mark.asyncio
    async def test_message_routing_between_handlers(self):
        """Test message routing between two message handlers."""
        # Create two handlers simulating two devices
        handler_a = MessageHandler(local_device_id="device-a")
        handler_b = MessageHandler(local_device_id="device-b")
        
        # Track received messages
        received_by_b = []
        
        async def on_receive(msg):
            received_by_b.append(msg)
        
        handler_b.set_message_received_callback(on_receive)
        
        # Device A creates and sends a message
        message_a = await handler_a.create_message(
            content="Hello from A!",
            sender_name="Device A"
        )
        
        # Simulate message being received by Device B
        message_bytes = message_a.to_bytes()
        msg, forward_to = await handler_b.receive_message(
            message_bytes,
            source_device="device-a",
            connected_devices=[]
        )
        
        # Verify message was received
        assert msg is not None
        assert msg.content == "Hello from A!"
        assert msg.sender_id == "device-a"
        assert len(received_by_b) == 1
    
    @pytest.mark.asyncio
    async def test_message_deduplication(self):
        """Test that duplicate messages are not processed twice."""
        handler = MessageHandler(local_device_id="device-x")
        
        received_count = 0
        
        async def count_received(msg):
            nonlocal received_count
            received_count += 1
        
        handler.set_message_received_callback(count_received)
        
        # Create a message
        protocol = MessageProtocol()
        original = protocol.create_broadcast_message(
            content="Unique message",
            sender_id="other-device"
        )
        
        # Receive it once
        msg1, _ = await handler.receive_message(
            original.to_bytes(),
            source_device="other-device",
            connected_devices=[]
        )
        assert msg1 is not None
        assert received_count == 1
        
        # Try to receive the same message again (duplicate)
        msg2, _ = await handler.receive_message(
            original.to_bytes(),
            source_device="another-device",  # Different source
            connected_devices=[]
        )
        
        # Should be rejected as duplicate
        assert msg2 is None
        assert received_count == 1  # Still 1, not 2
    
    @pytest.mark.asyncio
    async def test_message_ttl_decrements(self):
        """Test that TTL decrements when forwarding."""
        handler = MessageHandler(local_device_id="relay-device")
        
        protocol = MessageProtocol()
        original = protocol.create_broadcast_message(
            content="Forward me",
            sender_id="origin-device"
        )
        original.ttl = 3
        
        # Receive message
        msg, forward_to = await handler.receive_message(
            original.to_bytes(),
            source_device="origin-device",
            connected_devices=["device-a", "device-b"]
        )
        
        assert msg is not None
        
        # Prepare for forwarding
        forward_bytes = await handler.prepare_for_forwarding(msg)
        assert forward_bytes is not None
        
        # Parse forwarded message to check TTL
        forwarded_msg = Message.from_bytes(forward_bytes)
        assert forwarded_msg.ttl == 2  # Decremented from 3 to 2


class TestMessageProtocol:
    """Tests for the message protocol."""
    
    @pytest.fixture
    def protocol(self):
        return MessageProtocol()
    
    def test_create_broadcast_message(self, protocol):
        """Test creating a broadcast message."""
        msg = protocol.create_broadcast_message(
            content="Test content",
            sender_id="test-device",
            sender_name="Test"
        )
        
        assert msg.content == "Test content"
        assert msg.sender_id == "test-device"
        assert msg.sender_name == "Test"
        assert msg.ttl > 0
    
    def test_message_serialization(self, protocol):
        """Test message serialization round-trip."""
        original = protocol.create_broadcast_message(
            content="Serialize me",
            sender_id="device-1"
        )
        
        # Serialize
        json_str = original.to_json()
        assert isinstance(json_str, str)
        
        # Deserialize
        restored = Message.from_json(json_str)
        
        assert restored.content == original.content
        assert restored.sender_id == original.sender_id
        assert restored.message_id == original.message_id
    
    def test_message_bytes_serialization(self, protocol):
        """Test message bytes serialization."""
        original = protocol.create_broadcast_message(
            content="Bytes test",
            sender_id="device-2"
        )
        
        # To bytes
        data = original.to_bytes()
        assert isinstance(data, bytes)
        
        # From bytes
        restored = Message.from_bytes(data)
        
        assert restored.content == original.content
        assert restored.message_id == original.message_id


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
