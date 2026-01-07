"""
Web module for Bluetooth Mesh Broadcast Application.

Version 2.0: Uses async aiohttp + python-socketio
"""

from .async_server import (
    create_app,
    sio,
    set_bluetooth_manager,
    set_message_handler,
    set_discovery,
    set_gatt_server,
    emit_message_received,
    emit_devices_updated,
    emit_log_message,
    emit_error,
    run_server,
)

__all__ = [
    "create_app",
    "sio",
    "set_bluetooth_manager",
    "set_message_handler",
    "set_discovery",
    "set_gatt_server",
    "emit_message_received",
    "emit_devices_updated",
    "emit_log_message",
    "emit_error",
    "run_server",
]
