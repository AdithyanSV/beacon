"""
Input Sanitization for Message Content.

Provides security-focused sanitization to prevent:
- XSS attacks
- Injection attacks
- Control character injection
- Unicode abuse
"""

import re
import html
import unicodedata
from typing import Optional, Tuple

from config import Config
from exceptions import MessageValidationError


class MessageSanitizer:
    """
    Sanitizes and validates message content for security.
    """
    
    # Control characters to remove (except newline, tab)
    CONTROL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')
    
    # Dangerous HTML/script patterns
    DANGEROUS_PATTERNS = [
        re.compile(r'<\s*script', re.IGNORECASE),
        re.compile(r'javascript\s*:', re.IGNORECASE),
        re.compile(r'on\w+\s*=', re.IGNORECASE),  # Event handlers
        re.compile(r'<\s*iframe', re.IGNORECASE),
        re.compile(r'<\s*object', re.IGNORECASE),
        re.compile(r'<\s*embed', re.IGNORECASE),
        re.compile(r'<\s*form', re.IGNORECASE),
        re.compile(r'data\s*:', re.IGNORECASE),
    ]
    
    # Unicode categories to filter (if strict mode)
    BLOCKED_UNICODE_CATEGORIES = {
        'Cf',  # Format characters
        'Co',  # Private use
        'Cs',  # Surrogates
    }
    
    def __init__(self, strict_mode: bool = False):
        """
        Initialize the sanitizer.
        
        Args:
            strict_mode: If True, apply stricter filtering rules.
        """
        self._strict_mode = strict_mode
        self._enabled = Config.security.ENABLE_INPUT_SANITIZATION
    
    def sanitize(self, content: str) -> str:
        """
        Sanitize message content.
        
        Args:
            content: Raw message content.
            
        Returns:
            Sanitized content.
        """
        if not self._enabled:
            return content
        
        if not content:
            return ""
        
        # Step 1: Normalize Unicode
        content = self._normalize_unicode(content)
        
        # Step 2: Remove control characters
        content = self._remove_control_chars(content)
        
        # Step 3: Filter dangerous patterns
        content = self._filter_dangerous_patterns(content)
        
        # Step 4: HTML escape (for UI safety)
        content = self._html_escape(content)
        
        # Step 5: Trim and limit length
        content = self._trim_and_limit(content)
        
        # Step 6: Filter blocked Unicode categories (strict mode)
        if self._strict_mode:
            content = self._filter_unicode_categories(content)
        
        return content
    
    def validate(self, content: str) -> Tuple[bool, Optional[str]]:
        """
        Validate message content.
        
        Args:
            content: Message content to validate.
            
        Returns:
            Tuple of (is_valid, error_message).
        """
        if not content:
            return False, "Message content cannot be empty"
        
        # Check length
        if len(content) > Config.message.MAX_CONTENT_LENGTH:
            return False, f"Message exceeds maximum length of {Config.message.MAX_CONTENT_LENGTH} characters"
        
        # Check byte size
        byte_size = len(content.encode('utf-8'))
        if byte_size > Config.message.MAX_MESSAGE_SIZE:
            return False, f"Message exceeds maximum size of {Config.message.MAX_MESSAGE_SIZE} bytes"
        
        # Check for blocked patterns
        if self._enabled:
            for pattern in self.DANGEROUS_PATTERNS:
                if pattern.search(content):
                    return False, "Message contains blocked content"
        
        # Check for blocked words/patterns from config
        for blocked in Config.security.BLOCKED_PATTERNS:
            if blocked.lower() in content.lower():
                return False, "Message contains blocked content"
        
        return True, None
    
    def sanitize_and_validate(self, content: str) -> Tuple[str, bool, Optional[str]]:
        """
        Sanitize and validate in one operation.
        
        Args:
            content: Raw message content.
            
        Returns:
            Tuple of (sanitized_content, is_valid, error_message).
        """
        sanitized = self.sanitize(content)
        is_valid, error = self.validate(sanitized)
        return sanitized, is_valid, error
    
    def _normalize_unicode(self, content: str) -> str:
        """Normalize Unicode to NFC form."""
        return unicodedata.normalize('NFC', content)
    
    def _remove_control_chars(self, content: str) -> str:
        """Remove control characters except newline and tab."""
        # Replace with space to prevent text concatenation issues
        content = self.CONTROL_CHARS.sub(' ', content)
        # Normalize multiple spaces
        content = re.sub(r' +', ' ', content)
        return content
    
    def _filter_dangerous_patterns(self, content: str) -> str:
        """Remove or neutralize dangerous patterns."""
        for pattern in self.DANGEROUS_PATTERNS:
            content = pattern.sub('[blocked]', content)
        return content
    
    def _html_escape(self, content: str) -> str:
        """Escape HTML special characters."""
        return html.escape(content, quote=True)
    
    def _trim_and_limit(self, content: str) -> str:
        """Trim whitespace and limit length."""
        content = content.strip()
        
        # Limit length
        if len(content) > Config.message.MAX_CONTENT_LENGTH:
            content = content[:Config.message.MAX_CONTENT_LENGTH]
            # Try to break at word boundary
            last_space = content.rfind(' ')
            if last_space > Config.message.MAX_CONTENT_LENGTH * 0.8:
                content = content[:last_space]
        
        return content
    
    def _filter_unicode_categories(self, content: str) -> str:
        """Filter blocked Unicode categories (strict mode)."""
        result = []
        for char in content:
            category = unicodedata.category(char)
            if category not in self.BLOCKED_UNICODE_CATEGORIES:
                result.append(char)
        return ''.join(result)
    
    @staticmethod
    def sanitize_device_name(name: str) -> str:
        """
        Sanitize a device name for display.
        
        Args:
            name: Raw device name.
            
        Returns:
            Sanitized device name.
        """
        if not name:
            return "Unknown Device"
        
        # Remove control characters
        name = MessageSanitizer.CONTROL_CHARS.sub('', name)
        
        # HTML escape
        name = html.escape(name, quote=True)
        
        # Limit length
        if len(name) > 50:
            name = name[:50]
        
        return name.strip() or "Unknown Device"
    
    @staticmethod
    def sanitize_address(address: str) -> str:
        """
        Sanitize a device address.
        
        Args:
            address: Raw device address.
            
        Returns:
            Sanitized address or None if invalid.
        """
        if not address:
            return ""
        
        # Allow only hex characters, colons, and hyphens
        address = re.sub(r'[^0-9A-Fa-f:\-]', '', address)
        
        # Limit length
        if len(address) > 50:
            address = address[:50]
        
        return address
    
    @staticmethod
    def is_valid_uuid(uuid_str: str) -> bool:
        """
        Check if a string is a valid UUID.
        
        Args:
            uuid_str: String to check.
            
        Returns:
            True if valid UUID format.
        """
        uuid_pattern = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
            re.IGNORECASE
        )
        return bool(uuid_pattern.match(uuid_str or ''))
