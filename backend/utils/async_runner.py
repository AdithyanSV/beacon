"""
Async Task Runner for Eventlet Compatibility.

Runs async tasks in a background thread to avoid conflicts with eventlet.
"""

import asyncio
import threading
from typing import Optional
from utils.logger import get_logger

logger = get_logger(__name__)


class AsyncRunner:
    """
    Runs async tasks in a separate thread with its own event loop.
    This is necessary when using eventlet which monkey-patches asyncio.
    """
    
    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
    
    def start(self):
        """Start the async runner thread."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Async runner thread started")
    
    def stop(self):
        """Stop the async runner thread."""
        if not self._running:
            return
        
        self._running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        
        if self._thread:
            self._thread.join(timeout=5.0)
        
        logger.info("Async runner thread stopped")
    
    def _run_loop(self):
        """Run the event loop in this thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        
        try:
            self._loop.run_forever()
        except Exception as e:
            logger.error(f"Error in async runner loop: {e}")
        finally:
            self._loop.close()
    
    def run_coroutine(self, coro):
        """
        Run a coroutine in the async runner's event loop.
        
        Args:
            coro: Coroutine to run.
            
        Returns:
            Result of the coroutine.
        """
        if not self._loop or not self._running:
            raise RuntimeError("Async runner not started")
        
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()
    
    def schedule_task(self, coro):
        """
        Schedule a coroutine to run in the background.
        
        Args:
            coro: Coroutine to schedule.
            
        Returns:
            Future object.
        """
        if not self._loop or not self._running:
            raise RuntimeError("Async runner not started")
        
        return asyncio.run_coroutine_threadsafe(coro, self._loop)
    
    @property
    def loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """Get the event loop."""
        return self._loop
