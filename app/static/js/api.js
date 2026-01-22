/**
 * TG群链接验证工具 - API封装
 */

const API = {
    baseUrl: '',
    
    /**
     * 发送请求
     */
    async request(method, url, data = null) {
        const options = {
            method,
            headers: {
                'Content-Type': 'application/json',
            },
        };
        
        if (data) {
            options.body = JSON.stringify(data);
        }
        
        const response = await fetch(this.baseUrl + url, options);
        
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: '请求失败' }));
            throw new Error(error.detail || error.error || '请求失败');
        }
        
        return response.json();
    },
    
    /**
     * GET请求
     */
    get(url) {
        return this.request('GET', url);
    },
    
    /**
     * POST请求
     */
    post(url, data) {
        return this.request('POST', url, data);
    },
    
    /**
     * PUT请求
     */
    put(url, data) {
        return this.request('PUT', url, data);
    },
    
    /**
     * DELETE请求
     */
    delete(url) {
        return this.request('DELETE', url);
    },
    
    // ========== 文件API ==========
    
    /**
     * 上传文件
     */
    async uploadFile(file, onProgress) {
        const formData = new FormData();
        formData.append('file', file);
        
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            
            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable && onProgress) {
                    onProgress(Math.round((e.loaded / e.total) * 100));
                }
            });
            
            xhr.addEventListener('load', () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    resolve(JSON.parse(xhr.responseText));
                } else {
                    try {
                        const error = JSON.parse(xhr.responseText);
                        reject(new Error(error.detail || '上传失败'));
                    } catch {
                        reject(new Error('上传失败'));
                    }
                }
            });
            
            xhr.addEventListener('error', () => reject(new Error('网络错误')));
            xhr.open('POST', this.baseUrl + '/api/files/upload');
            xhr.send(formData);
        });
    },
    
    /**
     * 获取文件列表
     */
    getFiles() {
        return this.get('/api/files/list');
    },
    
    /**
     * 删除文件
     */
    deleteFile(filename) {
        return this.delete(`/api/files/${filename}`);
    },
    
    // ========== 导入API ==========
    
    /**
     * 开始导入（同步）
     */
    startImport(filename) {
        return this.post('/api/import/start', { filename });
    },
    
    /**
     * 开始异步导入
     */
    startImportAsync(filename) {
        return this.post('/api/import/async', { filename });
    },
    
    /**
     * 获取导入进度
     */
    getImportProgress(filename) {
        return this.get(`/api/import/progress/${filename}`);
    },
    
    /**
     * 获取导入统计
     */
    getImportStats() {
        return this.get('/api/import/stats');
    },
    
    // ========== 任务API ==========
    
    /**
     * 创建任务
     */
    createJob(name, linkIds = null) {
        return this.post('/api/jobs/create', { name, link_ids: linkIds });
    },
    
    /**
     * 获取任务列表
     */
    getJobs(limit = 100, offset = 0) {
        return this.get(`/api/jobs/list?limit=${limit}&offset=${offset}`);
    },
    
    /**
     * 获取任务详情
     */
    getJob(jobId) {
        return this.get(`/api/jobs/${jobId}`);
    },
    
    /**
     * 获取任务进度
     */
    getJobProgress(jobId) {
        return this.get(`/api/jobs/${jobId}/progress`);
    },
    
    /**
     * 启动任务
     */
    startJob(jobId) {
        return this.post(`/api/jobs/${jobId}/start`);
    },
    
    /**
     * 暂停任务
     */
    pauseJob(jobId) {
        return this.post(`/api/jobs/${jobId}/pause`);
    },
    
    /**
     * 继续任务
     */
    resumeJob(jobId) {
        return this.post(`/api/jobs/${jobId}/resume`);
    },
    
    /**
     * 停止任务
     */
    stopJob(jobId) {
        return this.post(`/api/jobs/${jobId}/stop`);
    },
    
    /**
     * 删除任务
     */
    deleteJob(jobId) {
        return this.delete(`/api/jobs/${jobId}`);
    },
    
    // ========== 结果API ==========
    
    /**
     * 获取任务结果
     */
    getResults(jobId, page = 1, pageSize = 50, validOnly = false, invalidOnly = false) {
        let url = `/api/results/${jobId}?page=${page}&page_size=${pageSize}`;
        if (validOnly) url += '&valid_only=true';
        if (invalidOnly) url += '&invalid_only=true';
        return this.get(url);
    },
    
    /**
     * 获取任务统计
     */
    getResultStats(jobId) {
        return this.get(`/api/results/${jobId}/stats`);
    },
    
    /**
     * 获取导出URL
     */
    getExportUrl(jobId, validOnly = false, includeErrors = false) {
        let url = `/api/results/${jobId}/export?`;
        if (validOnly) url += 'valid_only=true&';
        if (includeErrors) url += 'include_errors=true&';
        return url;
    },
    
    // ========== 配置API ==========
    
    /**
     * 获取配置
     */
    getConfig() {
        return this.get('/api/config/');
    },
    
    /**
     * 更新配置
     */
    updateConfig(config) {
        return this.put('/api/config/', config);
    },
    
    /**
     * 获取Clash状态
     */
    getClashStatus() {
        return this.get('/api/config/clash/status');
    },
    
    // ========== SSE事件 ==========
    
    /**
     * 订阅任务进度
     */
    subscribeJobProgress(jobId, callbacks) {
        const eventSource = new EventSource(`/api/events/job/${jobId}`);
        
        eventSource.addEventListener('progress', (e) => {
            if (callbacks.onProgress) {
                callbacks.onProgress(JSON.parse(e.data));
            }
        });
        
        eventSource.addEventListener('completed', (e) => {
            if (callbacks.onCompleted) {
                callbacks.onCompleted(JSON.parse(e.data));
            }
            eventSource.close();
        });
        
        eventSource.addEventListener('paused', (e) => {
            if (callbacks.onPaused) {
                callbacks.onPaused(JSON.parse(e.data));
            }
        });
        
        eventSource.addEventListener('cancelled', (e) => {
            if (callbacks.onCancelled) {
                callbacks.onCancelled(JSON.parse(e.data));
            }
            eventSource.close();
        });
        
        eventSource.addEventListener('error', (e) => {
            if (e.data && callbacks.onError) {
                callbacks.onError(JSON.parse(e.data));
            }
        });
        
        eventSource.onerror = () => {
            if (callbacks.onConnectionError) {
                callbacks.onConnectionError();
            }
        };
        
        return eventSource;
    },
    
    /**
     * 订阅导入进度
     */
    subscribeImportProgress(filename, callbacks) {
        const eventSource = new EventSource(`/api/import/events/${filename}`);
        
        eventSource.addEventListener('progress', (e) => {
            if (callbacks.onProgress) {
                callbacks.onProgress(JSON.parse(e.data));
            }
        });
        
        eventSource.addEventListener('completed', (e) => {
            if (callbacks.onCompleted) {
                callbacks.onCompleted(JSON.parse(e.data));
            }
            eventSource.close();
        });
        
        eventSource.addEventListener('error', (e) => {
            if (callbacks.onError) {
                callbacks.onError(JSON.parse(e.data));
            }
            eventSource.close();
        });
        
        return eventSource;
    }
};
