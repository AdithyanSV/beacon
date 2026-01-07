"""
Web Security - Rate Limiting and Origin Validation.

Provides security middleware for the Flask application including:
- Origin validation for WebSocket connections
- Rate limiting for API endpoints
- Request validation
"""

from functools import wraps
from typing import Optional, Callable, Any, Dict, List, Set
import time
import threading
from flask import request, abort, g
from flask_socketio import disconnect

from config import Config


class OriginValidator:
    """
    Validates request origins against allowed list.
    """
    
    def __init__(self, allowed_origins: List[str] = None):
        """
        Initialize the validator.
        
        Args:
            allowed_origins: List of allowed origins.
        """
        self._allowed_origins = set(allowed_origins or Config.web.ALLOWED_ORIGINS)
    
    def is_valid_origin(self, origin: str) -> bool:
        """
        Check if an origin is allowed.
        
        Args:
            origin: Origin header value.
            
        Returns:
            True if allowed, False otherwise.
        """
        if not origin:
            # Allow requests without Origin header (same-origin)
            return True
        
        # Normalize origin
        origin = origin.lower().rstrip('/')
        
        # Check against allowed list
        for allowed in self._allowed_origins:
            allowed = allowed.lower().rstrip('/')
            if origin == allowed:
                return True
            
            # Support wildcard subdomains (e.g., *.example.com)
            if allowed.startswith('*.'):
                domain = allowed[2:]
                if origin.endswith(domain):
                    return True
        
        return False
    
    def add_origin(self, origin: str) -> None:
        """Add an origin to the allowed list."""
        self._allowed_origins.add(origin.lower().rstrip('/'))
    
    def remove_origin(self, origin: str) -> None:
        """Remove an origin from the allowed list."""
        self._allowed_origins.discard(origin.lower().rstrip('/'))


class WebSocketRateLimiter:
    """
    Rate limiter specifically for WebSocket connections and events.
    """
    
    def __init__(self):
        self._connection_counts: Dict[str, int] = {}  # sid -> connection count
        self._event_timestamps: Dict[str, Dict[str, List[float]]] = {}  # sid -> event -> timestamps
        self._lock = threading.RLock()
        
        # Limits
        self._max_connections_per_ip = Config.web.MAX_WEBSOCKET_CONNECTIONS
        self._events_per_minute = {
            'send_message': Config.message.RATE_LIMIT_PER_CONNECTION,
            'request_devices': 30,
            'default': 60,
        }
    
    def can_connect(self, client_ip: str) -> bool:
        """
        Check if a new connection is allowed from this IP.
        
        Args:
            client_ip: Client IP address.
            
        Returns:
            True if connection allowed.
        """
        with self._lock:
            count = self._connection_counts.get(client_ip, 0)
            return count < self._max_connections_per_ip
    
    def register_connection(self, sid: str, client_ip: str) -> None:
        """Register a new WebSocket connection."""
        with self._lock:
            self._connection_counts[client_ip] = self._connection_counts.get(client_ip, 0) + 1
            self._event_timestamps[sid] = {}
    
    def unregister_connection(self, sid: str, client_ip: str) -> None:
        """Unregister a WebSocket connection."""
        with self._lock:
            if client_ip in self._connection_counts:
                self._connection_counts[client_ip] = max(0, self._connection_counts[client_ip] - 1)
                if self._connection_counts[client_ip] == 0:
                    del self._connection_counts[client_ip]
            
            if sid in self._event_timestamps:
                del self._event_timestamps[sid]
    
    def check_event_rate(self, sid: str, event: str) -> tuple[bool, Optional[float]]:
        """
        Check if an event is within rate limits.
        
        Args:
            sid: Session ID.
            event: Event name.
            
        Returns:
            Tuple of (allowed, retry_after).
        """
        if not Config.security.ENABLE_RATE_LIMITING:
            return True, None
        
        current_time = time.time()
        window = 60.0  # 1 minute window
        cutoff = current_time - window
        
        # Get limit for this event
        limit = self._events_per_minute.get(event, self._events_per_minute['default'])
        
        with self._lock:
            if sid not in self._event_timestamps:
                self._event_timestamps[sid] = {}
            
            if event not in self._event_timestamps[sid]:
                self._event_timestamps[sid][event] = []
            
            # Clean old timestamps
            timestamps = [t for t in self._event_timestamps[sid][event] if t > cutoff]
            self._event_timestamps[sid][event] = timestamps
            
            # Check limit
            if len(timestamps) >= limit:
                retry_after = timestamps[0] + window - current_time
                return False, retry_after
            
            # Record this event
            self._event_timestamps[sid][event].append(current_time)
            return True, None
    
    def get_remaining(self, sid: str, event: str) -> int:
        """Get remaining rate limit for an event."""
        current_time = time.time()
        window = 60.0
        cutoff = current_time - window
        limit = self._events_per_minute.get(event, self._events_per_minute['default'])
        
        with self._lock:
            if sid not in self._event_timestamps:
                return limit
            
            if event not in self._event_timestamps[sid]:
                return limit
            
            timestamps = [t for t in self._event_timestamps[sid][event] if t > cutoff]
            return max(0, limit - len(timestamps))


class SecurityMiddleware:
    """
    Security middleware for Flask application.
    """
    
    def __init__(self, app=None):
        self._origin_validator = OriginValidator()
        self._ws_rate_limiter = WebSocketRateLimiter()
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize with Flask app."""
        # Add before_request handler
        @app.before_request
        def check_origin():
            origin = request.headers.get('Origin')
            if origin and not self._origin_validator.is_valid_origin(origin):
                abort(403, description="Origin not allowed")
        
        # Store middleware in app context
        app.security_middleware = self
    
    @property
    def origin_validator(self) -> OriginValidator:
        """Get origin validator."""
        return self._origin_validator
    
    @property
    def ws_rate_limiter(self) -> WebSocketRateLimiter:
        """Get WebSocket rate limiter."""
        return self._ws_rate_limiter


def validate_origin(f: Callable) -> Callable:
    """
    Decorator to validate request origin.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        origin = request.headers.get('Origin')
        validator = OriginValidator()
        
        if origin and not validator.is_valid_origin(origin):
            abort(403, description="Origin not allowed")
        
        return f(*args, **kwargs)
    
    return decorated


def rate_limit_ws(event: str):
    """
    Decorator for rate limiting WebSocket events.
    
    Args:
        event: Event name for rate limiting.
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated(*args, **kwargs):
            from flask_socketio import emit
            from flask import request as flask_request
            
            # Get session ID
            sid = getattr(flask_request, 'sid', None)
            if not sid:
                return f(*args, **kwargs)
            
            # Get rate limiter from app context
            app = flask_request.environ.get('flask.app')
            if not app or not hasattr(app, 'security_middleware'):
                return f(*args, **kwargs)
            
            rate_limiter = app.security_middleware.ws_rate_limiter
            
            # Check rate limit
            allowed, retry_after = rate_limiter.check_event_rate(sid, event)
            
            if not allowed:
                emit('error', {
                    'message': 'Rate limit exceeded',
                    'code': 'RATE_LIMIT_EXCEEDED',
                    'retry_after': retry_after,
                })
                return None
            
            return f(*args, **kwargs)
        
        return decorated
    
    return decorator


class RequestValidator:
    """
    Validates incoming requests for security.
    """
    
    @staticmethod
    def validate_json_payload(data: dict, required_fields: List[str] = None) -> tuple[bool, Optional[str]]:
        """
        Validate a JSON payload.
        
        Args:
            data: JSON data to validate.
            required_fields: List of required field names.
            
        Returns:
            Tuple of (is_valid, error_message).
        """
        if not isinstance(data, dict):
            return False, "Invalid payload format"
        
        if required_fields:
            for field in required_fields:
                if field not in data:
                    return False, f"Missing required field: {field}"
        
        return True, None
    
    @staticmethod
    def sanitize_string(value: str, max_length: int = 1000) -> str:
        """
        Sanitize a string value.
        
        Args:
            value: String to sanitize.
            max_length: Maximum allowed length.
            
        Returns:
            Sanitized string.
        """
        if not isinstance(value, str):
            return ""
        
        # Trim to max length
        value = value[:max_length]
        
        # Remove null bytes
        value = value.replace('\x00', '')
        
        return value.strip()
