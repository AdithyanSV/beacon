"""
Bluetooth Mesh Broadcast Application - Terminal CLI Entry Point

Pure asyncio architecture for terminal-based mesh networking.
No web server, no async/sync mixing - just clean async code.
"""

import asyncio
import signal
import sys
import os
from typing import Optional

# Add backend directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up error suppression FIRST, before any other imports that might use stderr
from utils.error_suppression import setup_error_suppression

# Set up error suppression before other imports
_error_filter = setup_error_suppression()

# Now import Config and logging
from config import Config
from utils.logger import setup_logging, get_logger

# Set up logging after Config is available
setup_logging()
from cli.terminal import TerminalUI
from bluetooth.manager import BluetoothManager
from bluetooth.discovery import DeviceDiscovery
from bluetooth.gatt_server import BLEGATTServer
from bluetooth.connection_pool import ConnectionPool
from messaging.handler import MessageHandler

logger = get_logger(__name__)


class Application:
    """
    Main application class coordinating all components.
    
    Pure asyncio architecture with terminal interface.
    """
    
    def __init__(self):
        self._running = False
        self._shutdown_event = asyncio.Event()
        
        # Terminal UI
        self._terminal: Optional[TerminalUI] = None
        
        # Bluetooth components
        self._bluetooth_manager: Optional[BluetoothManager] = None
        self._discovery: Optional[DeviceDiscovery] = None
        self._gatt_server: Optional[BLEGATTServer] = None
        self._connection_pool: Optional[ConnectionPool] = None
        
        # Messaging
        self._message_handler: Optional[MessageHandler] = None
    
    async def initialize(self) -> bool:
        """Initialize all application components."""
        try:
            logger.info("Initializing application...")
            
            # Create terminal UI
            self._terminal = TerminalUI()
            self._terminal.print_banner()
            
            logger.info("Validating configuration...")
            print("[INIT] Validating configuration...")
            if not Config.validate():
                logger.error("Configuration validation failed")
                print("[ERROR] Configuration validation failed")
                return False
            
            # Initialize Bluetooth Manager
            logger.info("Initializing Bluetooth manager...")
            print("[INIT] Initializing Bluetooth manager...")
            self._bluetooth_manager = BluetoothManager()
            try:
                await self._bluetooth_manager.initialize()
                logger.info("Bluetooth manager initialized successfully")
                print("[OK] Bluetooth manager initialized")
            except Exception as e:
                logger.warning(f"Bluetooth initialization failed: {e}", exc_info=True)
                print(f"[WARN] Bluetooth initialization failed: {e}")
                print("[INFO] Continuing without Bluetooth client support...")
            
            # Initialize GATT Server
            logger.info("Initializing GATT server...")
            print("[INIT] Initializing GATT server...")
            try:
                self._gatt_server = BLEGATTServer()
                self._gatt_server.set_message_received_callback(self._on_gatt_message_received)
                logger.info("GATT server initialized")
            except Exception as e:
                logger.error(f"GATT server initialization failed: {e}", exc_info=True)
                print(f"[WARN] GATT server initialization failed: {e}")
                self._gatt_server = None
            
            # Initialize Discovery
            logger.info("Initializing device discovery...")
            print("[INIT] Initializing device discovery...")
            try:
                self._discovery = DeviceDiscovery(self._bluetooth_manager)
                logger.info("Device discovery initialized")
            except Exception as e:
                logger.error(f"Discovery initialization failed: {e}", exc_info=True)
                print(f"[WARN] Discovery initialization failed: {e}")
                self._discovery = None
            
            # Initialize Connection Pool
            logger.info("Initializing connection pool...")
            print("[INIT] Initializing connection pool...")
            try:
                self._connection_pool = ConnectionPool()
                logger.info("Connection pool initialized")
            except Exception as e:
                logger.error(f"Connection pool initialization failed: {e}", exc_info=True)
                print(f"[WARN] Connection pool initialization failed: {e}")
                self._connection_pool = None
            
            # Initialize Message Handler
            logger.info("Initializing message handler...")
            print("[INIT] Initializing message handler...")
            try:
                local_id = self._bluetooth_manager.local_address if self._bluetooth_manager else "local"
                self._message_handler = MessageHandler(local_device_id=local_id)
                logger.info("Message handler initialized")
            except Exception as e:
                logger.error(f"Message handler initialization failed: {e}", exc_info=True)
                print(f"[WARN] Message handler initialization failed: {e}")
                self._message_handler = None
            
            # Set up callbacks
            self._setup_callbacks()
            
            # Set up terminal command handlers
            self._setup_terminal_handlers()
            
            logger.info("Application initialized successfully")
            print("[OK] Application initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Initialization failed: {e}", exc_info=True)
            print(f"[ERROR] Initialization failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _setup_callbacks(self):
        """Set up callbacks between components."""
        if self._bluetooth_manager:
            self._bluetooth_manager.set_device_connected_callback(self._on_device_connected)
            self._bluetooth_manager.set_device_disconnected_callback(self._on_device_disconnected)
            self._bluetooth_manager.set_message_callback(self._on_bluetooth_message)
        
        if self._discovery:
            self._discovery.set_app_device_found_callback(self._on_app_device_found)
            self._discovery.set_device_found_callback(self._on_device_found)
            self._discovery.set_device_lost_callback(self._on_device_lost)
        
        if self._message_handler:
            self._message_handler.set_message_received_callback(self._on_message_received)
    
    def _setup_terminal_handlers(self):
        """Set up terminal command handlers."""
        self._terminal.set_send_handler(self._handle_send)
        self._terminal.set_list_handler(self._handle_list)
        self._terminal.set_scan_handler(self._handle_scan)
        self._terminal.set_connect_handler(self._handle_connect)
        self._terminal.set_disconnect_handler(self._handle_disconnect)
        self._terminal.set_status_handler(self._handle_status)
        self._terminal.set_stats_handler(self._handle_stats)
        self._terminal.set_quit_handler(self._handle_quit)
        self._terminal.set_live_stats_handler(self._get_live_stats)
    
    # ==================== Command Handlers ====================
    
    async def _handle_send(self, content: str):
        """Handle send command."""
        if not self._message_handler:
            self._terminal.print_error("Message handler not available")
            return
        
        try:
            # Create message
            message = await self._message_handler.create_message(
                content=content,
                sender_name="You"
            )
            
            # Get connected devices
            connected_addresses = []
            if self._bluetooth_manager:
                devices = await self._bluetooth_manager.get_connected_devices()
                connected_addresses = [d.address for d in devices]
            
            # Send through message handler
            targets = await self._message_handler.send_message(message, connected_addresses)
            
            # Send via Bluetooth
            sent_count = 0
            if self._bluetooth_manager and targets:
                message_bytes = message.to_bytes()
                for target in targets:
                    try:
                        success = await self._bluetooth_manager.send_data(target, message_bytes)
                        if success:
                            sent_count += 1
                            # Record in connection pool
                            if self._connection_pool:
                                await self._connection_pool.record_message_sent(target, len(message_bytes))
                    except Exception:
                        pass
            
            # Also broadcast via GATT server
            if self._gatt_server and self._gatt_server.is_running:
                try:
                    await self._gatt_server.broadcast_message(message.to_dict())
                except Exception:
                    pass
            
            # Show own message
            self._terminal.print_message(
                sender="You",
                content=content,
                timestamp=message.timestamp,
                is_own=True
            )
            
            if sent_count > 0:
                self._terminal.print_success(f"Message sent to {sent_count} device(s)")
            elif connected_addresses:
                self._terminal.print_warning("Message queued but no devices received it")
            else:
                self._terminal.print_info("Message created (no devices connected)")
            
        except Exception as e:
            self._terminal.print_error(f"Failed to send message: {e}")
    
    async def _handle_list(self):
        """Handle list command."""
        connected = []
        discovered = []
        
        if self._bluetooth_manager:
            devices = await self._bluetooth_manager.get_connected_devices()
            connected = [d.to_dict() if hasattr(d, 'to_dict') else {"address": str(d)} for d in devices]
        
        if self._discovery:
            app_devices = await self._discovery.get_app_devices()
            discovered = [d.to_dict() if hasattr(d, 'to_dict') else {"address": str(d)} for d in app_devices]
        
        self._terminal.print_devices_list(connected, discovered)
    
    async def _handle_scan(self):
        """Handle scan command."""
        if not self._discovery:
            self._terminal.print_error("Discovery not available")
            return
        
        self._terminal.print_info("Starting device scan...")
        self._discovery.force_scan()
        
        try:
            devices = await self._discovery.scan_once(timeout=5.0)
            if devices:
                self._terminal.print_success(f"Found {len(devices)} new device(s)")
            else:
                self._terminal.print_info("No new devices found")
        except Exception as e:
            self._terminal.print_error(f"Scan failed: {e}")
    
    async def _handle_connect(self, address: str):
        """Handle connect command."""
        if not self._bluetooth_manager:
            self._terminal.print_error("Bluetooth manager not available")
            return
        
        self._terminal.print_info(f"Connecting to {address}...")
        
        try:
            success = await self._bluetooth_manager.connect_to_device(address)
            if success:
                self._terminal.print_success(f"Connected to {address}")
            else:
                self._terminal.print_error(f"Failed to connect to {address}")
        except Exception as e:
            self._terminal.print_error(f"Connection error: {e}")
    
    async def _handle_disconnect(self, address: str):
        """Handle disconnect command."""
        if not self._bluetooth_manager:
            self._terminal.print_error("Bluetooth manager not available")
            return
        
        try:
            success = await self._bluetooth_manager.disconnect_device(address)
            if success:
                self._terminal.print_success(f"Disconnected from {address}")
            else:
                self._terminal.print_error(f"Device {address} was not connected")
        except Exception as e:
            self._terminal.print_error(f"Disconnect error: {e}")
    
    async def _handle_status(self):
        """Handle status command - includes discovery stats."""
        # Bluetooth status
        bt_running = self._bluetooth_manager.is_running if self._bluetooth_manager else False
        bt_connected = await self._bluetooth_manager.get_connection_count() if self._bluetooth_manager else 0
        
        # GATT status
        gatt_running = self._gatt_server.is_running if self._gatt_server else False
        
        # Discovery status and stats
        discovery_status = {
            "state": "N/A",
            "network_state": "N/A",
            "app_devices": 0,
            "total_scans": 0,
            "successful_scans": 0,
            "devices_found": 0,
            "consecutive_empty_scans": 0,
            "current_interval": 0.0,
        }
        
        if self._discovery:
            stats = self._discovery.stats
            app_devices = await self._discovery.get_app_devices()
            
            discovery_status.update(
                {
                    "state": self._discovery.state.name,
                    "network_state": self._discovery.network_state.name,
                    "app_devices": len(app_devices),
                    "total_scans": stats.total_scans,
                    "successful_scans": stats.successful_scans,
                    "devices_found": stats.devices_found,
                    "consecutive_empty_scans": stats.consecutive_empty_scans,
                    "current_interval": self._discovery.current_interval,
                }
            )
        
        status = {
            "bluetooth": {
                "running": bt_running,
                "connected": bt_connected,
                "max": Config.bluetooth.MAX_CONCURRENT_CONNECTIONS,
            },
            "gatt_server": {
                "running": gatt_running,
            },
            "discovery": discovery_status,
        }
        
        self._terminal.print_status(status)
    
    async def _handle_stats(self):
        """Handle stats command."""
        stats = {
            "messages": {},
            "router": {},
        }
        
        if self._message_handler:
            msg_stats = self._message_handler.stats
            stats["messages"] = {
                "sent": msg_stats.total_sent,
                "received": msg_stats.total_received,
                "forwarded": msg_stats.total_forwarded,
            }
            
            router_stats = self._message_handler.get_router_stats()
            stats["router"] = {
                "dropped_duplicate": router_stats.get("messages_dropped_duplicate", 0),
                "dropped_ttl": router_stats.get("messages_dropped_ttl", 0),
                "cache_size": router_stats.get("cache_size", 0),
            }
        
        self._terminal.print_stats(stats)
    
    async def _handle_quit(self):
        """Handle quit command."""
        await self.stop()
    
    async def _get_live_stats(self) -> dict:
        """Get live statistics for dashboard."""
        stats = {}
        
        # Local device info
        local_address = self._bluetooth_manager.local_address if self._bluetooth_manager else "N/A"
        local_name = Config.bluetooth.SERVICE_NAME
        stats["local_device"] = {
            "address": local_address,
            "name": local_name,
            "status": "Running" if (self._bluetooth_manager and self._bluetooth_manager.is_running) else "Stopped",
        }
        
        # Bluetooth status
        bt_running = self._bluetooth_manager.is_running if self._bluetooth_manager else False
        bt_connected = await self._bluetooth_manager.get_connection_count() if self._bluetooth_manager else 0
        
        # Get connected devices
        connected_devices = []
        if self._bluetooth_manager:
            connected = await self._bluetooth_manager.get_connected_devices()
            connected_devices = [d.to_dict() for d in connected]
        
        stats["bluetooth"] = {
            "running": bt_running,
            "connected": bt_connected,
            "max": Config.bluetooth.MAX_CONCURRENT_CONNECTIONS,
            "connected_devices": connected_devices,
        }
        
        # GATT status
        gatt_running = self._gatt_server.is_running if self._gatt_server else False
        stats["gatt_server"] = {
            "running": gatt_running,
        }
        
        # Discovery status and stats
        discovery_status = {
            "state": "N/A",
            "network_state": "N/A",
            "app_devices": 0,
            "total_devices": 0,
            "total_scans": 0,
            "successful_scans": 0,
            "devices_found": 0,
            "consecutive_empty_scans": 0,
            "current_interval": 0.0,
            "discovered_devices": [],
            "app_device_list": [],
        }
        
        app_device_list = []
        if self._discovery:
            disc_stats = self._discovery.stats
            app_devices = await self._discovery.get_app_devices()
            all_devices = await self._discovery.get_all_devices()
            
            # Convert to dict format
            discovered_list = [d.to_dict() for d in all_devices]
            app_device_list = [d.to_dict() for d in app_devices]
            
            discovery_status.update({
                "state": self._discovery.state.name,
                "network_state": self._discovery.network_state.name,
                "app_devices": len(app_devices),
                "total_devices": len(all_devices),
                "total_scans": disc_stats.total_scans,
                "successful_scans": disc_stats.successful_scans,
                "devices_found": disc_stats.devices_found,
                "consecutive_empty_scans": disc_stats.consecutive_empty_scans,
                "current_interval": self._discovery.current_interval,
                "discovered_devices": discovered_list,
                "app_device_list": app_device_list,
            })
        
        # Add connected devices list to discovery status for dashboard
        discovery_status["connected_devices_list"] = connected_devices
        discovery_status["discovered_app_devices_list"] = app_device_list if self._discovery else []
        
        stats["discovery"] = discovery_status
        
        # Message stats
        msg_stats = {}
        if self._message_handler:
            handler_stats = self._message_handler.stats
            msg_stats = {
                "sent": handler_stats.total_sent,
                "received": handler_stats.total_received,
                "forwarded": handler_stats.total_forwarded,
            }
        
        stats["messages"] = msg_stats
        
        return stats
    
    # ==================== Bluetooth Callbacks ====================
    
    async def _on_device_connected(self, device_info):
        """Handle device connection."""
        self._terminal.print_device_connected(
            address=device_info.address,
            name=device_info.name
        )
        
        if self._connection_pool:
            await self._connection_pool.add_connection(device_info.address, device_info)
            # Update resource monitor connection count
            if hasattr(self, '_resource_monitor') and self._resource_monitor:
                count = await self._bluetooth_manager.get_connection_count() if self._bluetooth_manager else 0
                self._resource_monitor.update_connection_count(count)
    
    async def _on_device_disconnected(self, device_info):
        """Handle device disconnection."""
        self._terminal.print_device_disconnected(
            address=device_info.address,
            name=device_info.name
        )
        
        if self._connection_pool:
            await self._connection_pool.remove_connection(device_info.address)
            # Update resource monitor connection count
            if hasattr(self, '_resource_monitor') and self._resource_monitor:
                count = await self._bluetooth_manager.get_connection_count() if self._bluetooth_manager else 0
                self._resource_monitor.update_connection_count(count)
    
    async def _on_bluetooth_message(self, address: str, data: dict):
        """Handle incoming Bluetooth message."""
        try:
            import json
            if isinstance(data, dict):
                message_bytes = json.dumps(data).encode('utf-8')
            elif isinstance(data, bytes):
                message_bytes = data
            else:
                message_bytes = str(data).encode('utf-8')
            
            # Record message received in connection pool
            if self._connection_pool:
                await self._connection_pool.record_message_received(address, len(message_bytes))
            
            connected = await self._bluetooth_manager.get_connected_devices() if self._bluetooth_manager else []
            connected_addresses = [d.address for d in connected]
            
            if not self._message_handler:
                logger.warning("Message handler not available, cannot process message")
                return
            
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
                        try:
                            if self._bluetooth_manager:
                                success = await self._bluetooth_manager.send_data(target, forward_data)
                                if success and self._connection_pool:
                                    await self._connection_pool.record_message_sent(target, len(forward_data))
                        except Exception as e:
                            logger.warning(f"Failed to forward message to {target}: {e}")
        except Exception as e:
            logger.error(f"Error processing Bluetooth message from {address}: {e}", exc_info=True)
            self._terminal.print_error(f"Error processing message: {e}")
    
    async def _on_gatt_message_received(self, client_address: str, data: bytes):
        """Handle message received via GATT server."""
        try:
            connected = await self._bluetooth_manager.get_connected_devices() if self._bluetooth_manager else []
            connected_addresses = [d.address for d in connected]
            
            if not self._message_handler:
                logger.warning("Message handler not available, cannot process GATT message")
                return
            
            message, forward_to = await self._message_handler.receive_message(
                data,
                source_device=client_address,
                connected_devices=connected_addresses
            )
            
            # Forward if needed
            if forward_to and message:
                forward_data = await self._message_handler.prepare_for_forwarding(message)
                if forward_data:
                    if self._bluetooth_manager:
                        for target in forward_to:
                            try:
                                await self._bluetooth_manager.send_data(target, forward_data)
                            except Exception as e:
                                logger.warning(f"Failed to forward GATT message to {target}: {e}")
                    if self._gatt_server:
                        try:
                            await self._gatt_server.send_notification(forward_data)
                        except Exception as e:
                            logger.warning(f"Failed to send GATT notification: {e}")
        except Exception as e:
            logger.error(f"Error processing GATT message from {client_address}: {e}", exc_info=True)
            self._terminal.print_error(f"Error processing GATT message: {e}")
    
    async def _on_app_device_found(self, device_info):
        """Handle app device discovery."""
        self._terminal.print_device_found(
            address=device_info.address,
            name=device_info.name,
            rssi=device_info.rssi,
            is_app=True
        )
        
        # Auto-connect if we have available slots
        if self._connection_pool and self._connection_pool.available_slots > 0:
            self._terminal.print_info(f"Auto-connecting to {device_info.address}...")
            try:
                success = await self._bluetooth_manager.connect_to_device(device_info.address)
                if not success:
                    self._terminal.print_warning(f"Auto-connect to {device_info.address} failed")
            except Exception as e:
                self._terminal.print_warning(f"Auto-connect error: {e}")
    
    async def _on_device_found(self, device_info):
        """Handle general device discovery."""
        # Only show in debug mode to avoid spam
        self._terminal.print_debug(
            f"Device: {device_info.address} | {device_info.name or 'Unknown'}"
        )
    
    async def _on_device_lost(self, device_info):
        """Handle device lost."""
        self._terminal.print_debug(f"Device lost: {device_info.address}")
    
    async def _on_message_received(self, message):
        """Handle received message for display."""
        self._terminal.print_message(
            sender=message.sender_name or message.sender_id[:8],
            content=message.content,
            timestamp=message.timestamp,
            is_own=False
        )
    
    # ==================== Lifecycle ====================
    
    async def start(self):
        """Start the application."""
        if self._running:
            return
        
        self._running = True
        logger.info("Starting application components...")
        print()
        print("[START] Starting components...")
        
        # Start GATT server
        if self._gatt_server:
            try:
                await self._gatt_server.start()
                logger.info("GATT server started successfully")
                print("[OK] GATT server started")
            except Exception as e:
                logger.error(f"GATT server failed to start: {e}", exc_info=True)
                print(f"[WARN] GATT server failed: {e}")
        
        # Start Bluetooth manager
        if self._bluetooth_manager:
            try:
                await self._bluetooth_manager.start()
                logger.info("Bluetooth manager started successfully")
                print("[OK] Bluetooth manager started")
            except Exception as e:
                logger.error(f"Bluetooth manager failed to start: {e}", exc_info=True)
                print(f"[WARN] Bluetooth manager failed: {e}")
        
        # Start discovery
        if self._discovery:
            try:
                await self._discovery.start()
                logger.info("Discovery started successfully")
                print("[OK] Discovery started")
            except Exception as e:
                logger.error(f"Discovery failed to start: {e}", exc_info=True)
                print(f"[WARN] Discovery failed: {e}")
        
        # Start connection pool
        if self._connection_pool:
            try:
                await self._connection_pool.start()
                logger.info("Connection pool started successfully")
                print("[OK] Connection pool started")
            except Exception as e:
                logger.error(f"Connection pool failed to start: {e}", exc_info=True)
                print(f"[WARN] Connection pool failed: {e}")
        
        print()
        print("=" * 50)
        print("APPLICATION RUNNING")
        print(f"  GATT Server: {'Running' if self._gatt_server and self._gatt_server.is_running else 'Not running'}")
        print(f"  Discovery:   {'Running' if self._discovery else 'Not running'}")
        print("=" * 50)
        print()
        
        self._terminal.print_startup_info(
            local_address=self._bluetooth_manager.local_address if self._bluetooth_manager else None
        )
        
        # Print separator before dashboard starts
        print("\n" + "=" * 50)
        print("Live dashboard will appear below. Logs will be preserved above.")
        print("=" * 50 + "\n")
        
        # Run terminal input loop (includes live dashboard)
        await self._terminal.start()
    
    async def stop(self):
        """Stop the application."""
        if not self._running:
            return
        
        self._running = False
        
        print("\n[STOP] Stopping components...")
        
        # Stop terminal
        if self._terminal:
            await self._terminal.stop()
        
        # Stop discovery
        if self._discovery:
            await self._discovery.stop()
        
        # Stop Bluetooth manager
        if self._bluetooth_manager:
            await self._bluetooth_manager.stop()
        
        # Stop GATT server
        if self._gatt_server:
            await self._gatt_server.stop()
        
        # Stop connection pool
        if self._connection_pool:
            await self._connection_pool.stop()
        
        self._shutdown_event.set()
        print("[OK] Application stopped")
    
    def request_shutdown(self):
        """Request application shutdown (for signal handlers)."""
        asyncio.create_task(self.stop())


async def main():
    """Main entry point."""
    app = Application()
    
    # Set up signal handlers
    loop = asyncio.get_event_loop()
    
    def signal_handler():
        print("\n[SIGNAL] Shutdown requested...")
        app.request_shutdown()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass
    
    try:
        if not await app.initialize():
            print("[ERROR] Failed to initialize application")
            sys.exit(1)
        
        await app.start()
        
    except KeyboardInterrupt:
        print("\n[INFO] Keyboard interrupt received")
    except Exception as e:
        print(f"[ERROR] Application error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await app.stop()
    
    print("[EXIT] Goodbye!")


if __name__ == "__main__":
    asyncio.run(main())
