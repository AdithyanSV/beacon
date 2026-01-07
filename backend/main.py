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
from utils.websocket_log_handler import setup_websocket_logging
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

# Set up WebSocket logging (will be initialized after socketio is created)


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
                # Initialize Bluetooth (this is async, we're in async context)
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
            
            # Note: Background services will be started after initialization
            # in a persistent async runner to avoid eventlet conflicts
            
            logger.info("Components initialized, background services will start after initialization")
            
            # Set up web handlers
            set_bluetooth_manager(self._bluetooth_manager)
            set_message_handler(self._message_handler)
            set_discovery(self._discovery)
            
            # Create Flask app
            self._app = create_app()
            
            # Set up WebSocket logging for real-time log streaming to frontend
            setup_websocket_logging(socketio)
            logger.info("WebSocket logging enabled - logs will stream to frontend")
            
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
            self._discovery.set_device_found_callback(
                self._on_device_found
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
        logger.info(f"🎉 APP DEVICE FOUND: {device_info.address}")
        logger.info(f"   Name: {device_info.name or 'Unknown'}")
        logger.info(f"   This device is running our application!")
        
        # Try to connect if not at capacity
        if self._connection_pool and self._connection_pool.available_slots > 0:
            try:
                logger.info(f"🔌 Connecting to app device {device_info.address}...")
                success = await self._bluetooth_manager.connect_to_device(device_info.address)
                if success:
                    logger.info(f"✅✅✅ SUCCESSFULLY CONNECTED TO APP DEVICE: {device_info.address}")
                else:
                    logger.warning(f"❌ Connection to app device {device_info.address} failed")
            except Exception as e:
                logger.error(f"❌ Failed to connect to app device {device_info.address}: {e}")
                import traceback
                logger.debug(traceback.format_exc())
        else:
            logger.warning(f"⚠️ Cannot connect to {device_info.address}: Connection pool full")
    
    async def _on_device_found(self, device_info):
        """Handle discovery of any device - try to connect to all devices."""
        logger.info(f"🎯 DEVICE DISCOVERED: {device_info.address}")
        logger.info(f"   Name: {device_info.name or 'Unknown'}")
        logger.info(f"   RSSI: {device_info.rssi}")
        logger.info(f"   State: {device_info.state.name}")
        
        # IMPORTANT: Try to connect to ALL discovered devices
        # We'll verify if they're app devices after connection
        if self._bluetooth_manager and self._connection_pool:
            # Check if already connected
            connected = await self._bluetooth_manager.get_connected_devices()
            already_connected = any(d.address == device_info.address for d in connected)
            
            if already_connected:
                logger.info(f"⏭️ Device {device_info.address} already connected, skipping")
            elif self._connection_pool.available_slots <= 0:
                logger.warning(f"⚠️ Connection pool full ({self._connection_pool.available_slots} slots), cannot connect to {device_info.address}")
            else:
                try:
                    logger.info(f"🔌 INITIATING CONNECTION to {device_info.address}...")
                    logger.info(f"   Available slots: {self._connection_pool.available_slots}")
                    success = await self._bluetooth_manager.connect_to_device(device_info.address)
                    if success:
                        logger.info(f"✅✅✅ CONNECTION SUCCESSFUL: {device_info.address}")
                    else:
                        logger.warning(f"❌ Connection attempt to {device_info.address} returned False")
                except Exception as e:
                    logger.warning(f"❌ Connection attempt to {device_info.address} failed: {e}")
                    import traceback
                    logger.debug(traceback.format_exc())
    
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
        
        # Start background async services in a separate thread
        # This ensures they run in a persistent event loop
        import threading
        
        def start_async_services():
            """Start async services in a background thread."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                async def start_all():
                    if self._bluetooth_manager:
                        await self._bluetooth_manager.start()
                        logger.info("✓ Bluetooth manager started")
                    
                    if self._discovery:
                        await self._discovery.start()
                        logger.info("✓ Device discovery started")
                    
                    if self._connection_pool:
                        await self._connection_pool.start()
                        logger.info("✓ Connection pool started")
                
                loop.run_until_complete(start_all())
                loop.run_forever()  # Keep loop running
            except Exception as e:
                logger.error(f"Error in async services thread: {e}")
                import traceback
                logger.debug(traceback.format_exc())
            finally:
                loop.close()
        
        # Start async services in background thread
        async_thread = threading.Thread(target=start_async_services, daemon=True)
        async_thread.start()
        logger.info("Async services thread started")
        
        # Give services a moment to start
        import time
        time.sleep(1)
        
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
