"""
Terminal UI for Bluetooth Mesh Broadcast.

Provides an async terminal interface for user interaction.
"""

import asyncio
import sys
import os
from typing import Optional, Callable, Any, List
from datetime import datetime

from cli.commands import CommandParser, Command, CommandType
from config import Config


# ANSI color codes
class Colors:
    """ANSI color codes for terminal output."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    
    # Colors
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    
    # Bright colors
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    
    @classmethod
    def disable(cls):
        """Disable all colors."""
        cls.RESET = ""
        cls.BOLD = ""
        cls.DIM = ""
        cls.RED = ""
        cls.GREEN = ""
        cls.YELLOW = ""
        cls.BLUE = ""
        cls.MAGENTA = ""
        cls.CYAN = ""
        cls.WHITE = ""
        cls.BRIGHT_RED = ""
        cls.BRIGHT_GREEN = ""
        cls.BRIGHT_YELLOW = ""
        cls.BRIGHT_BLUE = ""
        cls.BRIGHT_MAGENTA = ""
        cls.BRIGHT_CYAN = ""


class TerminalUI:
    """
    Async terminal interface for the mesh broadcast application.
    
    Handles user input and output without blocking the event loop.
    """
    
    def __init__(self):
        self._running = False
        self._input_prompt = "> "
        
        # Command handlers (set by Application)
        self._on_send: Optional[Callable[[str], Any]] = None
        self._on_list: Optional[Callable[[], Any]] = None
        self._on_scan: Optional[Callable[[], Any]] = None
        self._on_connect: Optional[Callable[[str], Any]] = None
        self._on_disconnect: Optional[Callable[[str], Any]] = None
        self._on_status: Optional[Callable[[], Any]] = None
        self._on_stats: Optional[Callable[[], Any]] = None
        self._on_quit: Optional[Callable[[], Any]] = None
        
        # Check if colors are supported
        if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
            Colors.disable()
    
    def print_banner(self):
        """Print application banner."""
        banner = f"""
{Colors.BRIGHT_CYAN}╔══════════════════════════════════════════════════════════╗
║{Colors.BOLD}          Bluetooth Mesh Broadcast Application            {Colors.RESET}{Colors.BRIGHT_CYAN}║
║{Colors.DIM}                    Terminal Edition                       {Colors.RESET}{Colors.BRIGHT_CYAN}║
╚══════════════════════════════════════════════════════════╝{Colors.RESET}
"""
        print(banner)
    
    def print_startup_info(self, local_address: str = None):
        """Print startup information."""
        print(f"{Colors.GREEN}[INFO]{Colors.RESET} Application starting...")
        if local_address:
            print(f"{Colors.GREEN}[INFO]{Colors.RESET} Local address: {Colors.CYAN}{local_address}{Colors.RESET}")
        print(f"{Colors.DIM}Type 'help' for available commands{Colors.RESET}")
        print()
    
    async def start(self):
        """Start the terminal input loop."""
        self._running = True
        
        while self._running:
            try:
                # Use asyncio-friendly input
                line = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input(self._input_prompt)
                )
                
                if line is None:
                    break
                
                await self._handle_input(line)
                
            except EOFError:
                # Ctrl+D pressed
                await self._handle_quit()
                break
            except KeyboardInterrupt:
                # Ctrl+C pressed
                print()  # New line after ^C
                await self._handle_quit()
                break
            except Exception as e:
                self.print_error(f"Input error: {e}")
    
    async def stop(self):
        """Stop the terminal UI."""
        self._running = False
    
    async def _handle_input(self, line: str):
        """Handle a line of user input."""
        command = CommandParser.parse(line)
        
        if command.type == CommandType.UNKNOWN:
            if command.raw:
                self.print_error(f"Unknown command: {command.raw.split()[0]}")
                print(f"{Colors.DIM}Type 'help' for available commands{Colors.RESET}")
            return
        
        await self._execute_command(command)
    
    async def _execute_command(self, command: Command):
        """Execute a parsed command."""
        try:
            if command.type == CommandType.SEND:
                if not command.args or not command.args[0]:
                    self.print_error("Usage: send <message>")
                    return
                if self._on_send:
                    await self._safe_callback(self._on_send, command.args[0])
            
            elif command.type == CommandType.LIST:
                if self._on_list:
                    await self._safe_callback(self._on_list)
            
            elif command.type == CommandType.SCAN:
                if self._on_scan:
                    await self._safe_callback(self._on_scan)
            
            elif command.type == CommandType.CONNECT:
                if not command.args or not command.args[0]:
                    self.print_error("Usage: connect <device_address>")
                    return
                if self._on_connect:
                    await self._safe_callback(self._on_connect, command.args[0])
            
            elif command.type == CommandType.DISCONNECT:
                if not command.args or not command.args[0]:
                    self.print_error("Usage: disconnect <device_address>")
                    return
                if self._on_disconnect:
                    await self._safe_callback(self._on_disconnect, command.args[0])
            
            elif command.type == CommandType.STATUS:
                if self._on_status:
                    await self._safe_callback(self._on_status)
            
            elif command.type == CommandType.STATS:
                if self._on_stats:
                    await self._safe_callback(self._on_stats)
            
            elif command.type == CommandType.CLEAR:
                self.clear_screen()
            
            elif command.type == CommandType.HELP:
                print(CommandParser.get_help_text())
            
            elif command.type == CommandType.QUIT:
                await self._handle_quit()
        
        except Exception as e:
            self.print_error(f"Command failed: {e}")
    
    async def _handle_quit(self):
        """Handle quit command."""
        print(f"\n{Colors.YELLOW}Shutting down...{Colors.RESET}")
        self._running = False
        if self._on_quit:
            await self._safe_callback(self._on_quit)
    
    async def _safe_callback(self, callback: Callable, *args) -> Any:
        """Safely execute a callback."""
        try:
            result = callback(*args)
            if asyncio.iscoroutine(result):
                return await result
            return result
        except Exception as e:
            self.print_error(f"Callback error: {e}")
            return None
    
    # ==================== Output Methods ====================
    
    def print_message(self, sender: str, content: str, timestamp: float = None, is_own: bool = False):
        """Print a received message."""
        time_str = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S") if timestamp else datetime.now().strftime("%H:%M:%S")
        
        if is_own:
            sender_display = f"{Colors.BRIGHT_GREEN}You{Colors.RESET}"
        else:
            sender_display = f"{Colors.BRIGHT_CYAN}{sender}{Colors.RESET}"
        
        print(f"\r{Colors.DIM}[{time_str}]{Colors.RESET} {sender_display}: {content}")
        print(self._input_prompt, end="", flush=True)
    
    def print_device_found(self, address: str, name: str = None, rssi: int = None, is_app: bool = False):
        """Print device discovery notification."""
        name_str = name or "Unknown"
        rssi_str = f" (RSSI: {rssi})" if rssi else ""
        
        if is_app:
            icon = f"{Colors.BRIGHT_GREEN}★{Colors.RESET}"
            label = f"{Colors.BRIGHT_GREEN}APP DEVICE{Colors.RESET}"
        else:
            icon = f"{Colors.BLUE}○{Colors.RESET}"
            label = "Device"
        
        print(f"\r{icon} {label}: {Colors.CYAN}{address}{Colors.RESET} | {name_str}{rssi_str}")
        print(self._input_prompt, end="", flush=True)
    
    def print_device_connected(self, address: str, name: str = None):
        """Print device connection notification."""
        name_str = f" ({name})" if name else ""
        print(f"\r{Colors.GREEN}✓ Connected:{Colors.RESET} {Colors.CYAN}{address}{Colors.RESET}{name_str}")
        print(self._input_prompt, end="", flush=True)
    
    def print_device_disconnected(self, address: str, name: str = None):
        """Print device disconnection notification."""
        name_str = f" ({name})" if name else ""
        print(f"\r{Colors.RED}✗ Disconnected:{Colors.RESET} {Colors.CYAN}{address}{Colors.RESET}{name_str}")
        print(self._input_prompt, end="", flush=True)
    
    def print_devices_list(self, connected: list, discovered: list):
        """Print list of devices."""
        print(f"\n{Colors.BOLD}Connected Devices ({len(connected)}/{Config.bluetooth.MAX_CONCURRENT_CONNECTIONS}):{Colors.RESET}")
        if connected:
            for dev in connected:
                addr = dev.get("address", dev.address if hasattr(dev, "address") else str(dev))
                name = dev.get("name", dev.name if hasattr(dev, "name") else None) or "Unknown"
                rssi = dev.get("rssi", dev.rssi if hasattr(dev, "rssi") else None)
                rssi_str = f" | RSSI: {rssi}" if rssi else ""
                print(f"  {Colors.GREEN}●{Colors.RESET} {Colors.CYAN}{addr}{Colors.RESET} | {name}{rssi_str}")
        else:
            print(f"  {Colors.DIM}No connected devices{Colors.RESET}")
        
        print(f"\n{Colors.BOLD}Discovered App Devices:{Colors.RESET}")
        if discovered:
            for dev in discovered:
                addr = dev.get("address", dev.address if hasattr(dev, "address") else str(dev))
                name = dev.get("name", dev.name if hasattr(dev, "name") else None) or "Unknown"
                rssi = dev.get("rssi", dev.rssi if hasattr(dev, "rssi") else None)
                rssi_str = f" | RSSI: {rssi}" if rssi else ""
                print(f"  {Colors.YELLOW}○{Colors.RESET} {Colors.CYAN}{addr}{Colors.RESET} | {name}{rssi_str}")
        else:
            print(f"  {Colors.DIM}No app devices discovered{Colors.RESET}")
        print()
    
    def print_status(self, status: dict):
        """Print system status."""
        print(f"\n{Colors.BOLD}System Status:{Colors.RESET}")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        # Bluetooth
        bt = status.get("bluetooth", {})
        bt_status = f"{Colors.GREEN}Running{Colors.RESET}" if bt.get("running") else f"{Colors.RED}Stopped{Colors.RESET}"
        print(f"  Bluetooth:     {bt_status}")
        print(f"  Connected:     {bt.get('connected', 0)}/{bt.get('max', Config.bluetooth.MAX_CONCURRENT_CONNECTIONS)}")
        
        # GATT Server
        gatt = status.get("gatt_server", {})
        gatt_status = f"{Colors.GREEN}Running{Colors.RESET}" if gatt.get("running") else f"{Colors.RED}Stopped{Colors.RESET}"
        print(f"  GATT Server:   {gatt_status}")
        
        # Discovery + scanning stats
        disc = status.get("discovery", {})
        disc_state = disc.get("state", "Unknown")
        disc_net_state = disc.get("network_state", "Unknown")
        disc_color = Colors.GREEN if disc_state == "SCANNING" else Colors.YELLOW
        
        print(f"  Discovery:     {disc_color}{disc_state}{Colors.RESET}  "
              f"(Network: {disc_net_state}, Interval: {disc.get('current_interval', 0.0):.1f}s)")
        print(f"  App Devices:   {disc.get('app_devices', 0)}")
        
        # Discovery statistics
        print(f"\n{Colors.BOLD}Discovery Statistics:{Colors.RESET}")
        print(f"  Total Scans:           {disc.get('total_scans', 0)}")
        print(f"  Successful Scans:      {disc.get('successful_scans', 0)}")
        print(f"  Devices Found (new):   {disc.get('devices_found', 0)}")
        print(f"  Consecutive Empty:     {disc.get('consecutive_empty_scans', 0)}")
        
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    
    def print_stats(self, stats: dict):
        """Print message statistics."""
        print(f"\n{Colors.BOLD}Message Statistics:{Colors.RESET}")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        msg = stats.get("messages", {})
        print(f"  Messages Sent:      {msg.get('sent', 0)}")
        print(f"  Messages Received:  {msg.get('received', 0)}")
        print(f"  Messages Forwarded: {msg.get('forwarded', 0)}")
        
        router = stats.get("router", {})
        print(f"\n{Colors.BOLD}Router Statistics:{Colors.RESET}")
        print(f"  Duplicates Dropped: {router.get('dropped_duplicate', 0)}")
        print(f"  TTL Expired:        {router.get('dropped_ttl', 0)}")
        print(f"  Cache Size:         {router.get('cache_size', 0)}")
        
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    
    def print_info(self, message: str):
        """Print an info message."""
        print(f"\r{Colors.GREEN}[INFO]{Colors.RESET} {message}")
        print(self._input_prompt, end="", flush=True)
    
    def print_warning(self, message: str):
        """Print a warning message."""
        print(f"\r{Colors.YELLOW}[WARN]{Colors.RESET} {message}")
        print(self._input_prompt, end="", flush=True)
    
    def print_error(self, message: str):
        """Print an error message."""
        print(f"{Colors.RED}[ERROR]{Colors.RESET} {message}")
    
    def print_debug(self, message: str):
        """Print a debug message (only if debug enabled)."""
        if Config.terminal.SHOW_DEBUG:
            print(f"\r{Colors.DIM}[DEBUG] {message}{Colors.RESET}")
            print(self._input_prompt, end="", flush=True)
    
    def print_success(self, message: str):
        """Print a success message."""
        print(f"\r{Colors.GREEN}[OK]{Colors.RESET} {message}")
        print(self._input_prompt, end="", flush=True)
    
    def clear_screen(self):
        """Clear the terminal screen."""
        os.system("cls" if os.name == "nt" else "clear")
        self.print_banner()
    
    # ==================== Handler Setters ====================
    
    def set_send_handler(self, handler: Callable[[str], Any]):
        """Set handler for send command."""
        self._on_send = handler
    
    def set_list_handler(self, handler: Callable[[], Any]):
        """Set handler for list command."""
        self._on_list = handler
    
    def set_scan_handler(self, handler: Callable[[], Any]):
        """Set handler for scan command."""
        self._on_scan = handler
    
    def set_connect_handler(self, handler: Callable[[str], Any]):
        """Set handler for connect command."""
        self._on_connect = handler
    
    def set_disconnect_handler(self, handler: Callable[[str], Any]):
        """Set handler for disconnect command."""
        self._on_disconnect = handler
    
    def set_status_handler(self, handler: Callable[[], Any]):
        """Set handler for status command."""
        self._on_status = handler
    
    def set_stats_handler(self, handler: Callable[[], Any]):
        """Set handler for stats command."""
        self._on_stats = handler
    
    def set_quit_handler(self, handler: Callable[[], Any]):
        """Set handler for quit command."""
        self._on_quit = handler
