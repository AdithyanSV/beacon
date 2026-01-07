"""
Bluetooth Mesh Broadcast Application - Main Entry Point

This is the main entry point for the application. It initializes all components
and starts the web server with Bluetooth support.
"""

import asyncio
import signal
import sys
import os
from typing import Optional

# Add backend directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import eventlet and monkey patch BEFORE other imports
import eventlet
eventlet.monkey_patch()

from config import Config
from utils.logger import setup_logging, get_logger
from utils.resource_monitor import ResourceMonitor
from bluetooth.manager import BluetoothManager
from bluetooth.discovery import DeviceDiscovery
from bluetooth.connection_pool import ConnectionPool
from messaging.handler import MessageHandler
from web.server import create_app, socketio
from web.handlers import (
    set_bluetooth_manager,
    set_message_handler,
    set_discovery,
    emit_message_received,
    emit_devices_updated,
)

# Set up logging
setup_logging()
logger = get_logger(__name__)


class Application:
    """
    Main application class that coordinates all components.
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
        
        # Flask app
        self._app = None
    
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
            except Exception as e:
                logger.warning(f"Bluetooth initialization failed: {e}")
                logger.info("Continuing without Bluetooth support...")
            
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
            
            # Start background services
            if self._bluetooth_manager:
                await self._bluetooth_manager.start()
                logger.info("Bluetooth manager started")
            
            if self._discovery:
                await self._discovery.start()
                logger.info("Device discovery started")
            
            if self._connection_pool:
                await self._connection_pool.start()
                logger.info("Connection pool started")
            
            # Set up web handlers
            set_bluetooth_manager(self._bluetooth_manager)
            set_message_handler(self._message_handler)
            set_discovery(self._discovery)
            
            # Create Flask app
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
            # Bluetooth Manager callbacks
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
            # Discovery callbacks
            self._discovery.set_app_device_found_callback(
                self._on_app_device_found
            )
            self._discovery.set_device_lost_callback(
                self._on_device_lost
            )
        
        if self._message_handler:
            # Message Handler callbacks
            self._message_handler.set_message_received_callback(
                self._on_message_received
            )
        
        if self._resource_monitor:
            # Resource Monitor callbacks
            self._resource_monitor.set_warning_callback(
                self._on_resource_warning
            )
            self._resource_monitor.set_error_callback(
                self._on_resource_error
            )
    
    async def _on_device_connected(self, device_info):
        """Handle device connection."""
        logger.info(f"Device connected: {device_info.address}")
        
        # Add to connection pool
        await self._connection_pool.add_connection(
            device_info.address,
            device_info
        )
        
        # Update UI
        await self._emit_device_update()
    
    async def _on_device_disconnected(self, device_info):
        """Handle device disconnection."""
        logger.info(f"Device disconnected: {device_info.address}")
        
        # Remove from connection pool
        await self._connection_pool.remove_connection(device_info.address)
        
        # Update UI
        await self._emit_device_update()
    
    async def _on_bluetooth_message(self, address: str, data: dict):
        """Handle incoming Bluetooth message."""
        try:
            # Convert dict to bytes if needed
            if isinstance(data, dict):
                import json
                message_bytes = json.dumps(data).encode('utf-8')
            elif isinstance(data, bytes):
                message_bytes = data
            else:
                message_bytes = str(data).encode('utf-8')
            
            # Get connected devices for forwarding
            connected = await self._bluetooth_manager.get_connected_devices()
            connected_addresses = [d.address for d in connected]
            
            # Process through message handler
            message, forward_to = await self._message_handler.receive_message(
                message_bytes,
                source_device=address,
                connected_devices=connected_addresses
            )
            
            # Forward if needed
            if forward_to and message:
                forward_data = await self._message_handler.prepare_for_forwarding(message)
                if forward_data:
                    for target in forward_to:
                        await self._bluetooth_manager.send_data(target, forward_data)
            
        except Exception as e:
            logger.error(f"Error processing Bluetooth message: {e}")
            import traceback
            traceback.print_exc()
    
    async def _on_app_device_found(self, device_info):
        """Handle discovery of app device."""
        logger.info(f"App device found: {device_info.address}")
        
        # Try to connect if not at capacity
        if self._connection_pool.available_slots > 0:
            try:
                await self._bluetooth_manager.connect_to_device(device_info.address)
            except Exception as e:
                logger.warning(f"Failed to connect to {device_info.address}: {e}")
    
    async def _on_device_lost(self, device_info):
        """Handle device lost from discovery."""
        logger.info(f"Device lost: {device_info.address}")
    
    async def _on_message_received(self, message):
        """Handle received message (for UI)."""
        # Emit to web clients
        emit_message_received(message.to_dict(), is_own=False)
        
        # Record for resource monitoring
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
            emit_devices_updated(device_list, len(device_list))
    
    def start_sync(self):
        """Start the application (synchronous version for eventlet)."""
        if self._running:
            return
        
        logger.info("Starting application...")
        self._running = True
        
        try:
            logger.info(f"Starting web server on {Config.web.HOST}:{Config.web.PORT}")
            
            # Run Flask-SocketIO (this blocks)
            socketio.run(
                self._app,
                host=Config.web.HOST,
                port=Config.web.PORT,
                debug=Config.web.DEBUG,
                use_reloader=False,  # Disable reloader for production
                log_output=True
            )
            
        except Exception as e:
            logger.error(f"Error starting application: {e}")
            raise
    
    def stop_sync(self):
        """Stop the application (synchronous version)."""
        if not self._running:
            return
        
        logger.info("Stopping application...")
        self._running = False
        logger.info("Application stopped")
    
    def handle_signal(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self._running = False


def main():
    """Main entry point."""
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║          Bluetooth Mesh Broadcast Application            ║
    ║                      Version 1.0.0                       ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    # Create application
    app = Application()
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, app.handle_signal)
    signal.signal(signal.SIGTERM, app.handle_signal)
    
    try:
        # Initialize using eventlet
        import eventlet
        
        # Run initialization
        def run_init():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(app.initialize())
            loop.close()
            return result
        
        init_result = run_init()
        
        if not init_result:
            logger.error("Failed to initialize application")
            sys.exit(1)
        
        # Start the application (blocking)
        app.start_sync()
        
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Application error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Cleanup
        app.stop_sync()
    
    logger.info("Application exited")


if __name__ == "__main__":
    main()
