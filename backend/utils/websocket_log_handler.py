"""
WebSocket Log Handler for Real-time Log Streaming to Frontend.

Updated to work with async python-socketio.
"""

import logging
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
from collections import deque

# Global log buffer
_log_buffer: deque = deque(maxlen=1000)

# Reference to socketio (set by async_server)
_sio = None


def set_socketio(sio):
    """Set the Socket.IO server reference."""
    global _sio
    _sio = sio


class AsyncWebSocketLogHandler(logging.Handler):
    """
    Log handler that sends logs to connected WebSocket clients.
    
    Works with async python-socketio.
    """
    
    def __init__(self, level=logging.NOTSET):
        super().__init__(level)
        self._enabled = True
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    def emit(self, record: logging.LogRecord):
        """Emit a log record to WebSocket clients."""
        if not self._enabled:
            return
        
        try:
            # Format log message
            log_data = {
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'level': record.levelname,
                'logger': record.name,
                'message': record.getMessage(),
                'time': datetime.fromtimestamp(record.created).strftime('%H:%M:%S.%f')[:-3],
            }
            
            # Add exception info if present
            if record.exc_info:
                log_data['exception'] = self.format(record)
            
            # Add source location
            log_data['source'] = {
                'file': record.filename,
                'line': record.lineno,
                'function': record.funcName,
            }
            
            # Add to buffer
            _log_buffer.append(log_data)
            
            # Emit to all connected clients
            if _sio:
                try:
                    # Get the running loop
                    try:
                        loop = asyncio.get_running_loop()
                        # Schedule the emit as a task
                        asyncio.create_task(self._emit_log(log_data))
                    except RuntimeError:
                        # No running loop - skip WebSocket emission
                        pass
                except Exception:
                    pass
            
        except Exception:
            # Don't let logging errors break the application
            pass
    
    async def _emit_log(self, log_data: Dict[str, Any]):
        """Async emit to WebSocket clients."""
        try:
            if _sio:
                await _sio.emit('log_message', log_data, room='broadcast')
        except Exception:
            pass
    
    def set_enabled(self, enabled: bool):
        """Enable or disable the handler."""
        self._enabled = enabled


def setup_websocket_logging(sio=None):
    """
    Set up WebSocket logging handler.
    
    Args:
        sio: Socket.IO server instance (optional, can be set later).
        
    Returns:
        The log handler instance.
    """
    global _sio
    if sio:
        _sio = sio
    
    # Create and add handler
    handler = AsyncWebSocketLogHandler(level=logging.DEBUG)
    handler.setFormatter(logging.Formatter('%(message)s'))
    
    # Add to root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    
    return handler


def get_log_buffer() -> List[Dict[str, Any]]:
    """Get the current log buffer."""
    return list(_log_buffer)


def clear_log_buffer():
    """Clear the log buffer."""
    _log_buffer.clear()
