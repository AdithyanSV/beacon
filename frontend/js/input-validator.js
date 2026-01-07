/**
 * Input Validator - Client-side input validation
 * 
 * Provides validation and sanitization for user inputs
 * before sending to the server.
 */

const InputValidator = {
    // Configuration
    config: {
        maxMessageLength: 450,
        maxContentBytes: 500,
        minMessageLength: 1,
    },

    // Dangerous patterns to block
    dangerousPatterns: [
        /<\s*script/i,
        /javascript\s*:/i,
        /on\w+\s*=/i,
        /<\s*iframe/i,
        /<\s*object/i,
        /<\s*embed/i,
    ],

    /**
     * Validate message content
     * @param {string} content - Message content to validate
     * @returns {Object} - { valid: boolean, error: string|null }
     */
    validateMessage(content) {
        // Check if empty
        if (!content || content.trim().length === 0) {
            return { valid: false, error: 'Message cannot be empty' };
        }

        // Check length
        const trimmed = content.trim();
        if (trimmed.length > this.config.maxMessageLength) {
            return { 
                valid: false, 
                error: `Message exceeds ${this.config.maxMessageLength} characters` 
            };
        }

        // Check byte size (UTF-8)
        const byteSize = new Blob([trimmed]).size;
        if (byteSize > this.config.maxContentBytes) {
            return { 
                valid: false, 
                error: `Message exceeds ${this.config.maxContentBytes} bytes` 
            };
        }

        // Check for dangerous patterns
        for (const pattern of this.dangerousPatterns) {
            if (pattern.test(content)) {
                return { valid: false, error: 'Message contains blocked content' };
            }
        }

        return { valid: true, error: null };
    },

    /**
     * Sanitize message content
     * @param {string} content - Content to sanitize
     * @returns {string} - Sanitized content
     */
    sanitize(content) {
        if (!content) return '';

        let sanitized = content;

        // Remove control characters (except newline and tab)
        sanitized = sanitized.replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, '');

        // Trim whitespace
        sanitized = sanitized.trim();

        // Limit length
        if (sanitized.length > this.config.maxMessageLength) {
            sanitized = sanitized.substring(0, this.config.maxMessageLength);
        }

        return sanitized;
    },

    /**
     * Escape HTML entities for safe display
     * @param {string} text - Text to escape
     * @returns {string} - Escaped text
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    /**
     * Get character count info
     * @param {string} content - Content to count
     * @returns {Object} - { count: number, remaining: number, status: string }
     */
    getCharacterInfo(content) {
        const count = content ? content.length : 0;
        const remaining = this.config.maxMessageLength - count;
        
        let status = 'normal';
        if (remaining <= 0) {
            status = 'error';
        } else if (remaining <= 50) {
            status = 'warning';
        }

        return { count, remaining, status };
    },

    /**
     * Check if content is valid for sending
     * @param {string} content - Content to check
     * @returns {boolean}
     */
    canSend(content) {
        const validation = this.validateMessage(content);
        return validation.valid;
    },

    /**
     * Format timestamp for display
     * @param {number} timestamp - Unix timestamp
     * @returns {string} - Formatted time string
     */
    formatTimestamp(timestamp) {
        const date = new Date(timestamp * 1000);
        return date.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });
    },

    /**
     * Truncate text with ellipsis
     * @param {string} text - Text to truncate
     * @param {number} maxLength - Maximum length
     * @returns {string}
     */
    truncate(text, maxLength = 50) {
        if (!text || text.length <= maxLength) return text;
        return text.substring(0, maxLength - 3) + '...';
    }
};

// Export for use in other modules
window.InputValidator = InputValidator;
