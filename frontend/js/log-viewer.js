/**
 * Log Viewer - Real-time log display from WebSocket
 */

const LogViewer = {
    elements: {
        logsPanel: null,
        logsContainer: null,
        clearLogsBtn: null,
        toggleLogsBtn: null,
    },
    
    maxLogs: 500,
    autoScroll: true,
    isExpanded: false,
    
    init() {
        this.elements.logsPanel = document.getElementById('logsPanel');
        this.elements.logsContainer = document.getElementById('logsContainer');
        this.elements.clearLogsBtn = document.getElementById('clearLogs');
        this.elements.toggleLogsBtn = document.getElementById('toggleLogs');
        
        if (!this.elements.logsPanel) return;
        
        // Set up event listeners
        if (this.elements.clearLogsBtn) {
            this.elements.clearLogsBtn.addEventListener('click', () => this.clearLogs());
        }
        
        if (this.elements.toggleLogsBtn) {
            this.elements.toggleLogsBtn.addEventListener('click', () => this.togglePanel());
        }
        
        // Start collapsed
        this.collapsePanel();
    },
    
    addLog(logData) {
        if (!this.elements.logsContainer) return;
        
        const logEntry = document.createElement('div');
        logEntry.className = `log-entry ${logData.level.toLowerCase()}`;
        
        const time = logData.time || logData.timestamp || '--:--:--';
        const level = logData.level || 'INFO';
        const message = logData.message || '';
        const source = logData.source ? `${logData.source.file}:${logData.source.line}` : '';
        
        logEntry.innerHTML = `
            <span class="log-time">${time}</span>
            <span class="log-level">${level}</span>
            <span class="log-message">${this.escapeHtml(message)}</span>
            ${source ? `<span class="log-source">${this.escapeHtml(source)}</span>` : ''}
        `;
        
        this.elements.logsContainer.appendChild(logEntry);
        
        // Limit number of logs
        const logs = this.elements.logsContainer.querySelectorAll('.log-entry');
        if (logs.length > this.maxLogs) {
            logs[0].remove();
        }
        
        // Auto-scroll to bottom
        if (this.autoScroll) {
            this.elements.logsContainer.scrollTop = this.elements.logsContainer.scrollHeight;
        }
    },
    
    clearLogs() {
        if (!this.elements.logsContainer) return;
        this.elements.logsContainer.innerHTML = '';
        this.addLog({
            level: 'INFO',
            message: 'Logs cleared',
            time: new Date().toLocaleTimeString()
        });
    },
    
    togglePanel() {
        if (this.isExpanded) {
            this.collapsePanel();
        } else {
            this.expandPanel();
        }
    },
    
    expandPanel() {
        if (this.elements.logsPanel) {
            this.elements.logsPanel.classList.add('expanded');
            this.isExpanded = true;
            if (this.elements.toggleLogsBtn) {
                this.elements.toggleLogsBtn.querySelector('svg').style.transform = 'rotate(180deg)';
            }
        }
    },
    
    collapsePanel() {
        if (this.elements.logsPanel) {
            this.elements.logsPanel.classList.remove('expanded');
            this.isExpanded = false;
            if (this.elements.toggleLogsBtn) {
                this.elements.toggleLogsBtn.querySelector('svg').style.transform = 'rotate(0deg)';
            }
        }
    },
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },
    
    setAutoScroll(enabled) {
        this.autoScroll = enabled;
    }
};

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => LogViewer.init());
} else {
    LogViewer.init();
}
