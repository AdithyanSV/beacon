"""
Command Parser for CLI interface.

Handles parsing and validation of user commands.
"""

from dataclasses import dataclass
from typing import Optional, List, Tuple
from enum import Enum, auto


class CommandType(Enum):
    """Types of CLI commands."""
    SEND = auto()
    LIST = auto()
    SCAN = auto()
    CONNECT = auto()
    DISCONNECT = auto()
    STATUS = auto()
    STATS = auto()
    CLEAR = auto()
    HELP = auto()
    QUIT = auto()
    UNKNOWN = auto()


@dataclass
class Command:
    """Parsed command with arguments."""
    type: CommandType
    args: List[str]
    raw: str


class CommandParser:
    """
    Parses user input into commands.
    """
    
    # Command aliases
    COMMAND_MAP = {
        "send": CommandType.SEND,
        "s": CommandType.SEND,
        "list": CommandType.LIST,
        "ls": CommandType.LIST,
        "devices": CommandType.LIST,
        "scan": CommandType.SCAN,
        "discover": CommandType.SCAN,
        "connect": CommandType.CONNECT,
        "c": CommandType.CONNECT,
        "disconnect": CommandType.DISCONNECT,
        "dc": CommandType.DISCONNECT,
        "status": CommandType.STATUS,
        "st": CommandType.STATUS,
        "stats": CommandType.STATS,
        "statistics": CommandType.STATS,
        "clear": CommandType.CLEAR,
        "cls": CommandType.CLEAR,
        "help": CommandType.HELP,
        "h": CommandType.HELP,
        "?": CommandType.HELP,
        "quit": CommandType.QUIT,
        "exit": CommandType.QUIT,
        "q": CommandType.QUIT,
    }
    
    @classmethod
    def parse(cls, input_line: str) -> Command:
        """
        Parse a line of input into a command.
        
        Args:
            input_line: Raw input string.
            
        Returns:
            Parsed Command object.
        """
        raw = input_line.strip()
        
        if not raw:
            return Command(type=CommandType.UNKNOWN, args=[], raw=raw)
        
        parts = raw.split(maxsplit=1)
        cmd_str = parts[0].lower()
        args_str = parts[1] if len(parts) > 1 else ""
        
        cmd_type = cls.COMMAND_MAP.get(cmd_str, CommandType.UNKNOWN)
        
        # Parse arguments based on command type
        if cmd_type == CommandType.SEND:
            # Everything after "send" is the message
            args = [args_str] if args_str else []
        elif cmd_type in (CommandType.CONNECT, CommandType.DISCONNECT):
            # Single argument: device address
            args = [args_str.strip()] if args_str else []
        else:
            # No arguments expected
            args = args_str.split() if args_str else []
        
        return Command(type=cmd_type, args=args, raw=raw)
    
    @classmethod
    def get_help_text(cls) -> str:
        """Get help text for all commands."""
        return """
Available Commands:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  send <message>      Broadcast a message to the mesh network
                      Aliases: s

  list                Show connected and discovered devices
                      Aliases: ls, devices

  scan                Force an immediate device scan
                      Aliases: discover

  connect <address>   Connect to a device by address
                      Aliases: c

  disconnect <addr>   Disconnect from a device
                      Aliases: dc

  status              Show system status
                      Aliases: st

  stats               Show message statistics
                      Aliases: statistics

  clear               Clear the screen
                      Aliases: cls

  help                Show this help message
                      Aliases: h, ?

  quit                Exit the application
                      Aliases: exit, q

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
