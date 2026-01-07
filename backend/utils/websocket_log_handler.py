"""
WebSocket Log Handler for Real-time Log Streaming to Frontend.
"""

import logging
import json
from datetime import datetime
from typing import Optional
from flask_socketio import SocketIO

# Global socketio instance (set by main.py)
_socketio: Optional[SocketIO] = None
_log_buffer = []
_max_buffer_size = 1000


class WebSocketLogHandler(logging.Handler):
    """
    Log handler that sends logs to connected WebSocket clients.
    """
    
    def __init__(self, level=logging.NOTSET):
        super().__init__(level)
        self._enabled = True
    
    def emit(self, record: logging.LogRecord):
        """Emit a log record to WebSocket clients."""
        if not self._enabled or not _socketio:
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
            if len(_log_buffer) > _max_buffer_size:
                _log_buffer.pop(0)
            
            # Emit to all connected clients
            _socketio.emit('log_message', log_data, room='broadcast')
            
        except Exception:
            # Don't let logging errors break the application
            pass
    
    def set_enabled(self, enabled: bool):
        """Enable or disable the handler."""
        self._enabled = enabled


def setup_websocket_logging(socketio_instance: SocketIO):
    """Set up WebSocket logging handler."""
    global _socketio
    _socketio = socketio_instance
    
    # Create and add handler
    handler = WebSocketLogHandler(level=logging.DEBUG)
    handler.setFormatter(logging.Formatter('%(message)s'))
    
    # Add to root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    
    return handler


def get_log_buffer() -> list:
    """Get the current log buffer."""
    return _log_buffer.copy()


def clear_log_buffer():
    """Clear the log buffer."""
    global _log_buffer
    _log_buffer.clear()
