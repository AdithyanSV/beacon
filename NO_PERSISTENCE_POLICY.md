# No Persistence Policy

## Overview

This application follows a **strict no-persistence policy**. All data is stored in-memory only and is lost when the application stops.

## In-Memory Only Components

### 1. Message Cache
- **Location**: `backend/messaging/router.py`
- **Implementation**: `TTLCache` from `cachetools` library
- **Purpose**: Message deduplication to prevent loops
- **Persistence**: None - all entries are lost on application stop
- **TTL**: 300 seconds (5 minutes) by default
- **Max Size**: 100 messages by default

### 2. Device Discovery Cache
- **Location**: `backend/bluetooth/discovery.py`
- **Implementation**: In-memory dictionaries and sets
- **Purpose**: Track discovered devices and app devices
- **Persistence**: None - all device information is lost on application stop

### 3. Connection Pool
- **Location**: `backend/bluetooth/connection_pool.py`
- **Implementation**: In-memory dictionaries
- **Purpose**: Track active connections and connection health
- **Persistence**: None - all connection data is lost on application stop

### 4. Routing Statistics
- **Location**: `backend/messaging/router.py`
- **Implementation**: In-memory dataclass
- **Purpose**: Track routing performance metrics
- **Persistence**: None - all statistics are lost on application stop

### 5. Message Handler Statistics
- **Location**: `backend/messaging/handler.py`
- **Implementation**: In-memory dataclass
- **Purpose**: Track message sending/receiving statistics
- **Persistence**: None - all statistics are lost on application stop

## Optional Persistence (Disabled by Default)

### Log File
- **Location**: `backend/utils/logger.py`
- **Configuration**: `Config.log.LOG_FILE` (default: `None`)
- **Purpose**: Optional file-based logging
- **Default**: Disabled (no file logging)
- **Note**: This is the ONLY persistence mechanism, and it's disabled by default

To enable log file (if needed):
```python
# In .env file or environment variable
LOG_FILE=/path/to/logfile.log
```

## Why No Persistence?

1. **Privacy**: No message content is stored on disk
2. **Simplicity**: No database or file I/O overhead
3. **Ephemeral Nature**: Mesh networking is designed for real-time communication
4. **Security**: No sensitive data left on disk after application stops
5. **Performance**: In-memory operations are faster

## Data Lifecycle

1. **Application Start**: All caches and data structures are empty
2. **Runtime**: Data accumulates in memory as the application runs
3. **Application Stop**: All data is immediately lost (no save/restore)

## Verification

To verify no persistence:
1. Check that `LOG_FILE` is `None` by default
2. Verify no file I/O operations for data storage (only optional logging)
3. All caches use in-memory data structures (dicts, sets, TTLCache)
4. No database connections or file writes for application data

## Configuration

All cache sizes and TTLs are configurable but remain in-memory:
- `MESSAGE_CACHE_SIZE`: Maximum number of cached messages (default: 100)
- `MESSAGE_CACHE_TTL`: Time-to-live for cached messages in seconds (default: 300)

These can be adjusted via environment variables but do not enable persistence.
