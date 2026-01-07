/**
 * UI Controller - Manages UI updates and interactions
 * 
 * Handles DOM manipulation and user interface state.
 */

const UIController = {
    // DOM element references
    elements: {
        statusIndicator: null,
        statusText: null,
        deviceCount: null,
        devicesList: null,
        messagesContainer: null,
        messageInput: null,
        charCount: null,
        sendButton: null,
        clearButton: null,
        inputHint: null,
        toastContainer: null,
    },

    // State
    messageIds: new Set(), // Track displayed message IDs

    /**
     * Initialize UI controller
     */
    init() {
        this._cacheElements();
        this._setupEventListeners();
        this._setupTextareaAutoResize();
    },

    /**
     * Cache DOM element references
     */
    _cacheElements() {
        this.elements.statusIndicator = document.getElementById('statusIndicator');
        this.elements.statusText = this.elements.statusIndicator?.querySelector('.status-text');
        this.elements.deviceCount = document.getElementById('deviceCount');
        this.elements.devicesList = document.getElementById('devicesList');
        this.elements.messagesContainer = document.getElementById('messagesContainer');
        this.elements.messageInput = document.getElementById('messageInput');
        this.elements.charCount = document.getElementById('charCount');
        this.elements.sendButton = document.getElementById('sendButton');
        this.elements.clearButton = document.getElementById('clearMessages');
        this.elements.inputHint = document.getElementById('inputHint');
        this.elements.toastContainer = document.getElementById('toastContainer');
    },

    /**
     * Set up event listeners
     */
    _setupEventListeners() {
        // Message input
        if (this.elements.messageInput) {
            this.elements.messageInput.addEventListener('input', () => {
                this._handleInputChange();
            });

            this.elements.messageInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this._handleSend();
                }
            });
        }

        // Send button
        if (this.elements.sendButton) {
            this.elements.sendButton.addEventListener('click', () => {
                this._handleSend();
            });
        }

        // Clear button
        if (this.elements.clearButton) {
            this.elements.clearButton.addEventListener('click', () => {
                this.clearMessages();
            });
        }
    },

    /**
     * Set up textarea auto-resize
     */
    _setupTextareaAutoResize() {
        const textarea = this.elements.messageInput;
        if (!textarea) return;

        textarea.addEventListener('input', () => {
            textarea.style.height = 'auto';
            textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
        });
    },

    /**
     * Handle input change
     */
    _handleInputChange() {
        const content = this.elements.messageInput.value;
        const charInfo = InputValidator.getCharacterInfo(content);

        // Update character count
        this.elements.charCount.textContent = charInfo.count;
        
        // Update character count styling
        const charCountContainer = this.elements.charCount.parentElement;
        charCountContainer.classList.remove('warning', 'error');
        if (charInfo.status !== 'normal') {
            charCountContainer.classList.add(charInfo.status);
        }

        // Validate and update send button
        const validation = InputValidator.validateMessage(content);
        this.elements.sendButton.disabled = !validation.valid;

        // Update hint
        if (!validation.valid && content.length > 0) {
            this.elements.inputHint.textContent = validation.error;
        } else {
            this.elements.inputHint.textContent = '';
        }
    },

    /**
     * Handle send action
     */
    _handleSend() {
        const content = this.elements.messageInput.value;
        
        if (!InputValidator.canSend(content)) {
            return;
        }

        // Sanitize content
        const sanitized = InputValidator.sanitize(content);

        // Send via socket
        SocketHandler.sendMessage(sanitized);

        // Clear input
        this.elements.messageInput.value = '';
        this.elements.messageInput.style.height = 'auto';
        this._handleInputChange();
    },

    /**
     * Update connection status
     * @param {string} status - 'connected', 'disconnected', 'connecting', 'error'
     * @param {string} message - Status message
     */
    setConnectionStatus(status, message) {
        if (!this.elements.statusIndicator) return;

        // Remove all status classes
        this.elements.statusIndicator.classList.remove('connected', 'error');

        // Add appropriate class
        if (status === 'connected') {
            this.elements.statusIndicator.classList.add('connected');
        } else if (status === 'error') {
            this.elements.statusIndicator.classList.add('error');
        }

        // Update text
        if (this.elements.statusText) {
            this.elements.statusText.textContent = message || status;
        }
    },

    /**
     * Update devices list
     * @param {Array} devices - Array of device objects
     * @param {number} count - Total device count
     */
    updateDevices(devices, count) {
        // Update count
        if (this.elements.deviceCount) {
            this.elements.deviceCount.textContent = `${count}/5`;
        }

        // Update list
        if (!this.elements.devicesList) return;

        if (!devices || devices.length === 0) {
            this.elements.devicesList.innerHTML = `
                <div class="empty-state">
                    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="2"/>
                        <path d="M12 1V3M12 21V23M4.22 4.22L5.64 5.64M18.36 18.36L19.78 19.78M1 12H3M21 12H23M4.22 19.78L5.64 18.36M18.36 5.64L19.78 4.22" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    </svg>
                    <p>Scanning for devices...</p>
                </div>
            `;
            return;
        }

        this.elements.devicesList.innerHTML = devices.map(device => `
            <div class="device-item">
                <div class="device-status"></div>
                <div class="device-info">
                    <div class="device-name">${InputValidator.escapeHtml(device.name || 'Unknown Device')}</div>
                    <div class="device-address">${InputValidator.escapeHtml(device.address || device.id || '')}</div>
                </div>
            </div>
        `).join('');
    },

    /**
     * Add a message to the display
     * @param {Object} message - Message object
     */
    addMessage(message) {
        if (!this.elements.messagesContainer) return;

        // Check for duplicate
        if (this.messageIds.has(message.message_id)) {
            return;
        }
        this.messageIds.add(message.message_id);

        // Remove welcome message if present
        const welcome = this.elements.messagesContainer.querySelector('.welcome-message');
        if (welcome) {
            welcome.remove();
        }

        // Create message element
        const messageEl = document.createElement('div');
        messageEl.className = `message ${message.is_own ? 'own' : 'other'}`;
        messageEl.dataset.messageId = message.message_id;

        const senderName = message.is_own ? 'You' : (message.sender_name || 'Unknown');
        const timestamp = InputValidator.formatTimestamp(message.timestamp);
        const content = InputValidator.escapeHtml(message.content);

        messageEl.innerHTML = `
            <div class="message-header">
                <span class="message-sender">${InputValidator.escapeHtml(senderName)}</span>
                <span class="message-time">${timestamp}</span>
            </div>
            <div class="message-bubble">${content}</div>
        `;

        this.elements.messagesContainer.appendChild(messageEl);

        // Auto-scroll to bottom
        this._scrollToBottom();

        // Limit displayed messages
        this._trimMessages();
    },

    /**
     * Clear all messages
     */
    clearMessages() {
        if (!this.elements.messagesContainer) return;

        this.elements.messagesContainer.innerHTML = `
            <div class="welcome-message">
                <p>Welcome to Bluetooth Mesh Broadcast!</p>
                <p class="sub">Send a message to broadcast it to all connected devices.</p>
            </div>
        `;
        this.messageIds.clear();
    },

    /**
     * Scroll messages to bottom
     */
    _scrollToBottom() {
        if (this.elements.messagesContainer) {
            this.elements.messagesContainer.scrollTop = this.elements.messagesContainer.scrollHeight;
        }
    },

    /**
     * Trim old messages to limit
     */
    _trimMessages() {
        const maxMessages = 50;
        const messages = this.elements.messagesContainer.querySelectorAll('.message');
        
        if (messages.length > maxMessages) {
            const toRemove = messages.length - maxMessages;
            for (let i = 0; i < toRemove; i++) {
                const msg = messages[i];
                this.messageIds.delete(msg.dataset.messageId);
                msg.remove();
            }
        }
    },

    /**
     * Show a toast notification
     * @param {string} message - Toast message
     * @param {string} type - 'error', 'success', 'info'
     * @param {number} duration - Duration in ms
     */
    showToast(message, type = 'info', duration = 5000) {
        if (!this.elements.toastContainer) return;

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <span class="toast-message">${InputValidator.escapeHtml(message)}</span>
            <button class="toast-close">&times;</button>
        `;

        // Close button handler
        toast.querySelector('.toast-close').addEventListener('click', () => {
            toast.remove();
        });

        this.elements.toastContainer.appendChild(toast);

        // Auto-remove after duration
        setTimeout(() => {
            if (toast.parentElement) {
                toast.remove();
            }
        }, duration);
    },

    /**
     * Show error toast
     * @param {string} message - Error message
     */
    showError(message) {
        this.showToast(message, 'error');
    },

    /**
     * Show success toast
     * @param {string} message - Success message
     */
    showSuccess(message) {
        this.showToast(message, 'success');
    },

    /**
     * Enable/disable input
     * @param {boolean} enabled
     */
    setInputEnabled(enabled) {
        if (this.elements.messageInput) {
            this.elements.messageInput.disabled = !enabled;
        }
        if (this.elements.sendButton) {
            this.elements.sendButton.disabled = !enabled;
        }
    }
};

// Export for use in other modules
window.UIController = UIController;
