"""
Configuration settings for Bluetooth Mesh Broadcast Application.

Terminal CLI Edition - Web server configuration removed.
All values can be overridden via environment variables.
"""

import os
from typing import List
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def get_bool_env(key: str, default: bool) -> bool:
    """Get boolean value from environment variable."""
    value = os.getenv(key, str(default)).lower()
    return value in ("true", "1", "yes", "on")


def get_int_env(key: str, default: int) -> int:
    """Get integer value from environment variable."""
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def get_list_env(key: str, default: List[str]) -> List[str]:
    """Get list value from environment variable (comma-separated)."""
    value = os.getenv(key)
    if value:
        return [item.strip() for item in value.split(",")]
    return default


class BluetoothConfig:
    """Bluetooth-related configuration."""
    
    # Service identification
    SERVICE_NAME = "BluetoothMeshBroadcast"
    # Custom UUID for BLE service (128-bit UUID)
    SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"
    # Characteristic UUID for message exchange
    CHARACTERISTIC_UUID = "12345678-1234-5678-1234-56789abcdef1"
    
    # Connection settings
    CONNECTION_TIMEOUT = get_int_env("CONNECTION_TIMEOUT", 30)  # seconds
    MAX_CONCURRENT_CONNECTIONS = get_int_env("MAX_CONCURRENT_CONNECTIONS", 4)
    MAX_RECONNECT_ATTEMPTS = get_int_env("MAX_RECONNECT_ATTEMPTS", 3)
    RECONNECT_DELAY = get_int_env("RECONNECT_DELAY", 30)  # seconds
    
    # Discovery settings (adaptive intervals)
    DISCOVERY_INTERVAL_INITIAL = get_int_env("DISCOVERY_INTERVAL_INITIAL", 5)  # seconds
    DISCOVERY_INTERVAL_MODERATE = get_int_env("DISCOVERY_INTERVAL_MODERATE", 15)  # seconds
    DISCOVERY_INTERVAL_STABLE = get_int_env("DISCOVERY_INTERVAL_STABLE", 30)  # seconds
    DISCOVERY_INTERVAL_NO_DEVICES = get_int_env("DISCOVERY_INTERVAL_NO_DEVICES", 10)  # seconds
    
    # Heartbeat
    HEARTBEAT_INTERVAL = get_int_env("HEARTBEAT_INTERVAL", 15)  # seconds
    HEARTBEAT_TIMEOUT = get_int_env("HEARTBEAT_TIMEOUT", 45)  # seconds
    
    # Device tracking
    DEVICE_LOST_THRESHOLD = get_int_env("DEVICE_LOST_THRESHOLD", 60)  # seconds
    CONNECTION_BLACKLIST_DURATION = get_int_env("CONNECTION_BLACKLIST_DURATION", 60)  # seconds
    
    # Scanner timeouts
    SCANNER_START_TIMEOUT = get_int_env("SCANNER_START_TIMEOUT", 5)  # seconds
    SCANNER_STOP_TIMEOUT = get_int_env("SCANNER_STOP_TIMEOUT", 5)  # seconds


class MessageConfig:
    """Message-related configuration."""
    
    # Size limits
    MAX_MESSAGE_SIZE = get_int_env("MAX_MESSAGE_SIZE", 500)  # bytes
    MAX_CONTENT_LENGTH = get_int_env("MAX_CONTENT_LENGTH", 450)  # characters
    
    # Mesh routing
    MESSAGE_TTL = get_int_env("MESSAGE_TTL", 3)  # hops
    
    # Cache settings
    MESSAGE_CACHE_SIZE = get_int_env("MESSAGE_CACHE_SIZE", 100)  # messages
    MESSAGE_CACHE_TTL = get_int_env("MESSAGE_CACHE_TTL", 300)  # seconds (5 min)
    
    # Rate limiting
    RATE_LIMIT_PER_CONNECTION = get_int_env("RATE_LIMIT_PER_CONNECTION", 10)  # messages/minute
    RATE_LIMIT_PER_DEVICE = get_int_env("RATE_LIMIT_PER_DEVICE", 30)  # messages/minute
    RATE_LIMIT_GLOBAL = get_int_env("RATE_LIMIT_GLOBAL", 100)  # messages/minute


class ResourceConfig:
    """Resource management configuration."""
    
    # Memory limits
    MAX_MEMORY_USAGE_MB = get_int_env("MAX_MEMORY_USAGE_MB", 100)
    MEMORY_WARNING_THRESHOLD = 0.8  # 80%
    MEMORY_ERROR_THRESHOLD = 0.95  # 95%
    
    # Connection limits
    MAX_TOTAL_CONNECTIONS = get_int_env("MAX_TOTAL_CONNECTIONS", 5)  # 4 peer + 1 incoming


class SecurityConfig:
    """Security-related configuration."""
    
    ENABLE_RATE_LIMITING = get_bool_env("ENABLE_RATE_LIMITING", True)
    ENABLE_INPUT_SANITIZATION = get_bool_env("ENABLE_INPUT_SANITIZATION", True)
    
    # Allowed characters in messages (for sanitization)
    # Allow printable ASCII and common Unicode
    MIN_ALLOWED_CHAR = 32  # Space
    MAX_ALLOWED_CHAR = 126  # Tilde
    ALLOW_UNICODE = True
    
    # Block list for content (optional)
    BLOCKED_PATTERNS: List[str] = []


class LogConfig:
    """
    Logging configuration.
    
    NOTE: LOG_FILE is optional and disabled by default.
    The application does NOT persist any data to disk by default.
    All caches and data structures are in-memory only.
    """
    
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT = os.getenv("LOG_FORMAT", "text")
    # Optional file path - set to None to disable file logging (default: no persistence)
    LOG_FILE = os.getenv("LOG_FILE", None)  # None = no file logging, all in-memory
    
    # Security logging
    LOG_SECURITY_EVENTS = get_bool_env("LOG_SECURITY_EVENTS", True)
    LOG_CONNECTION_EVENTS = get_bool_env("LOG_CONNECTION_EVENTS", True)
    LOG_MESSAGE_EVENTS = get_bool_env("LOG_MESSAGE_EVENTS", False)  # Disabled by default for privacy


class TerminalConfig:
    """Terminal UI configuration."""
    
    # Display settings
    MAX_DISPLAYED_MESSAGES = get_int_env("MAX_DISPLAYED_MESSAGES", 50)
    SHOW_DEBUG = get_bool_env("SHOW_DEBUG", False)
    COLOR_OUTPUT = get_bool_env("COLOR_OUTPUT", True)
    
    # Auto-connect behavior
    AUTO_CONNECT = get_bool_env("AUTO_CONNECT", True)
    
    # Prompt
    PROMPT = os.getenv("PROMPT", "> ")


class UIConfig:
    """UI-related configuration (for compatibility)."""
    
    MAX_DISPLAYED_MESSAGES = get_int_env("MAX_DISPLAYED_MESSAGES", 50)
    AUTO_SCROLL = True
    RECONNECT_ATTEMPTS = get_int_env("RECONNECT_ATTEMPTS", 5)
    RECONNECT_DELAY_MS = get_int_env("RECONNECT_DELAY_MS", 3000)  # milliseconds
    UPDATE_INTERVAL_MS = get_int_env("UPDATE_INTERVAL_MS", 1000)  # milliseconds


# Convenience access to all configs
class Config:
    """Main configuration class aggregating all settings."""
    
    bluetooth = BluetoothConfig
    message = MessageConfig
    resource = ResourceConfig
    security = SecurityConfig
    log = LogConfig
    terminal = TerminalConfig
    ui = UIConfig
    
    @classmethod
    def validate(cls) -> bool:
        """Validate configuration settings."""
        errors = []
        
        # Validate message size
        if cls.message.MAX_CONTENT_LENGTH >= cls.message.MAX_MESSAGE_SIZE:
            errors.append("MAX_CONTENT_LENGTH must be less than MAX_MESSAGE_SIZE")
        
        # Validate connection limits
        if cls.bluetooth.MAX_CONCURRENT_CONNECTIONS > cls.resource.MAX_TOTAL_CONNECTIONS:
            errors.append("MAX_CONCURRENT_CONNECTIONS cannot exceed MAX_TOTAL_CONNECTIONS")
        
        # Validate rate limits
        if cls.message.RATE_LIMIT_PER_CONNECTION > cls.message.RATE_LIMIT_PER_DEVICE:
            errors.append("RATE_LIMIT_PER_CONNECTION should not exceed RATE_LIMIT_PER_DEVICE")
        
        if errors:
            for error in errors:
                print(f"Config Error: {error}")
            return False
        
        return True
