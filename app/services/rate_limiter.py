"""
TG群链接验证工具 - 令牌桶限速器
"""
import time
import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from app import config

logger = logging.getLogger(__name__)


@dataclass
class RateLimiterState:
    """限速器状态"""
    tokens: float
    last_update: float
    current_rate: float
    is_throttled: bool


class TokenBucketRateLimiter:
    """令牌桶限速器"""
    
    def __init__(
        self,
        bucket_size: int = None,
        refill_rate: float = None,
        adaptive: bool = True
    ):
        """
        初始化限速器
        
        Args:
            bucket_size: 桶容量（最大令牌数）
            refill_rate: 令牌恢复速率（每秒）
            adaptive: 是否启用自适应限速
        """
        self.bucket_size = bucket_size or config.RATE_LIMIT_BUCKET_SIZE
        self.base_refill_rate = refill_rate or config.RATE_LIMIT_REFILL_RATE
        self.current_refill_rate = self.base_refill_rate
        self.adaptive = adaptive
        
        self.tokens = float(self.bucket_size)
        self.last_update = time.time()
        self.is_throttled = False
        
        self._lock = asyncio.Lock()
        
        # 自适应参数
        self.slowdown_factor = config.ADAPTIVE_SLOWDOWN_FACTOR
        self.recovery_rate = config.ADAPTIVE_RECOVERY_RATE
        self.last_recovery = time.time()
    
    def _refill(self):
        """补充令牌"""
        now = time.time()
        elapsed = now - self.last_update
        
        # 根据经过的时间补充令牌
        self.tokens = min(
            self.bucket_size,
            self.tokens + elapsed * self.current_refill_rate
        )
        self.last_update = now
        
        # 自适应恢复
        if self.adaptive and self.current_refill_rate < self.base_refill_rate:
            recovery_elapsed = now - self.last_recovery
            if recovery_elapsed >= 60:  # 每分钟恢复一次
                old_rate = self.current_refill_rate
                self.current_refill_rate = min(
                    self.base_refill_rate,
                    self.current_refill_rate * (1 + self.recovery_rate)
                )
                self.last_recovery = now
                if old_rate != self.current_refill_rate:
                    logger.info(f"限速恢复: {old_rate:.2f} -> {self.current_refill_rate:.2f} 令牌/秒")
    
    async def acquire(self, tokens: int = 1) -> bool:
        """
        获取令牌
        
        Args:
            tokens: 需要的令牌数
            
        Returns:
            是否成功获取
        """
        async with self._lock:
            self._refill()
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                self.is_throttled = False
                return True
            else:
                self.is_throttled = True
                return False
    
    async def wait_for_token(self, tokens: int = 1) -> float:
        """
        等待并获取令牌
        
        Args:
            tokens: 需要的令牌数
            
        Returns:
            等待的时间（秒）
        """
        wait_time = 0.0
        
        while True:
            async with self._lock:
                self._refill()
                
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    self.is_throttled = False
                    return wait_time
                
                # 计算需要等待的时间
                needed = tokens - self.tokens
                sleep_time = needed / self.current_refill_rate
            
            self.is_throttled = True
            await asyncio.sleep(min(sleep_time, 0.1))  # 最多等0.1秒后重试
            wait_time += min(sleep_time, 0.1)
    
    def report_rate_limit(self):
        """报告遇到速率限制（触发降速）"""
        if not self.adaptive:
            return
        
        old_rate = self.current_refill_rate
        self.current_refill_rate *= self.slowdown_factor
        self.last_recovery = time.time()  # 重置恢复计时
        
        logger.warning(f"检测到速率限制，降速: {old_rate:.2f} -> {self.current_refill_rate:.2f} 令牌/秒")
    
    def get_state(self) -> RateLimiterState:
        """获取当前状态"""
        self._refill()
        return RateLimiterState(
            tokens=self.tokens,
            last_update=self.last_update,
            current_rate=self.current_refill_rate,
            is_throttled=self.is_throttled
        )
    
    def reset(self):
        """重置限速器"""
        self.tokens = float(self.bucket_size)
        self.current_refill_rate = self.base_refill_rate
        self.last_update = time.time()
        self.is_throttled = False
        logger.info("限速器已重置")


class SimpleRateLimiter:
    """简单限速器（用于直连模式）"""
    
    def __init__(self, interval: float = None):
        """
        初始化
        
        Args:
            interval: 请求间隔（秒）
        """
        self.interval = interval or config.DIRECT_REQUEST_INTERVAL
        self.last_request = 0.0
        self._lock = asyncio.Lock()
    
    async def wait(self):
        """等待直到可以发送下一个请求"""
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_request
            
            if elapsed < self.interval:
                await asyncio.sleep(self.interval - elapsed)
            
            self.last_request = time.time()
