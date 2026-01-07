"""
Web module for Bluetooth Mesh Broadcast Application.
"""

from .server import create_app, socketio
from .handlers import register_handlers
from .security import SecurityMiddleware, validate_origin

__all__ = [
    "create_app",
    "socketio",
    "register_handlers",
    "SecurityMiddleware",
    "validate_origin",
]
