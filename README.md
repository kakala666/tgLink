# TG群链接验证工具

批量验证Telegram群组/频道链接有效性，提取群名，支持百万级链接处理。

## 功能特性

- **批量导入**: 支持TXT文件导入，每行一个链接
- **智能去重**: 自动标准化URL并去重
- **高效验证**: 通过抓取t.me页面提取群名（SSR，无需JavaScript）
- **代理支持**: 集成Clash代理池，60节点轮询，50并发
- **实时进度**: SSE实时推送验证进度
- **CSV导出**: GB2312编码，Tab分隔，Excel直接打开
- **阻止检测**: 滑动窗口统计，自动暂停防封

## 技术栈

- **后端**: Python + FastAPI
- **数据库**: SQLite（WAL模式）
- **前端**: 纯HTML/CSS/JS
- **代理**: Clash代理池

## 快速开始

### 1. 克隆项目

```bash
git clone git@github.com:kakala666/tgLink.git
cd tgLink
```

### 2. 安装依赖

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

pip install -r requirements.txt
```

### 3. 启动服务

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

访问 http://localhost:8000

## Debian服务器部署

### 1. 安装依赖

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git
```

### 2. 安装Clash（可选，代理模式需要）

```bash
# 下载Clash Premium
wget https://github.com/Dreamacro/clash/releases/download/premium/clash-linux-amd64-2023.xx.xx.gz
gunzip clash-linux-amd64-*.gz
chmod +x clash-linux-amd64-*
sudo mv clash-linux-amd64-* /usr/local/bin/clash

# 创建配置目录
sudo mkdir -p /etc/clash
sudo cp deploy/clash-config.yaml /etc/clash/config.yaml
# 编辑配置文件，填入您的VLESS节点
sudo nano /etc/clash/config.yaml

# 创建Clash服务
sudo tee /etc/systemd/system/clash.service << EOF
[Unit]
Description=Clash daemon
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/clash -d /etc/clash
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable clash
sudo systemctl start clash
```

### 3. 部署应用

```bash
# 克隆项目
cd /opt
sudo git clone git@github.com:kakala666/tgLink.git tglink
cd tglink

# 创建虚拟环境
sudo python3 -m venv venv
sudo ./venv/bin/pip install -r requirements.txt

# 设置权限
sudo chown -R www-data:www-data /opt/tglink

# 创建日志目录
sudo mkdir -p /var/log/tglink
sudo chown www-data:www-data /var/log/tglink

# 安装服务
sudo cp deploy/tglink.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tglink
sudo systemctl start tglink
```

### 4. 配置Nginx（可选）

```bash
sudo apt install -y nginx

sudo tee /etc/nginx/sites-available/tglink << EOF
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        
        # SSE支持
        proxy_buffering off;
        proxy_cache off;
    }
    
    # 文件上传大小限制
    client_max_body_size 500M;
}
EOF

sudo ln -s /etc/nginx/sites-available/tglink /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 配置说明

编辑 `app/config.py` 修改配置：

```python
# 代理模式开关
PROXY_ENABLED = True  # True=使用Clash代理，False=直连

# 代理模式并发数
PROXY_CONCURRENCY = 50

# 直连模式请求间隔
DIRECT_REQUEST_INTERVAL = 1.0

# 阻止检测
BLOCK_DETECTION_WINDOW = 60  # 检测窗口（秒）
BLOCK_DETECTION_THRESHOLD = 5  # 触发阈值
```

## 性能估算

| 模式 | 并发 | 120万链接预计时间 |
|------|------|-------------------|
| 代理模式 | 50 | ~14小时 |
| 直连模式 | 1 | ~14天 |

## 使用流程

1. **上传文件**: 首页上传包含TG链接的txt文件
2. **导入链接**: 点击"开始导入"解析并去重
3. **创建任务**: 输入任务名称，创建验证任务
4. **启动验证**: 在任务详情页点击"启动"
5. **查看进度**: 实时查看验证进度和结果
6. **导出结果**: 下载CSV格式的验证结果

## 项目结构

```
tgLink/
├── app/
│   ├── api/              # API路由
│   │   ├── routes_files.py
│   │   ├── routes_import.py
│   │   ├── routes_jobs.py
│   │   ├── routes_results.py
│   │   ├── routes_events.py
│   │   └── routes_config.py
│   ├── db/               # 数据库
│   │   ├── schema.sql
│   │   └── sqlite.py
│   ├── models/           # 数据模型
│   │   └── schemas.py
│   ├── services/         # 业务服务
│   │   ├── import_service.py
│   │   ├── validator.py
│   │   ├── rate_limiter.py
│   │   ├── block_detector.py
│   │   ├── job_service.py
│   │   ├── exporter.py
│   │   └── clash_client.py
│   ├── workers/          # 任务运行器
│   │   └── runner.py
│   ├── static/           # 前端文件
│   │   ├── css/
│   │   ├── js/
│   │   ├── index.html
│   │   ├── jobs.html
│   │   ├── job_detail.html
│   │   └── settings.html
│   ├── config.py         # 配置
│   └── main.py           # 入口
├── deploy/               # 部署文件
│   ├── tglink.service
│   └── clash-config.yaml
├── data/                 # 数据目录
│   └── uploads/
├── requirements.txt
└── README.md
```

## API文档

启动服务后访问 http://localhost:8000/docs 查看Swagger文档。

## 许可证

MIT License
