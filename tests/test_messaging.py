"""
Tests for messaging module.
"""

import pytest
import asyncio
import time
from unittest.mock import MagicMock, AsyncMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from messaging.sanitizer import MessageSanitizer
from messaging.protocol import Message, MessageProtocol, MessageType
from messaging.router import MeshRouter


class TestMessageSanitizer:
    """Tests for MessageSanitizer class."""
    
    def setup_method(self):
        self.sanitizer = MessageSanitizer()
    
    def test_sanitize_empty_string(self):
        """Test sanitizing empty string."""
        result = self.sanitizer.sanitize("")
        assert result == ""
    
    def test_sanitize_normal_text(self):
        """Test sanitizing normal text."""
        result = self.sanitizer.sanitize("Hello, World!")
        assert "Hello" in result
        assert "World" in result
    
    def test_sanitize_removes_control_characters(self):
        """Test that control characters are removed."""
        result = self.sanitizer.sanitize("Hello\x00World\x1f!")
        assert "\x00" not in result
        assert "\x1f" not in result
    
    def test_sanitize_blocks_script_tags(self):
        """Test that script tags are blocked."""
        result = self.sanitizer.sanitize("<script>alert('xss')</script>")
        assert "<script" not in result.lower()
    
    def test_sanitize_blocks_javascript_protocol(self):
        """Test that javascript: protocol is blocked."""
        result = self.sanitizer.sanitize("javascript:alert('xss')")
        assert "javascript:" not in result.lower()
    
    def test_sanitize_html_escapes(self):
        """Test that HTML is escaped."""
        result = self.sanitizer.sanitize("<div>test</div>")
        assert "<div>" not in result
        assert "&lt;" in result or "div" in result
    
    def test_validate_empty_message(self):
        """Test validation of empty message."""
        is_valid, error = self.sanitizer.validate("")
        assert not is_valid
        assert error is not None
    
    def test_validate_valid_message(self):
        """Test validation of valid message."""
        is_valid, error = self.sanitizer.validate("Hello, World!")
        assert is_valid
        assert error is None
    
    def test_validate_too_long_message(self):
        """Test validation of too long message."""
        long_message = "x" * 500
        is_valid, error = self.sanitizer.validate(long_message)
        assert not is_valid
        assert "length" in error.lower() or "size" in error.lower()
    
    def test_sanitize_device_name(self):
        """Test device name sanitization."""
        result = MessageSanitizer.sanitize_device_name("Test\x00Device")
        assert "\x00" not in result
        assert "Test" in result
    
    def test_sanitize_device_name_empty(self):
        """Test empty device name sanitization."""
        result = MessageSanitizer.sanitize_device_name("")
        assert result == "Unknown Device"
    
    def test_is_valid_uuid(self):
        """Test UUID validation."""
        valid_uuid = "550e8400-e29b-41d4-a716-446655440000"
        invalid_uuid = "not-a-uuid"
        
        assert MessageSanitizer.is_valid_uuid(valid_uuid)
        assert not MessageSanitizer.is_valid_uuid(invalid_uuid)


class TestMessage:
    """Tests for Message class."""
    
    def test_create_message(self):
        """Test creating a message."""
        msg = Message(
            sender_id="device-1",
            content="Hello",
        )
        
        assert msg.sender_id == "device-1"
        assert msg.content == "Hello"
        assert msg.ttl == 3  # Default TTL
        assert msg.message_id is not None
    
    def test_message_to_dict(self):
        """Test converting message to dict."""
        msg = Message(
            sender_id="device-1",
            content="Hello",
        )
        
        d = msg.to_dict()
        
        assert d["sender_id"] == "device-1"
        assert d["content"] == "Hello"
        assert "message_id" in d
        assert "timestamp" in d
    
    def test_message_from_dict(self):
        """Test creating message from dict."""
        data = {
            "message_id": "test-id",
            "sender_id": "device-1",
            "content": "Hello",
            "timestamp": time.time(),
            "ttl": 2,
            "seen_by": ["device-1"],
        }
        
        msg = Message.from_dict(data)
        
        assert msg.message_id == "test-id"
        assert msg.sender_id == "device-1"
        assert msg.content == "Hello"
        assert msg.ttl == 2
    
    def test_message_to_json(self):
        """Test converting message to JSON."""
        msg = Message(
            sender_id="device-1",
            content="Hello",
        )
        
        json_str = msg.to_json()
        
        assert "device-1" in json_str
        assert "Hello" in json_str
    
    def test_message_from_json(self):
        """Test creating message from JSON."""
        msg = Message(
            sender_id="device-1",
            content="Hello",
        )
        
        json_str = msg.to_json()
        restored = Message.from_json(json_str)
        
        assert restored.sender_id == msg.sender_id
        assert restored.content == msg.content
    
    def test_decrement_ttl(self):
        """Test TTL decrement."""
        msg = Message(ttl=3)
        
        assert msg.decrement_ttl() == 2
        assert msg.ttl == 2
        
        msg.decrement_ttl()
        msg.decrement_ttl()
        
        assert msg.ttl == 0
        assert msg.decrement_ttl() == 0  # Should not go below 0
    
    def test_can_forward(self):
        """Test can_forward check."""
        msg = Message(ttl=1)
        assert msg.can_forward()
        
        msg.decrement_ttl()
        assert not msg.can_forward()
    
    def test_seen_by(self):
        """Test seen_by functionality."""
        msg = Message(sender_id="device-1")
        
        assert msg.has_been_seen_by("device-1")
        assert not msg.has_been_seen_by("device-2")
        
        msg.add_seen_by("device-2")
        assert msg.has_been_seen_by("device-2")


class TestMessageProtocol:
    """Tests for MessageProtocol class."""
    
    def setup_method(self):
        self.protocol = MessageProtocol()
    
    def test_create_broadcast_message(self):
        """Test creating a broadcast message."""
        msg = self.protocol.create_broadcast_message(
            content="Hello",
            sender_id="device-1",
        )
        
        assert msg.content == "Hello"
        assert msg.sender_id == "device-1"
        assert msg.message_type == MessageType.BROADCAST
    
    def test_create_heartbeat_message(self):
        """Test creating a heartbeat message."""
        msg = self.protocol.create_heartbeat_message("device-1")
        
        assert msg.message_type == MessageType.HEARTBEAT
        assert msg.ttl == 1
    
    def test_validate_message_valid(self):
        """Test validating a valid message."""
        msg = Message(
            sender_id="device-1",
            content="Hello",
        )
        
        is_valid, error = self.protocol.validate_message(msg)
        assert is_valid
        assert error is None
    
    def test_validate_message_no_sender(self):
        """Test validating message without sender."""
        msg = Message(content="Hello")
        
        is_valid, error = self.protocol.validate_message(msg)
        assert not is_valid
        assert "sender" in error.lower()
    
    def test_prepare_for_forwarding(self):
        """Test preparing message for forwarding."""
        msg = Message(
            sender_id="device-1",
            content="Hello",
            ttl=3,
        )
        
        forwarded = self.protocol.prepare_for_forwarding(msg, "device-2")
        
        assert forwarded is not None
        assert forwarded.ttl == 2
        assert "device-2" in forwarded.seen_by
    
    def test_prepare_for_forwarding_ttl_zero(self):
        """Test that message with TTL 0 cannot be forwarded."""
        msg = Message(
            sender_id="device-1",
            content="Hello",
            ttl=0,
        )
        
        forwarded = self.protocol.prepare_for_forwarding(msg, "device-2")
        assert forwarded is None


class TestMeshRouter:
    """Tests for MeshRouter class."""
    
    def setup_method(self):
        self.router = MeshRouter(local_device_id="local-device")
    
    @pytest.mark.asyncio
    async def test_route_new_message(self):
        """Test routing a new message."""
        msg = Message(
            sender_id="device-1",
            content="Hello",
            ttl=3,
        )
        
        should_process, forward_to = await self.router.route_message(
            msg,
            source_device="device-1",
            connected_devices=["device-2", "device-3"]
        )
        
        assert should_process
        assert "device-2" in forward_to
        assert "device-3" in forward_to
        assert "device-1" not in forward_to  # Should not forward to source
    
    @pytest.mark.asyncio
    async def test_route_duplicate_message(self):
        """Test that duplicate messages are dropped."""
        msg = Message(
            sender_id="device-1",
            content="Hello",
        )
        
        # First routing
        await self.router.route_message(msg, "device-1", ["device-2"])
        
        # Second routing (duplicate)
        should_process, forward_to = await self.router.route_message(
            msg, "device-1", ["device-2"]
        )
        
        assert not should_process
        assert len(forward_to) == 0
    
    @pytest.mark.asyncio
    async def test_route_message_ttl_zero(self):
        """Test that message with TTL 0 is not forwarded."""
        msg = Message(
            sender_id="device-1",
            content="Hello",
            ttl=0,
        )
        
        should_process, forward_to = await self.router.route_message(
            msg,
            source_device="device-1",
            connected_devices=["device-2"]
        )
        
        assert should_process  # Should still process locally
        assert len(forward_to) == 0  # But not forward
    
    @pytest.mark.asyncio
    async def test_originate_message(self):
        """Test originating a new message."""
        msg = Message(content="Hello")
        
        targets = await self.router.originate_message(
            msg,
            connected_devices=["device-1", "device-2"]
        )
        
        assert "device-1" in targets
        assert "device-2" in targets
        assert msg.sender_id == "local-device"
    
    def test_stats(self):
        """Test routing statistics."""
        stats = self.router.stats
        
        assert stats.messages_received == 0
        assert stats.messages_forwarded == 0
    
    def test_clear_cache(self):
        """Test clearing message cache."""
        self.router.clear_cache()
        assert self.router.get_cache_size() == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
