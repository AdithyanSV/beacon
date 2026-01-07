"""
Message handling exceptions.
"""


class MessageError(Exception):
    """Base exception for message-related errors."""
    
    def __init__(self, message: str, message_id: str = None):
        self.message = message
        self.message_id = message_id
        super().__init__(self.message)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for logging/API response."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "message_id": self.message_id,
        }


class MessageValidationError(MessageError):
    """Message failed validation."""
    
    def __init__(self, message: str, message_id: str = None, field: str = None):
        super().__init__(message, message_id)
        self.field = field
    
    def to_dict(self) -> dict:
        result = super().to_dict()
        result["field"] = self.field
        return result


class MessageSizeError(MessageError):
    """Message exceeds size limits."""
    
    def __init__(self, message: str, message_id: str = None, 
                 actual_size: int = None, max_size: int = None):
        super().__init__(message, message_id)
        self.actual_size = actual_size
        self.max_size = max_size
    
    def to_dict(self) -> dict:
        result = super().to_dict()
        result["actual_size"] = self.actual_size
        result["max_size"] = self.max_size
        return result


class MessageRateLimitError(MessageError):
    """Rate limit exceeded for messages."""
    
    def __init__(self, message: str, message_id: str = None,
                 limit_type: str = None, retry_after: float = None):
        super().__init__(message, message_id)
        self.limit_type = limit_type  # "connection", "device", or "global"
        self.retry_after = retry_after  # seconds
    
    def to_dict(self) -> dict:
        result = super().to_dict()
        result["limit_type"] = self.limit_type
        result["retry_after"] = self.retry_after
        return result


class MessageRoutingError(MessageError):
    """Error routing message through the mesh network."""
    
    def __init__(self, message: str, message_id: str = None,
                 source_device: str = None, target_device: str = None):
        super().__init__(message, message_id)
        self.source_device = source_device
        self.target_device = target_device
    
    def to_dict(self) -> dict:
        result = super().to_dict()
        result["source_device"] = self.source_device
        result["target_device"] = self.target_device
        return result
