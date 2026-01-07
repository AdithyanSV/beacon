"""
Thread-Safe Mesh Router with LRU Cache.

Handles message routing through the mesh network with:
- Deduplication using LRU+TTL cache
- Thread-safe operations
- Loop prevention
- Intelligent forwarding decisions
"""

import asyncio
import threading
from typing import Dict, List, Optional, Set, Callable, Any, Tuple
from dataclasses import dataclass, field
import time

from cachetools import TTLCache

from config import Config
from exceptions import MessageRoutingError
from messaging.protocol import Message, MessageType


@dataclass
class RoutingStats:
    """Statistics for routing operations."""
    messages_received: int = 0
    messages_forwarded: int = 0
    messages_dropped_duplicate: int = 0
    messages_dropped_ttl: int = 0
    messages_dropped_seen: int = 0
    messages_originated: int = 0
    cache_hits: int = 0
    cache_misses: int = 0


class ThreadSafeCache:
    """
    Thread-safe wrapper around TTLCache for message deduplication.
    """
    
    def __init__(self, maxsize: int, ttl: float):
        """
        Initialize the cache.
        
        Args:
            maxsize: Maximum number of entries.
            ttl: Time-to-live in seconds.
        """
        self._cache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = threading.RLock()
    
    def get(self, key: str) -> Optional[Any]:
        """Get a value from the cache."""
        with self._lock:
            return self._cache.get(key)
    
    def set(self, key: str, value: Any) -> None:
        """Set a value in the cache."""
        with self._lock:
            self._cache[key] = value
    
    def contains(self, key: str) -> bool:
        """Check if key exists in cache."""
        with self._lock:
            return key in self._cache
    
    def delete(self, key: str) -> bool:
        """Delete a key from the cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> None:
        """Clear the cache."""
        with self._lock:
            self._cache.clear()
    
    def size(self) -> int:
        """Get current cache size."""
        with self._lock:
            return len(self._cache)
    
    def expire(self) -> None:
        """Manually trigger expiration of old entries."""
        with self._lock:
            self._cache.expire()


@dataclass
class CachedMessage:
    """Cached message entry with metadata."""
    message_id: str
    sender_id: str
    received_at: float = field(default_factory=time.time)
    forwarded_to: Set[str] = field(default_factory=set)
    forward_count: int = 0


class MeshRouter:
    """
    Thread-safe mesh router for message propagation.
    
    Implements flooding-based routing with deduplication and loop prevention.
    """
    
    def __init__(self, local_device_id: str = None):
        """
        Initialize the router.
        
        Args:
            local_device_id: ID of the local device.
        """
        self._local_device_id = local_device_id
        
        # Message cache for deduplication (thread-safe)
        self._message_cache = ThreadSafeCache(
            maxsize=Config.message.MESSAGE_CACHE_SIZE,
            ttl=Config.message.MESSAGE_CACHE_TTL
        )
        
        # Async lock for routing operations
        self._routing_lock = asyncio.Lock()
        
        # Statistics
        self._stats = RoutingStats()
        self._stats_lock = threading.Lock()
        
        # Callbacks
        self._on_message_for_local: Optional[Callable[[Message], Any]] = None
        self._on_message_to_forward: Optional[Callable[[Message, List[str]], Any]] = None
    
    @property
    def local_device_id(self) -> Optional[str]:
        """Get local device ID."""
        return self._local_device_id
    
    @local_device_id.setter
    def local_device_id(self, value: str) -> None:
        """Set local device ID."""
        self._local_device_id = value
    
    @property
    def stats(self) -> RoutingStats:
        """Get routing statistics."""
        with self._stats_lock:
            return RoutingStats(
                messages_received=self._stats.messages_received,
                messages_forwarded=self._stats.messages_forwarded,
                messages_dropped_duplicate=self._stats.messages_dropped_duplicate,
                messages_dropped_ttl=self._stats.messages_dropped_ttl,
                messages_dropped_seen=self._stats.messages_dropped_seen,
                messages_originated=self._stats.messages_originated,
                cache_hits=self._stats.cache_hits,
                cache_misses=self._stats.cache_misses,
            )
    
    async def route_message(
        self,
        message: Message,
        source_device: str = None,
        connected_devices: List[str] = None
    ) -> Tuple[bool, List[str]]:
        """
        Route a message through the mesh network.
        
        Args:
            message: Message to route.
            source_device: Device that sent us this message (None if originated locally).
            connected_devices: List of connected device IDs to potentially forward to.
            
        Returns:
            Tuple of (should_process_locally, devices_to_forward_to).
        """
        connected_devices = connected_devices or []
        
        async with self._routing_lock:
            with self._stats_lock:
                self._stats.messages_received += 1
            
            # Check if we've seen this message before
            if self._is_duplicate(message.message_id):
                with self._stats_lock:
                    self._stats.messages_dropped_duplicate += 1
                    self._stats.cache_hits += 1
                return False, []
            
            with self._stats_lock:
                self._stats.cache_misses += 1
            
            # Check if we're in the seen_by list
            if self._local_device_id and message.has_been_seen_by(self._local_device_id):
                with self._stats_lock:
                    self._stats.messages_dropped_seen += 1
                return False, []
            
            # Add to cache
            self._cache_message(message)
            
            # Add ourselves to seen_by
            if self._local_device_id:
                message.add_seen_by(self._local_device_id)
            
            # Determine if message should be processed locally
            should_process = True
            
            # Determine forwarding targets
            forward_to = []
            
            if message.can_forward():
                # Forward to all connected devices except:
                # - The source device
                # - Devices in seen_by list
                for device_id in connected_devices:
                    if device_id == source_device:
                        continue
                    if message.has_been_seen_by(device_id):
                        continue
                    forward_to.append(device_id)
                
                if forward_to:
                    with self._stats_lock:
                        self._stats.messages_forwarded += 1
            else:
                with self._stats_lock:
                    self._stats.messages_dropped_ttl += 1
            
            # Notify callbacks
            if should_process and self._on_message_for_local:
                await self._safe_callback(self._on_message_for_local, message)
            
            if forward_to and self._on_message_to_forward:
                await self._safe_callback(self._on_message_to_forward, message, forward_to)
            
            return should_process, forward_to
    
    async def originate_message(
        self,
        message: Message,
        connected_devices: List[str] = None
    ) -> List[str]:
        """
        Originate a new message from this device.
        
        Args:
            message: Message to send.
            connected_devices: List of connected device IDs.
            
        Returns:
            List of devices to send to.
        """
        connected_devices = connected_devices or []
        
        async with self._routing_lock:
            with self._stats_lock:
                self._stats.messages_originated += 1
            
            # Ensure sender is set
            if self._local_device_id:
                message.sender_id = self._local_device_id
                message.add_seen_by(self._local_device_id)
            
            # Add to cache
            self._cache_message(message)
            
            # Send to all connected devices
            return connected_devices.copy()
    
    def _is_duplicate(self, message_id: str) -> bool:
        """Check if a message is a duplicate."""
        return self._message_cache.contains(message_id)
    
    def _cache_message(self, message: Message) -> None:
        """Add a message to the cache."""
        cached = CachedMessage(
            message_id=message.message_id,
            sender_id=message.sender_id,
        )
        self._message_cache.set(message.message_id, cached)
    
    def _get_cached(self, message_id: str) -> Optional[CachedMessage]:
        """Get a cached message entry."""
        return self._message_cache.get(message_id)
    
    async def mark_forwarded(self, message_id: str, device_id: str) -> None:
        """Mark a message as forwarded to a device."""
        cached = self._get_cached(message_id)
        if cached:
            cached.forwarded_to.add(device_id)
            cached.forward_count += 1
    
    def clear_cache(self) -> None:
        """Clear the message cache."""
        self._message_cache.clear()
    
    def get_cache_size(self) -> int:
        """Get current cache size."""
        return self._message_cache.size()
    
    def expire_cache(self) -> None:
        """Manually expire old cache entries."""
        self._message_cache.expire()
    
    def reset_stats(self) -> None:
        """Reset routing statistics."""
        with self._stats_lock:
            self._stats = RoutingStats()
    
    def set_local_message_callback(self, callback: Callable[[Message], Any]) -> None:
        """Set callback for messages to process locally."""
        self._on_message_for_local = callback
    
    def set_forward_message_callback(self, callback: Callable[[Message, List[str]], Any]) -> None:
        """Set callback for messages to forward."""
        self._on_message_to_forward = callback
    
    async def _safe_callback(self, callback: Callable, *args) -> None:
        """Safely execute a callback."""
        try:
            result = callback(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            pass  # Don't let callback errors crash routing
    
    def get_routing_decision_info(self, message: Message, source_device: str = None) -> dict:
        """
        Get information about routing decision for a message.
        
        Useful for debugging and logging.
        """
        is_duplicate = self._is_duplicate(message.message_id)
        is_in_seen_by = self._local_device_id and message.has_been_seen_by(self._local_device_id)
        can_forward = message.can_forward()
        
        return {
            "message_id": message.message_id,
            "sender_id": message.sender_id,
            "source_device": source_device,
            "ttl": message.ttl,
            "seen_by_count": len(message.seen_by),
            "is_duplicate": is_duplicate,
            "is_in_seen_by": is_in_seen_by,
            "can_forward": can_forward,
            "will_process": not is_duplicate and not is_in_seen_by,
            "will_forward": not is_duplicate and not is_in_seen_by and can_forward,
        }
