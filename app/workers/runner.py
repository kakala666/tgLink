"""
TG群链接验证工具 - 任务运行器
负责并发执行验证任务，支持暂停/继续/停止
"""
import asyncio
import time
import logging
from typing import Optional, Dict, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum

from app import config
from app.models.schemas import JobStatus, JobItemStatus
from app.services.job_service import JobService
from app.services.validator import TelegramValidator, ValidatorPool
from app.services.rate_limiter import TokenBucketRateLimiter, SimpleRateLimiter
from app.services.block_detector import BlockDetector
from app.services.clash_client import ClashClient, ProxyRotator

logger = logging.getLogger(__name__)


class RunnerState(str, Enum):
    """运行器状态"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"


@dataclass
class RunnerStats:
    """运行统计"""
    job_id: int
    state: RunnerState
    total_count: int = 0
    processed_count: int = 0
    valid_count: int = 0
    invalid_count: int = 0
    error_count: int = 0
    start_time: Optional[float] = None
    speed: float = 0.0  # 每秒处理数
    eta_seconds: Optional[int] = None  # 预计剩余时间


@dataclass
class JobRunner:
    """单个任务的运行器"""
    job_id: int
    state: RunnerState = RunnerState.IDLE
    stats: RunnerStats = None
    
    # 控制信号
    _pause_event: asyncio.Event = field(default_factory=asyncio.Event)
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    
    # 进度回调
    progress_callback: Optional[Callable[[RunnerStats], Awaitable[None]]] = None
    
    def __post_init__(self):
        self._pause_event.set()  # 默认不暂停
        self._stop_event.clear()  # 默认不停止
        self.stats = RunnerStats(job_id=self.job_id, state=self.state)


class TaskRunner:
    """任务运行器管理器"""
    
    def __init__(self):
        self.runners: Dict[int, JobRunner] = {}
        self.rate_limiter: Optional[TokenBucketRateLimiter] = None
        self.simple_limiter: Optional[SimpleRateLimiter] = None
        self.block_detector: Optional[BlockDetector] = None
        self.validator_pool: Optional[ValidatorPool] = None
        self.clash_client: Optional[ClashClient] = None
        self.proxy_rotator: Optional[ProxyRotator] = None
        self._initialized = False
        
        self._lock = asyncio.Lock()
    
    async def _ensure_initialized(self):
        """确保已初始化"""
        if not self._initialized:
            await self.initialize()
    
    async def initialize(self):
        """初始化运行器"""
        # 初始化两种限速器（都初始化，根据配置使用）
        self.rate_limiter = TokenBucketRateLimiter()
        self.simple_limiter = SimpleRateLimiter()
        
        # 初始化阻止检测器
        self.block_detector = BlockDetector(
            on_block_callback=self._on_block_detected
        )
        
        # 初始化代理
        if config.PROXY_ENABLED:
            self.clash_client = ClashClient()
            self.proxy_rotator = ProxyRotator(self.clash_client)
            await self.proxy_rotator.refresh_proxies()
            
            # 创建验证器池
            proxy_url = self.proxy_rotator.get_proxy_url()
            self.validator_pool = ValidatorPool([proxy_url])
        else:
            self.validator_pool = ValidatorPool()
        
        self._initialized = True
        logger.info(f"任务运行器初始化完成，代理模式: {config.PROXY_ENABLED}")
    
    async def _on_block_detected(self):
        """阻止检测回调"""
        logger.warning("检测到阻止，暂停所有运行中的任务")
        for runner in self.runners.values():
            if runner.state == RunnerState.RUNNING:
                await self.pause_job(runner.job_id)
    
    async def start_job(
        self, 
        job_id: int,
        progress_callback: Optional[Callable[[RunnerStats], Awaitable[None]]] = None
    ) -> bool:
        """
        启动任务
        
        Args:
            job_id: 任务ID
            progress_callback: 进度回调
            
        Returns:
            是否成功启动
        """
        # 确保已初始化
        await self._ensure_initialized()
        
        async with self._lock:
            # 检查任务是否存在
            job = JobService.get_job(job_id)
            if not job:
                logger.error(f"任务不存在: {job_id}")
                return False
            
            # 检查任务状态
            if job.status == JobStatus.RUNNING:
                logger.warning(f"任务已在运行: {job_id}")
                return False
            
            if job.status == JobStatus.COMPLETED:
                logger.warning(f"任务已完成: {job_id}")
                return False
            
            # 创建或获取运行器
            if job_id in self.runners:
                runner = self.runners[job_id]
                runner._pause_event.set()
                runner._stop_event.clear()
            else:
                runner = JobRunner(job_id=job_id, progress_callback=progress_callback)
                self.runners[job_id] = runner
            
            runner.state = RunnerState.RUNNING
            runner.stats.state = RunnerState.RUNNING
            runner.stats.total_count = job.total_count
            runner.stats.start_time = time.time()
            
            # 更新任务状态
            JobService.update_job_status(job_id, JobStatus.RUNNING)
            
            # 启动工作协程
            asyncio.create_task(self._run_job(runner))
            
            logger.info(f"任务启动: {job_id}")
            return True
    
    async def pause_job(self, job_id: int) -> bool:
        """暂停任务"""
        if job_id not in self.runners:
            return False
        
        runner = self.runners[job_id]
        if runner.state != RunnerState.RUNNING:
            return False
        
        runner._pause_event.clear()
        runner.state = RunnerState.PAUSED
        runner.stats.state = RunnerState.PAUSED
        
        JobService.update_job_status(job_id, JobStatus.PAUSED)
        logger.info(f"任务暂停: {job_id}")
        return True
    
    async def resume_job(self, job_id: int) -> bool:
        """继续任务"""
        if job_id not in self.runners:
            # 如果运行器不存在，重新启动任务
            return await self.start_job(job_id)
        
        runner = self.runners[job_id]
        if runner.state != RunnerState.PAUSED:
            return False
        
        runner._pause_event.set()
        runner.state = RunnerState.RUNNING
        runner.stats.state = RunnerState.RUNNING
        
        JobService.update_job_status(job_id, JobStatus.RUNNING)
        logger.info(f"任务继续: {job_id}")
        return True
    
    async def stop_job(self, job_id: int) -> bool:
        """停止任务"""
        if job_id not in self.runners:
            return False
        
        runner = self.runners[job_id]
        runner._stop_event.set()
        runner._pause_event.set()  # 解除暂停，让循环能够检测停止
        runner.state = RunnerState.STOPPING
        runner.stats.state = RunnerState.STOPPING
        
        logger.info(f"任务停止中: {job_id}")
        return True
    
    def get_runner_stats(self, job_id: int) -> Optional[RunnerStats]:
        """获取运行统计"""
        if job_id not in self.runners:
            return None
        return self.runners[job_id].stats
    
    async def _run_job(self, runner: JobRunner):
        """执行任务的核心循环"""
        job_id = runner.job_id
        batch_size = config.PROXY_CONCURRENCY if config.PROXY_ENABLED else config.DIRECT_CONCURRENCY
        
        try:
            while True:
                # 检查停止信号
                if runner._stop_event.is_set():
                    JobService.update_job_status(job_id, JobStatus.CANCELLED)
                    break
                
                # 检查暂停信号
                await runner._pause_event.wait()
                
                # 检查阻止状态
                if self.block_detector:
                    await self.block_detector.wait_if_blocked()
                
                # 获取待处理项
                items = JobService.get_pending_items(job_id, limit=batch_size)
                if not items:
                    # 没有待处理项，任务完成
                    JobService.update_job_status(job_id, JobStatus.COMPLETED)
                    runner.state = RunnerState.IDLE
                    runner.stats.state = RunnerState.IDLE
                    logger.info(f"任务完成: {job_id}")
                    break
                
                # 并发验证
                tasks = []
                for item in items:
                    task = asyncio.create_task(
                        self._validate_item(runner, item)
                    )
                    tasks.append(task)
                
                await asyncio.gather(*tasks, return_exceptions=True)
                
                # 更新统计
                self._update_stats(runner)
                
                # 回调进度
                if runner.progress_callback:
                    try:
                        await runner.progress_callback(runner.stats)
                    except Exception as e:
                        logger.error(f"进度回调错误: {e}")
        
        except Exception as e:
            logger.exception(f"任务执行错误: {job_id}")
            JobService.update_job_status(job_id, JobStatus.FAILED, str(e))
            runner.state = RunnerState.IDLE
            runner.stats.state = RunnerState.IDLE
        
        finally:
            # 清理
            if job_id in self.runners:
                del self.runners[job_id]
    
    async def _validate_item(self, runner: JobRunner, item: dict):
        """验证单个项"""
        job_id = runner.job_id
        item_id = item['id']
        link_id = item['link_id']
        url = item['normalized_url']
        
        try:
            # 限速
            if config.PROXY_ENABLED:
                await self.rate_limiter.wait_for_token()
            else:
                await self.simple_limiter.wait()
            
            # 更新项状态
            JobService.update_item_status(item_id, JobItemStatus.PROCESSING)
            
            # 验证
            result = await self.validator_pool.validate(url)
            
            # 检测阻止
            if result.http_status and self.block_detector:
                await self.block_detector.report_error(result.http_status)
                
                # 如果是速率限制，通知限速器
                if result.error_type == 'rate_limit' and self.rate_limiter:
                    self.rate_limiter.report_rate_limit()
            
            # 保存结果
            JobService.save_result(job_id, link_id, {
                'is_valid': result.is_valid,
                'group_name': result.group_name,
                'member_count': result.member_count,
                'description': result.description,
                'http_status': result.http_status,
                'error_type': result.error_type,
                'error_message': result.error_message,
                'response_time_ms': result.response_time_ms,
                'proxy_used': result.proxy_used
            })
            
            # 更新项状态
            JobService.update_item_status(item_id, JobItemStatus.COMPLETED)
            
            # 更新任务计数
            if result.is_valid is True:
                JobService.increment_job_count(job_id, 'valid_count')
                runner.stats.valid_count += 1
            elif result.is_valid is False:
                JobService.increment_job_count(job_id, 'invalid_count')
                runner.stats.invalid_count += 1
            else:
                JobService.increment_job_count(job_id, 'error_count')
                runner.stats.error_count += 1
            
            JobService.increment_job_count(job_id, 'pending_count', -1)
            runner.stats.processed_count += 1
            
        except Exception as e:
            logger.error(f"验证项 {item_id} 时出错: {e}")
            JobService.update_item_status(item_id, JobItemStatus.ERROR)
            JobService.increment_job_count(job_id, 'error_count')
            runner.stats.error_count += 1
    
    def _update_stats(self, runner: JobRunner):
        """更新统计信息"""
        if runner.stats.start_time:
            elapsed = time.time() - runner.stats.start_time
            if elapsed > 0:
                runner.stats.speed = runner.stats.processed_count / elapsed
                
                remaining = runner.stats.total_count - runner.stats.processed_count
                if runner.stats.speed > 0:
                    runner.stats.eta_seconds = int(remaining / runner.stats.speed)


# 全局运行器实例
task_runner = TaskRunner()
