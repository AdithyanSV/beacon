"""
Async Bluetooth Manager using Bleak library.

Handles Bluetooth Low Energy (BLE) operations including:
- Adapter initialization
- Device scanning and discovery
- Connection management
- Data transmission/reception

Integrated with ConnectionPool for unified connection state management.
"""

import asyncio
import json
from typing import Dict, Optional, Callable, Any, List
from dataclasses import dataclass
import time

from bleak import BleakClient, BleakScanner, BleakError
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from config import Config
from utils.logger import get_logger
from exceptions import (
    BluetoothConnectionError,
    BluetoothDiscoveryError,
    BluetoothTimeoutError,
    BluetoothAdapterError,
    BluetoothNotAvailableError,
)
from bluetooth.constants import (
    ConnectionState,
    DeviceInfo,
    BluetoothConstants,
    MessageType,
)

logger = get_logger(__name__)


@dataclass
class PeerConnection:
    """Represents a connection to a peer device."""
    device_info: DeviceInfo
    client: Optional[BleakClient] = None
    connected_at: float = 0.0
    bytes_sent: int = 0
    bytes_received: int = 0
    messages_sent: int = 0
    messages_received: int = 0


class BluetoothManager:
    """
    Async Bluetooth Manager for BLE mesh networking.
    
    Uses a single internal connection tracking system.
    Thread-safe and designed for concurrent operations using asyncio.
    """
    
    def __init__(self):
        self._initialized = False
        self._running = False
        
        # Single source of truth for connections
        self._connections: Dict[str, PeerConnection] = {}
        self._connection_lock = asyncio.Lock()
        
        # Device tracking
        self._discovered_devices: Dict[str, DeviceInfo] = {}
        self._device_lock = asyncio.Lock()
        
        # Callbacks
        self._on_message_received: Optional[Callable[[str, dict], Any]] = None
        self._on_device_connected: Optional[Callable[[DeviceInfo], Any]] = None
        self._on_device_disconnected: Optional[Callable[[DeviceInfo], Any]] = None
        self._on_device_discovered: Optional[Callable[[DeviceInfo], Any]] = None
        
        # Background tasks
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # Local device info
        self._local_address: Optional[str] = None
    
    async def initialize(self) -> bool:
        """
        Initialize the Bluetooth adapter.
        
        Returns:
            True if initialization successful, False otherwise.
        """
        if self._initialized:
            return True
        
        try:
            # Test if Bluetooth is available
            scanner = BleakScanner()
            await asyncio.wait_for(scanner.start(), timeout=5.0)
            await scanner.stop()
            
            # Generate a pseudo-local address
            import uuid
            self._local_address = str(uuid.uuid4())[:17].replace("-", ":")
            
            self._initialized = True
            logger.info(f"Bluetooth manager initialized (local: {self._local_address})")
            return True
            
        except asyncio.TimeoutError:
            raise BluetoothAdapterError("Bluetooth adapter initialization timed out")
        except BleakError as e:
            raise BluetoothNotAvailableError(f"Bluetooth not available: {e}")
        except Exception as e:
            raise BluetoothAdapterError(f"Failed to initialize Bluetooth: {e}")
    
    async def start(self) -> None:
        """Start the Bluetooth manager and background tasks."""
        if not self._initialized:
            await self.initialize()
        
        if self._running:
            return
        
        self._running = True
        
        # Start background tasks
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info("Bluetooth manager started")
    
    async def stop(self) -> None:
        """Stop the Bluetooth manager and cleanup."""
        self._running = False
        
        # Cancel background tasks
        for task in [self._heartbeat_task, self._cleanup_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Disconnect all peers
        async with self._connection_lock:
            for address in list(self._connections.keys()):
                await self._disconnect_peer(address)
        
        logger.info("Bluetooth manager stopped")
    
    @property
    def local_address(self) -> Optional[str]:
        """Get the local device address."""
        return self._local_address
    
    @property
    def is_running(self) -> bool:
        """Check if the manager is running."""
        return self._running
    
    @property
    def connection_count(self) -> int:
        """Get the number of active connections."""
        return len([c for c in self._connections.values() 
                   if c.device_info.state == ConnectionState.CONNECTED])
    
    @property
    def available_slots(self) -> int:
        """Get number of available connection slots."""
        return max(0, Config.bluetooth.MAX_CONCURRENT_CONNECTIONS - self.connection_count)
    
    # ==================== Connection Management ====================
    
    async def connect_to_device(self, address: str) -> bool:
        """
        Connect to a BLE device.
        
        Args:
            address: Device address to connect to.
            
        Returns:
            True if connection successful, False otherwise.
        """
        async with self._connection_lock:
            # Check if already connected
            if address in self._connections:
                conn = self._connections[address]
                if conn.device_info.state == ConnectionState.CONNECTED:
                    logger.debug(f"Already connected to {address}")
                    return True
            
            # Check connection limit
            if self.connection_count >= Config.bluetooth.MAX_CONCURRENT_CONNECTIONS:
                logger.warning(f"Connection limit reached, cannot connect to {address}")
                return False
            
            # Get or create device info
            device_info = self._discovered_devices.get(address)
            if not device_info:
                device_info = DeviceInfo(address=address)
            
            device_info.state = ConnectionState.CONNECTING
            device_info.connection_attempts += 1
        
        try:
            logger.info(f"🔌 Connecting to {address}...")
            
            client = BleakClient(address)
            await asyncio.wait_for(
                client.connect(),
                timeout=Config.bluetooth.CONNECTION_TIMEOUT
            )
            
            if client.is_connected:
                logger.info(f"✅ Connected to {address}")
                
                # Verify service UUID
                has_service = await self._verify_service_uuid(client)
                if not has_service:
                    logger.warning(f"⚠️ Device {address} doesn't have our service UUID")
                
                # Set up notifications
                try:
                    await self._setup_notifications(client, address)
                except Exception as e:
                    logger.warning(f"Failed to setup notifications for {address}: {e}")
                
                async with self._connection_lock:
                    device_info.state = ConnectionState.CONNECTED
                    device_info.update_heartbeat()
                    
                    self._connections[address] = PeerConnection(
                        device_info=device_info,
                        client=client,
                        connected_at=time.time(),
                    )
                
                # Set up disconnect callback
                client.set_disconnected_callback(
                    lambda c: asyncio.create_task(self._handle_disconnect(address))
                )
                
                # Notify callback
                if self._on_device_connected:
                    await self._safe_callback(self._on_device_connected, device_info)
                
                return True
            else:
                async with self._connection_lock:
                    device_info.state = ConnectionState.DISCONNECTED
                return False
                
        except asyncio.TimeoutError:
            logger.warning(f"Connection to {address} timed out")
            async with self._connection_lock:
                device_info.state = ConnectionState.ERROR
                device_info.decrease_health(0.2)
            return False
        except BleakError as e:
            logger.warning(f"Connection to {address} failed: {e}")
            async with self._connection_lock:
                device_info.state = ConnectionState.ERROR
                device_info.decrease_health(0.3)
            return False
        except Exception as e:
            logger.error(f"Unexpected error connecting to {address}: {e}")
            async with self._connection_lock:
                device_info.state = ConnectionState.ERROR
            return False
    
    async def disconnect_device(self, address: str) -> bool:
        """
        Disconnect from a device.
        
        Args:
            address: Device address to disconnect from.
            
        Returns:
            True if disconnection successful, False otherwise.
        """
        async with self._connection_lock:
            return await self._disconnect_peer(address)
    
    async def _disconnect_peer(self, address: str) -> bool:
        """Internal method to disconnect a peer (must hold lock)."""
        if address not in self._connections:
            return False
        
        conn = self._connections[address]
        conn.device_info.state = ConnectionState.DISCONNECTING
        
        try:
            if conn.client and conn.client.is_connected:
                await conn.client.disconnect()
        except Exception:
            pass
        
        conn.device_info.state = ConnectionState.DISCONNECTED
        del self._connections[address]
        
        # Notify callback
        if self._on_device_disconnected:
            await self._safe_callback(self._on_device_disconnected, conn.device_info)
        
        logger.info(f"Disconnected from {address}")
        return True
    
    async def _handle_disconnect(self, address: str) -> None:
        """Handle unexpected disconnection."""
        async with self._connection_lock:
            if address in self._connections:
                conn = self._connections[address]
                conn.device_info.state = ConnectionState.DISCONNECTED
                conn.device_info.decrease_health(0.2)
                
                if self._on_device_disconnected:
                    await self._safe_callback(self._on_device_disconnected, conn.device_info)
                
                del self._connections[address]
        
        logger.info(f"Device {address} disconnected unexpectedly")
    
    # ==================== Data Transmission ====================
    
    async def _verify_service_uuid(self, client: BleakClient) -> bool:
        """Verify if a connected device has our service UUID."""
        try:
            services = await client.get_services()
            target_uuid = BluetoothConstants.SERVICE_UUID.lower()
            
            for service in services:
                if target_uuid in str(service.uuid).lower():
                    return True
            return False
        except Exception as e:
            logger.warning(f"Error verifying service UUID: {e}")
            return True  # Assume OK if we can't verify
    
    async def _setup_notifications(self, client: BleakClient, address: str) -> None:
        """Set up notification subscription for receiving messages."""
        try:
            services = await client.get_services()
            target_char = None
            
            for service in services:
                if BluetoothConstants.SERVICE_UUID.lower() in str(service.uuid).lower():
                    for char in service.characteristics:
                        if BluetoothConstants.CHARACTERISTIC_UUID.lower() in str(char.uuid).lower():
                            if "notify" in char.properties or "indicate" in char.properties:
                                target_char = char
                                break
                    if target_char:
                        break
            
            if not target_char:
                logger.debug(f"No notification characteristic found on {address}")
                return
            
            await client.start_notify(
                target_char.uuid,
                lambda sender, data: asyncio.create_task(
                    self._notification_handler(address, data)
                )
            )
            
            logger.info(f"Subscribed to notifications on {address}")
            
        except Exception as e:
            logger.warning(f"Could not setup notifications for {address}: {e}")
    
    async def _notification_handler(self, address: str, data: bytes) -> None:
        """Handle incoming BLE notification."""
        try:
            async with self._connection_lock:
                if address in self._connections:
                    conn = self._connections[address]
                    conn.bytes_received += len(data)
                    conn.messages_received += 1
                    conn.device_info.update_heartbeat()
            
            # Parse message
            try:
                message_dict = json.loads(data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                if isinstance(data, dict):
                    message_dict = data
                else:
                    logger.warning(f"Failed to parse message from {address}")
                    return
            
            if self._on_message_received:
                await self._safe_callback(self._on_message_received, address, message_dict)
                
        except Exception as e:
            logger.error(f"Error handling notification from {address}: {e}")
    
    async def send_data(self, address: str, data: bytes) -> bool:
        """
        Send data to a connected device.
        
        Args:
            address: Target device address.
            data: Raw bytes to send.
            
        Returns:
            True if send successful, False otherwise.
        """
        async with self._connection_lock:
            if address not in self._connections:
                logger.warning(f"Cannot send to {address}: not connected")
                return False
            
            conn = self._connections[address]
            if not conn.client or not conn.client.is_connected:
                logger.warning(f"Cannot send to {address}: client not connected")
                return False
        
        try:
            services = await conn.client.get_services()
            target_char = None
            
            for service in services:
                if BluetoothConstants.SERVICE_UUID.lower() in str(service.uuid).lower():
                    for char in service.characteristics:
                        if BluetoothConstants.CHARACTERISTIC_UUID.lower() in str(char.uuid).lower():
                            if "write" in char.properties or "write-without-response" in char.properties:
                                target_char = char
                                break
                    if target_char:
                        break
            
            if not target_char:
                logger.warning(f"No write characteristic found on {address}")
                return False
            
            use_response = "write-without-response" not in target_char.properties
            
            await conn.client.write_gatt_char(
                target_char.uuid,
                data,
                response=use_response
            )
            
            async with self._connection_lock:
                conn.bytes_sent += len(data)
                conn.messages_sent += 1
            
            logger.debug(f"Sent {len(data)} bytes to {address}")
            return True
            
        except Exception as e:
            logger.warning(f"Error sending data to {address}: {e}")
            async with self._connection_lock:
                if address in self._connections:
                    self._connections[address].device_info.decrease_health(0.1)
            return False
    
    async def send_message(self, address: str, message: dict) -> bool:
        """Send a JSON message to a connected device."""
        try:
            data = json.dumps(message).encode("utf-8")
            return await self.send_data(address, data)
        except Exception:
            return False
    
    async def broadcast_message(self, message: dict, exclude: List[str] = None) -> int:
        """Broadcast a message to all connected devices."""
        exclude = exclude or []
        success_count = 0
        
        async with self._connection_lock:
            addresses = [
                addr for addr, conn in self._connections.items()
                if conn.device_info.state == ConnectionState.CONNECTED
                and addr not in exclude
            ]
        
        for address in addresses:
            if await self.send_message(address, message):
                success_count += 1
        
        return success_count
    
    # ==================== Status & Info ====================
    
    async def get_connected_devices(self) -> List[DeviceInfo]:
        """Get list of currently connected devices."""
        async with self._connection_lock:
            return [
                conn.device_info
                for conn in self._connections.values()
                if conn.device_info.state == ConnectionState.CONNECTED
            ]
    
    async def get_all_devices(self) -> List[DeviceInfo]:
        """Get list of all known devices."""
        async with self._device_lock:
            return list(self._discovered_devices.values())
    
    async def get_connection_count(self) -> int:
        """Get number of active connections."""
        async with self._connection_lock:
            return sum(
                1 for conn in self._connections.values()
                if conn.device_info.state == ConnectionState.CONNECTED
            )
    
    async def get_connection_stats(self, address: str) -> Optional[dict]:
        """Get connection statistics for a device."""
        async with self._connection_lock:
            if address not in self._connections:
                return None
            
            conn = self._connections[address]
            return {
                "address": address,
                "connected_at": conn.connected_at,
                "bytes_sent": conn.bytes_sent,
                "bytes_received": conn.bytes_received,
                "messages_sent": conn.messages_sent,
                "messages_received": conn.messages_received,
                "health_score": conn.device_info.health_score,
            }
    
    # ==================== Callbacks ====================
    
    def set_message_callback(self, callback: Callable[[str, dict], Any]) -> None:
        """Set callback for received messages."""
        self._on_message_received = callback
    
    def set_device_connected_callback(self, callback: Callable[[DeviceInfo], Any]) -> None:
        """Set callback for device connection."""
        self._on_device_connected = callback
    
    def set_device_disconnected_callback(self, callback: Callable[[DeviceInfo], Any]) -> None:
        """Set callback for device disconnection."""
        self._on_device_disconnected = callback
    
    def set_device_discovered_callback(self, callback: Callable[[DeviceInfo], Any]) -> None:
        """Set callback for device discovery."""
        self._on_device_discovered = callback
    
    async def _safe_callback(self, callback: Callable, *args) -> None:
        """Safely execute a callback."""
        try:
            result = callback(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.error(f"Error in callback: {e}")
    
    # ==================== Background Tasks ====================
    
    async def _heartbeat_loop(self) -> None:
        """Background task to send heartbeats."""
        while self._running:
            try:
                await asyncio.sleep(Config.bluetooth.HEARTBEAT_INTERVAL)
                
                heartbeat_message = {
                    "type": MessageType.HEARTBEAT.value,
                    "timestamp": time.time(),
                    "sender_id": self._local_address,
                }
                
                await self.broadcast_message(heartbeat_message)
                
            except asyncio.CancelledError:
                break
            except Exception:
                pass
    
    async def _cleanup_loop(self) -> None:
        """Background task to cleanup stale connections."""
        while self._running:
            try:
                await asyncio.sleep(30)
                
                current_time = time.time()
                stale_addresses = []
                
                async with self._connection_lock:
                    for address, conn in self._connections.items():
                        if conn.device_info.last_heartbeat > 0:
                            time_since_heartbeat = current_time - conn.device_info.last_heartbeat
                            if time_since_heartbeat > Config.bluetooth.HEARTBEAT_TIMEOUT:
                                stale_addresses.append(address)
                                conn.device_info.decrease_health(0.3)
                        
                        if conn.device_info.health_score < BluetoothConstants.HEALTH_SCORE_CRITICAL:
                            stale_addresses.append(address)
                
                for address in set(stale_addresses):
                    logger.info(f"Removing stale connection: {address}")
                    await self.disconnect_device(address)
                
            except asyncio.CancelledError:
                break
            except Exception:
                pass
