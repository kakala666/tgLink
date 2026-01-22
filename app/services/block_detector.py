"""
TG群链接验证工具 - 阻止检测器
滑动窗口统计，检测是否被Telegram阻止
"""
import time
import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional, Awaitable

from app import config

logger = logging.getLogger(__name__)


@dataclass
class BlockDetectorState:
    """检测器状态"""
    error_count: int
    window_start: float
    is_blocked: bool
    block_until: Optional[float]


class BlockDetector:
    """阻止检测器"""
    
    def __init__(
        self,
        window_seconds: int = None,
        threshold: int = None,
        pause_duration: int = None,
        on_block_callback: Optional[Callable[[], Awaitable[None]]] = None
    ):
        """
        初始化检测器
        
        Args:
            window_seconds: 滑动窗口时间（秒）
            threshold: 触发阈值
            pause_duration: 暂停时间（秒）
            on_block_callback: 检测到阻止时的回调
        """
        self.window_seconds = window_seconds or config.BLOCK_DETECTION_WINDOW
        self.threshold = threshold or config.BLOCK_DETECTION_THRESHOLD
        self.pause_duration = pause_duration or config.BLOCK_PAUSE_DURATION
        self.on_block_callback = on_block_callback
        
        # 错误时间戳队列
        self.error_timestamps: deque = deque()
        self.is_blocked = False
        self.block_until: Optional[float] = None
        
        self._lock = asyncio.Lock()
    
    def _cleanup_old_errors(self):
        """清理过期的错误记录"""
        now = time.time()
        cutoff = now - self.window_seconds
        
        while self.error_timestamps and self.error_timestamps[0] < cutoff:
            self.error_timestamps.popleft()
    
    async def report_error(self, status_code: int) -> bool:
        """
        报告错误
        
        Args:
            status_code: HTTP状态码
            
        Returns:
            是否触发了阻止
        """
        # 只关注特定的状态码
        if status_code not in config.BLOCK_STATUS_CODES:
            return False
        
        async with self._lock:
            now = time.time()
            
            # 如果正在阻止中，直接返回
            if self.is_blocked and self.block_until and now < self.block_until:
                return True
            
            # 清理过期记录
            self._cleanup_old_errors()
            
            # 记录新错误
            self.error_timestamps.append(now)
            
            # 检查是否达到阈值
            if len(self.error_timestamps) >= self.threshold:
                logger.warning(
                    f"检测到阻止！{self.window_seconds}秒内收到{len(self.error_timestamps)}个错误响应 "
                    f"(阈值: {self.threshold})，暂停{self.pause_duration}秒"
                )
                
                self.is_blocked = True
                self.block_until = now + self.pause_duration
                
                # 触发回调
                if self.on_block_callback:
                    try:
                        await self.on_block_callback()
                    except Exception as e:
                        logger.error(f"阻止回调执行失败: {e}")
                
                return True
        
        return False
    
    async def report_success(self):
        """报告成功（可用于重置某些状态）"""
        # 成功不清理错误队列，让其自然过期
        pass
    
    async def check_blocked(self) -> bool:
        """
        检查是否被阻止
        
        Returns:
            是否被阻止
        """
        async with self._lock:
            if not self.is_blocked:
                return False
            
            now = time.time()
            if self.block_until and now >= self.block_until:
                # 阻止时间已过
                logger.info("阻止时间已结束，恢复验证")
                self.is_blocked = False
                self.block_until = None
                self.error_timestamps.clear()
                return False
            
            return True
    
    async def wait_if_blocked(self) -> float:
        """
        如果被阻止，等待直到解除
        
        Returns:
            等待的时间（秒）
        """
        if not await self.check_blocked():
            return 0.0
        
        async with self._lock:
            if self.block_until:
                wait_time = self.block_until - time.time()
                if wait_time > 0:
                    logger.info(f"等待阻止解除，还需 {wait_time:.1f} 秒")
                    await asyncio.sleep(wait_time)
                    
                    # 解除阻止
                    self.is_blocked = False
                    self.block_until = None
                    self.error_timestamps.clear()
                    
                    return wait_time
        
        return 0.0
    
    def get_state(self) -> BlockDetectorState:
        """获取当前状态"""
        self._cleanup_old_errors()
        return BlockDetectorState(
            error_count=len(self.error_timestamps),
            window_start=time.time() - self.window_seconds,
            is_blocked=self.is_blocked,
            block_until=self.block_until
        )
    
    def reset(self):
        """重置检测器"""
        self.error_timestamps.clear()
        self.is_blocked = False
        self.block_until = None
        logger.info("阻止检测器已重置")
