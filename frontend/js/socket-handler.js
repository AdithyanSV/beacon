/**
 * Socket Handler - WebSocket communication with server
 * 
 * Manages Socket.IO connection and event handling.
 */

const SocketHandler = {
    socket: null,
    connected: false,
    reconnectAttempts: 0,
    maxReconnectAttempts: 5,
    
    // Event callbacks
    callbacks: {
        onConnect: null,
        onDisconnect: null,
        onError: null,
        onMessageReceived: null,
        onMessageSent: null,
        onDevicesUpdated: null,
        onStatusUpdate: null,
    },

    /**
     * Initialize the socket connection
     */
    init() {
        // Connect to the server
        this.socket = io({
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionAttempts: this.maxReconnectAttempts,
            reconnectionDelay: 1000,
            reconnectionDelayMax: 5000,
            timeout: 20000,
        });

        this._setupEventListeners();
    },

    /**
     * Set up socket event listeners
     */
    _setupEventListeners() {
        // Connection events
        this.socket.on('connect', () => {
            console.log('Connected to server');
            this.connected = true;
            this.reconnectAttempts = 0;
            
            if (this.callbacks.onConnect) {
                this.callbacks.onConnect();
            }
        });

        this.socket.on('disconnect', (reason) => {
            console.log('Disconnected from server:', reason);
            this.connected = false;
            
            if (this.callbacks.onDisconnect) {
                this.callbacks.onDisconnect(reason);
            }
        });

        this.socket.on('connect_error', (error) => {
            console.error('Connection error:', error);
            this.reconnectAttempts++;
            
            if (this.callbacks.onError) {
                this.callbacks.onError({
                    message: 'Connection failed',
                    code: 'CONNECTION_ERROR',
                });
            }
        });

        // Server events
        this.socket.on('connected', (data) => {
            console.log('Server acknowledged connection:', data);
            
            // Store session info
            this.sessionId = data.session_id;
            this.limits = data.limits;
            
            // Request initial data
            this.requestDevices();
            this.requestMessages();
        });

        this.socket.on('message_received', (data) => {
            console.log('Message received:', data);
            
            if (this.callbacks.onMessageReceived) {
                this.callbacks.onMessageReceived(data);
            }
        });

        this.socket.on('message_sent', (data) => {
            console.log('Message sent confirmation:', data);
            
            if (this.callbacks.onMessageSent) {
                this.callbacks.onMessageSent(data);
            }
        });

        this.socket.on('devices_updated', (data) => {
            console.log('Devices updated:', data);
            
            if (this.callbacks.onDevicesUpdated) {
                this.callbacks.onDevicesUpdated(data);
            }
        });

        this.socket.on('messages_list', (data) => {
            console.log('Messages list received:', data);
            
            // Process each message
            if (data.messages && this.callbacks.onMessageReceived) {
                data.messages.forEach(msg => {
                    this.callbacks.onMessageReceived(msg);
                });
            }
        });

        this.socket.on('status', (data) => {
            console.log('Status update:', data);
            
            if (this.callbacks.onStatusUpdate) {
                this.callbacks.onStatusUpdate(data);
            }
        });

        this.socket.on('status_update', (data) => {
            if (this.callbacks.onStatusUpdate) {
                this.callbacks.onStatusUpdate(data);
            }
        });

        this.socket.on('error', (data) => {
            console.error('Server error:', data);
            
            if (this.callbacks.onError) {
                this.callbacks.onError(data);
            }
        });
        
        // Log messages from server
        this.socket.on('log_message', (logData) => {
            console.log('[LOG]', logData);
            if (typeof LogViewer !== 'undefined' && LogViewer.addLog) {
                LogViewer.addLog(logData);
            }
        });
    },

    /**
     * Send a message to broadcast
     * @param {string} content - Message content
     */
    sendMessage(content) {
        if (!this.connected) {
            console.error('Not connected to server');
            if (this.callbacks.onError) {
                this.callbacks.onError({
                    message: 'Not connected to server',
                    code: 'NOT_CONNECTED',
                });
            }
            return;
        }

        this.socket.emit('send_message', { content });
    },

    /**
     * Request device list from server
     */
    requestDevices() {
        if (this.connected) {
            this.socket.emit('request_devices');
        }
    },

    /**
     * Request recent messages from server
     */
    requestMessages() {
        if (this.connected) {
            this.socket.emit('request_messages');
        }
    },

    /**
     * Request system status
     */
    requestStatus() {
        if (this.connected) {
            this.socket.emit('request_status');
        }
    },

    /**
     * Set callback for an event
     * @param {string} event - Event name
     * @param {Function} callback - Callback function
     */
    on(event, callback) {
        const callbackName = 'on' + event.charAt(0).toUpperCase() + event.slice(1);
        if (callbackName in this.callbacks) {
            this.callbacks[callbackName] = callback;
        }
    },

    /**
     * Disconnect from server
     */
    disconnect() {
        if (this.socket) {
            this.socket.disconnect();
        }
    },

    /**
     * Reconnect to server
     */
    reconnect() {
        if (this.socket) {
            this.socket.connect();
        }
    },

    /**
     * Check if connected
     * @returns {boolean}
     */
    isConnected() {
        return this.connected;
    }
};

// Export for use in other modules
window.SocketHandler = SocketHandler;
