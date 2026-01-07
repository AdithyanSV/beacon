"""
Bluetooth-specific exceptions.
"""


class BluetoothError(Exception):
    """Base exception for Bluetooth-related errors."""
    
    def __init__(self, message: str, device_address: str = None):
        self.message = message
        self.device_address = device_address
        super().__init__(self.message)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for logging/API response."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "device_address": self.device_address,
        }


class BluetoothConnectionError(BluetoothError):
    """Error establishing or maintaining a Bluetooth connection."""
    
    def __init__(self, message: str, device_address: str = None, retry_count: int = 0):
        super().__init__(message, device_address)
        self.retry_count = retry_count
    
    def to_dict(self) -> dict:
        result = super().to_dict()
        result["retry_count"] = self.retry_count
        return result


class BluetoothDiscoveryError(BluetoothError):
    """Error during device discovery."""
    pass


class BluetoothTimeoutError(BluetoothError):
    """Timeout during Bluetooth operation."""
    
    def __init__(self, message: str, device_address: str = None, timeout_seconds: float = None):
        super().__init__(message, device_address)
        self.timeout_seconds = timeout_seconds
    
    def to_dict(self) -> dict:
        result = super().to_dict()
        result["timeout_seconds"] = self.timeout_seconds
        return result


class BluetoothAdapterError(BluetoothError):
    """Error with the Bluetooth adapter itself."""
    pass


class BluetoothNotAvailableError(BluetoothError):
    """Bluetooth is not available on this system."""
    
    def __init__(self, message: str = "Bluetooth is not available on this system"):
        super().__init__(message)
