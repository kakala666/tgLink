/**
 * TG群链接验证工具 - 公共JS
 */

const App = {
    /**
     * 显示提示消息
     */
    showMessage(message, type = 'info') {
        const container = document.getElementById('message-container') || this.createMessageContainer();
        
        const alert = document.createElement('div');
        alert.className = `alert alert-${type}`;
        alert.innerHTML = `
            <span>${message}</span>
            <button type="button" onclick="this.parentElement.remove()" style="background:none;border:none;cursor:pointer;font-size:18px;margin-left:auto;">&times;</button>
        `;
        alert.style.cssText = 'display:flex;align-items:center;animation:slideIn 0.3s ease;';
        
        container.appendChild(alert);
        
        // 自动消失
        setTimeout(() => {
            if (alert.parentElement) {
                alert.style.animation = 'slideOut 0.3s ease';
                setTimeout(() => alert.remove(), 300);
            }
        }, 5000);
    },
    
    createMessageContainer() {
        const container = document.createElement('div');
        container.id = 'message-container';
        container.style.cssText = 'position:fixed;top:80px;right:20px;z-index:1000;width:350px;';
        document.body.appendChild(container);
        
        // 添加动画样式
        const style = document.createElement('style');
        style.textContent = `
            @keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
            @keyframes slideOut { from { transform: translateX(0); opacity: 1; } to { transform: translateX(100%); opacity: 0; } }
        `;
        document.head.appendChild(style);
        
        return container;
    },
    
    /**
     * 格式化文件大小
     */
    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },
    
    /**
     * 格式化时间
     */
    formatTime(seconds) {
        if (!seconds || seconds <= 0) return '-';
        
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = Math.floor(seconds % 60);
        
        if (h > 0) {
            return `${h}小时${m}分钟`;
        } else if (m > 0) {
            return `${m}分钟${s}秒`;
        } else {
            return `${s}秒`;
        }
    },
    
    /**
     * 格式化日期时间
     */
    formatDateTime(dateStr) {
        if (!dateStr) return '-';
        const date = new Date(dateStr);
        return date.toLocaleString('zh-CN');
    },
    
    /**
     * 格式化数字
     */
    formatNumber(num) {
        if (num === null || num === undefined) return '0';
        return num.toLocaleString('zh-CN');
    },
    
    /**
     * 获取状态标签HTML
     */
    getStatusBadge(status) {
        const statusMap = {
            pending: { text: '待开始', class: 'badge-pending' },
            running: { text: '运行中', class: 'badge-running' },
            paused: { text: '已暂停', class: 'badge-paused' },
            completed: { text: '已完成', class: 'badge-completed' },
            failed: { text: '失败', class: 'badge-failed' },
            cancelled: { text: '已取消', class: 'badge-cancelled' },
        };
        
        const info = statusMap[status] || { text: status, class: 'badge-pending' };
        return `<span class="badge ${info.class}">${info.text}</span>`;
    },
    
    /**
     * 获取有效性标签HTML
     */
    getValidBadge(isValid) {
        if (isValid === true) {
            return '<span class="badge badge-valid">有效</span>';
        } else if (isValid === false) {
            return '<span class="badge badge-invalid">无效</span>';
        } else {
            return '<span class="badge badge-pending">未知</span>';
        }
    },
    
    /**
     * 确认对话框
     */
    confirm(message) {
        return window.confirm(message);
    },
    
    /**
     * 显示加载遮罩
     */
    showLoading() {
        let overlay = document.getElementById('loading-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'loading-overlay';
            overlay.className = 'loading-overlay';
            overlay.innerHTML = '<div class="spinner" style="width:40px;height:40px;border-width:3px;"></div>';
            document.body.appendChild(overlay);
        }
        overlay.style.display = 'flex';
    },
    
    /**
     * 隐藏加载遮罩
     */
    hideLoading() {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) {
            overlay.style.display = 'none';
        }
    },
    
    /**
     * 设置按钮加载状态
     */
    setButtonLoading(button, loading) {
        if (loading) {
            button.disabled = true;
            button.dataset.originalText = button.innerHTML;
            button.innerHTML = '<span class="spinner"></span> 处理中...';
        } else {
            button.disabled = false;
            button.innerHTML = button.dataset.originalText || button.innerHTML;
        }
    },
    
    /**
     * 初始化导航栏活动状态
     */
    initNavbar() {
        const path = window.location.pathname;
        document.querySelectorAll('.navbar-nav a').forEach(link => {
            if (link.getAttribute('href') === path) {
                link.classList.add('active');
            }
        });
    }
};

// 页面加载完成后初始化导航栏
document.addEventListener('DOMContentLoaded', () => {
    App.initNavbar();
});
