"""
Structured Logging Configuration.

Provides consistent logging throughout the application with:
- Structured JSON logging option
- Security-aware logging (no sensitive data)
- Log level configuration
"""

import logging
import sys
from typing import Optional, Any, Dict
import json
from datetime import datetime

from config import Config


class JSONFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        # Add extra fields
        if hasattr(record, 'extra_data'):
            log_data['data'] = record.extra_data
        
        # Add source location
        log_data['source'] = {
            'file': record.filename,
            'line': record.lineno,
            'function': record.funcName,
        }
        
        return json.dumps(log_data)


class TextFormatter(logging.Formatter):
    """
    Human-readable text formatter.
    """
    
    def __init__(self):
        super().__init__(
            fmt='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )


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
        # Redact sensitive data in message
        message = record.getMessage()
        for field in self.SENSITIVE_FIELDS:
            if field.lower() in message.lower():
                # Simple redaction - replace values after = or :
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
        extra = kwargs.get('extra', {})
        extra['extra_data'] = {**self.extra, **extra.get('extra_data', {})}
        kwargs['extra'] = extra
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
    
    # Set formatter based on config
    if Config.log.LOG_FORMAT.lower() == 'json':
        formatter = JSONFormatter()
    else:
        formatter = TextFormatter()
    
    console_handler.setFormatter(formatter)
    
    # Add security filter
    console_handler.addFilter(SecurityFilter())
    
    # Add handler to root logger
    root_logger.addHandler(console_handler)
    
    # Add file handler if configured
    if Config.log.LOG_FILE:
        file_handler = logging.FileHandler(Config.log.LOG_FILE)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(SecurityFilter())
        root_logger.addHandler(file_handler)
    
    # Set level for third-party loggers
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('engineio').setLevel(logging.WARNING)
    logging.getLogger('socketio').setLevel(logging.WARNING)
    logging.getLogger('bleak').setLevel(logging.WARNING)


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


# Convenience functions for security logging

def log_security_event(
    event_type: str,
    message: str,
    severity: str = 'WARNING',
    **context
) -> None:
    """
    Log a security-related event.
    
    Args:
        event_type: Type of security event.
        message: Event description.
        severity: Log level (INFO, WARNING, ERROR).
        **context: Additional context.
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
    
    Args:
        event_type: Type of connection event.
        device_address: Device address.
        message: Event description.
        **context: Additional context.
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
    
    Args:
        event_type: Type of message event.
        message_id: Message ID.
        description: Event description.
        **context: Additional context.
    """
    if not Config.log.LOG_MESSAGE_EVENTS:
        return
    
    logger = get_logger('message', {
        'event_type': event_type,
        'message_id': message_id,
        **context
    })
    logger.debug(description)
