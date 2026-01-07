"""
Utility Helper Functions.

Common utility functions used throughout the application.
"""

import uuid
import time
import hashlib
from datetime import datetime
from typing import Optional


def generate_device_name(address: str = None) -> str:
    """
    Generate a human-readable device name.
    
    Args:
        address: Optional device address to derive name from.
        
    Returns:
        Generated device name.
    """
    if address:
        # Use last 4 characters of address
        suffix = address.replace(':', '').replace('-', '')[-4:].upper()
        return f"Device-{suffix}"
    else:
        # Generate random suffix
        suffix = uuid.uuid4().hex[:4].upper()
        return f"Device-{suffix}"


def generate_message_id() -> str:
    """
    Generate a unique message ID.
    
    Returns:
        UUID string.
    """
    return str(uuid.uuid4())


def format_timestamp(timestamp: float = None, format_str: str = "%H:%M:%S") -> str:
    """
    Format a Unix timestamp for display.
    
    Args:
        timestamp: Unix timestamp (default: current time).
        format_str: strftime format string.
        
    Returns:
        Formatted timestamp string.
    """
    if timestamp is None:
        timestamp = time.time()
    
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime(format_str)


def format_timestamp_iso(timestamp: float = None) -> str:
    """
    Format a Unix timestamp as ISO 8601.
    
    Args:
        timestamp: Unix timestamp (default: current time).
        
    Returns:
        ISO 8601 formatted string.
    """
    if timestamp is None:
        timestamp = time.time()
    
    dt = datetime.fromtimestamp(timestamp)
    return dt.isoformat() + 'Z'


def format_bytes(size: int) -> str:
    """
    Format byte size for human readability.
    
    Args:
        size: Size in bytes.
        
    Returns:
        Human-readable size string.
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def format_duration(seconds: float) -> str:
    """
    Format duration for human readability.
    
    Args:
        seconds: Duration in seconds.
        
    Returns:
        Human-readable duration string.
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def truncate_string(s: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate a string to a maximum length.
    
    Args:
        s: String to truncate.
        max_length: Maximum length.
        suffix: Suffix to add if truncated.
        
    Returns:
        Truncated string.
    """
    if len(s) <= max_length:
        return s
    
    return s[:max_length - len(suffix)] + suffix


def hash_string(s: str) -> str:
    """
    Create a short hash of a string.
    
    Args:
        s: String to hash.
        
    Returns:
        8-character hex hash.
    """
    return hashlib.sha256(s.encode()).hexdigest()[:8]


def is_valid_mac_address(address: str) -> bool:
    """
    Check if a string is a valid MAC address format.
    
    Args:
        address: Address string to check.
        
    Returns:
        True if valid MAC address format.
    """
    import re
    
    # Support both : and - separators
    patterns = [
        r'^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$',  # XX:XX:XX:XX:XX:XX
        r'^([0-9A-Fa-f]{2}-){5}[0-9A-Fa-f]{2}$',  # XX-XX-XX-XX-XX-XX
    ]
    
    for pattern in patterns:
        if re.match(pattern, address):
            return True
    
    return False


def normalize_mac_address(address: str) -> Optional[str]:
    """
    Normalize a MAC address to uppercase with colons.
    
    Args:
        address: MAC address string.
        
    Returns:
        Normalized MAC address or None if invalid.
    """
    if not address:
        return None
    
    # Remove separators and convert to uppercase
    cleaned = address.replace(':', '').replace('-', '').upper()
    
    # Check length
    if len(cleaned) != 12:
        return None
    
    # Check if all hex
    try:
        int(cleaned, 16)
    except ValueError:
        return None
    
    # Format with colons
    return ':'.join(cleaned[i:i+2] for i in range(0, 12, 2))


def clamp(value: float, min_value: float, max_value: float) -> float:
    """
    Clamp a value between min and max.
    
    Args:
        value: Value to clamp.
        min_value: Minimum allowed value.
        max_value: Maximum allowed value.
        
    Returns:
        Clamped value.
    """
    return max(min_value, min(max_value, value))


def retry_with_backoff(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0
):
    """
    Decorator for retrying a function with exponential backoff.
    
    Args:
        max_attempts: Maximum number of attempts.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay in seconds.
    """
    import asyncio
    from functools import wraps
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            delay = base_delay
            
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(delay)
                        delay = min(delay * 2, max_delay)
            
            raise last_exception
        
        return wrapper
    
    return decorator
