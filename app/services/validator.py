"""
TG群链接验证工具 - Telegram链接验证器
通过抓取t.me页面验证链接有效性并提取群名
"""
import re
import time
import random
import asyncio
import logging
from typing import Optional, Tuple
from dataclasses import dataclass

import httpx

from app import config

logger = logging.getLogger(__name__)

# 群名提取正则（从og:title meta标签，支持属性顺序不同）
OG_TITLE_PATTERNS = [
    re.compile(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:title["\']', re.IGNORECASE),
]
# 备选：从title标签
TITLE_PATTERN = re.compile(r'<title>([^<]+)</title>', re.IGNORECASE)
# 成员数提取
MEMBER_COUNT_PATTERN = re.compile(r'(\d[\d\s,]*)\s*(?:members?|subscribers?|участник)', re.IGNORECASE)
# 描述提取（支持属性顺序不同）
OG_DESC_PATTERNS = [
    re.compile(r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:description["\']', re.IGNORECASE),
]

# 无效标识（页面存在但群组无效）
INVALID_INDICATORS = [
    "If you have Telegram, you can contact",  # 用户页面
    "This group can't be displayed",  # 被封禁
    "This channel can't be displayed",  # 被封禁
    "this chat is private",  # 私有群
    "Group not found",  # 群组不存在
    "Channel not found",  # 频道不存在
    "Telegram: Contact @",  # 联系页面（不是群组）
]


@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: Optional[bool] = None
    group_name: Optional[str] = None
    member_count: Optional[int] = None
    description: Optional[str] = None
    http_status: Optional[int] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    response_time_ms: Optional[int] = None
    proxy_used: Optional[str] = None


class TelegramValidator:
    """Telegram链接验证器"""
    
    def __init__(self, proxy_url: Optional[str] = None):
        """
        初始化验证器
        
        Args:
            proxy_url: 代理URL，如 http://127.0.0.1:7890
        """
        self.proxy_url = proxy_url
        self.timeout = httpx.Timeout(config.REQUEST_TIMEOUT, connect=5.0)
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 httpx 客户端（复用连接）"""
        if self._client is None or self._client.is_closed:
            client_kwargs = {
                "timeout": self.timeout,
                "follow_redirects": True,
                "limits": httpx.Limits(max_keepalive_connections=10, max_connections=20),
            }
            if self.proxy_url:
                client_kwargs["proxy"] = self.proxy_url
            self._client = httpx.AsyncClient(**client_kwargs)
        return self._client
    
    async def close(self):
        """关闭客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    def _get_random_user_agent(self) -> str:
        """获取随机User-Agent"""
        return random.choice(config.USER_AGENTS)
    
    def _get_headers(self) -> dict:
        """获取请求头"""
        return {
            "User-Agent": self._get_random_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
    
    def _parse_response(self, html: str, status_code: int) -> ValidationResult:
        """
        解析响应内容
        
        Args:
            html: HTML内容
            status_code: HTTP状态码
            
        Returns:
            ValidationResult
        """
        result = ValidationResult(http_status=status_code)
        
        logger.debug(f"解析响应，HTML长度: {len(html)}")
        
        # 检查无效标识
        for indicator in INVALID_INDICATORS:
            if indicator.lower() in html.lower():
                result.is_valid = False
                result.error_type = "invalid_group"
                result.error_message = indicator
                logger.debug(f"检测到无效标识: {indicator}")
                return result
        
        # 提取群名 - 尝试多种模式
        group_name = None
        for pattern in OG_TITLE_PATTERNS:
            og_match = pattern.search(html)
            if og_match:
                group_name = og_match.group(1).strip()
                logger.debug(f"从og:title提取群名: {group_name}")
                break
        
        if not group_name:
            title_match = TITLE_PATTERN.search(html)
            if title_match:
                title = title_match.group(1).strip()
                # 过滤掉默认标题
                if title and title.lower() not in ['telegram', 'telegram: contact', 'telegram: join group chat']:
                    group_name = title
                    logger.debug(f"从title提取群名: {group_name}")
        
        result.group_name = group_name
        
        # 检查群名是否是无效的格式
        if result.group_name:
            invalid_names = [
                "telegram: contact",
                "telegram: join group",
                "telegram",
            ]
            name_lower = result.group_name.lower()
            # 检查是否是 "Telegram: Contact @xxx" 格式
            if name_lower.startswith("telegram: contact") or name_lower in invalid_names:
                result.is_valid = False
                result.error_type = "invalid_group"
                result.error_message = "不是有效的群组或频道"
                result.group_name = None
                logger.debug(f"群名无效: {group_name}")
                return result
        
        # 如果有群名，认为有效
        if result.group_name:
            result.is_valid = True
            
            # 尝试提取成员数
            member_match = MEMBER_COUNT_PATTERN.search(html)
            if member_match:
                try:
                    result.member_count = int(member_match.group(1).replace(' ', '').replace(',', ''))
                except ValueError:
                    pass
            
            # 尝试提取描述 - 尝试多种模式
            for pattern in OG_DESC_PATTERNS:
                desc_match = pattern.search(html)
                if desc_match:
                    result.description = desc_match.group(1).strip()[:500]  # 限制长度
                    break
            
            logger.info(f"验证成功: {result.group_name}, 成员: {result.member_count}")
        else:
            # 无法提取群名，可能是无效页面
            result.is_valid = False
            result.error_type = "no_group_name"
            result.error_message = "无法从页面提取群名"
            # 记录HTML片段用于调试
            logger.warning(f"无法提取群名，HTML前500字符: {html[:500]}")
        
        return result
    
    async def validate(self, url: str) -> ValidationResult:
        """
        验证单个链接
        
        Args:
            url: Telegram链接
            
        Returns:
            ValidationResult
        """
        start_time = time.time()
        result = ValidationResult(proxy_used=self.proxy_url)
        
        try:
            # 获取复用的客户端
            client = await self._get_client()
            
            # 发送请求
            response = await client.get(url, headers=self._get_headers())
                
            result.response_time_ms = int((time.time() - start_time) * 1000)
            result.http_status = response.status_code
            
            if response.status_code == 200:
                return self._parse_response(response.text, response.status_code)
            elif response.status_code == 404:
                result.is_valid = False
                result.error_type = "not_found"
                result.error_message = "页面不存在"
            elif response.status_code == 429:
                result.is_valid = None  # 待重试
                result.error_type = "rate_limit"
                result.error_message = "请求过于频繁"
            elif response.status_code in [403, 503]:
                result.is_valid = None
                result.error_type = "blocked"
                result.error_message = f"被封禁或服务不可用: {response.status_code}"
            else:
                result.is_valid = None
                result.error_type = "http_error"
                result.error_message = f"HTTP错误: {response.status_code}"
                
        except httpx.TimeoutException:
            result.response_time_ms = int((time.time() - start_time) * 1000)
            result.error_type = "timeout"
            result.error_message = "请求超时"
        except httpx.ConnectError as e:
            result.response_time_ms = int((time.time() - start_time) * 1000)
            result.error_type = "connect_error"
            result.error_message = f"连接错误: {str(e)[:200]}"
        except Exception as e:
            result.response_time_ms = int((time.time() - start_time) * 1000)
            result.error_type = "unknown_error"
            result.error_message = f"未知错误: {str(e)[:200]}"
            logger.exception(f"验证链接时发生错误: {url}")
        
        return result
    
    async def validate_with_retry(self, url: str, max_retries: int = None) -> ValidationResult:
        """
        带重试的验证
        
        Args:
            url: Telegram链接
            max_retries: 最大重试次数
            
        Returns:
            ValidationResult
        """
        if max_retries is None:
            max_retries = config.REQUEST_RETRIES
        
        for attempt in range(max_retries + 1):
            result = await self.validate(url)
            
            # 如果结果明确（有效或无效），返回
            if result.is_valid is not None:
                return result
            
            # 如果是速率限制或临时错误，等待后重试
            if result.error_type in ['rate_limit', 'blocked', 'timeout']:
                if attempt < max_retries:
                    delay = config.REQUEST_RETRY_DELAY * (attempt + 1)
                    await asyncio.sleep(delay)
                    continue
            
            # 其他错误不重试
            break
        
        return result


class ValidatorPool:
    """验证器池，管理多个验证器实例"""
    
    def __init__(self, proxy_urls: list = None):
        """
        初始化验证器池
        
        Args:
            proxy_urls: 代理URL列表
        """
        self.proxy_urls = proxy_urls or []
        self.validators = []
        self._index = 0
        self._lock = asyncio.Lock()
        
        if self.proxy_urls:
            # 代理模式：创建多个验证器实例以支持真正的并发
            concurrency = config.PROXY_CONCURRENCY
            for i in range(concurrency):
                proxy_url = self.proxy_urls[i % len(self.proxy_urls)]
                self.validators.append(TelegramValidator(proxy_url))
            logger.info(f"创建 {concurrency} 个验证器实例，代理: {self.proxy_urls}")
        else:
            # 直连模式：也创建多个验证器实例支持并发
            concurrency = config.DIRECT_CONCURRENCY
            for i in range(concurrency):
                self.validators.append(TelegramValidator())
            logger.info(f"创建 {concurrency} 个直连验证器实例")
    
    async def get_validator(self) -> TelegramValidator:
        """获取下一个验证器（轮询）"""
        async with self._lock:
            validator = self.validators[self._index]
            self._index = (self._index + 1) % len(self.validators)
            return validator
    
    async def validate(self, url: str) -> ValidationResult:
        """使用池中的验证器验证链接"""
        validator = await self.get_validator()
        # 直接验证，不重试（加快速度）
        return await validator.validate(url)
