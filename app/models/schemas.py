"""
TG群链接验证工具 - Pydantic数据模型
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum


# ============ 枚举类型 ============

class LinkType(str, Enum):
    """链接类型"""
    GROUP = "group"
    CHANNEL = "channel"
    USER = "user"
    JOINCHAT = "joinchat"
    UNKNOWN = "unknown"


class JobStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobItemStatus(str, Enum):
    """任务项状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"


# ============ 链接模型 ============

class LinkBase(BaseModel):
    """链接基础模型"""
    original_url: str
    normalized_url: str
    link_type: LinkType
    identifier: str


class LinkCreate(LinkBase):
    """创建链接"""
    pass


class LinkResponse(LinkBase):
    """链接响应"""
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ============ 任务模型 ============

class JobBase(BaseModel):
    """任务基础模型"""
    name: str


class JobCreate(BaseModel):
    """创建任务请求"""
    name: str
    link_ids: Optional[List[int]] = None  # 如果为空，使用所有未验证的链接


class JobResponse(BaseModel):
    """任务响应"""
    id: int
    name: str
    status: JobStatus
    total_count: int
    pending_count: int
    valid_count: int
    invalid_count: int
    error_count: int
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    
    # 计算属性
    @property
    def progress(self) -> float:
        if self.total_count == 0:
            return 0.0
        return (self.total_count - self.pending_count) / self.total_count * 100

    class Config:
        from_attributes = True


class JobListResponse(BaseModel):
    """任务列表响应"""
    jobs: List[JobResponse]
    total: int


class JobProgressResponse(BaseModel):
    """任务进度响应"""
    job_id: int
    status: JobStatus
    total_count: int
    pending_count: int
    valid_count: int
    invalid_count: int
    error_count: int
    progress: float
    speed: float  # 每秒处理数
    eta_seconds: Optional[int] = None  # 预计剩余时间


# ============ 验证结果模型 ============

class ValidationResult(BaseModel):
    """单个验证结果"""
    link_id: int
    original_url: str
    is_valid: Optional[bool] = None
    group_name: Optional[str] = None
    member_count: Optional[int] = None
    description: Optional[str] = None
    http_status: Optional[int] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    response_time_ms: Optional[int] = None


class ResultResponse(BaseModel):
    """结果响应"""
    id: int
    link_id: int
    job_id: int
    original_url: str
    normalized_url: str
    is_valid: Optional[bool] = None
    group_name: Optional[str] = None
    member_count: Optional[int] = None
    description: Optional[str] = None
    http_status: Optional[int] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    response_time_ms: Optional[int] = None
    verified_at: datetime

    class Config:
        from_attributes = True


class ResultListResponse(BaseModel):
    """结果列表响应"""
    results: List[ResultResponse]
    total: int
    page: int
    page_size: int


class ResultStatsResponse(BaseModel):
    """结果统计响应"""
    job_id: int
    total: int
    valid: int
    invalid: int
    error: int
    pending: int


# ============ 导入模型 ============

class ImportRequest(BaseModel):
    """导入请求"""
    filename: str


class ImportResponse(BaseModel):
    """导入响应"""
    filename: str
    file_size: int
    total_lines: int
    valid_links: int
    duplicate_links: int
    invalid_lines: int
    elapsed_seconds: float


class ImportProgressResponse(BaseModel):
    """导入进度响应"""
    filename: str
    processed_lines: int
    total_lines: int
    valid_links: int
    duplicate_links: int
    invalid_lines: int
    progress: float


# ============ 配置模型 ============

class ConfigResponse(BaseModel):
    """配置响应"""
    proxy_enabled: bool
    clash_api_url: str
    proxy_concurrency: int
    direct_request_interval: float
    direct_concurrency: int
    rate_limit_bucket_size: int
    rate_limit_refill_rate: int
    block_detection_window: int
    block_detection_threshold: int
    request_timeout: int
    request_retries: int


class ConfigUpdateRequest(BaseModel):
    """配置更新请求"""
    proxy_enabled: Optional[bool] = None
    clash_api_url: Optional[str] = None
    proxy_concurrency: Optional[int] = None
    direct_request_interval: Optional[float] = None
    direct_concurrency: Optional[int] = None
    rate_limit_bucket_size: Optional[int] = None
    rate_limit_refill_rate: Optional[int] = None
    block_detection_window: Optional[int] = None
    block_detection_threshold: Optional[int] = None
    request_timeout: Optional[int] = None
    request_retries: Optional[int] = None


# ============ 通用响应模型 ============

class MessageResponse(BaseModel):
    """通用消息响应"""
    message: str
    success: bool = True


class ErrorResponse(BaseModel):
    """错误响应"""
    error: str
    detail: Optional[str] = None


# ============ SSE事件模型 ============

class SSEEvent(BaseModel):
    """SSE事件"""
    event: str
    data: dict
