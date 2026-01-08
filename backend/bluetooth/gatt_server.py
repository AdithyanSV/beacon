"""
BLE GATT Server using bless library.

This module provides the BLE peripheral/server functionality that was missing.
It hosts our custom service UUID and characteristic, allowing other devices
to connect to us and exchange messages.
"""

import asyncio
import logging
from typing import Optional, Callable, Any, Dict
from dataclasses import dataclass
import json

from bless import (
    BlessServer,
    BlessGATTCharacteristic,
    GATTCharacteristicProperties,
    GATTAttributePermissions,
)

from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class GATTServerConfig:
    """Configuration for the GATT server."""
    service_uuid: str = Config.bluetooth.SERVICE_UUID
    characteristic_uuid: str = Config.bluetooth.CHARACTERISTIC_UUID
    service_name: str = Config.bluetooth.SERVICE_NAME
    

class BLEGATTServer:
    """
    BLE GATT Server that hosts our mesh broadcast service.
    
    This allows other devices running our app to:
    - Discover us via our service UUID
    - Connect to us
    - Write messages to our characteristic
    - Subscribe to notifications for incoming messages
    """
    
    def __init__(self, config: GATTServerConfig = None):
        self._config = config or GATTServerConfig()
        self._server: Optional[BlessServer] = None
        self._running = False
        
        # Callbacks
        self._on_message_received: Optional[Callable[[str, bytes], Any]] = None
        self._on_client_connected: Optional[Callable[[str], Any]] = None
        self._on_client_disconnected: Optional[Callable[[str], Any]] = None
        
        # Connected clients
        self._connected_clients: Dict[str, Any] = {}
        
        # Message buffer for the characteristic
        self._read_buffer: bytes = b""
        
    @property
    def is_running(self) -> bool:
        """Check if the server is running."""
        return self._running
    
    @property
    def service_uuid(self) -> str:
        """Get the service UUID."""
        return self._config.service_uuid
    
    @property
    def characteristic_uuid(self) -> str:
        """Get the characteristic UUID."""
        return self._config.characteristic_uuid
    
    async def start(self) -> bool:
        """
        Start the GATT server.
        
        Returns:
            True if started successfully, False otherwise.
        """
        if self._running:
            logger.warning("GATT server already running")
            return True
        
        try:
            logger.info(f"Starting GATT server with service UUID: {self._config.service_uuid}")
            
            # Create the server
            self._server = BlessServer(
                name=self._config.service_name,
                loop=asyncio.get_event_loop()
            )
            
            # Set up read/write request handlers
            self._server.read_request_func = self._handle_read_request
            self._server.write_request_func = self._handle_write_request
            
            # Add our service
            await self._server.add_new_service(self._config.service_uuid)
            
            # Add the characteristic for message exchange
            # Properties: Read, Write, WriteWithoutResponse, Notify
            char_flags = (
                GATTCharacteristicProperties.read |
                GATTCharacteristicProperties.write |
                GATTCharacteristicProperties.write_without_response |
                GATTCharacteristicProperties.notify
            )
            
            permissions = (
                GATTAttributePermissions.readable |
                GATTAttributePermissions.writeable
            )
            
            await self._server.add_new_characteristic(
                self._config.service_uuid,
                self._config.characteristic_uuid,
                char_flags,
                None,  # Initial value
                permissions
            )
            
            # Start advertising
            await self._server.start()
            
            self._running = True
            logger.info("✅ GATT server started successfully")
            logger.info(f"   Service UUID: {self._config.service_uuid}")
            logger.info(f"   Characteristic UUID: {self._config.characteristic_uuid}")
            logger.info("   Device is now discoverable and accepting connections")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start GATT server: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False
    
    async def stop(self) -> None:
        """Stop the GATT server."""
        if not self._running:
            return
        
        try:
            if self._server:
                await self._server.stop()
                self._server = None
            
            self._running = False
            self._connected_clients.clear()
            logger.info("GATT server stopped")
            
        except Exception as e:
            logger.error(f"Error stopping GATT server: {e}")
    
    def _handle_read_request(
        self,
        characteristic: BlessGATTCharacteristic,
        **kwargs
    ) -> bytearray:
        """
        Handle read requests from connected clients.
        
        Returns the current read buffer contents.
        """
        logger.debug(f"Read request on characteristic: {characteristic.uuid}")
        return bytearray(self._read_buffer)
    
    def _handle_write_request(
        self,
        characteristic: BlessGATTCharacteristic,
        value: Any,
        **kwargs
    ) -> None:
        """
        Handle write requests from connected clients.
        
        This is how we receive messages from other devices.
        """
        try:
            # Convert to bytes if needed
            if isinstance(value, bytearray):
                data = bytes(value)
            elif isinstance(value, bytes):
                data = value
            else:
                data = bytes(value)
            
            logger.info(f"📨 Received message via GATT write ({len(data)} bytes)")
            logger.debug(f"   Characteristic: {characteristic.uuid}")
            
            # Get client address if available
            client_address = kwargs.get('client_address', 'unknown')
            
            # Notify callback
            if self._on_message_received:
                asyncio.create_task(
                    self._safe_callback(self._on_message_received, client_address, data)
                )
            
        except Exception as e:
            logger.error(f"Error handling write request: {e}")
    
    async def send_notification(self, data: bytes) -> bool:
        """
        Send a notification to all subscribed clients.
        
        Args:
            data: Message data to send.
            
        Returns:
            True if notification was sent, False otherwise.
        """
        if not self._running or not self._server:
            logger.warning("Cannot send notification: server not running")
            return False
        
        try:
            # Get the characteristic
            characteristic = self._server.get_characteristic(self._config.characteristic_uuid)
            if not characteristic:
                logger.warning(f"Characteristic {self._config.characteristic_uuid} not found")
                return False
            
            # Update the characteristic value
            self._server.update_value(
                self._config.service_uuid,
                self._config.characteristic_uuid
            )
            
            # The notification will be sent to all subscribed clients
            # by updating the characteristic value
            await asyncio.sleep(0)  # Yield to allow notification to be sent
            
            logger.debug(f"📤 Sent notification ({len(data)} bytes)")
            return True
            
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            return False
    
    async def broadcast_message(self, message: dict) -> bool:
        """
        Broadcast a message to all connected clients via notification.
        
        Args:
            message: Message dictionary to broadcast.
            
        Returns:
            True if broadcast was sent, False otherwise.
        """
        try:
            data = json.dumps(message).encode('utf-8')
            return await self.send_notification(data)
        except Exception as e:
            logger.error(f"Error broadcasting message: {e}")
            return False
    
    def set_message_received_callback(self, callback: Callable[[str, bytes], Any]) -> None:
        """Set callback for when a message is received via GATT write."""
        self._on_message_received = callback
    
    def set_client_connected_callback(self, callback: Callable[[str], Any]) -> None:
        """Set callback for when a client connects."""
        self._on_client_connected = callback
    
    def set_client_disconnected_callback(self, callback: Callable[[str], Any]) -> None:
        """Set callback for when a client disconnects."""
        self._on_client_disconnected = callback
    
    async def _safe_callback(self, callback: Callable, *args) -> None:
        """Safely execute a callback."""
        try:
            result = callback(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.error(f"Error in callback: {e}")


# Convenience function to create and start a server
async def create_gatt_server(
    on_message_received: Callable[[str, bytes], Any] = None
) -> BLEGATTServer:
    """
    Create and start a GATT server.
    
    Args:
        on_message_received: Callback for received messages.
        
    Returns:
        Started BLEGATTServer instance.
    """
    server = BLEGATTServer()
    
    if on_message_received:
        server.set_message_received_callback(on_message_received)
    
    await server.start()
    return server
