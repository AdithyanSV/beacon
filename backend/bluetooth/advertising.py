"""
BLE Advertising Module using BlueZ.

This module handles BLE advertising to make the device discoverable by other devices.
Since Bleak doesn't support BLE server mode on Linux, we use BlueZ D-Bus API or
system commands to set up advertising.
"""

import asyncio
import subprocess
import logging
from typing import Optional
from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)


class BLEAdvertising:
    """
    Handles BLE advertising to make the device discoverable.
    
    Uses BlueZ via D-Bus or system commands to advertise the service UUID.
    """
    
    def __init__(self):
        self._advertising = False
        self._adapter_path: Optional[str] = None
        
    async def start_advertising(self) -> bool:
        """
        Start BLE advertising with our service UUID.
        
        Returns:
            True if advertising started successfully, False otherwise.
        """
        if self._advertising:
            logger.info("Already advertising")
            return True
        
        try:
            # Try to use BlueZ D-Bus API first (if dbus-python available)
            try:
                return await self._start_advertising_dbus()
            except ImportError:
                logger.info("dbus-python not available, using system commands")
                return await self._start_advertising_system()
        except Exception as e:
            logger.error(f"Failed to start advertising: {e}")
            return False
    
    async def stop_advertising(self) -> bool:
        """
        Stop BLE advertising.
        
        Returns:
            True if advertising stopped successfully, False otherwise.
        """
        if not self._advertising:
            return True
        
        try:
            # Try D-Bus first
            try:
                return await self._stop_advertising_dbus()
            except ImportError:
                return await self._stop_advertising_system()
        except Exception as e:
            logger.error(f"Failed to stop advertising: {e}")
            return False
    
    async def _start_advertising_dbus(self) -> bool:
        """Start advertising using BlueZ D-Bus API."""
        try:
            import dbus
            import dbus.exceptions
            
            # Get system bus
            bus = dbus.SystemBus()
            
            # Get BlueZ manager
            bluez_manager = bus.get_object('org.bluez', '/')
            adapter_manager = dbus.Interface(bluez_manager, 'org.freedesktop.DBus.ObjectManager')
            
            # Find the first adapter
            objects = adapter_manager.GetManagedObjects()
            adapter_path = None
            for path, interfaces in objects.items():
                if 'org.bluez.Adapter1' in interfaces:
                    adapter_path = path
                    break
            
            if not adapter_path:
                logger.error("No Bluetooth adapter found")
                return False
            
            self._adapter_path = adapter_path
            
            # Get adapter interface
            adapter = bus.get_object('org.bluez', adapter_path)
            adapter_props = dbus.Interface(adapter, 'org.freedesktop.DBus.Properties')
            
            # Set adapter to powered and discoverable
            adapter_props.Set('org.bluez.Adapter1', 'Powered', dbus.Boolean(1))
            adapter_props.Set('org.bluez.Adapter1', 'Discoverable', dbus.Boolean(1))
            adapter_props.Set('org.bluez.Adapter1', 'DiscoverableTimeout', dbus.UInt32(0))  # 0 = permanent
            
            # Try to set up LE advertising (may not be available on all systems)
            try:
                le_advertising_manager = dbus.Interface(adapter, 'org.bluez.LEAdvertisingManager1')
                
                # Create advertising data with service UUID
                service_uuid = Config.bluetooth.SERVICE_UUID
                
                # Note: Full LE advertising setup requires more complex D-Bus calls
                # For now, we just make the device discoverable
                logger.info("LE Advertising Manager available, but full implementation requires additional setup")
                
            except dbus.exceptions.DBusException:
                logger.info("LE Advertising Manager not available, using classic Bluetooth discoverable mode")
            
            self._advertising = True
            logger.info(f"Device set to discoverable mode (service UUID: {Config.bluetooth.SERVICE_UUID})")
            return True
            
        except ImportError:
            raise ImportError("dbus-python not available")
        except Exception as e:
            logger.error(f"D-Bus advertising failed: {e}")
            raise
    
    async def _stop_advertising_dbus(self) -> bool:
        """Stop advertising using D-Bus."""
        try:
            import dbus
            
            if not self._adapter_path:
                return True
            
            bus = dbus.SystemBus()
            adapter = bus.get_object('org.bluez', self._adapter_path)
            adapter_props = dbus.Interface(adapter, 'org.freedesktop.DBus.Properties')
            
            adapter_props.Set('org.bluez.Adapter1', 'Discoverable', dbus.Boolean(0))
            
            self._advertising = False
            logger.info("BLE advertising stopped")
            return True
            
        except ImportError:
            raise ImportError("dbus-python not available")
        except Exception as e:
            logger.error(f"Failed to stop D-Bus advertising: {e}")
            return False
    
    async def _start_advertising_system(self) -> bool:
        """Start advertising using system commands (bluetoothctl)."""
        try:
            # Use bluetoothctl to make device discoverable
            # Note: This makes the device discoverable via classic Bluetooth, not BLE advertising
            # For full BLE advertising, we'd need BlueZ D-Bus API
            
            process = await asyncio.create_subprocess_exec(
                'bluetoothctl', 'discoverable', 'on',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                self._advertising = True
                logger.info("Device set to discoverable mode (classic Bluetooth)")
                logger.warning("Full BLE advertising requires dbus-python. Install with: pip install dbus-python")
                return True
            else:
                logger.error(f"Failed to set discoverable: {stderr.decode()}")
                return False
                
        except FileNotFoundError:
            logger.error("bluetoothctl not found. Please install BlueZ.")
            return False
        except Exception as e:
            logger.error(f"System command advertising failed: {e}")
            return False
    
    async def _stop_advertising_system(self) -> bool:
        """Stop advertising using system commands."""
        try:
            process = await asyncio.create_subprocess_exec(
                'bluetoothctl', 'discoverable', 'off',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            
            if process.returncode == 0:
                self._advertising = False
                logger.info("Device set to non-discoverable mode")
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Failed to stop system advertising: {e}")
            return False
    
    @property
    def is_advertising(self) -> bool:
        """Check if currently advertising."""
        return self._advertising
