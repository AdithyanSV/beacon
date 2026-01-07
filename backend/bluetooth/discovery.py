"""
Smart Device Discovery with Adaptive Intervals.

Implements intelligent scanning that adjusts frequency based on:
- Network state (no devices, finding devices, stable network)
- Connection status
- Discovery success rate
"""

import asyncio
from typing import Dict, List, Optional, Callable, Any, Set
from enum import Enum, auto
from dataclasses import dataclass
import time

from bleak import BleakScanner, BleakError
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from config import Config
from exceptions import BluetoothDiscoveryError
from bluetooth.constants import (
    DeviceInfo,
    ConnectionState,
    DiscoveryState,
    BluetoothConstants,
)


class NetworkState(Enum):
    """Current state of the mesh network."""
    NO_DEVICES = auto()      # No devices found
    DISCOVERING = auto()     # Finding new devices
    MODERATE = auto()        # Some devices connected
    STABLE = auto()          # Network is stable


@dataclass
class DiscoveryStats:
    """Statistics for discovery operations."""
    total_scans: int = 0
    successful_scans: int = 0
    devices_found: int = 0
    last_scan_time: float = 0.0
    last_device_found_time: float = 0.0
    consecutive_empty_scans: int = 0


class DeviceDiscovery:
    """
    Smart device discovery with adaptive scanning intervals.
    
    Adjusts scan frequency based on network conditions to optimize
    battery usage and discovery speed.
    """
    
    def __init__(self, bluetooth_manager=None):
        self._manager = bluetooth_manager
        self._state = DiscoveryState.IDLE
        self._network_state = NetworkState.NO_DEVICES
        
        # Device tracking
        self._discovered_devices: Dict[str, DeviceInfo] = {}
        self._app_devices: Set[str] = set()  # Devices running our app
        self._device_lock = asyncio.Lock()
        
        # Statistics
        self._stats = DiscoveryStats()
        
        # Callbacks
        self._on_device_found: Optional[Callable[[DeviceInfo], Any]] = None
        self._on_app_device_found: Optional[Callable[[DeviceInfo], Any]] = None
        self._on_device_lost: Optional[Callable[[DeviceInfo], Any]] = None
        
        # Scanner
        self._scanner: Optional[BleakScanner] = None
        self._scan_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Adaptive interval settings
        self._current_interval = Config.bluetooth.DISCOVERY_INTERVAL_INITIAL
        self._min_interval = 3.0  # Minimum scan interval
        self._max_interval = 60.0  # Maximum scan interval
    
    @property
    def state(self) -> DiscoveryState:
        """Get current discovery state."""
        return self._state
    
    @property
    def network_state(self) -> NetworkState:
        """Get current network state."""
        return self._network_state
    
    @property
    def current_interval(self) -> float:
        """Get current scan interval in seconds."""
        return self._current_interval
    
    @property
    def stats(self) -> DiscoveryStats:
        """Get discovery statistics."""
        return self._stats
    
    async def start(self) -> None:
        """Start the discovery service."""
        if self._running:
            return
        
        self._running = True
        self._state = DiscoveryState.SCANNING
        self._scan_task = asyncio.create_task(self._scan_loop())
    
    async def stop(self) -> None:
        """Stop the discovery service."""
        self._running = False
        self._state = DiscoveryState.STOPPED
        
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
        
        if self._scanner:
            try:
                await self._scanner.stop()
            except Exception:
                pass
    
    async def scan_once(self, timeout: float = None) -> List[DeviceInfo]:
        """
        Perform a single scan operation.
        
        Args:
            timeout: Scan timeout in seconds.
            
        Returns:
            List of discovered devices.
        """
        timeout = timeout or BluetoothConstants.DEFAULT_SCAN_TIMEOUT
        discovered = []
        
        def detection_callback(device: BLEDevice, advertisement_data: AdvertisementData):
            """Handle device detection."""
            # IMPORTANT: Don't filter by service UUID initially - discover ALL devices
            # We'll verify if it's an app device after connection attempt
            is_app_device = self._is_app_device(device, advertisement_data)
            
            device_info = DeviceInfo(
                address=device.address,
                name=device.name or advertisement_data.local_name,
                rssi=advertisement_data.rssi,
                state=ConnectionState.DISCONNECTED,
            )
            device_info.update_seen()
            discovered.append((device_info, is_app_device))
        
        try:
            self._stats.total_scans += 1
            self._stats.last_scan_time = time.time()
            
            from utils.logger import get_logger
            logger = get_logger(__name__)
            logger.debug(f"Starting BLE scan (timeout: {timeout}s)")
            
            scanner = BleakScanner(detection_callback=detection_callback)
            await scanner.start()
            logger.debug("BLE scanner started, waiting for devices...")
            await asyncio.sleep(timeout)
            await scanner.stop()
            logger.debug(f"BLE scan completed, found {len(discovered)} device(s) in callback")
            
            # Process discovered devices
            devices_found = []
            async with self._device_lock:
                for device_info, is_app_device in discovered:
                    address = device_info.address
                    
                    # Check if this is a new device
                    is_new = address not in self._discovered_devices
                    
                    # Update device cache
                    if address in self._discovered_devices:
                        # Update existing device
                        existing = self._discovered_devices[address]
                        existing.rssi = device_info.rssi
                        existing.update_seen()
                        device_info = existing
                    else:
                        self._discovered_devices[address] = device_info
                    
                    # Track app devices
                    if is_app_device:
                        self._app_devices.add(address)
                        if is_new and self._on_app_device_found:
                            await self._safe_callback(self._on_app_device_found, device_info)
                    
                    # Notify general device found
                    if is_new and self._on_device_found:
                        await self._safe_callback(self._on_device_found, device_info)
                    
                    devices_found.append(device_info)
            
            # Update statistics
            if devices_found:
                self._stats.successful_scans += 1
                self._stats.devices_found += len(devices_found)
                self._stats.last_device_found_time = time.time()
                self._stats.consecutive_empty_scans = 0
            else:
                self._stats.consecutive_empty_scans += 1
            
            # Update network state and interval
            await self._update_network_state()
            
            return devices_found
            
        except BleakError as e:
            raise BluetoothDiscoveryError(f"Scan failed: {e}")
        except Exception as e:
            raise BluetoothDiscoveryError(f"Unexpected scan error: {e}")
    
    def _is_app_device(self, device: BLEDevice, advertisement_data: AdvertisementData) -> bool:
        """
        Check if a device is running our app.
        
        Looks for our service UUID in the advertisement data.
        """
        if not advertisement_data.service_uuids:
            return False
        
        # Check if our service UUID is advertised
        target_uuid = BluetoothConstants.SERVICE_UUID.lower()
        for uuid in advertisement_data.service_uuids:
            if uuid.lower() == target_uuid:
                return True
        
        # Also check service data
        if advertisement_data.service_data:
            for uuid in advertisement_data.service_data.keys():
                if uuid.lower() == target_uuid:
                    return True
        
        return False
    
    async def _scan_loop(self) -> None:
        """Main scan loop with adaptive intervals."""
        from utils.logger import get_logger
        logger = get_logger(__name__)
        
        logger.info("Discovery scan loop started")
        scan_count = 0
        
        while self._running:
            try:
                scan_count += 1
                logger.debug(f"Starting scan #{scan_count} (interval: {self._current_interval:.1f}s)")
                
                # Perform scan
                devices = await self.scan_once()
                
                if devices:
                    logger.info(f"Scan #{scan_count}: Found {len(devices)} device(s)")
                    for device in devices:
                        logger.debug(f"  - {device.address} ({device.name or 'Unknown'}, RSSI: {device.rssi})")
                else:
                    logger.debug(f"Scan #{scan_count}: No devices found")
                
                # Check for lost devices
                await self._check_lost_devices()
                
                # Log statistics
                async with self._device_lock:
                    total_devices = len(self._discovered_devices)
                    app_devices = len(self._app_devices)
                    logger.debug(f"Total discovered: {total_devices}, App devices: {app_devices}")
                
                # Wait for next scan
                await asyncio.sleep(self._current_interval)
                
            except asyncio.CancelledError:
                logger.info("Discovery scan loop cancelled")
                break
            except BluetoothDiscoveryError as e:
                logger.warning(f"Discovery error: {e}")
                # Increase interval on errors
                self._current_interval = min(
                    self._current_interval * 1.5,
                    self._max_interval
                )
                await asyncio.sleep(self._current_interval)
            except Exception as e:
                logger.error(f"Unexpected error in scan loop: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                await asyncio.sleep(self._current_interval)
    
    async def _update_network_state(self) -> None:
        """Update network state and adjust scan interval."""
        async with self._device_lock:
            app_device_count = len(self._app_devices)
            connected_count = sum(
                1 for d in self._discovered_devices.values()
                if d.state == ConnectionState.CONNECTED
            )
        
        # Determine network state
        if app_device_count == 0:
            self._network_state = NetworkState.NO_DEVICES
        elif connected_count == 0:
            self._network_state = NetworkState.DISCOVERING
        elif connected_count < Config.bluetooth.MAX_CONCURRENT_CONNECTIONS:
            self._network_state = NetworkState.MODERATE
        else:
            self._network_state = NetworkState.STABLE
        
        # Adjust scan interval based on network state
        if self._network_state == NetworkState.NO_DEVICES:
            # No devices - use balanced interval
            target_interval = Config.bluetooth.DISCOVERY_INTERVAL_NO_DEVICES
        elif self._network_state == NetworkState.DISCOVERING:
            # Finding devices - scan more frequently
            target_interval = Config.bluetooth.DISCOVERY_INTERVAL_INITIAL
        elif self._network_state == NetworkState.MODERATE:
            # Some connections - moderate interval
            target_interval = Config.bluetooth.DISCOVERY_INTERVAL_MODERATE
        else:
            # Stable network - scan less frequently
            target_interval = Config.bluetooth.DISCOVERY_INTERVAL_STABLE
        
        # Adjust based on consecutive empty scans
        if self._stats.consecutive_empty_scans > 5:
            target_interval = min(target_interval * 1.5, self._max_interval)
        elif self._stats.consecutive_empty_scans > 10:
            target_interval = min(target_interval * 2, self._max_interval)
        
        # Smooth transition to new interval
        self._current_interval = (self._current_interval + target_interval) / 2
        self._current_interval = max(self._min_interval, min(self._current_interval, self._max_interval))
    
    async def _check_lost_devices(self) -> None:
        """Check for devices that haven't been seen recently."""
        current_time = time.time()
        lost_threshold = 60.0  # Consider device lost after 60 seconds
        
        lost_devices = []
        
        async with self._device_lock:
            for address, device in list(self._discovered_devices.items()):
                time_since_seen = current_time - device.last_seen
                if time_since_seen > lost_threshold:
                    lost_devices.append(device)
                    del self._discovered_devices[address]
                    self._app_devices.discard(address)
        
        # Notify callbacks
        for device in lost_devices:
            if self._on_device_lost:
                await self._safe_callback(self._on_device_lost, device)
    
    async def get_app_devices(self) -> List[DeviceInfo]:
        """Get list of devices running our app."""
        async with self._device_lock:
            return [
                self._discovered_devices[addr]
                for addr in self._app_devices
                if addr in self._discovered_devices
            ]
    
    async def get_all_devices(self) -> List[DeviceInfo]:
        """Get all discovered devices."""
        async with self._device_lock:
            return list(self._discovered_devices.values())
    
    async def get_device(self, address: str) -> Optional[DeviceInfo]:
        """Get a specific device by address."""
        async with self._device_lock:
            return self._discovered_devices.get(address)
    
    def set_device_found_callback(self, callback: Callable[[DeviceInfo], Any]) -> None:
        """Set callback for when any device is found."""
        self._on_device_found = callback
    
    def set_app_device_found_callback(self, callback: Callable[[DeviceInfo], Any]) -> None:
        """Set callback for when an app device is found."""
        self._on_app_device_found = callback
    
    def set_device_lost_callback(self, callback: Callable[[DeviceInfo], Any]) -> None:
        """Set callback for when a device is lost."""
        self._on_device_lost = callback
    
    async def _safe_callback(self, callback: Callable, *args) -> None:
        """Safely execute a callback."""
        try:
            result = callback(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            pass  # Don't let callback errors crash discovery
    
    def force_scan(self) -> None:
        """Force an immediate scan by resetting interval."""
        self._current_interval = self._min_interval
    
    async def clear_cache(self) -> None:
        """Clear the discovered devices cache."""
        async with self._device_lock:
            self._discovered_devices.clear()
            self._app_devices.clear()
