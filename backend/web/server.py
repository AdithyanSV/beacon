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
        return {
            'status': 'running',
            'version': '1.0.0',
            'bluetooth': {
                'enabled': True,
                'max_connections': Config.bluetooth.MAX_CONCURRENT_CONNECTIONS,
            },
            'limits': {
                'max_message_size': Config.message.MAX_MESSAGE_SIZE,
                'max_content_length': Config.message.MAX_CONTENT_LENGTH,
                'message_ttl': Config.message.MESSAGE_TTL,
            }
        }
    
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
