"""
WebSocket Event Handlers.

Handles SocketIO events for real-time communication with the frontend.
"""

from typing import Optional, Dict, Any
from flask import request
from flask_socketio import emit, join_room, leave_room
import time
import asyncio
import eventlet

from web.server import socketio
from web.security import rate_limit_ws, RequestValidator
from config import Config


# Store for connected clients
_connected_clients: Dict[str, Dict[str, Any]] = {}

# Reference to app components (set by main.py)
_bluetooth_manager = None
_message_handler = None
_discovery = None


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


def register_handlers(app):
    """
    Register all SocketIO event handlers.
    
    Args:
        app: Flask application.
    """
    # Handlers are registered via decorators below
    pass


def _run_async(coro):
    """
    Run async function in eventlet-compatible way.
    
    Since eventlet monkey-patches asyncio, we need to use a thread pool
    to run the async code without blocking the eventlet greenlet.
    """
    import concurrent.futures
    
    def run_in_thread():
        # Create new event loop in thread (eventlet doesn't interfere here)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    
    # Use thread pool executor to run async code
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_in_thread)
        return future.result(timeout=30)  # 30 second timeout


def _get_devices_sync():
    """Get devices list synchronously."""
    devices = []
    if _bluetooth_manager:
        try:
            devices_list = _run_async(_bluetooth_manager.get_connected_devices())
            devices = [d.to_dict() for d in devices_list]
        except Exception:
            pass
    return devices


def _get_messages_sync():
    """Get messages list synchronously."""
    messages = []
    if _message_handler:
        try:
            messages_list = _run_async(_message_handler.get_recent_messages(50))
            messages = [m.to_dict() for m in messages_list]
        except Exception:
            # Fallback to direct access if available
            if hasattr(_message_handler, '_recent_messages'):
                messages = [m.to_dict() for m in _message_handler._recent_messages[-50:]]
    return messages


@socketio.on('connect')
def handle_connect():
    """Handle new WebSocket connection."""
    sid = request.sid
    client_ip = request.remote_addr
    
    # Get rate limiter from app context
    app = request.environ.get('flask.app')
    if app and hasattr(app, 'security_middleware'):
        rate_limiter = app.security_middleware.ws_rate_limiter
        
        # Check connection limit
        if not rate_limiter.can_connect(client_ip):
            emit('error', {
                'message': 'Too many connections from this IP',
                'code': 'CONNECTION_LIMIT_EXCEEDED',
            })
            return False
        
        # Register connection
        rate_limiter.register_connection(sid, client_ip)
    
    # Store client info
    _connected_clients[sid] = {
        'ip': client_ip,
        'connected_at': time.time(),
    }
    
    # Join the broadcast room
    join_room('broadcast')
    
    # Send initial state
    emit('connected', {
        'message': 'Connected to Bluetooth Mesh Broadcast',
        'session_id': sid,
        'limits': {
            'max_message_length': Config.message.MAX_CONTENT_LENGTH,
            'rate_limit': Config.message.RATE_LIMIT_PER_CONNECTION,
        }
    })
    
    # Send current device list
    devices = _get_devices_sync()
    emit('devices_updated', {
        'devices': devices,
        'count': len(devices),
    })
    
    # Send recent messages
    messages = _get_messages_sync()
    if messages:
        emit('messages_list', {
            'messages': messages,
            'count': len(messages),
        })


@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection."""
    sid = request.sid
    client_ip = request.remote_addr
    
    # Unregister from rate limiter
    app = request.environ.get('flask.app')
    if app and hasattr(app, 'security_middleware'):
        rate_limiter = app.security_middleware.ws_rate_limiter
        rate_limiter.unregister_connection(sid, client_ip)
    
    # Remove from connected clients
    if sid in _connected_clients:
        del _connected_clients[sid]
    
    # Leave the broadcast room
    leave_room('broadcast')


@socketio.on('send_message')
@rate_limit_ws('send_message')
def handle_send_message(data):
    """
    Handle message send request from client.
    
    Expected data:
        {
            "content": "message text"
        }
    """
    sid = request.sid
    
    # Validate payload
    is_valid, error = RequestValidator.validate_json_payload(data, ['content'])
    if not is_valid:
        emit('error', {
            'message': error,
            'code': 'INVALID_PAYLOAD',
        })
        return
    
    content = RequestValidator.sanitize_string(
        data.get('content', ''),
        max_length=Config.message.MAX_CONTENT_LENGTH
    )
    
    if not content:
        emit('error', {
            'message': 'Message content cannot be empty',
            'code': 'EMPTY_CONTENT',
        })
        return
    
    # Create and send message using proper message handler
    if _message_handler:
        try:
            # Use message handler to create message (includes rate limiting, validation)
            message = _run_async(
                _message_handler.create_message(
                    content=content,
                    sender_name='You',
                    connection_id=sid
                )
            )
            
            # Get connected devices for sending
            connected_devices = []
            if _bluetooth_manager:
                try:
                    devices = _run_async(_bluetooth_manager.get_connected_devices())
                    connected_devices = [d.address for d in devices]
                except Exception:
                    pass
            
            # Send message through handler (includes routing)
            targets = _run_async(
                _message_handler.send_message(message, connected_devices)
            )
            
            # Send via Bluetooth to connected devices
            if _bluetooth_manager and targets:
                message_bytes = message.to_bytes()
                for target in targets:
                    try:
                        _run_async(_bluetooth_manager.send_data(target, message_bytes))
                    except Exception as e:
                        # Log but continue
                        pass
            
            # Emit success to sender
            emit('message_sent', {
                'message_id': message.message_id,
                'timestamp': message.timestamp,
                'success': True,
            })
            
            # Broadcast to all web clients
            socketio.emit('message_received', {
                'message_id': message.message_id,
                'sender_id': message.sender_id,
                'sender_name': 'You',
                'content': message.content,
                'timestamp': message.timestamp,
                'is_own': True,
            }, room='broadcast')
            
        except Exception as e:
            error_msg = str(e)
            error_code = 'SEND_ERROR'
            
            # Check for specific error types
            from exceptions import MessageRateLimitError, MessageValidationError, MessageSizeError
            if isinstance(e, MessageRateLimitError):
                error_code = 'RATE_LIMIT_EXCEEDED'
                error_msg = f"Rate limit exceeded. Please wait {int(e.retry_after or 60)} seconds."
            elif isinstance(e, MessageValidationError):
                error_code = 'VALIDATION_ERROR'
            elif isinstance(e, MessageSizeError):
                error_code = 'MESSAGE_TOO_LARGE'
            
            emit('error', {
                'message': error_msg,
                'code': error_code,
            })
    else:
        emit('error', {
            'message': 'Message handler not available',
            'code': 'SERVICE_UNAVAILABLE',
        })


@socketio.on('request_devices')
@rate_limit_ws('request_devices')
def handle_request_devices():
    """Handle request for device list."""
    devices = _get_devices_sync()
    emit('devices_updated', {
        'devices': devices,
        'count': len(devices),
    })


@socketio.on('request_messages')
@rate_limit_ws('request_messages')
def handle_request_messages():
    """Handle request for recent messages."""
    messages = _get_messages_sync()
    emit('messages_list', {
        'messages': messages,
        'count': len(messages),
    })


@socketio.on('request_status')
def handle_request_status():
    """Handle request for system status."""
    status = {
        'bluetooth': {
            'available': _bluetooth_manager is not None,
            'running': False,
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
    
    # Safely access attributes
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
    
    emit('status', status)


# Functions to emit events from other parts of the application

def emit_message_received(message_dict: dict, is_own: bool = False):
    """
    Emit a received message to all connected clients.
    
    Args:
        message_dict: Message dictionary.
        is_own: Whether this is the sender's own message.
    """
    socketio.emit('message_received', {
        **message_dict,
        'is_own': is_own,
    }, room='broadcast')


def emit_devices_updated(devices: list, count: int):
    """
    Emit device list update to all connected clients.
    
    Args:
        devices: List of device dictionaries.
        count: Total device count.
    """
    socketio.emit('devices_updated', {
        'devices': devices,
        'count': count,
    }, room='broadcast')


def emit_error(message: str, code: str, sid: str = None):
    """
    Emit an error to a specific client or all clients.
    
    Args:
        message: Error message.
        code: Error code.
        sid: Optional session ID (None for broadcast).
    """
    error_data = {
        'message': message,
        'code': code,
    }
    
    if sid:
        socketio.emit('error', error_data, room=sid)
    else:
        socketio.emit('error', error_data, room='broadcast')


def emit_status_update(status: dict):
    """
    Emit a status update to all connected clients.
    
    Args:
        status: Status dictionary.
    """
    socketio.emit('status_update', status, room='broadcast')
