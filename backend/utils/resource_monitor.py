"""
Resource Monitoring for System Health.

Monitors:
- Memory usage
- Connection counts
- Message throughput
- System health
"""

import asyncio
import threading
from typing import Dict, Optional, Callable, Any, List
from dataclasses import dataclass, field
import time
import psutil

from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ResourceSnapshot:
    """Snapshot of resource usage."""
    timestamp: float = field(default_factory=time.time)
    memory_percent: float = 0.0
    memory_mb: float = 0.0
    cpu_percent: float = 0.0
    connection_count: int = 0
    message_rate: float = 0.0  # messages per second
    cache_size: int = 0
    

@dataclass
class ResourceLimits:
    """Resource limit thresholds."""
    max_memory_mb: float = Config.resource.MAX_MEMORY_USAGE_MB
    memory_warning: float = Config.resource.MEMORY_WARNING_THRESHOLD
    memory_error: float = Config.resource.MEMORY_ERROR_THRESHOLD
    max_connections: int = Config.resource.MAX_TOTAL_CONNECTIONS


class ResourceMonitor:
    """
    Monitors system resources and triggers alerts when thresholds are exceeded.
    """
    
    def __init__(self):
        self._limits = ResourceLimits()
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        
        # Current state
        self._current_snapshot: Optional[ResourceSnapshot] = None
        self._lock = threading.RLock()
        
        # History (last 60 snapshots = 1 minute at 1/sec)
        self._history: List[ResourceSnapshot] = []
        self._max_history = 60
        
        # Message counting for rate calculation
        self._message_count = 0
        self._last_rate_check = time.time()
        
        # Callbacks
        self._on_warning: Optional[Callable[[str, ResourceSnapshot], Any]] = None
        self._on_error: Optional[Callable[[str, ResourceSnapshot], Any]] = None
        
        # Process reference
        self._process = psutil.Process()
    
    async def start(self) -> None:
        """Start the resource monitor."""
        if self._running:
            return
        
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Resource monitor started")
    
    async def stop(self) -> None:
        """Stop the resource monitor."""
        self._running = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Resource monitor stopped")
    
    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self._take_snapshot()
                await asyncio.sleep(1)  # Check every second
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in resource monitor: {e}")
                await asyncio.sleep(5)  # Wait longer on error
    
    async def _take_snapshot(self) -> None:
        """Take a resource snapshot and check thresholds."""
        try:
            # Get memory info
            memory_info = self._process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)
            memory_percent = self._process.memory_percent()
            
            # Get CPU info
            cpu_percent = self._process.cpu_percent()
            
            # Calculate message rate
            current_time = time.time()
            time_delta = current_time - self._last_rate_check
            message_rate = 0.0
            if time_delta > 0:
                message_rate = self._message_count / time_delta
                self._message_count = 0
                self._last_rate_check = current_time
            
            # Create snapshot
            snapshot = ResourceSnapshot(
                timestamp=current_time,
                memory_percent=memory_percent,
                memory_mb=memory_mb,
                cpu_percent=cpu_percent,
                message_rate=message_rate,
            )
            
            with self._lock:
                self._current_snapshot = snapshot
                self._history.append(snapshot)
                
                # Trim history
                if len(self._history) > self._max_history:
                    self._history = self._history[-self._max_history:]
            
            # Check thresholds
            await self._check_thresholds(snapshot)
            
        except Exception as e:
            logger.error(f"Error taking resource snapshot: {e}")
    
    async def _check_thresholds(self, snapshot: ResourceSnapshot) -> None:
        """Check resource thresholds and trigger callbacks."""
        # Memory checks
        memory_ratio = snapshot.memory_mb / self._limits.max_memory_mb
        
        if memory_ratio >= self._limits.memory_error:
            message = f"Critical memory usage: {snapshot.memory_mb:.1f}MB ({memory_ratio*100:.1f}%)"
            logger.error(message)
            if self._on_error:
                await self._safe_callback(self._on_error, message, snapshot)
        elif memory_ratio >= self._limits.memory_warning:
            message = f"High memory usage: {snapshot.memory_mb:.1f}MB ({memory_ratio*100:.1f}%)"
            logger.warning(message)
            if self._on_warning:
                await self._safe_callback(self._on_warning, message, snapshot)
        
        # Connection checks
        if snapshot.connection_count >= self._limits.max_connections:
            message = f"Maximum connections reached: {snapshot.connection_count}"
            logger.warning(message)
            if self._on_warning:
                await self._safe_callback(self._on_warning, message, snapshot)
    
    def record_message(self) -> None:
        """Record a message for rate calculation."""
        with self._lock:
            self._message_count += 1
    
    def update_connection_count(self, count: int) -> None:
        """Update the current connection count."""
        with self._lock:
            if self._current_snapshot:
                self._current_snapshot.connection_count = count
    
    def update_cache_size(self, size: int) -> None:
        """Update the current cache size."""
        with self._lock:
            if self._current_snapshot:
                self._current_snapshot.cache_size = size
    
    def get_current_snapshot(self) -> Optional[ResourceSnapshot]:
        """Get the current resource snapshot."""
        with self._lock:
            return self._current_snapshot
    
    def get_history(self, limit: int = None) -> List[ResourceSnapshot]:
        """Get resource history."""
        limit = limit or self._max_history
        with self._lock:
            return self._history[-limit:]
    
    def get_average_stats(self, seconds: int = 60) -> Dict[str, float]:
        """
        Get average statistics over a time period.
        
        Args:
            seconds: Time period in seconds.
            
        Returns:
            Dictionary of average statistics.
        """
        with self._lock:
            if not self._history:
                return {
                    'avg_memory_mb': 0.0,
                    'avg_cpu_percent': 0.0,
                    'avg_message_rate': 0.0,
                }
            
            cutoff = time.time() - seconds
            recent = [s for s in self._history if s.timestamp > cutoff]
            
            if not recent:
                recent = self._history[-1:]
            
            return {
                'avg_memory_mb': sum(s.memory_mb for s in recent) / len(recent),
                'avg_cpu_percent': sum(s.cpu_percent for s in recent) / len(recent),
                'avg_message_rate': sum(s.message_rate for s in recent) / len(recent),
            }
    
    def get_status(self) -> Dict[str, Any]:
        """Get current resource status."""
        snapshot = self.get_current_snapshot()
        
        if not snapshot:
            return {
                'status': 'unknown',
                'memory_mb': 0,
                'memory_percent': 0,
                'cpu_percent': 0,
                'connection_count': 0,
                'message_rate': 0,
            }
        
        # Determine status
        memory_ratio = snapshot.memory_mb / self._limits.max_memory_mb
        if memory_ratio >= self._limits.memory_error:
            status = 'critical'
        elif memory_ratio >= self._limits.memory_warning:
            status = 'warning'
        else:
            status = 'healthy'
        
        return {
            'status': status,
            'memory_mb': round(snapshot.memory_mb, 1),
            'memory_percent': round(snapshot.memory_percent, 1),
            'cpu_percent': round(snapshot.cpu_percent, 1),
            'connection_count': snapshot.connection_count,
            'message_rate': round(snapshot.message_rate, 2),
            'cache_size': snapshot.cache_size,
        }
    
    def set_warning_callback(self, callback: Callable[[str, ResourceSnapshot], Any]) -> None:
        """Set callback for warning alerts."""
        self._on_warning = callback
    
    def set_error_callback(self, callback: Callable[[str, ResourceSnapshot], Any]) -> None:
        """Set callback for error alerts."""
        self._on_error = callback
    
    async def _safe_callback(self, callback: Callable, *args) -> None:
        """Safely execute a callback."""
        try:
            result = callback(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.error(f"Error in resource monitor callback: {e}")
