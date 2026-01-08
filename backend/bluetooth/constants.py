"""
Bluetooth constants and enumerations.
"""

from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional
import time

# Import config to use consistent UUIDs
try:
    from config import Config
except ImportError:
    # Fallback if config not available
    Config = None


class ConnectionState(Enum):
    """Bluetooth connection states."""
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    DISCONNECTING = auto()
    ERROR = auto()


class DiscoveryState(Enum):
    """Device discovery states."""
    IDLE = auto()
    SCANNING = auto()
    STOPPED = auto()


class MessageType(Enum):
    """Bluetooth message types."""
    BROADCAST = "broadcast"
    HEARTBEAT = "heartbeat"
    ACK = "ack"
    DISCOVERY = "discovery"


@dataclass
class DeviceInfo:
    """Information about a discovered/connected device."""
    
    address: str  # MAC address or BLE address
    name: Optional[str] = None
    rssi: Optional[int] = None  # Signal strength
    state: ConnectionState = ConnectionState.DISCONNECTED
    last_seen: float = 0.0
    last_heartbeat: float = 0.0
    connection_attempts: int = 0
    health_score: float = 1.0  # 0.0 to 1.0
    
    def __post_init__(self):
        if self.last_seen == 0.0:
            self.last_seen = time.time()
    
    def update_seen(self):
        """Update last seen timestamp."""
        self.last_seen = time.time()
    
    def update_heartbeat(self):
        """Update last heartbeat timestamp."""
        self.last_heartbeat = time.time()
        self.health_score = min(1.0, self.health_score + 0.1)
    
    def decrease_health(self, amount: float = 0.1):
        """Decrease health score."""
        self.health_score = max(0.0, self.health_score - amount)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "address": self.address,
            "name": self.name or f"Device-{self.address[-5:].replace(':', '')}",
            "rssi": self.rssi,
            "state": self.state.name,
            "connected": self.state == ConnectionState.CONNECTED,
            "health_score": round(self.health_score, 2),
        }


class _UUIDDescriptor:
    """Descriptor for lazy UUID access from Config."""
    def __init__(self, config_attr, fallback):
        self.config_attr = config_attr
        self.fallback = fallback
        self._value = None
    
    def __get__(self, obj, objtype=None):
        if self._value is None:
            if Config:
                self._value = getattr(Config.bluetooth, self.config_attr)
            else:
                self._value = self.fallback
        return self._value


class BluetoothConstants:
    """Bluetooth protocol constants."""
    
    # Service UUIDs - automatically use Config values for consistency
    SERVICE_UUID = _UUIDDescriptor('SERVICE_UUID', "12345678-1234-5678-1234-56789abcdef0")
    CHARACTERISTIC_UUID = _UUIDDescriptor('CHARACTERISTIC_UUID', "12345678-1234-5678-1234-56789abcdef1")
    
    # Protocol constants
    PROTOCOL_VERSION = 1
    HEADER_SIZE = 4  # bytes
    MAX_PACKET_SIZE = 512  # bytes
    
    # Timing constants (in seconds)
    DEFAULT_SCAN_TIMEOUT = 10.0
    DEFAULT_CONNECTION_TIMEOUT = 30.0
    DEFAULT_HEARTBEAT_INTERVAL = 15.0
    
    # Retry constants
    MAX_RETRY_ATTEMPTS = 3
    RETRY_BACKOFF_BASE = 2.0  # Exponential backoff base
    
    # Health score thresholds
    HEALTH_SCORE_CRITICAL = 0.2
    HEALTH_SCORE_WARNING = 0.5
    HEALTH_SCORE_GOOD = 0.8
