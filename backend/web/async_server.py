"""
Async Web Server using aiohttp and python-socketio.

Replaces Flask + eventlet with pure asyncio for proper integration
with bleak and other async Bluetooth libraries.
"""

import os
import asyncio
from typing import Optional, Dict, Any, Callable
from aiohttp import web
import socketio
import aiohttp_cors

from config import Config
from utils.logger import get_logger
from utils.websocket_log_handler import set_socketio, get_log_buffer

logger = get_logger(__name__)

# Create Socket.IO server with async support
sio = socketio.AsyncServer(
    async_mode='aiohttp',
    cors_allowed_origins=Config.web.ALLOWED_ORIGINS,
    ping_timeout=60,
    ping_interval=25,
)

# Set socketio for log handler
set_socketio(sio)

# Store for connected clients
_connected_clients: Dict[str, Dict[str, Any]] = {}

# Component references (set by main.py)
_bluetooth_manager = None
_message_handler = None
_discovery = None
_gatt_server = None


def set_bluetooth_manager(manager):
    """Set the Bluetooth manager reference."""
    global _bluetooth_manager
    _bluetooth_manager = manager


def set_message_handler(handler):
    """Set the message handler reference."""
    global _message_handler
    _message_handler = handler


def set_discovery(discovery):
    """Set the discovery reference."""
    global _discovery
    _discovery = discovery


def set_gatt_server(server):
    """Set the GATT server reference."""
    global _gatt_server
    _gatt_server = server


async def index_handler(request: web.Request) -> web.Response:
    """Serve the main HTML page."""
    frontend_dir = _get_frontend_dir()
    return web.FileResponse(os.path.join(frontend_dir, 'index.html'))


async def health_handler(request: web.Request) -> web.Response:
    """Health check endpoint."""
    return web.json_response({
        'status': 'healthy',
        'service': 'bluetooth-mesh-broadcast'
    })


async def status_handler(request: web.Request) -> web.Response:
    """API status endpoint."""
    status = {
        'status': 'running',
        'version': '2.0.0',
        'async_mode': 'aiohttp',
        'bluetooth': {
            'enabled': _bluetooth_manager is not None,
            'running': False,
            'max_connections': Config.bluetooth.MAX_CONCURRENT_CONNECTIONS,
        },
        'gatt_server': {
            'enabled': _gatt_server is not None,
            'running': _gatt_server.is_running if _gatt_server else False,
        },
        'discovery': {
            'enabled': _discovery is not None,
            'state': 'UNKNOWN',
            'network_state': 'UNKNOWN',
        },
        'limits': {
            'max_message_size': Config.message.MAX_MESSAGE_SIZE,
            'max_content_length': Config.message.MAX_CONTENT_LENGTH,
            'message_ttl': Config.message.MESSAGE_TTL,
        }
    }
    
    if _bluetooth_manager:
        try:
            status['bluetooth']['running'] = getattr(_bluetooth_manager, 'is_running', False)
            connected = await _bluetooth_manager.get_connected_devices()
            status['bluetooth']['connected_devices'] = len(connected)
        except Exception:
            pass
    
    if _discovery:
        try:
            if hasattr(_discovery, 'state') and _discovery.state:
                status['discovery']['state'] = _discovery.state.name
            if hasattr(_discovery, 'network_state') and _discovery.network_state:
                status['discovery']['network_state'] = _discovery.network_state.name
        except Exception:
            pass
    
    return web.json_response(status)


def _get_frontend_dir() -> str:
    """Get the frontend directory path."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(project_root, 'frontend')


def create_app() -> web.Application:
    """
    Create and configure the aiohttp application.
    
    Returns:
        Configured aiohttp Application.
    """
    app = web.Application()
    
    # Attach Socket.IO to the app
    sio.attach(app)
    
    # Set up CORS
    cors = aiohttp_cors.setup(app, defaults={
        origin: aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
        for origin in Config.web.ALLOWED_ORIGINS
    })
    
    # Add routes
    frontend_dir = _get_frontend_dir()
    
    # API routes
    app.router.add_get('/', index_handler)
    app.router.add_get('/health', health_handler)
    app.router.add_get('/api/status', status_handler)
    
    # Static file routes
    app.router.add_static('/css', os.path.join(frontend_dir, 'css'))
    app.router.add_static('/js', os.path.join(frontend_dir, 'js'))
    
    # Apply CORS to routes
    for route in list(app.router.routes()):
        if hasattr(route, 'resource'):
            try:
                cors.add(route)
            except ValueError:
                pass  # Skip routes that can't have CORS added
    
    return app


# ==================== Socket.IO Event Handlers ====================

@sio.event
async def connect(sid, environ):
    """Handle new WebSocket connection."""
    client_ip = environ.get('REMOTE_ADDR', 'unknown')
    
    logger.info(f"Client connected: {sid} from {client_ip}")
    
    # Store client info
    _connected_clients[sid] = {
        'ip': client_ip,
        'connected_at': asyncio.get_event_loop().time(),
    }
    
    # Join the broadcast room
    await sio.enter_room(sid, 'broadcast')
    
    # Send initial state
    await sio.emit('connected', {
        'message': 'Connected to Bluetooth Mesh Broadcast',
        'session_id': sid,
        'limits': {
            'max_message_length': Config.message.MAX_CONTENT_LENGTH,
            'rate_limit': Config.message.RATE_LIMIT_PER_CONNECTION,
        }
    }, room=sid)
    
    # Send current device list
    devices = await _get_devices()
    await sio.emit('devices_updated', {
        'devices': devices,
        'count': len(devices),
    }, room=sid)
    
    # Send recent messages
    messages = await _get_messages()
    if messages:
        await sio.emit('messages_list', {
            'messages': messages,
            'count': len(messages),
        }, room=sid)
    
    # Send log buffer to new client
    try:
        log_buffer = get_log_buffer()
        for log_entry in log_buffer[-100:]:  # Send last 100 logs
            await sio.emit('log_message', log_entry, room=sid)
    except Exception:
        pass


@sio.event
async def disconnect(sid):
    """Handle WebSocket disconnection."""
    logger.info(f"Client disconnected: {sid}")
    
    # Remove from connected clients
    if sid in _connected_clients:
        del _connected_clients[sid]
    
    # Leave the broadcast room
    await sio.leave_room(sid, 'broadcast')


@sio.event
async def send_message(sid, data):
    """Handle message send request from client."""
    if not isinstance(data, dict):
        await sio.emit('error', {
            'message': 'Invalid payload format',
            'code': 'INVALID_PAYLOAD',
        }, room=sid)
        return
    
    content = data.get('content', '').strip()
    
    if not content:
        await sio.emit('error', {
            'message': 'Message content cannot be empty',
            'code': 'EMPTY_CONTENT',
        }, room=sid)
        return
    
    if len(content) > Config.message.MAX_CONTENT_LENGTH:
        content = content[:Config.message.MAX_CONTENT_LENGTH]
    
    if _message_handler:
        try:
            # Create message via handler
            message = await _message_handler.create_message(
                content=content,
                sender_name='You',
                connection_id=sid
            )
            
            # Get connected devices for sending
            connected_devices = []
            if _bluetooth_manager:
                try:
                    devices = await _bluetooth_manager.get_connected_devices()
                    connected_devices = [d.address for d in devices]
                except Exception:
                    pass
            
            # Send message through handler
            targets = await _message_handler.send_message(message, connected_devices)
            
            # Send via Bluetooth to connected devices
            if _bluetooth_manager and targets:
                message_bytes = message.to_bytes()
                for target in targets:
                    try:
                        await _bluetooth_manager.send_data(target, message_bytes)
                    except Exception:
                        pass
            
            # Also broadcast via GATT server notifications
            if _gatt_server and _gatt_server.is_running:
                try:
                    await _gatt_server.broadcast_message(message.to_dict())
                except Exception:
                    pass
            
            # Emit success to sender
            await sio.emit('message_sent', {
                'message_id': message.message_id,
                'timestamp': message.timestamp,
                'success': True,
            }, room=sid)
            
            # Broadcast to all web clients
            await sio.emit('message_received', {
                'message_id': message.message_id,
                'sender_id': message.sender_id,
                'sender_name': 'You',
                'content': message.content,
                'timestamp': message.timestamp,
                'is_own': True,
            }, room='broadcast')
            
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            await sio.emit('error', {
                'message': str(e),
                'code': 'SEND_ERROR',
            }, room=sid)
    else:
        await sio.emit('error', {
            'message': 'Message handler not available',
            'code': 'SERVICE_UNAVAILABLE',
        }, room=sid)


@sio.event
async def request_devices(sid):
    """Handle request for device list."""
    devices = await _get_devices()
    await sio.emit('devices_updated', {
        'devices': devices,
        'count': len(devices),
    }, room=sid)


@sio.event
async def request_messages(sid):
    """Handle request for recent messages."""
    messages = await _get_messages()
    await sio.emit('messages_list', {
        'messages': messages,
        'count': len(messages),
    }, room=sid)


@sio.event
async def request_status(sid):
    """Handle request for system status."""
    status = {
        'bluetooth': {
            'available': _bluetooth_manager is not None,
            'running': False,
        },
        'gatt_server': {
            'available': _gatt_server is not None,
            'running': _gatt_server.is_running if _gatt_server else False,
        },
        'messaging': {
            'available': _message_handler is not None,
        },
        'discovery': {
            'available': _discovery is not None,
            'state': 'UNKNOWN',
        },
        'connected_clients': len(_connected_clients),
    }
    
    if _bluetooth_manager:
        try:
            status['bluetooth']['running'] = getattr(_bluetooth_manager, 'is_running', False)
        except Exception:
            pass
    
    if _discovery:
        try:
            if hasattr(_discovery, 'state') and _discovery.state:
                status['discovery']['state'] = _discovery.state.name
        except Exception:
            pass
    
    await sio.emit('status', status, room=sid)


# ==================== Helper Functions ====================

async def _get_devices() -> list:
    """Get devices list."""
    devices = []
    if _bluetooth_manager:
        try:
            devices_list = await _bluetooth_manager.get_connected_devices()
            devices = [d.to_dict() for d in devices_list]
        except Exception:
            pass
    return devices


async def _get_messages() -> list:
    """Get messages list."""
    messages = []
    if _message_handler:
        try:
            messages_list = await _message_handler.get_recent_messages(50)
            messages = [m.to_dict() for m in messages_list]
        except Exception:
            pass
    return messages


# ==================== Emit Functions ====================

async def emit_message_received(message_dict: dict, is_own: bool = False):
    """Emit a received message to all connected clients."""
    await sio.emit('message_received', {
        **message_dict,
        'is_own': is_own,
    }, room='broadcast')


async def emit_devices_updated(devices: list, count: int):
    """Emit device list update to all connected clients."""
    await sio.emit('devices_updated', {
        'devices': devices,
        'count': count,
    }, room='broadcast')


async def emit_log_message(log_data: dict):
    """Emit a log message to all connected clients."""
    await sio.emit('log_message', log_data, room='broadcast')


async def emit_error(message: str, code: str, sid: str = None):
    """Emit an error to a specific client or all clients."""
    error_data = {
        'message': message,
        'code': code,
    }
    
    if sid:
        await sio.emit('error', error_data, room=sid)
    else:
        await sio.emit('error', error_data, room='broadcast')


# ==================== Server Runner ====================

async def run_server(host: str = None, port: int = None):
    """
    Run the web server.
    
    Args:
        host: Host to bind to.
        port: Port to bind to.
    """
    host = host or Config.web.HOST
    port = port or Config.web.PORT
    
    app = create_app()
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, host, port)
    await site.start()
    
    logger.info(f"Web server running at http://{host}:{port}")
    
    # Keep the server running
    while True:
        await asyncio.sleep(3600)
