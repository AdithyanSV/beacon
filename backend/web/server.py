"""
Flask + SocketIO Server Setup.

Creates and configures the Flask application with SocketIO support.
"""

import os
from flask import Flask, send_from_directory
from flask_socketio import SocketIO

from config import Config
from web.security import SecurityMiddleware

# Create SocketIO instance
socketio = SocketIO(
    async_mode=Config.web.SOCKETIO_ASYNC_MODE,
    cors_allowed_origins=Config.web.ALLOWED_ORIGINS,
    ping_timeout=60,
    ping_interval=25,
)


def create_app() -> Flask:
    """
    Create and configure the Flask application.
    
    Returns:
        Configured Flask application.
    """
    # Get the project root directory
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    frontend_dir = os.path.join(project_root, 'frontend')
    
    app = Flask(
        __name__,
        static_folder=frontend_dir,
        static_url_path='/static'
    )
    
    # Configuration
    app.config['SECRET_KEY'] = Config.web.SECRET_KEY
    app.config['DEBUG'] = Config.web.DEBUG
    
    # Initialize security middleware
    security = SecurityMiddleware(app)
    
    # Initialize SocketIO
    socketio.init_app(app)
    
    # Register routes
    register_routes(app, frontend_dir)
    
    return app


def register_routes(app: Flask, frontend_dir: str) -> None:
    """
    Register HTTP routes.
    
    Args:
        app: Flask application.
        frontend_dir: Path to frontend directory.
    """
    
    @app.route('/')
    def index():
        """Serve the main HTML page."""
        return send_from_directory(frontend_dir, 'index.html')
    
    @app.route('/css/<path:filename>')
    def serve_css(filename):
        """Serve CSS files."""
        return send_from_directory(os.path.join(frontend_dir, 'css'), filename)
    
    @app.route('/js/<path:filename>')
    def serve_js(filename):
        """Serve JavaScript files."""
        return send_from_directory(os.path.join(frontend_dir, 'js'), filename)
    
    @app.route('/health')
    def health_check():
        """Health check endpoint."""
        return {'status': 'healthy', 'service': 'bluetooth-mesh-broadcast'}
    
    @app.route('/api/status')
    def api_status():
        """API status endpoint."""
        from web.handlers import _bluetooth_manager, _discovery
        
        # Build status with safe attribute access
        status = {
            'status': 'running',
            'version': '1.0.0',
            'bluetooth': {
                'enabled': _bluetooth_manager is not None,
                'running': False,
                'max_connections': Config.bluetooth.MAX_CONCURRENT_CONNECTIONS,
            },
            'discovery': {
                'enabled': _discovery is not None,
                'state': 'UNKNOWN',
                'network_state': 'UNKNOWN',
                'current_interval': 0,
                'stats': {
                    'total_scans': 0,
                    'successful_scans': 0,
                    'devices_found': 0,
                    'consecutive_empty_scans': 0,
                },
            },
            'limits': {
                'max_message_size': Config.message.MAX_MESSAGE_SIZE,
                'max_content_length': Config.message.MAX_CONTENT_LENGTH,
                'message_ttl': Config.message.MESSAGE_TTL,
            }
        }
        
        # Safely access bluetooth manager attributes
        if _bluetooth_manager:
            try:
                status['bluetooth']['running'] = getattr(_bluetooth_manager, 'is_running', False)
            except Exception:
                pass
        
        # Safely access discovery attributes
        if _discovery:
            try:
                if hasattr(_discovery, 'state') and _discovery.state:
                    status['discovery']['state'] = _discovery.state.name
                if hasattr(_discovery, 'network_state') and _discovery.network_state:
                    status['discovery']['network_state'] = _discovery.network_state.name
                if hasattr(_discovery, 'current_interval'):
                    status['discovery']['current_interval'] = _discovery.current_interval
                if hasattr(_discovery, 'stats') and _discovery.stats:
                    stats = _discovery.stats
                    status['discovery']['stats'] = {
                        'total_scans': getattr(stats, 'total_scans', 0),
                        'successful_scans': getattr(stats, 'successful_scans', 0),
                        'devices_found': getattr(stats, 'devices_found', 0),
                        'consecutive_empty_scans': getattr(stats, 'consecutive_empty_scans', 0),
                    }
            except Exception as e:
                # Log but don't fail - status endpoint should always work
                import logging
                logging.getLogger(__name__).debug(f"Error accessing discovery attributes: {e}")
        
        # Try to get device counts (with error handling)
        if _bluetooth_manager:
            try:
                import asyncio
                import concurrent.futures
                
                def get_devices():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        connected = loop.run_until_complete(_bluetooth_manager.get_connected_devices())
                        all_devices = loop.run_until_complete(_bluetooth_manager.get_all_devices())
                        return len(connected), len(all_devices)
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).debug(f"Error getting device counts: {e}")
                        return 0, 0
                    finally:
                        loop.close()
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(get_devices)
                    try:
                        connected_count, all_count = future.result(timeout=5)
                        status['bluetooth']['connected_devices'] = connected_count
                        status['bluetooth']['discovered_devices'] = all_count
                    except Exception:
                        pass  # Silently fail - device counts are optional
            except Exception:
                pass  # Silently fail - device counts are optional
        
        if _discovery:
            try:
                import asyncio
                import concurrent.futures
                
                def get_discovery_devices():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        app_devices = loop.run_until_complete(_discovery.get_app_devices())
                        all_devices = loop.run_until_complete(_discovery.get_all_devices())
                        return len(app_devices), len(all_devices)
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).debug(f"Error getting discovery device counts: {e}")
                        return 0, 0
                    finally:
                        loop.close()
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(get_discovery_devices)
                    try:
                        app_count, all_count = future.result(timeout=5)
                        status['discovery']['app_devices'] = app_count
                        status['discovery']['all_discovered'] = all_count
                    except Exception:
                        pass  # Silently fail - device counts are optional
            except Exception:
                pass  # Silently fail - device counts are optional
        
        return status
    
    @app.errorhandler(403)
    def forbidden(e):
        """Handle 403 errors."""
        return {'error': 'Forbidden', 'message': str(e.description)}, 403
    
    @app.errorhandler(404)
    def not_found(e):
        """Handle 404 errors."""
        return {'error': 'Not Found', 'message': 'Resource not found'}, 404
    
    @app.errorhandler(500)
    def internal_error(e):
        """Handle 500 errors."""
        return {'error': 'Internal Server Error', 'message': 'An unexpected error occurred'}, 500
