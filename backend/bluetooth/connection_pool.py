"""
Connection Pool Management for Bluetooth Mesh Network.

Manages connection lifecycle, health monitoring, and optimal connection selection.
"""

import asyncio
from typing import Dict, List, Optional, Callable, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum, auto
import time
import heapq

from config import Config
from exceptions import BluetoothConnectionError
from bluetooth.constants import (
    DeviceInfo,
    ConnectionState,
    BluetoothConstants,
)


class ConnectionPriority(Enum):
    """Priority levels for connections."""
    HIGH = 1      # Important connections (relay nodes)
    NORMAL = 2    # Regular peer connections
    LOW = 3       # Background/optional connections


@dataclass
class ConnectionEntry:
    """Entry in the connection pool."""
    address: str
    device_info: DeviceInfo
    priority: ConnectionPriority = ConnectionPriority.NORMAL
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    messages_sent: int = 0
    messages_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    errors: int = 0
    reconnect_attempts: int = 0
    
    @property
    def health_score(self) -> float:
        """Calculate connection health score (0.0 to 1.0)."""
        base_score = self.device_info.health_score
        
        # Penalize for errors
        error_penalty = min(self.errors * 0.1, 0.5)
        
        # Penalize for inactivity
        time_since_activity = time.time() - self.last_activity
        inactivity_penalty = min(time_since_activity / 300, 0.3)  # Max 0.3 after 5 min
        
        # Bonus for message throughput
        throughput_bonus = min((self.messages_sent + self.messages_received) * 0.01, 0.2)
        
        score = base_score - error_penalty - inactivity_penalty + throughput_bonus
        return max(0.0, min(1.0, score))
    
    def record_activity(self) -> None:
        """Record activity on this connection."""
        self.last_activity = time.time()
    
    def record_error(self) -> None:
        """Record an error on this connection."""
        self.errors += 1
        self.device_info.decrease_health(0.1)
    
    def record_message_sent(self, size: int) -> None:
        """Record a sent message."""
        self.messages_sent += 1
        self.bytes_sent += size
        self.record_activity()
    
    def record_message_received(self, size: int) -> None:
        """Record a received message."""
        self.messages_received += 1
        self.bytes_received += size
        self.record_activity()
    
    def __lt__(self, other: "ConnectionEntry") -> bool:
        """Compare for priority queue (higher health = higher priority)."""
        return self.health_score > other.health_score


class ConnectionPool:
    """
    Manages a pool of Bluetooth connections with health monitoring
    and automatic lifecycle management.
    """
    
    def __init__(self, max_connections: int = None):
        self._max_connections = max_connections or Config.bluetooth.MAX_CONCURRENT_CONNECTIONS
        
        # Connection storage
        self._connections: Dict[str, ConnectionEntry] = {}
        self._lock = asyncio.Lock()
        
        # Pending connections (waiting to connect)
        self._pending: Dict[str, DeviceInfo] = {}
        
        # Blacklist (temporarily blocked devices)
        self._blacklist: Dict[str, float] = {}  # address -> unblock_time
        self._blacklist_duration = 60.0  # seconds
        
        # Callbacks
        self._on_connection_added: Optional[Callable[[ConnectionEntry], Any]] = None
        self._on_connection_removed: Optional[Callable[[ConnectionEntry], Any]] = None
        self._on_health_changed: Optional[Callable[[ConnectionEntry], Any]] = None
        
        # Background tasks
        self._maintenance_task: Optional[asyncio.Task] = None
        self._running = False
    
    @property
    def connection_count(self) -> int:
        """Get current number of connections."""
        return len(self._connections)
    
    @property
    def available_slots(self) -> int:
        """Get number of available connection slots."""
        return max(0, self._max_connections - len(self._connections))
    
    @property
    def is_full(self) -> bool:
        """Check if pool is at capacity."""
        return len(self._connections) >= self._max_connections
    
    async def start(self) -> None:
        """Start the connection pool maintenance."""
        if self._running:
            return
        
        self._running = True
        self._maintenance_task = asyncio.create_task(self._maintenance_loop())
    
    async def stop(self) -> None:
        """Stop the connection pool."""
        self._running = False
        
        if self._maintenance_task:
            self._maintenance_task.cancel()
            try:
                await self._maintenance_task
            except asyncio.CancelledError:
                pass
    
    async def add_connection(
        self,
        address: str,
        device_info: DeviceInfo,
        priority: ConnectionPriority = ConnectionPriority.NORMAL
    ) -> bool:
        """
        Add a connection to the pool.
        
        Args:
            address: Device address.
            device_info: Device information.
            priority: Connection priority.
            
        Returns:
            True if added successfully, False otherwise.
        """
        async with self._lock:
            # Check blacklist
            if address in self._blacklist:
                if time.time() < self._blacklist[address]:
                    return False
                else:
                    del self._blacklist[address]
            
            # Check if already exists
            if address in self._connections:
                return True
            
            # Check capacity
            if self.is_full:
                # Try to evict a lower priority connection
                evicted = await self._evict_lowest_priority(priority)
                if not evicted:
                    return False
            
            # Create entry
            entry = ConnectionEntry(
                address=address,
                device_info=device_info,
                priority=priority,
            )
            
            self._connections[address] = entry
            
            # Notify callback
            if self._on_connection_added:
                await self._safe_callback(self._on_connection_added, entry)
            
            return True
    
    async def remove_connection(self, address: str, blacklist: bool = False) -> bool:
        """
        Remove a connection from the pool.
        
        Args:
            address: Device address.
            blacklist: Whether to temporarily blacklist the device.
            
        Returns:
            True if removed, False if not found.
        """
        async with self._lock:
            if address not in self._connections:
                return False
            
            entry = self._connections[address]
            del self._connections[address]
            
            # Add to blacklist if requested
            if blacklist:
                self._blacklist[address] = time.time() + self._blacklist_duration
            
            # Notify callback
            if self._on_connection_removed:
                await self._safe_callback(self._on_connection_removed, entry)
            
            return True
    
    async def get_connection(self, address: str) -> Optional[ConnectionEntry]:
        """Get a connection entry by address."""
        async with self._lock:
            return self._connections.get(address)
    
    async def get_all_connections(self) -> List[ConnectionEntry]:
        """Get all connections."""
        async with self._lock:
            return list(self._connections.values())
    
    async def get_healthy_connections(self, min_health: float = 0.5) -> List[ConnectionEntry]:
        """Get connections above a health threshold."""
        async with self._lock:
            return [
                entry for entry in self._connections.values()
                if entry.health_score >= min_health
            ]
    
    async def get_best_connections(self, count: int = None) -> List[ConnectionEntry]:
        """Get the healthiest connections."""
        count = count or self._max_connections
        async with self._lock:
            sorted_connections = sorted(
                self._connections.values(),
                key=lambda e: e.health_score,
                reverse=True
            )
            return sorted_connections[:count]
    
    async def has_connection(self, address: str) -> bool:
        """Check if a connection exists."""
        async with self._lock:
            return address in self._connections
    
    async def is_blacklisted(self, address: str) -> bool:
        """Check if an address is blacklisted."""
        async with self._lock:
            if address not in self._blacklist:
                return False
            if time.time() >= self._blacklist[address]:
                del self._blacklist[address]
                return False
            return True
    
    async def record_activity(self, address: str) -> None:
        """Record activity on a connection."""
        async with self._lock:
            if address in self._connections:
                self._connections[address].record_activity()
    
    async def record_error(self, address: str) -> None:
        """Record an error on a connection."""
        async with self._lock:
            if address in self._connections:
                entry = self._connections[address]
                entry.record_error()
                
                # Notify health change
                if self._on_health_changed:
                    await self._safe_callback(self._on_health_changed, entry)
    
    async def record_message_sent(self, address: str, size: int) -> None:
        """Record a sent message."""
        async with self._lock:
            if address in self._connections:
                self._connections[address].record_message_sent(size)
    
    async def record_message_received(self, address: str, size: int) -> None:
        """Record a received message."""
        async with self._lock:
            if address in self._connections:
                self._connections[address].record_message_received(size)
    
    async def get_statistics(self) -> dict:
        """Get pool statistics."""
        async with self._lock:
            total_sent = sum(e.messages_sent for e in self._connections.values())
            total_received = sum(e.messages_received for e in self._connections.values())
            total_bytes_sent = sum(e.bytes_sent for e in self._connections.values())
            total_bytes_received = sum(e.bytes_received for e in self._connections.values())
            avg_health = (
                sum(e.health_score for e in self._connections.values()) / len(self._connections)
                if self._connections else 0.0
            )
            
            return {
                "connection_count": len(self._connections),
                "max_connections": self._max_connections,
                "available_slots": self.available_slots,
                "blacklisted_count": len(self._blacklist),
                "total_messages_sent": total_sent,
                "total_messages_received": total_received,
                "total_bytes_sent": total_bytes_sent,
                "total_bytes_received": total_bytes_received,
                "average_health": round(avg_health, 2),
            }
    
    async def _evict_lowest_priority(self, new_priority: ConnectionPriority) -> bool:
        """
        Evict the lowest priority connection to make room.
        
        Must be called with lock held.
        
        Returns:
            True if a connection was evicted, False otherwise.
        """
        if not self._connections:
            return False
        
        # Find lowest priority connection with lowest health
        candidates = [
            entry for entry in self._connections.values()
            if entry.priority.value >= new_priority.value
        ]
        
        if not candidates:
            return False
        
        # Sort by priority (descending) then health (ascending)
        candidates.sort(key=lambda e: (e.priority.value, -e.health_score), reverse=True)
        
        # Evict the worst candidate
        victim = candidates[0]
        del self._connections[victim.address]
        
        # Notify callback
        if self._on_connection_removed:
            await self._safe_callback(self._on_connection_removed, victim)
        
        return True
    
    async def _maintenance_loop(self) -> None:
        """Background maintenance task."""
        while self._running:
            try:
                await asyncio.sleep(30)  # Run every 30 seconds
                
                async with self._lock:
                    current_time = time.time()
                    
                    # Clean up expired blacklist entries
                    expired = [
                        addr for addr, unblock_time in self._blacklist.items()
                        if current_time >= unblock_time
                    ]
                    for addr in expired:
                        del self._blacklist[addr]
                    
                    # Check for unhealthy connections
                    unhealthy = [
                        entry for entry in self._connections.values()
                        if entry.health_score < BluetoothConstants.HEALTH_SCORE_CRITICAL
                    ]
                    
                    for entry in unhealthy:
                        # Notify health change
                        if self._on_health_changed:
                            await self._safe_callback(self._on_health_changed, entry)
                
            except asyncio.CancelledError:
                break
            except Exception:
                pass  # Continue maintenance on errors
    
    def set_connection_added_callback(self, callback: Callable[[ConnectionEntry], Any]) -> None:
        """Set callback for connection added."""
        self._on_connection_added = callback
    
    def set_connection_removed_callback(self, callback: Callable[[ConnectionEntry], Any]) -> None:
        """Set callback for connection removed."""
        self._on_connection_removed = callback
    
    def set_health_changed_callback(self, callback: Callable[[ConnectionEntry], Any]) -> None:
        """Set callback for health changes."""
        self._on_health_changed = callback
    
    async def _safe_callback(self, callback: Callable, *args) -> None:
        """Safely execute a callback."""
        try:
            result = callback(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            pass
