"""
Message Protocol Definition and Validation.

Defines the structure and validation rules for mesh network messages.
"""

import json
import uuid
import time
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from enum import Enum

from config import Config
from exceptions import MessageValidationError, MessageSizeError
from messaging.sanitizer import MessageSanitizer


class MessageType(Enum):
    """Types of messages in the mesh network."""
    BROADCAST = "broadcast"      # Regular broadcast message
    HEARTBEAT = "heartbeat"      # Keep-alive ping
    ACK = "ack"                  # Acknowledgment
    DISCOVERY = "discovery"      # Discovery announcement
    SYSTEM = "system"           # System message


@dataclass
class Message:
    """
    Represents a message in the mesh network.
    
    Attributes:
        message_id: Unique identifier for the message.
        sender_id: Device ID of the original sender.
        content: Message content (text).
        timestamp: Unix timestamp of message creation.
        ttl: Time-to-live (hop count).
        seen_by: List of device IDs that have seen this message.
        message_type: Type of message.
        sender_name: Human-readable sender name.
    """
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender_id: str = ""
    content: str = ""
    timestamp: float = field(default_factory=time.time)
    ttl: int = field(default_factory=lambda: Config.message.MESSAGE_TTL)
    seen_by: List[str] = field(default_factory=list)
    message_type: MessageType = MessageType.BROADCAST
    sender_name: Optional[str] = None
    
    def __post_init__(self):
        """Post-initialization processing."""
        # Ensure seen_by is a list
        if self.seen_by is None:
            self.seen_by = []
        
        # Add sender to seen_by if not present
        if self.sender_id and self.sender_id not in self.seen_by:
            self.seen_by.append(self.sender_id)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "content": self.content,
            "timestamp": self.timestamp,
            "ttl": self.ttl,
            "seen_by": self.seen_by.copy(),
            "type": self.message_type.value,
            "sender_name": self.sender_name,
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())
    
    def to_bytes(self) -> bytes:
        """Convert to bytes for transmission."""
        return self.to_json().encode('utf-8')
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """Create a Message from a dictionary."""
        message_type = data.get("type", MessageType.BROADCAST.value)
        if isinstance(message_type, str):
            try:
                message_type = MessageType(message_type)
            except ValueError:
                message_type = MessageType.BROADCAST
        
        return cls(
            message_id=data.get("message_id", str(uuid.uuid4())),
            sender_id=data.get("sender_id", ""),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", time.time()),
            ttl=data.get("ttl", Config.message.MESSAGE_TTL),
            seen_by=data.get("seen_by", []),
            message_type=message_type,
            sender_name=data.get("sender_name"),
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> "Message":
        """Create a Message from a JSON string."""
        try:
            data = json.loads(json_str)
            return cls.from_dict(data)
        except json.JSONDecodeError as e:
            raise MessageValidationError(f"Invalid JSON: {e}")
    
    @classmethod
    def from_bytes(cls, data: bytes) -> "Message":
        """Create a Message from bytes."""
        try:
            json_str = data.decode('utf-8')
            return cls.from_json(json_str)
        except UnicodeDecodeError as e:
            raise MessageValidationError(f"Invalid encoding: {e}")
    
    def add_seen_by(self, device_id: str) -> None:
        """Add a device ID to the seen_by list."""
        if device_id and device_id not in self.seen_by:
            self.seen_by.append(device_id)
    
    def has_been_seen_by(self, device_id: str) -> bool:
        """Check if a device has seen this message."""
        return device_id in self.seen_by
    
    def decrement_ttl(self) -> int:
        """Decrement TTL and return new value."""
        self.ttl = max(0, self.ttl - 1)
        return self.ttl
    
    def can_forward(self) -> bool:
        """Check if message can be forwarded (TTL > 0)."""
        return self.ttl > 0
    
    def get_byte_size(self) -> int:
        """Get the size of the message in bytes."""
        return len(self.to_bytes())
    
    def is_expired(self, max_age: float = None) -> bool:
        """Check if message has expired based on age."""
        max_age = max_age or Config.message.MESSAGE_CACHE_TTL
        return (time.time() - self.timestamp) > max_age


class MessageProtocol:
    """
    Handles message protocol operations including validation and creation.
    """
    
    def __init__(self):
        self._sanitizer = MessageSanitizer()
    
    def create_broadcast_message(
        self,
        content: str,
        sender_id: str,
        sender_name: str = None
    ) -> Message:
        """
        Create a new broadcast message.
        
        Args:
            content: Message content.
            sender_id: Sender device ID.
            sender_name: Optional sender name.
            
        Returns:
            New Message object.
            
        Raises:
            MessageValidationError: If content is invalid.
            MessageSizeError: If message exceeds size limits.
        """
        # Sanitize content
        sanitized_content, is_valid, error = self._sanitizer.sanitize_and_validate(content)
        
        if not is_valid:
            raise MessageValidationError(error)
        
        # Create message
        message = Message(
            sender_id=sender_id,
            content=sanitized_content,
            message_type=MessageType.BROADCAST,
            sender_name=MessageSanitizer.sanitize_device_name(sender_name) if sender_name else None,
        )
        
        # Validate size
        byte_size = message.get_byte_size()
        if byte_size > Config.message.MAX_MESSAGE_SIZE:
            raise MessageSizeError(
                f"Message size ({byte_size} bytes) exceeds limit ({Config.message.MAX_MESSAGE_SIZE} bytes)",
                message_id=message.message_id,
                actual_size=byte_size,
                max_size=Config.message.MAX_MESSAGE_SIZE,
            )
        
        return message
    
    def create_heartbeat_message(self, sender_id: str) -> Message:
        """Create a heartbeat message."""
        return Message(
            sender_id=sender_id,
            content="",
            message_type=MessageType.HEARTBEAT,
            ttl=1,  # Heartbeats don't need to propagate
        )
    
    def create_discovery_message(self, sender_id: str, sender_name: str = None) -> Message:
        """Create a discovery announcement message."""
        return Message(
            sender_id=sender_id,
            content="",
            message_type=MessageType.DISCOVERY,
            sender_name=sender_name,
            ttl=2,  # Limited propagation for discovery
        )
    
    def create_system_message(self, content: str, sender_id: str) -> Message:
        """Create a system message."""
        return Message(
            sender_id=sender_id,
            content=content,
            message_type=MessageType.SYSTEM,
            ttl=Config.message.MESSAGE_TTL,
        )
    
    def validate_message(self, message: Message) -> tuple[bool, Optional[str]]:
        """
        Validate a message.
        
        Args:
            message: Message to validate.
            
        Returns:
            Tuple of (is_valid, error_message).
        """
        # Check message ID
        if not message.message_id:
            return False, "Message ID is required"
        
        if not MessageSanitizer.is_valid_uuid(message.message_id):
            return False, "Invalid message ID format"
        
        # Check sender ID
        if not message.sender_id:
            return False, "Sender ID is required"
        
        # Check content for broadcast messages
        if message.message_type == MessageType.BROADCAST:
            if not message.content:
                return False, "Content is required for broadcast messages"
            
            _, is_valid, error = self._sanitizer.sanitize_and_validate(message.content)
            if not is_valid:
                return False, error
        
        # Check TTL
        if message.ttl < 0:
            return False, "TTL cannot be negative"
        
        if message.ttl > Config.message.MESSAGE_TTL:
            return False, f"TTL exceeds maximum ({Config.message.MESSAGE_TTL})"
        
        # Check timestamp
        current_time = time.time()
        if message.timestamp > current_time + 60:  # Allow 1 minute clock skew
            return False, "Message timestamp is in the future"
        
        if message.is_expired():
            return False, "Message has expired"
        
        # Check size
        byte_size = message.get_byte_size()
        if byte_size > Config.message.MAX_MESSAGE_SIZE:
            return False, f"Message size ({byte_size}) exceeds limit"
        
        return True, None
    
    def parse_message(self, data: bytes) -> Message:
        """
        Parse and validate a message from bytes.
        
        Args:
            data: Raw message bytes.
            
        Returns:
            Validated Message object.
            
        Raises:
            MessageValidationError: If message is invalid.
        """
        # Parse
        message = Message.from_bytes(data)
        
        # Validate
        is_valid, error = self.validate_message(message)
        if not is_valid:
            raise MessageValidationError(error, message_id=message.message_id)
        
        return message
    
    def prepare_for_forwarding(self, message: Message, forwarder_id: str) -> Optional[Message]:
        """
        Prepare a message for forwarding.
        
        Args:
            message: Message to forward.
            forwarder_id: ID of the forwarding device.
            
        Returns:
            Message ready for forwarding, or None if cannot forward.
        """
        if not message.can_forward():
            return None
        
        # Create a copy for forwarding
        forwarded = Message(
            message_id=message.message_id,
            sender_id=message.sender_id,
            content=message.content,
            timestamp=message.timestamp,
            ttl=message.ttl - 1,
            seen_by=message.seen_by.copy(),
            message_type=message.message_type,
            sender_name=message.sender_name,
        )
        
        # Add forwarder to seen_by
        forwarded.add_seen_by(forwarder_id)
        
        return forwarded
