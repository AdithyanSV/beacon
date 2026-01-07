"""
Bluetooth Mesh Broadcast Application - Main Entry Point

This is the main entry point for the application. It uses a single asyncio
event loop to coordinate all components:
- BLE GATT Server (to accept incoming connections)
- BLE Client/Scanner (to discover and connect to other devices)
- Web Server with WebSocket support
- Message handling and routing

Version 2.0 - Pure asyncio architecture (no eventlet)
"""

import asyncio
import signal
import sys
import os
from typing import Optional
from aiohttp import web

# Add backend directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from utils.logger import setup_logging, get_logger
from utils.resource_monitor import ResourceMonitor
from bluetooth.manager import BluetoothManager
from bluetooth.discovery import DeviceDiscovery
from bluetooth.connection_pool import ConnectionPool
from bluetooth.gatt_server import BLEGATTServer
from messaging.handler import MessageHandler
from web.async_server import (
    create_app,
    sio,
    set_bluetooth_manager,
    set_message_handler,
    set_discovery,
    set_gatt_server,
    emit_message_received,
    emit_devices_updated,
)

# Set up logging
setup_logging()
logger = get_logger(__name__)


class Application:
    """
    Main application class that coordinates all components.
    
    Uses a single asyncio event loop for all async operations.
    """
    
    def __init__(self):
        self._running = False
        self._shutdown_event = asyncio.Event()
        
        # Components
        self._bluetooth_manager: Optional[BluetoothManager] = None
        self._discovery: Optional[DeviceDiscovery] = None
        self._connection_pool: Optional[ConnectionPool] = None
        self._message_handler: Optional[MessageHandler] = None
        self._resource_monitor: Optional[ResourceMonitor] = None
        self._gatt_server: Optional[BLEGATTServer] = None
        
        # Web app
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
    
    async def initialize(self) -> bool:
        """
        Initialize all application components.
        
        Returns:
            True if initialization successful.
        """
        logger.info("Initializing application...")
        
        # Validate configuration
        if not Config.validate():
            logger.error("Configuration validation failed")
            return False
        
        try:
            # Initialize Bluetooth Manager
            logger.info("Initializing Bluetooth manager...")
            self._bluetooth_manager = BluetoothManager()
            try:
                await self._bluetooth_manager.initialize()
                logger.info("✓ Bluetooth manager initialized")
            except Exception as e:
                logger.warning(f"Bluetooth initialization failed: {e}")
                logger.info("Continuing without Bluetooth client support...")
            
            # Initialize GATT Server (NEW - hosts our service UUID)
            logger.info("Initializing GATT server...")
            self._gatt_server = BLEGATTServer()
            self._gatt_server.set_message_received_callback(self._on_gatt_message_received)
            
            # Initialize Discovery
            logger.info("Initializing device discovery...")
            self._discovery = DeviceDiscovery(self._bluetooth_manager)
            
            # Initialize Connection Pool
            logger.info("Initializing connection pool...")
            self._connection_pool = ConnectionPool()
            
            # Initialize Message Handler
            logger.info("Initializing message handler...")
            self._message_handler = MessageHandler(
                local_device_id=self._bluetooth_manager.local_address if self._bluetooth_manager else "local"
            )
            
            # Initialize Resource Monitor
            logger.info("Initializing resource monitor...")
            self._resource_monitor = ResourceMonitor()
            
            # Set up callbacks
            self._setup_callbacks()
            
            # Set up web handlers
            set_bluetooth_manager(self._bluetooth_manager)
            set_message_handler(self._message_handler)
            set_discovery(self._discovery)
            set_gatt_server(self._gatt_server)
            
            # Create web app
            self._app = create_app()
            
            logger.info("Application initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _setup_callbacks(self):
        """Set up callbacks between components."""
        
        if self._bluetooth_manager:
            self._bluetooth_manager.set_device_connected_callback(
                self._on_device_connected
            )
            self._bluetooth_manager.set_device_disconnected_callback(
                self._on_device_disconnected
            )
            self._bluetooth_manager.set_message_callback(
                self._on_bluetooth_message
            )
        
        if self._discovery:
            self._discovery.set_app_device_found_callback(
                self._on_app_device_found
            )
            self._discovery.set_device_found_callback(
                self._on_device_found
            )
            self._discovery.set_device_lost_callback(
                self._on_device_lost
            )
        
        if self._message_handler:
            self._message_handler.set_message_received_callback(
                self._on_message_received
            )
        
        if self._resource_monitor:
            self._resource_monitor.set_warning_callback(
                self._on_resource_warning
            )
            self._resource_monitor.set_error_callback(
                self._on_resource_error
            )
    
    async def _on_device_connected(self, device_info):
        """Handle device connection."""
        logger.info(f"✅ Device connected: {device_info.address}")
        
        # Add to connection pool
        await self._connection_pool.add_connection(
            device_info.address,
            device_info
        )
        
        # Update UI
        await self._emit_device_update()
    
    async def _on_device_disconnected(self, device_info):
        """Handle device disconnection."""
        logger.info(f"❌ Device disconnected: {device_info.address}")
        
        # Remove from connection pool
        await self._connection_pool.remove_connection(device_info.address)
        
        # Update UI
        await self._emit_device_update()
    
    async def _on_bluetooth_message(self, address: str, data: dict):
        """Handle incoming Bluetooth message from a connected device."""
        try:
            import json
            if isinstance(data, dict):
                message_bytes = json.dumps(data).encode('utf-8')
            elif isinstance(data, bytes):
                message_bytes = data
            else:
                message_bytes = str(data).encode('utf-8')
            
            connected = await self._bluetooth_manager.get_connected_devices()
            connected_addresses = [d.address for d in connected]
            
            message, forward_to = await self._message_handler.receive_message(
                message_bytes,
                source_device=address,
                connected_devices=connected_addresses
            )
            
            if forward_to and message:
                forward_data = await self._message_handler.prepare_for_forwarding(message)
                if forward_data:
                    for target in forward_to:
                        await self._bluetooth_manager.send_data(target, forward_data)
            
        except Exception as e:
            logger.error(f"Error processing Bluetooth message: {e}")
    
    async def _on_gatt_message_received(self, client_address: str, data: bytes):
        """Handle message received via GATT server (from incoming connection)."""
        logger.info(f"📨 Message received via GATT from {client_address}")
        
        try:
            connected = []
            if self._bluetooth_manager:
                connected = await self._bluetooth_manager.get_connected_devices()
            connected_addresses = [d.address for d in connected]
            
            message, forward_to = await self._message_handler.receive_message(
                data,
                source_device=client_address,
                connected_devices=connected_addresses
            )
            
            # Forward if needed
            if forward_to and message:
                forward_data = await self._message_handler.prepare_for_forwarding(message)
                if forward_data:
                    # Forward via BLE client connections
                    if self._bluetooth_manager:
                        for target in forward_to:
                            await self._bluetooth_manager.send_data(target, forward_data)
                    
                    # Also broadcast via GATT server to other connected clients
                    if self._gatt_server:
                        await self._gatt_server.send_notification(forward_data)
            
        except Exception as e:
            logger.error(f"Error processing GATT message: {e}")
    
    async def _on_app_device_found(self, device_info):
        """Handle discovery of app device (advertising our service UUID)."""
        logger.info(f"🎉 APP DEVICE FOUND: {device_info.address}")
        logger.info(f"   Name: {device_info.name or 'Unknown'}")
        logger.info(f"   This device is running our application!")
        
        # Try to connect
        if self._connection_pool and self._connection_pool.available_slots > 0:
            try:
                logger.info(f"🔌 Connecting to app device {device_info.address}...")
                success = await self._bluetooth_manager.connect_to_device(device_info.address)
                if success:
                    logger.info(f"✅ CONNECTED TO APP DEVICE: {device_info.address}")
                else:
                    logger.warning(f"❌ Connection to {device_info.address} failed")
            except Exception as e:
                logger.error(f"❌ Connection error: {e}")
    
    async def _on_device_found(self, device_info):
        """Handle discovery of any device."""
        logger.debug(f"📱 Device discovered: {device_info.address} | {device_info.name or 'Unknown'}")
    
    async def _on_device_lost(self, device_info):
        """Handle device lost from discovery."""
        logger.debug(f"Device lost: {device_info.address}")
    
    async def _on_message_received(self, message):
        """Handle received message (for UI)."""
        await emit_message_received(message.to_dict(), is_own=False)
        self._resource_monitor.record_message()
    
    async def _on_resource_warning(self, message: str, snapshot):
        """Handle resource warning."""
        logger.warning(f"Resource warning: {message}")
    
    async def _on_resource_error(self, message: str, snapshot):
        """Handle resource error."""
        logger.error(f"Resource error: {message}")
    
    async def _emit_device_update(self):
        """Emit device list update to web clients."""
        if self._bluetooth_manager:
            devices = await self._bluetooth_manager.get_connected_devices()
            device_list = [d.to_dict() for d in devices]
            await emit_devices_updated(device_list, len(device_list))
    
    async def start(self):
        """Start the application - all components in single event loop."""
        if self._running:
            return
        
        logger.info("Starting application...")
        self._running = True
        
        # Start all components as concurrent tasks
        tasks = []
        
        # Start GATT server
        if self._gatt_server:
            try:
                await self._gatt_server.start()
                logger.info("✓ GATT server started")
            except Exception as e:
                logger.warning(f"Failed to start GATT server: {e}")
        
        # Start Bluetooth manager
        if self._bluetooth_manager:
            try:
                await self._bluetooth_manager.start()
                logger.info("✓ Bluetooth manager started")
            except Exception as e:
                logger.warning(f"Failed to start Bluetooth manager: {e}")
        
        # Start discovery
        if self._discovery:
            try:
                await self._discovery.start()
                logger.info("✓ Device discovery started")
            except Exception as e:
                logger.warning(f"Failed to start discovery: {e}")
        
        # Start connection pool
        if self._connection_pool:
            try:
                await self._connection_pool.start()
                logger.info("✓ Connection pool started")
            except Exception as e:
                logger.warning(f"Failed to start connection pool: {e}")
        
        # Start web server
        try:
            self._runner = web.AppRunner(self._app)
            await self._runner.setup()
            
            self._site = web.TCPSite(
                self._runner,
                Config.web.HOST,
                Config.web.PORT
            )
            await self._site.start()
            
            logger.info(f"✓ Web server started at http://{Config.web.HOST}:{Config.web.PORT}")
        except Exception as e:
            logger.error(f"Failed to start web server: {e}")
            raise
        
        logger.info("=" * 50)
        logger.info("APPLICATION RUNNING")
        logger.info(f"  Web UI: http://{Config.web.HOST}:{Config.web.PORT}")
        logger.info(f"  GATT Server: {'Running' if self._gatt_server and self._gatt_server.is_running else 'Not running'}")
        logger.info(f"  BLE Discovery: {'Running' if self._discovery else 'Not running'}")
        logger.info("=" * 50)
        
        # Wait for shutdown signal
        await self._shutdown_event.wait()
    
    async def stop(self):
        """Stop the application."""
        if not self._running:
            return
        
        logger.info("Stopping application...")
        self._running = False
        
        # Stop web server
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        
        # Stop components
        if self._discovery:
            await self._discovery.stop()
        
        if self._bluetooth_manager:
            await self._bluetooth_manager.stop()
        
        if self._gatt_server:
            await self._gatt_server.stop()
        
        if self._connection_pool:
            await self._connection_pool.stop()
        
        self._shutdown_event.set()
        logger.info("Application stopped")
    
    def request_shutdown(self):
        """Request application shutdown (can be called from signal handler)."""
        asyncio.create_task(self.stop())


async def main():
    """Main entry point."""
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║          Bluetooth Mesh Broadcast Application            ║
    ║                  Version 2.0.0 (Async)                   ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    # Create application
    app = Application()
    
    # Set up signal handlers
    loop = asyncio.get_event_loop()
    
    def signal_handler():
        logger.info("Received shutdown signal")
        app.request_shutdown()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
    
    try:
        # Initialize
        if not await app.initialize():
            logger.error("Failed to initialize application")
            sys.exit(1)
        
        # Start (runs until shutdown)
        await app.start()
        
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Application error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await app.stop()
    
    logger.info("Application exited")


if __name__ == "__main__":
    asyncio.run(main())
