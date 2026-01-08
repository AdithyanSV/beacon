"""
Global error suppression utilities.

Suppresses known non-fatal errors from third-party libraries that would
otherwise clutter the terminal output.
"""

import sys
import logging
from io import StringIO
from typing import Optional


class GlobalStderrFilter:
    """
    Global stderr filter to suppress known non-fatal errors.
    
    This is a singleton that replaces sys.stderr to filter out
    known non-fatal errors from third-party libraries like bleak/dbus-fast.
    """
    
    _instance: Optional['GlobalStderrFilter'] = None
    _original_stderr = sys.stderr
    
    # Patterns to filter from stderr - only filter specific known non-fatal errors
    FILTERED_PATTERNS = [
        "KeyError: 'Device'",
        "A message handler raised an exception: 'Device'",
    ]
    
    # Patterns that indicate the start of a traceback we want to filter
    TRACEBACK_START_PATTERNS = [
        "Traceback (most recent call last):",
    ]
    
    # File paths that indicate this is a known non-fatal error
    FILTERED_FILE_PATTERNS = [
        "dbus_fast/message_bus.py",
        "bleak/backends/bluezdbus/manager.py",
        "_parse_msg",
        "service_map.setdefault(service_props[\"Device\"]",
    ]
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
            cls._instance._buffer = StringIO()
            cls._instance._filtering_active = False
            cls._instance._current_traceback = []
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._initialized = True
    
    def install(self):
        """Install the stderr filter globally."""
        if not self._filtering_active:
            sys.stderr = self
            self._filtering_active = True
    
    def uninstall(self):
        """Uninstall the stderr filter."""
        if self._filtering_active:
            sys.stderr = self._original_stderr
            self._filtering_active = False
    
    def write(self, text: str):
        """
        Write to stderr, filtering known errors.
        
        This method intercepts all stderr writes and filters out
        known non-fatal errors from bleak/dbus-fast.
        """
        if not text.strip():
            return
        
        text_lower = text.lower()
        
        # Check if this line matches a filtered pattern directly
        should_filter_line = any(pattern.lower() in text_lower for pattern in self.FILTERED_PATTERNS)
        
        # If it's a traceback start, begin collecting
        if any(pattern in text for pattern in self.TRACEBACK_START_PATTERNS):
            self._current_traceback = [text]
            return  # Don't write traceback start yet
        
        # If we're collecting a traceback
        if self._current_traceback:
            self._current_traceback.append(text)
            
            # Check if this traceback is for a filtered error
            traceback_text = "".join(self._current_traceback).lower()
            
            # Check if it contains filtered patterns or filtered file patterns
            is_filtered_error = (
                any(pattern.lower() in traceback_text for pattern in self.FILTERED_PATTERNS) or
                any(pattern.lower() in traceback_text for pattern in self.FILTERED_FILE_PATTERNS)
            )
            
            # If traceback is complete (ends with the error line) or is long enough
            if len(self._current_traceback) > 8 or (not text.strip() and len(self._current_traceback) > 3):
                if is_filtered_error:
                    # Discard filtered traceback
                    self._current_traceback = []
                    return
                else:
                    # Write non-filtered traceback
                    for line in self._current_traceback:
                        self._original_stderr.write(line)
                    self._current_traceback = []
                    return
        
        # If this line should be filtered directly
        if should_filter_line:
            return  # Don't write filtered lines
        
        # Write non-filtered content
        self._original_stderr.write(text)
    
    def flush(self):
        """Flush stderr."""
        if self._current_traceback:
            # Write any remaining traceback
            for line in self._current_traceback:
                self._original_stderr.write(line)
            self._current_traceback = []
        self._original_stderr.flush()
    
    def isatty(self):
        """Check if stderr is a TTY."""
        return self._original_stderr.isatty()


def setup_error_suppression():
    """
    Set up global error suppression for known non-fatal errors.
    
    This should be called at application startup to suppress
    known non-fatal errors from third-party libraries.
    """
    # Install global stderr filter
    filter_instance = GlobalStderrFilter()
    filter_instance.install()
    
    # Also configure logging filters
    _setup_logging_filters()
    
    return filter_instance


def _setup_logging_filters():
    """Set up logging filters for known errors."""
    class BleakErrorFilter(logging.Filter):
        """Filter to suppress known non-fatal bleak errors."""
        def filter(self, record):
            message = record.getMessage()
            # Suppress KeyError: 'Device' messages
            if 'Device' in message and 'KeyError' in message:
                return False
            # Suppress traceback messages for Device errors
            if 'dbus_fast' in message and 'Device' in message:
                return False
            return True
    
    # Apply filter to relevant loggers
    error_filter = BleakErrorFilter()
    logging.getLogger('bleak').addFilter(error_filter)
    logging.getLogger('dbus_fast').addFilter(error_filter)
    logging.getLogger('dbus-fast').addFilter(error_filter)
    logging.getLogger('bleak.backends.bluezdbus').addFilter(error_filter)
