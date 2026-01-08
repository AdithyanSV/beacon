"""
Smart Device Discovery with Adaptive Intervals.

Implements intelligent scanning that adjusts frequency based on:
- Network state (no devices, finding devices, stable network)
- Connection status
- Discovery success rate

Fixed: Deduplication now happens in the callback to avoid duplicate processing.
"""

import asyncio
import warnings
import logging
import sys
from typing import Dict, List, Optional, Callable, Any, Set
from enum import Enum, auto
from dataclasses import dataclass
from io import StringIO
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
from utils.logger import get_logger

logger = get_logger(__name__)

# Suppress known non-fatal errors from bleak/BlueZ D-Bus backend
# This KeyError happens when BlueZ sends D-Bus messages without expected keys
# It's a known issue and doesn't affect functionality
_bleak_logger = logging.getLogger('bleak')
_bleak_logger.setLevel(logging.ERROR)  # Only show errors, not warnings

# Also suppress dbus-fast internal errors
_dbus_logger = logging.getLogger('dbus_fast')
_dbus_logger.setLevel(logging.ERROR)
_dbus_logger = logging.getLogger('dbus-fast')
_dbus_logger.setLevel(logging.ERROR)


class StderrFilter:
    """Context manager to filter known non-fatal errors from stderr."""
    
    def __init__(self):
        self.original_stderr = sys.stderr
        self.buffer = StringIO()
        self.filtered_patterns = [
            "KeyError: 'Device'",
            "A message handler raised an exception: 'Device'",
        ]
    
    def __enter__(self):
        sys.stderr = self
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stderr = self.original_stderr
        # Only print if it's not a filtered error
        content = self.buffer.getvalue()
        if content:
            should_filter = any(pattern in content for pattern in self.filtered_patterns)
            if not should_filter:
                self.original_stderr.write(content)
        return False
    
    def write(self, text):
        """Write to buffer, filtering known errors."""
        # Check if this is a known error we want to suppress
        if not any(pattern in text for pattern in self.filtered_patterns):
            self.buffer.write(text)
    
    def flush(self):
        """Flush buffer."""
        pass


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
    
    Fixed: Deduplication happens in the scan callback to avoid
    processing the same device multiple times per scan.
    """
    
    def __init__(self, bluetooth_manager=None):
        self._manager = bluetooth_manager
        self._state = DiscoveryState.IDLE
        self._network_state = NetworkState.NO_DEVICES
        
        # Device tracking - with proper deduplication
        self._discovered_devices: Dict[str, DeviceInfo] = {}
        self._app_devices: Set[str] = set()  # Devices running our app
        self._device_lock = asyncio.Lock()
        
        # Track devices seen in current scan (for deduplication)
        self._current_scan_devices: Set[str] = set()
        
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
        logger.info("Device discovery started")
    
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
        
        logger.info("Device discovery stopped")
    
    async def scan_once(self, timeout: float = None) -> List[DeviceInfo]:
        """
        Perform a single scan operation.
        
        Fixed: Deduplication now happens in the callback to avoid
        logging and processing the same device multiple times.
        """
        timeout = timeout or BluetoothConstants.DEFAULT_SCAN_TIMEOUT
        
        # Reset current scan tracking
        self._current_scan_devices.clear()
        new_devices_this_scan: List[DeviceInfo] = []
        
        async def detection_callback(device: BLEDevice, advertisement_data: AdvertisementData):
            """
            Handle device detection - with proper deduplication.
            
            This callback fires for EVERY advertisement packet, including
            RSSI updates. We only want to process each device ONCE per scan.
            """
            address = device.address
            
            # Skip if already seen in this scan (deduplication)
            if address in self._current_scan_devices:
                return
            
            self._current_scan_devices.add(address)
            
            # Check if this is an app device (advertising our service UUID)
            is_app_device = self._is_app_device(device, advertisement_data)
            
            device_info = DeviceInfo(
                address=address,
                name=device.name or advertisement_data.local_name,
                rssi=advertisement_data.rssi,
                state=ConnectionState.DISCONNECTED,
            )
            device_info.update_seen()
            
            # Check if this is a new device overall
            async with self._device_lock:
                is_new_device = address not in self._discovered_devices
                
                if is_new_device:
                    self._discovered_devices[address] = device_info
                    logger.info(f"🆕 NEW DEVICE: {address} | {device_info.name or 'Unknown'} | RSSI: {device_info.rssi} | App: {is_app_device}")
                    new_devices_this_scan.append(device_info)
                    
                    # Track app devices
                    if is_app_device:
                        self._app_devices.add(address)
                        logger.info(f"✅ APP DEVICE IDENTIFIED: {address}")
                        if self._on_app_device_found:
                            asyncio.create_task(self._safe_callback(self._on_app_device_found, device_info))
                    
                    # Notify general device found callback
                    if self._on_device_found:
                        asyncio.create_task(self._safe_callback(self._on_device_found, device_info))
                else:
                    # Update existing device info
                    existing = self._discovered_devices[address]
                    existing.rssi = device_info.rssi
                    existing.update_seen()
                    
                    # Check if it became an app device
                    if is_app_device and address not in self._app_devices:
                        self._app_devices.add(address)
                        logger.info(f"✅ EXISTING DEVICE NOW IDENTIFIED AS APP: {address}")
                        if self._on_app_device_found:
                            asyncio.create_task(self._safe_callback(self._on_app_device_found, existing))
        
        try:
            self._stats.total_scans += 1
            self._stats.last_scan_time = time.time()
            
            logger.info(f"🔍 Starting BLE scan #{self._stats.total_scans} (timeout: {timeout}s)")
            
            scanner = BleakScanner(detection_callback=detection_callback)
            
            # Suppress known non-fatal dbus-fast KeyError during scan operations
            with StderrFilter():
                try:
                    await asyncio.wait_for(
                        scanner.start(),
                        timeout=Config.bluetooth.SCANNER_START_TIMEOUT
                    )
                    await asyncio.sleep(timeout)
                    await asyncio.wait_for(
                        scanner.stop(),
                        timeout=Config.bluetooth.SCANNER_STOP_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    logger.warning("Scanner operation timed out")
                    try:
                        await scanner.stop()
                    except Exception:
                        pass
                    raise BluetoothDiscoveryError("Scanner operation timed out")
            
            # Log results
            unique_devices_seen = len(self._current_scan_devices)
            new_count = len(new_devices_this_scan)
            
            async with self._device_lock:
                total_known = len(self._discovered_devices)
                app_count = len(self._app_devices)
            
            logger.info(f"📡 Scan complete: {unique_devices_seen} unique devices seen, {new_count} new")
            logger.info(f"📊 Total known: {total_known} | App devices: {app_count}")
            
            # Update statistics
            if new_devices_this_scan:
                self._stats.successful_scans += 1
                self._stats.devices_found += new_count
                self._stats.last_device_found_time = time.time()
                self._stats.consecutive_empty_scans = 0
            else:
                if unique_devices_seen == 0:
                    self._stats.consecutive_empty_scans += 1
            
            # Update network state and interval
            await self._update_network_state()
            
            return new_devices_this_scan
            
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
        logger.info(f"🚀 Discovery scan loop started (interval: {self._current_interval:.1f}s)")
        
        while self._running:
            try:
                # Perform scan
                await self.scan_once()
                
                # Check for lost devices
                await self._check_lost_devices()
                
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
            target_interval = Config.bluetooth.DISCOVERY_INTERVAL_NO_DEVICES
        elif self._network_state == NetworkState.DISCOVERING:
            target_interval = Config.bluetooth.DISCOVERY_INTERVAL_INITIAL
        elif self._network_state == NetworkState.MODERATE:
            target_interval = Config.bluetooth.DISCOVERY_INTERVAL_MODERATE
        else:
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
        lost_threshold = float(Config.bluetooth.DEVICE_LOST_THRESHOLD)
        
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
            logger.info(f"📴 Device lost: {device.address}")
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
        except Exception as e:
            logger.error(f"Error in callback: {e}")
    
    def force_scan(self) -> None:
        """Force an immediate scan by resetting interval."""
        self._current_interval = self._min_interval
    
    async def clear_cache(self) -> None:
        """Clear the discovered devices cache."""
        async with self._device_lock:
            self._discovered_devices.clear()
            self._app_devices.clear()
        logger.info("Discovery cache cleared")
