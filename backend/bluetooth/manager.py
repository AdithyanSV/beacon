"""
Async Bluetooth Manager using Bleak library.

Handles Bluetooth Low Energy (BLE) operations including:
- Adapter initialization
- Device scanning and discovery
- Connection management
- Data transmission/reception
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
from bluetooth.advertising import BLEAdvertising

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
    
    Thread-safe and designed for concurrent operations using asyncio.
    """
    
    def __init__(self):
        self._initialized = False
        self._running = False
        
        # Connection management
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
        
        # Scanner
        self._scanner: Optional[BleakScanner] = None
        
        # BLE Advertising
        self._advertising: Optional[BLEAdvertising] = None
        
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
        
        Raises:
            BluetoothNotAvailableError: If Bluetooth is not available.
            BluetoothAdapterError: If adapter initialization fails.
        """
        if self._initialized:
            return True
        
        try:
            # Test if Bluetooth is available by attempting a quick scan
            scanner = BleakScanner()
            await asyncio.wait_for(
                scanner.start(),
                timeout=5.0
            )
            await scanner.stop()
            
            # Generate a pseudo-local address (BLE doesn't expose local address easily)
            import uuid
            self._local_address = str(uuid.uuid4())[:17].replace("-", ":")
            
            # Initialize BLE advertising
            self._advertising = BLEAdvertising()
            
            self._initialized = True
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
        
        # Start BLE advertising to make device discoverable
        if self._advertising:
            try:
                await self._advertising.start_advertising()
                logger.info("BLE advertising started - device is now discoverable")
            except Exception as e:
                logger.warning(f"Failed to start BLE advertising: {e}")
                logger.info("Device discovery may be limited - other devices may not find this device")
        
        # Start background tasks
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    async def stop(self) -> None:
        """Stop the Bluetooth manager and cleanup."""
        self._running = False
        
        # Stop BLE advertising
        if self._advertising:
            try:
                await self._advertising.stop_advertising()
            except Exception as e:
                logger.warning(f"Failed to stop BLE advertising: {e}")
        
        # Cancel background tasks
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Stop scanner
        if self._scanner:
            await self._scanner.stop()
        
        # Disconnect all peers
        async with self._connection_lock:
            for address in list(self._connections.keys()):
                await self._disconnect_peer(address)
    
    @property
    def local_address(self) -> Optional[str]:
        """Get the local device address."""
        return self._local_address
    
    @property
    def is_running(self) -> bool:
        """Check if the manager is running."""
        return self._running
    
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
                    return True
            
            # Check connection limit
            active_connections = sum(
                1 for c in self._connections.values()
                if c.device_info.state == ConnectionState.CONNECTED
            )
            if active_connections >= Config.bluetooth.MAX_CONCURRENT_CONNECTIONS:
                return False
            
            # Get or create device info
            device_info = self._discovered_devices.get(address)
            if not device_info:
                device_info = DeviceInfo(address=address)
            
            device_info.state = ConnectionState.CONNECTING
            device_info.connection_attempts += 1
        
        try:
            client = BleakClient(address)
            await asyncio.wait_for(
                client.connect(),
                timeout=Config.bluetooth.CONNECTION_TIMEOUT
            )
            
            if client.is_connected:
                # Verify device has our service UUID (check if it's an app device)
                # Note: We're lenient here - if verification fails, we still allow connection
                # This is because devices might not have the service set up yet
                has_service = await self._verify_service_uuid(client)
                if not has_service:
                    logger.warning(f"Device {address} connected but doesn't have our service UUID. Connection allowed for now.")
                    # Don't disconnect - allow connection and verify later during message exchange
                
                # Subscribe to notifications for receiving messages
                try:
                    await self._setup_notifications(client, address)
                except Exception as e:
                    logger.warning(f"Failed to setup notifications for {address}: {e}")
                    # Continue anyway - we can still send messages
                
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
            async with self._connection_lock:
                device_info.state = ConnectionState.ERROR
                device_info.decrease_health(0.2)
            raise BluetoothTimeoutError(
                f"Connection to {address} timed out",
                device_address=address,
                timeout_seconds=Config.bluetooth.CONNECTION_TIMEOUT
            )
        except BleakError as e:
            async with self._connection_lock:
                device_info.state = ConnectionState.ERROR
                device_info.decrease_health(0.3)
            raise BluetoothConnectionError(
                f"Failed to connect to {address}: {e}",
                device_address=address,
                retry_count=device_info.connection_attempts
            )
    
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
            pass  # Ignore disconnect errors
        
        conn.device_info.state = ConnectionState.DISCONNECTED
        del self._connections[address]
        
        # Notify callback
        if self._on_device_disconnected:
            await self._safe_callback(self._on_device_disconnected, conn.device_info)
        
        return True
    
    async def _handle_disconnect(self, address: str) -> None:
        """Handle unexpected disconnection."""
        async with self._connection_lock:
            if address in self._connections:
                conn = self._connections[address]
                conn.device_info.state = ConnectionState.DISCONNECTED
                conn.device_info.decrease_health(0.2)
                
                # Notify callback
                if self._on_device_disconnected:
                    await self._safe_callback(self._on_device_disconnected, conn.device_info)
                
                del self._connections[address]
    
    # ==================== Data Transmission ====================
    
    async def _verify_service_uuid(self, client: BleakClient) -> bool:
        """
        Verify if a connected device has our service UUID.
        
        Args:
            client: Connected BLE client.
            
        Returns:
            True if device has our service UUID, False otherwise.
        """
        try:
            services = await client.get_services()
            target_uuid = BluetoothConstants.SERVICE_UUID.lower()
            
            for service in services:
                service_uuid_str = str(service.uuid).lower()
                if target_uuid in service_uuid_str:
                    return True
            return False
        except Exception as e:
            logger.warning(f"Error verifying service UUID: {e}")
            # If we can't verify, assume it's OK (for compatibility)
            return True
    
    async def _setup_notifications(self, client: BleakClient, address: str) -> None:
        """
        Set up notification subscription for receiving messages.
        
        Args:
            client: Connected BLE client.
            address: Device address.
        """
        try:
            # Get services to find the characteristic
            services = await client.get_services()
            
            # Find our service and characteristic
            target_char = None
            for service in services:
                service_uuid_str = str(service.uuid).lower()
                if BluetoothConstants.SERVICE_UUID.lower() in service_uuid_str:
                    for char in service.characteristics:
                        char_uuid_str = str(char.uuid).lower()
                        if BluetoothConstants.CHARACTERISTIC_UUID.lower() in char_uuid_str:
                            # Check if characteristic supports notifications
                            if "notify" in char.properties or "indicate" in char.properties:
                                target_char = char
                                break
                    if target_char:
                        break
            
            # If characteristic not found, log warning and return
            if not target_char:
                logger.warning(
                    f"Characteristic {BluetoothConstants.CHARACTERISTIC_UUID} not found "
                    f"or doesn't support notifications on {address}. "
                    f"Message reception may not work."
                )
                return
            
            # Subscribe to notifications
            await client.start_notify(
                target_char.uuid,
                lambda sender, data: asyncio.create_task(
                    self._notification_handler(address, data)
                )
            )
            
            logger.info(f"Successfully subscribed to notifications on {address}")
            
        except BleakError as e:
            # Log but don't fail - some devices might not support notifications
            logger.warning(f"Could not setup notifications for {address}: {e}")
        except Exception as e:
            logger.warning(f"Unexpected error setting up notifications for {address}: {e}")
    
    async def _notification_handler(self, address: str, data: bytes) -> None:
        """
        Handle incoming BLE notification (message received).
        
        Args:
            address: Device address that sent the message.
            data: Raw message data.
        """
        try:
            # Update connection stats
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
                # Try to handle as raw dict if already parsed
                if isinstance(data, dict):
                    message_dict = data
                else:
                    logger.warning(f"Failed to parse message from {address}")
                    return
            
            # Notify callback
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
                return False
            
            conn = self._connections[address]
            if not conn.client or not conn.client.is_connected:
                return False
        
        try:
            # Get services to find the characteristic
            services = await conn.client.get_services()
            
            # Find our service and characteristic
            target_char = None
            for service in services:
                service_uuid_str = str(service.uuid).lower()
                if BluetoothConstants.SERVICE_UUID.lower() in service_uuid_str:
                    for char in service.characteristics:
                        char_uuid_str = str(char.uuid).lower()
                        if BluetoothConstants.CHARACTERISTIC_UUID.lower() in char_uuid_str:
                            # Check if characteristic supports write
                            if "write" in char.properties or "write-without-response" in char.properties:
                                target_char = char
                                break
                    if target_char:
                        break
            
            # If characteristic not found, try UUID directly
            if not target_char:
                char_uuid = BluetoothConstants.CHARACTERISTIC_UUID
                logger.warning(
                    f"Characteristic not found for {address}, trying UUID directly. "
                    f"Message sending may fail."
                )
            else:
                char_uuid = target_char.uuid
            
            # Write to characteristic (use write-without-response if available for speed)
            use_response = False
            if target_char and "write-without-response" in target_char.properties:
                use_response = False
            elif target_char and "write" in target_char.properties:
                use_response = True
            
            await conn.client.write_gatt_char(
                char_uuid,
                data,
                response=use_response
            )
            
            async with self._connection_lock:
                conn.bytes_sent += len(data)
                conn.messages_sent += 1
            
            return True
            
        except BleakError as e:
            async with self._connection_lock:
                if address in self._connections:
                    self._connections[address].device_info.decrease_health(0.1)
            return False
        except Exception as e:
            logger.warning(f"Error sending data to {address}: {e}")
            return False
    
    async def send_message(self, address: str, message: dict) -> bool:
        """
        Send a JSON message to a connected device.
        
        Args:
            address: Target device address.
            message: Message dictionary to send.
            
        Returns:
            True if send successful, False otherwise.
        """
        try:
            data = json.dumps(message).encode("utf-8")
            return await self.send_data(address, data)
        except (json.JSONDecodeError, UnicodeEncodeError):
            return False
    
    async def broadcast_message(self, message: dict, exclude: List[str] = None) -> int:
        """
        Broadcast a message to all connected devices.
        
        Args:
            message: Message dictionary to broadcast.
            exclude: List of addresses to exclude from broadcast.
            
        Returns:
            Number of successful sends.
        """
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
    
    # ==================== Device Discovery ====================
    
    async def scan_for_devices(self, timeout: float = None) -> List[DeviceInfo]:
        """
        Scan for nearby BLE devices.
        
        Args:
            timeout: Scan timeout in seconds.
            
        Returns:
            List of discovered devices.
        """
        timeout = timeout or BluetoothConstants.DEFAULT_SCAN_TIMEOUT
        
        discovered = []
        
        def detection_callback(device: BLEDevice, advertisement_data: AdvertisementData):
            """Callback for device detection."""
            # IMPORTANT: Discover ALL BLE devices, not just those with our service UUID
            # This allows discovery even when devices aren't advertising yet
            # We'll verify service UUID after connection attempt
            
            device_info = DeviceInfo(
                address=device.address,
                name=device.name or advertisement_data.local_name,
                rssi=advertisement_data.rssi,
                state=ConnectionState.DISCONNECTED,
            )
            device_info.update_seen()
            discovered.append(device_info)
        
        try:
            scanner = BleakScanner(detection_callback=detection_callback)
            await scanner.start()
            await asyncio.sleep(timeout)
            await scanner.stop()
            
            # Update discovered devices cache
            async with self._device_lock:
                for device in discovered:
                    self._discovered_devices[device.address] = device
                    
                    # Notify callback
                    if self._on_device_discovered:
                        await self._safe_callback(self._on_device_discovered, device)
            
            return discovered
            
        except BleakError as e:
            raise BluetoothDiscoveryError(f"Scan failed: {e}")
    
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
        """Get list of all known devices (connected and discovered)."""
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
        except Exception:
            pass  # Don't let callback errors crash the manager
    
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
                pass  # Continue heartbeat loop on errors
    
    async def _cleanup_loop(self) -> None:
        """Background task to cleanup stale connections."""
        while self._running:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                current_time = time.time()
                stale_addresses = []
                
                async with self._connection_lock:
                    for address, conn in self._connections.items():
                        # Check for heartbeat timeout
                        if conn.device_info.last_heartbeat > 0:
                            time_since_heartbeat = current_time - conn.device_info.last_heartbeat
                            if time_since_heartbeat > Config.bluetooth.HEARTBEAT_TIMEOUT:
                                stale_addresses.append(address)
                                conn.device_info.decrease_health(0.3)
                        
                        # Check for very low health
                        if conn.device_info.health_score < BluetoothConstants.HEALTH_SCORE_CRITICAL:
                            stale_addresses.append(address)
                
                # Disconnect stale connections
                for address in set(stale_addresses):
                    await self.disconnect_device(address)
                
            except asyncio.CancelledError:
                break
            except Exception:
                pass  # Continue cleanup loop on errors
