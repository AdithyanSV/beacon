"""
Simple Logging Configuration for Terminal CLI.

Provides consistent logging throughout the application.
Simplified from the web version - no SocketIO or web-specific logging.
"""

import logging
import sys
from typing import Optional, Any, Dict
from datetime import datetime

from config import Config


class SimpleFormatter(logging.Formatter):
    """
    Simple text formatter for terminal output.
    """
    
    # ANSI colors
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m',
    }
    
    def __init__(self, use_colors: bool = True):
        super().__init__(
            fmt='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        self.use_colors = use_colors and sys.stdout.isatty()
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record with optional colors."""
        # Save original levelname
        original_levelname = record.levelname
        
        if self.use_colors:
            color = self.COLORS.get(record.levelname, '')
            reset = self.COLORS['RESET']
            record.levelname = f"{color}{record.levelname}{reset}"
        
        result = super().format(record)
        
        # Restore original levelname
        record.levelname = original_levelname
        
        return result


class SecurityFilter(logging.Filter):
    """
    Filter to redact sensitive information from logs.
    """
    
    SENSITIVE_FIELDS = {
        'password', 'secret', 'token', 'key', 'auth',
        'credential', 'private', 'session_id', 'cookie',
    }
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Filter and redact sensitive data."""
        message = record.getMessage()
        for field in self.SENSITIVE_FIELDS:
            if field.lower() in message.lower():
                import re
                pattern = rf'({field}["\']?\s*[:=]\s*["\']?)([^"\'\s,}}]+)'
                record.msg = re.sub(
                    pattern,
                    r'\1[REDACTED]',
                    str(record.msg),
                    flags=re.IGNORECASE
                )
        return True


class ContextLogger(logging.LoggerAdapter):
    """
    Logger adapter that adds context to all log messages.
    """
    
    def __init__(self, logger: logging.Logger, context: Dict[str, Any] = None):
        super().__init__(logger, context or {})
    
    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        """Add context to log message."""
        if self.extra:
            context_str = ' '.join(f'{k}={v}' for k, v in self.extra.items())
            msg = f"{msg} [{context_str}]"
        return msg, kwargs
    
    def with_context(self, **context) -> 'ContextLogger':
        """Create a new logger with additional context."""
        new_context = {**self.extra, **context}
        return ContextLogger(self.logger, new_context)


def setup_logging() -> None:
    """
    Set up logging configuration for the application.
    """
    # Get log level from config
    log_level = getattr(logging, Config.log.LOG_LEVEL.upper(), logging.INFO)
    
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    # Set formatter
    use_colors = Config.terminal.COLOR_OUTPUT if hasattr(Config, 'terminal') else True
    formatter = SimpleFormatter(use_colors=use_colors)
    console_handler.setFormatter(formatter)
    
    # Add security filter
    console_handler.addFilter(SecurityFilter())
    
    # Add handler to root logger
    root_logger.addHandler(console_handler)
    
    # Add file handler if configured
    if Config.log.LOG_FILE:
        file_handler = logging.FileHandler(Config.log.LOG_FILE)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(SimpleFormatter(use_colors=False))
        file_handler.addFilter(SecurityFilter())
        root_logger.addHandler(file_handler)
    
    # Set level for third-party loggers to reduce noise
    logging.getLogger('bleak').setLevel(logging.ERROR)  # Only show errors
    logging.getLogger('bless').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    logging.getLogger('dbus_fast').setLevel(logging.ERROR)  # Suppress D-Bus message handler errors
    logging.getLogger('dbus-fast').setLevel(logging.ERROR)  # Alternative name
    
    # Suppress specific known non-fatal errors from bleak/BlueZ
    # The KeyError: 'Device' is a known issue where BlueZ sends D-Bus messages
    # without expected keys - it's non-fatal and doesn't affect functionality
    class BleakErrorFilter(logging.Filter):
        """Filter to suppress known non-fatal bleak errors."""
        def filter(self, record):
            # Suppress KeyError: 'Device' messages from bleak/dbus-fast
            if 'Device' in record.getMessage() and 'KeyError' in record.getMessage():
                return False
            return True
    
    # Apply filter to relevant loggers
    error_filter = BleakErrorFilter()
    logging.getLogger('bleak').addFilter(error_filter)
    logging.getLogger('dbus_fast').addFilter(error_filter)
    logging.getLogger('dbus-fast').addFilter(error_filter)


def get_logger(name: str, context: Dict[str, Any] = None) -> ContextLogger:
    """
    Get a logger with optional context.
    
    Args:
        name: Logger name (usually __name__).
        context: Optional context to add to all log messages.
        
    Returns:
        ContextLogger instance.
    """
    logger = logging.getLogger(name)
    return ContextLogger(logger, context)


# Convenience functions for event logging

def log_security_event(
    event_type: str,
    message: str,
    severity: str = 'WARNING',
    **context
) -> None:
    """
    Log a security-related event.
    """
    if not Config.log.LOG_SECURITY_EVENTS:
        return
    
    logger = get_logger('security', {'event_type': event_type, **context})
    level = getattr(logging, severity.upper(), logging.WARNING)
    logger.log(level, message)


def log_connection_event(
    event_type: str,
    device_address: str,
    message: str,
    **context
) -> None:
    """
    Log a connection-related event.
    """
    if not Config.log.LOG_CONNECTION_EVENTS:
        return
    
    logger = get_logger('connection', {
        'event_type': event_type,
        'device_address': device_address,
        **context
    })
    logger.info(message)


def log_message_event(
    event_type: str,
    message_id: str,
    description: str,
    **context
) -> None:
    """
    Log a message-related event.
    """
    if not Config.log.LOG_MESSAGE_EVENTS:
        return
    
    logger = get_logger('message', {
        'event_type': event_type,
        'message_id': message_id,
        **context
    })
    logger.debug(description)
