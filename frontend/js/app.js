/**
 * Main Application - Entry point and initialization
 * 
 * Coordinates all modules and handles application lifecycle.
 */

const App = {
    // Application state
    initialized: false,
    
    /**
     * Initialize the application
     */
    init() {
        if (this.initialized) return;
        
        console.log('Initializing Bluetooth Mesh Broadcast...');
        
        // Initialize UI
        UIController.init();
        
        // Set up socket callbacks
        this._setupSocketCallbacks();
        
        // Initialize socket connection
        SocketHandler.init();
        
        // Set initial status
        UIController.setConnectionStatus('connecting', 'Connecting...');
        
        this.initialized = true;
        console.log('Application initialized');
    },

    /**
     * Set up socket event callbacks
     */
    _setupSocketCallbacks() {
        // Connection events
        SocketHandler.on('connect', () => {
            UIController.setConnectionStatus('connected', 'Connected');
            UIController.setInputEnabled(true);
        });

        SocketHandler.on('disconnect', (reason) => {
            UIController.setConnectionStatus('disconnected', 'Disconnected');
            UIController.setInputEnabled(false);
            
            if (reason === 'io server disconnect') {
                UIController.showError('Disconnected by server');
            } else {
                UIController.showError('Connection lost. Reconnecting...');
            }
        });

        // Error handling
        SocketHandler.on('error', (error) => {
            console.error('Socket error:', error);
            
            let message = error.message || 'An error occurred';
            
            // Handle specific error codes
            switch (error.code) {
                case 'RATE_LIMIT_EXCEEDED':
                    message = `Rate limit exceeded. Please wait ${Math.ceil(error.retry_after || 60)} seconds.`;
                    break;
                case 'NOT_CONNECTED':
                    message = 'Not connected to server';
                    break;
                case 'CONNECTION_ERROR':
                    message = 'Failed to connect to server';
                    UIController.setConnectionStatus('error', 'Connection Error');
                    break;
                case 'INVALID_PAYLOAD':
                case 'EMPTY_CONTENT':
                    message = error.message;
                    break;
            }
            
            UIController.showError(message);
        });

        // Message events
        SocketHandler.on('messageReceived', (message) => {
            UIController.addMessage(message);
        });

        SocketHandler.on('messageSent', (data) => {
            if (data.success) {
                console.log('Message sent successfully:', data.message_id);
            }
        });

        // Device events
        SocketHandler.on('devicesUpdated', (data) => {
            UIController.updateDevices(data.devices, data.count);
        });

        // Status events
        SocketHandler.on('statusUpdate', (status) => {
            console.log('Status update:', status);
            // Could update UI with detailed status if needed
        });
    },

    /**
     * Refresh device list
     */
    refreshDevices() {
        SocketHandler.requestDevices();
    },

    /**
     * Refresh messages
     */
    refreshMessages() {
        SocketHandler.requestMessages();
    },

    /**
     * Get application status
     */
    getStatus() {
        return {
            initialized: this.initialized,
            connected: SocketHandler.isConnected(),
        };
    }
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    App.init();
});

// Handle page visibility changes
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
        // Refresh data when page becomes visible
        if (SocketHandler.isConnected()) {
            App.refreshDevices();
        }
    }
});

// Handle before unload
window.addEventListener('beforeunload', () => {
    SocketHandler.disconnect();
});

// Export for debugging
window.App = App;
