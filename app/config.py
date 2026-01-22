"""
TG群链接验证工具 - 配置文件
"""
import os
from pathlib import Path

# ============ 基础路径 ============
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "tglink.db"

# 确保目录存在
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ============ 代理配置 ============
# 代理总开关
# True: 使用Clash代理池
# False: 直连模式
PROXY_ENABLED = False  # 默认直连

# Clash API配置（用于获取代理列表，可选）
CLASH_API_URL = "http://127.0.0.1:9097"
CLASH_API_SECRET = "abcdefg"  # 如果Clash设置了secret，在这里填写

# Clash HTTP代理端口（用于实际请求）
CLASH_PROXY_PORT = 7897

# 代理模式下的并发数
PROXY_CONCURRENCY = 50  # 代理模式下可以高并发

# ============ 直连模式配置 ============
# 直连模式下的并发数（太高会被Telegram限流）
DIRECT_CONCURRENCY = 10  # 降低到10，避免被限流

# 每批次之间的间隔（秒），让Telegram服务器喘口气
BATCH_DELAY = 1.0

# ============ 限速配置 ============
# 令牌桶容量
RATE_LIMIT_BUCKET_SIZE = 100

# 令牌恢复速率（每秒）
RATE_LIMIT_REFILL_RATE = 50

# 自适应限速：遇到429时降速比例
ADAPTIVE_SLOWDOWN_FACTOR = 0.5

# 自适应限速：恢复速率（每分钟）
ADAPTIVE_RECOVERY_RATE = 0.1

# ============ 阻止检测配置 ============
# 滑动窗口时间（秒）
BLOCK_DETECTION_WINDOW = 60

# 触发告警的连续错误次数
BLOCK_DETECTION_THRESHOLD = 5

# 检测的HTTP状态码
BLOCK_STATUS_CODES = [429, 403, 503]

# 触发阻止后的暂停时间（秒）
BLOCK_PAUSE_DURATION = 300

# ============ 请求配置 ============
# 请求超时（秒）
REQUEST_TIMEOUT = 10

# 重试次数
REQUEST_RETRIES = 3

# 重试间隔（秒）
REQUEST_RETRY_DELAY = 2

# User-Agent列表（随机选择）
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

# ============ 导出配置 ============
# CSV编码 - UTF-8 with BOM, Excel可正确识别中文
EXPORT_ENCODING = "utf-8-sig"

# CSV分隔符 - 逗号分隔，Excel标准格式
EXPORT_DELIMITER = ","

# ============ 服务器配置 ============
# 监听地址
SERVER_HOST = "0.0.0.0"

# 监听端口
SERVER_PORT = 8000

# ============ 日志配置 ============
LOG_LEVEL = "DEBUG"  # 调试时使用DEBUG，生产环境改为INFO
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
