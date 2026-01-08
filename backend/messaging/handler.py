"""
Message Handler - Central coordinator for message operations.

Integrates sanitization, protocol, routing, and rate limiting.
"""

import asyncio
from typing import Optional, Callable, Any, List, Dict, Tuple
from dataclasses import dataclass, field
import time

from config import Config
from exceptions import (
    MessageValidationError,
    MessageSizeError,
    MessageRateLimitError,
)
from messaging.sanitizer import MessageSanitizer
from messaging.protocol import Message, MessageProtocol, MessageType
from messaging.router import MeshRouter
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class MessageStats:
    """Statistics for message handling."""
    total_received: int = 0
    total_sent: int = 0
    total_forwarded: int = 0
    validation_errors: int = 0
    rate_limit_errors: int = 0
    size_errors: int = 0


class RateLimitTracker:
    """
    Simple rate limit tracker for message sending.
    """
    
    def __init__(self):
        self._connection_counts: Dict[str, List[float]] = {}  # connection_id -> timestamps
        self._device_counts: Dict[str, List[float]] = {}  # device_id -> timestamps
        self._global_timestamps: List[float] = []
        self._lock = asyncio.Lock()
    
    async def check_and_record(
        self,
        connection_id: str = None,
        device_id: str = None
    ) -> Tuple[bool, Optional[str], Optional[float]]:
        """
        Check rate limits and record if allowed.
        
        Returns:
            Tuple of (allowed, limit_type, retry_after).
        """
        if not Config.security.ENABLE_RATE_LIMITING:
            return True, None, None
        
        current_time = time.time()
        window = 60.0  # 1 minute window
        
        async with self._lock:
            # Clean old entries
            cutoff = current_time - window
            
            # Check global limit
            self._global_timestamps = [t for t in self._global_timestamps if t > cutoff]
            if len(self._global_timestamps) >= Config.message.RATE_LIMIT_GLOBAL:
                retry_after = self._global_timestamps[0] + window - current_time
                return False, "global", retry_after
            
            # Check device limit
            if device_id:
                if device_id not in self._device_counts:
                    self._device_counts[device_id] = []
                self._device_counts[device_id] = [
                    t for t in self._device_counts[device_id] if t > cutoff
                ]
                if len(self._device_counts[device_id]) >= Config.message.RATE_LIMIT_PER_DEVICE:
                    retry_after = self._device_counts[device_id][0] + window - current_time
                    return False, "device", retry_after
            
            # Check connection limit
            if connection_id:
                if connection_id not in self._connection_counts:
                    self._connection_counts[connection_id] = []
                self._connection_counts[connection_id] = [
                    t for t in self._connection_counts[connection_id] if t > cutoff
                ]
                if len(self._connection_counts[connection_id]) >= Config.message.RATE_LIMIT_PER_CONNECTION:
                    retry_after = self._connection_counts[connection_id][0] + window - current_time
                    return False, "connection", retry_after
            
            # Record this request
            self._global_timestamps.append(current_time)
            if device_id:
                self._device_counts[device_id].append(current_time)
            if connection_id:
                self._connection_counts[connection_id].append(current_time)
            
            return True, None, None
    
    async def get_remaining(
        self,
        connection_id: str = None,
        device_id: str = None
    ) -> Dict[str, int]:
        """Get remaining rate limit allowances."""
        current_time = time.time()
        window = 60.0
        cutoff = current_time - window
        
        async with self._lock:
            # Clean and count
            self._global_timestamps = [t for t in self._global_timestamps if t > cutoff]
            global_remaining = Config.message.RATE_LIMIT_GLOBAL - len(self._global_timestamps)
            
            device_remaining = Config.message.RATE_LIMIT_PER_DEVICE
            if device_id and device_id in self._device_counts:
                self._device_counts[device_id] = [
                    t for t in self._device_counts[device_id] if t > cutoff
                ]
                device_remaining = Config.message.RATE_LIMIT_PER_DEVICE - len(self._device_counts[device_id])
            
            connection_remaining = Config.message.RATE_LIMIT_PER_CONNECTION
            if connection_id and connection_id in self._connection_counts:
                self._connection_counts[connection_id] = [
                    t for t in self._connection_counts[connection_id] if t > cutoff
                ]
                connection_remaining = Config.message.RATE_LIMIT_PER_CONNECTION - len(self._connection_counts[connection_id])
            
            return {
                "global": max(0, global_remaining),
                "device": max(0, device_remaining),
                "connection": max(0, connection_remaining),
            }


class MessageHandler:
    """
    Central message handler coordinating all message operations.
    """
    
    def __init__(self, local_device_id: str = None):
        """
        Initialize the message handler.
        
        Args:
            local_device_id: ID of the local device.
        """
        self._local_device_id = local_device_id
        
        # Components
        self._sanitizer = MessageSanitizer()
        self._protocol = MessageProtocol()
        self._router = MeshRouter(local_device_id)
        self._rate_limiter = RateLimitTracker()
        
        # Statistics
        self._stats = MessageStats()
        
        # Recent messages for UI (limited buffer)
        self._recent_messages: List[Message] = []
        self._max_recent = Config.ui.MAX_DISPLAYED_MESSAGES
        self._messages_lock = asyncio.Lock()
        
        # Callbacks
        self._on_message_received: Optional[Callable[[Message], Any]] = None
        self._on_message_sent: Optional[Callable[[Message], Any]] = None
        self._on_error: Optional[Callable[[Exception], Any]] = None
    
    @property
    def local_device_id(self) -> Optional[str]:
        """Get local device ID."""
        return self._local_device_id
    
    @local_device_id.setter
    def local_device_id(self, value: str) -> None:
        """Set local device ID."""
        self._local_device_id = value
        self._router.local_device_id = value
    
    @property
    def stats(self) -> MessageStats:
        """Get message statistics."""
        return self._stats
    
    async def create_message(
        self,
        content: str,
        sender_name: str = None,
        connection_id: str = None
    ) -> Message:
        """
        Create a new message for sending.
        
        Args:
            content: Message content.
            sender_name: Optional sender name.
            connection_id: Optional connection ID for rate limiting.
            
        Returns:
            Created Message object.
            
        Raises:
            MessageValidationError: If content is invalid.
            MessageSizeError: If message is too large.
            MessageRateLimitError: If rate limit exceeded.
        """
        # Check rate limit
        allowed, limit_type, retry_after = await self._rate_limiter.check_and_record(
            connection_id=connection_id,
            device_id=self._local_device_id,
        )
        
        if not allowed:
            self._stats.rate_limit_errors += 1
            raise MessageRateLimitError(
                f"Rate limit exceeded ({limit_type})",
                limit_type=limit_type,
                retry_after=retry_after,
            )
        
        try:
            # Create message using protocol
            message = self._protocol.create_broadcast_message(
                content=content,
                sender_id=self._local_device_id or "",
                sender_name=sender_name,
            )
            
            return message
            
        except MessageValidationError as e:
            self._stats.validation_errors += 1
            raise
        except MessageSizeError as e:
            self._stats.size_errors += 1
            raise
    
    async def send_message(
        self,
        message: Message,
        connected_devices: List[str] = None
    ) -> List[str]:
        """
        Send a message to the mesh network.
        
        Args:
            message: Message to send.
            connected_devices: List of connected device IDs.
            
        Returns:
            List of devices to send to.
        """
        connected_devices = connected_devices or []
        
        # Originate through router
        targets = await self._router.originate_message(message, connected_devices)
        
        # Add to recent messages
        await self._add_recent_message(message)
        
        # Update stats
        self._stats.total_sent += 1
        
        # Notify callback
        if self._on_message_sent:
            await self._safe_callback(self._on_message_sent, message)
        
        return targets
    
    async def receive_message(
        self,
        data: bytes,
        source_device: str,
        connected_devices: List[str] = None
    ) -> Tuple[Optional[Message], List[str]]:
        """
        Process a received message.
        
        Args:
            data: Raw message bytes.
            source_device: Device that sent the message.
            connected_devices: List of connected device IDs for forwarding.
            
        Returns:
            Tuple of (message if should display, devices to forward to).
        """
        connected_devices = connected_devices or []
        
        try:
            # Parse and validate
            message = self._protocol.parse_message(data)
            
            # Route through mesh
            should_process, forward_to = await self._router.route_message(
                message=message,
                source_device=source_device,
                connected_devices=connected_devices,
            )
            
            if should_process:
                # Add to recent messages
                await self._add_recent_message(message)
                
                # Update stats
                self._stats.total_received += 1
                
                # Notify callback
                if self._on_message_received:
                    await self._safe_callback(self._on_message_received, message)
                
                return message, forward_to
            
            if forward_to:
                self._stats.total_forwarded += 1
            
            return None, forward_to
            
        except MessageValidationError as e:
            self._stats.validation_errors += 1
            logger.warning(f"Message validation error from {source_device}: {e}")
            if self._on_error:
                await self._safe_callback(self._on_error, e)
            return None, []
        except Exception as e:
            logger.error(f"Unexpected error processing message from {source_device}: {e}", exc_info=True)
            if self._on_error:
                await self._safe_callback(self._on_error, e)
            return None, []
    
    async def prepare_for_forwarding(
        self,
        message: Message
    ) -> Optional[bytes]:
        """
        Prepare a message for forwarding.
        
        Args:
            message: Message to forward.
            
        Returns:
            Bytes to send, or None if cannot forward.
        """
        forwarded = self._protocol.prepare_for_forwarding(
            message,
            self._local_device_id or ""
        )
        
        if forwarded:
            return forwarded.to_bytes()
        
        return None
    
    async def get_recent_messages(self, limit: int = None) -> List[Message]:
        """Get recent messages."""
        limit = limit or self._max_recent
        async with self._messages_lock:
            return self._recent_messages[-limit:]
    
    async def clear_recent_messages(self) -> None:
        """Clear recent messages."""
        async with self._messages_lock:
            self._recent_messages.clear()
    
    async def _add_recent_message(self, message: Message) -> None:
        """Add a message to the recent messages buffer."""
        async with self._messages_lock:
            self._recent_messages.append(message)
            
            # Trim if needed
            if len(self._recent_messages) > self._max_recent:
                self._recent_messages = self._recent_messages[-self._max_recent:]
    
    async def get_rate_limit_status(
        self,
        connection_id: str = None
    ) -> Dict[str, int]:
        """Get current rate limit status."""
        return await self._rate_limiter.get_remaining(
            connection_id=connection_id,
            device_id=self._local_device_id,
        )
    
    def get_router_stats(self) -> dict:
        """Get router statistics."""
        stats = self._router.stats
        return {
            "messages_received": stats.messages_received,
            "messages_forwarded": stats.messages_forwarded,
            "messages_dropped_duplicate": stats.messages_dropped_duplicate,
            "messages_dropped_ttl": stats.messages_dropped_ttl,
            "messages_dropped_seen": stats.messages_dropped_seen,
            "messages_originated": stats.messages_originated,
            "cache_hits": stats.cache_hits,
            "cache_misses": stats.cache_misses,
            "cache_size": self._router.get_cache_size(),
        }
    
    def set_message_received_callback(self, callback: Callable[[Message], Any]) -> None:
        """Set callback for received messages."""
        self._on_message_received = callback
    
    def set_message_sent_callback(self, callback: Callable[[Message], Any]) -> None:
        """Set callback for sent messages."""
        self._on_message_sent = callback
    
    def set_error_callback(self, callback: Callable[[Exception], Any]) -> None:
        """Set callback for errors."""
        self._on_error = callback
    
    async def _safe_callback(self, callback: Callable, *args) -> None:
        """Safely execute a callback."""
        try:
            result = callback(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            pass
