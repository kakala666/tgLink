-- TG群链接验证工具 - 数据库表结构

-- 链接表：存储所有导入的链接
CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_url TEXT NOT NULL,           -- 原始URL
    normalized_url TEXT NOT NULL UNIQUE,  -- 标准化URL（用于去重）
    link_type TEXT NOT NULL,              -- 链接类型: group, channel, user, joinchat, unknown
    identifier TEXT NOT NULL,             -- 提取的标识符（用户名或hash）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引加速查询
CREATE INDEX IF NOT EXISTS idx_links_normalized ON links(normalized_url);
CREATE INDEX IF NOT EXISTS idx_links_identifier ON links(identifier);

-- 任务表：存储验证任务
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                   -- 任务名称
    status TEXT NOT NULL DEFAULT 'pending', -- pending, running, paused, completed, failed, cancelled
    total_count INTEGER DEFAULT 0,        -- 总链接数
    pending_count INTEGER DEFAULT 0,      -- 待验证数
    valid_count INTEGER DEFAULT 0,        -- 有效数
    invalid_count INTEGER DEFAULT 0,      -- 无效数
    error_count INTEGER DEFAULT 0,        -- 错误数
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT                    -- 错误信息
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);

-- 任务项表：任务与链接的关联
CREATE TABLE IF NOT EXISTS job_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    link_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', -- pending, processing, completed, error
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
    FOREIGN KEY (link_id) REFERENCES links(id) ON DELETE CASCADE,
    UNIQUE(job_id, link_id)
);

CREATE INDEX IF NOT EXISTS idx_job_items_job_id ON job_items(job_id);
CREATE INDEX IF NOT EXISTS idx_job_items_status ON job_items(status);
CREATE INDEX IF NOT EXISTS idx_job_items_job_status ON job_items(job_id, status);

-- 验证结果表
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    link_id INTEGER NOT NULL,
    job_id INTEGER NOT NULL,
    is_valid BOOLEAN,                     -- 是否有效
    group_name TEXT,                      -- 群名/频道名
    member_count INTEGER,                 -- 成员数（如果能获取）
    description TEXT,                     -- 描述（如果能获取）
    http_status INTEGER,                  -- HTTP状态码
    error_type TEXT,                      -- 错误类型
    error_message TEXT,                   -- 错误信息
    response_time_ms INTEGER,             -- 响应时间（毫秒）
    proxy_used TEXT,                      -- 使用的代理
    verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (link_id) REFERENCES links(id) ON DELETE CASCADE,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_results_link_id ON results(link_id);
CREATE INDEX IF NOT EXISTS idx_results_job_id ON results(job_id);
CREATE INDEX IF NOT EXISTS idx_results_is_valid ON results(is_valid);
CREATE INDEX IF NOT EXISTS idx_results_job_valid ON results(job_id, is_valid);

-- 导入记录表
CREATE TABLE IF NOT EXISTS import_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    file_size INTEGER,
    total_lines INTEGER,                  -- 文件总行数
    valid_links INTEGER,                  -- 有效链接数
    duplicate_links INTEGER,              -- 重复链接数
    invalid_lines INTEGER,                -- 无效行数
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
