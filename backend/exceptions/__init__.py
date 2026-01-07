"""
Custom exceptions for Bluetooth Mesh Broadcast Application.
"""

from .bluetooth_errors import (
    BluetoothError,
    BluetoothConnectionError,
    BluetoothDiscoveryError,
    BluetoothTimeoutError,
    BluetoothAdapterError,
    BluetoothNotAvailableError,
)

from .message_errors import (
    MessageError,
    MessageValidationError,
    MessageSizeError,
    MessageRateLimitError,
    MessageRoutingError,
)

__all__ = [
    # Bluetooth errors
    "BluetoothError",
    "BluetoothConnectionError",
    "BluetoothDiscoveryError",
    "BluetoothTimeoutError",
    "BluetoothAdapterError",
    "BluetoothNotAvailableError",
    # Message errors
    "MessageError",
    "MessageValidationError",
    "MessageSizeError",
    "MessageRateLimitError",
    "MessageRoutingError",
]
