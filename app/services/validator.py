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
from pathlib import Path

import httpx

from app import config

logger = logging.getLogger(__name__)

# 群名提取正则（按优先级排序）
# 1. Telegram 特有的 class（最准确）
TGME_TITLE_PATTERN = re.compile(r'<div[^>]+class="tgme_page_title"[^>]*>\s*<span[^>]*>([^<]+)</span>', re.IGNORECASE)
TGME_TITLE_PATTERN2 = re.compile(r'class="tgme_page_title"[^>]*>([^<]+)<', re.IGNORECASE)
# 2. og:title meta标签
OG_TITLE_PATTERNS = [
    re.compile(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:title["\']', re.IGNORECASE),
    re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']', re.IGNORECASE),
]
# 3. title标签（最后的备选）
TITLE_PATTERN = re.compile(r'<title>([^<]+)</title>', re.IGNORECASE)

# 成员数提取（从 tgme_page_extra 或页面其他位置）
TGME_EXTRA_PATTERN = re.compile(r'class="tgme_page_extra"[^>]*>([^<]+)<', re.IGNORECASE)
MEMBER_COUNT_PATTERN = re.compile(r'(\d[\d\s,]*)(?:\s*)(?:members?|subscribers?|участник|人)', re.IGNORECASE)

# 描述提取
OG_DESC_PATTERNS = [
    re.compile(r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:description["\']', re.IGNORECASE),
    re.compile(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']', re.IGNORECASE),
]

# 无效标识（页面存在但群组无效）
INVALID_INDICATORS = [
    "If you have Telegram, you can contact",  # 用户页面
    "This group can't be displayed",  # 被封禁
    "This channel can't be displayed",  # 被封禁
    "this chat is private",  # 私有群
    "Group not found",  # 群组不存在
    "Channel not found",  # 频道不存在
]

# 有效群组/频道的标识（优先级高于无效标识）
VALID_INDICATORS = [
    "members",
    "subscribers", 
    "online",
    "Join Group",
    "Join Channel",
    "Preview channel",
    "tgme_page_extra",  # Telegram 页面特有的 class
]

# 调试：保存失败的 HTML（设为 True 开启）
DEBUG_SAVE_FAILED_HTML = False  # 关闭保存HTML
DEBUG_HTML_DIR = Path(__file__).parent.parent.parent / "debug_html"


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
    
    def _parse_response(self, html: str, status_code: int, url: str = "") -> ValidationResult:
        """解析响应内容"""
        result = ValidationResult(http_status=status_code)
        html_lower = html.lower()
        
        # 检测是否是限流/验证码页面
        if len(html) < 1000:
            logger.warning(f"[{url}] 页面内容过短({len(html)}字节)，可能是限流页面")
        
        # 1. 提取成员数
        member_count = None
        extra_match = TGME_EXTRA_PATTERN.search(html)
        if extra_match:
            extra_text = extra_match.group(1)
            member_match = MEMBER_COUNT_PATTERN.search(extra_text)
            if member_match:
                try:
                    member_count = int(member_match.group(1).replace(' ', '').replace(',', ''))
                except ValueError:
                    pass
        
        if not member_count:
            member_match = MEMBER_COUNT_PATTERN.search(html)
            if member_match:
                try:
                    member_count = int(member_match.group(1).replace(' ', '').replace(',', ''))
                except ValueError:
                    pass
        
        # 2. 提取群名（按优先级）
        group_name = None
        source = None
        
        # 2.1 tgme_page_title
        tgme_match = TGME_TITLE_PATTERN.search(html)
        if tgme_match:
            group_name = tgme_match.group(1).strip()
            source = "tgme_page_title(span)"
        
        if not group_name:
            tgme_match2 = TGME_TITLE_PATTERN2.search(html)
            if tgme_match2:
                group_name = tgme_match2.group(1).strip()
                source = "tgme_page_title"
        
        # 2.2 og:title（过滤 Telegram: 前缀）
        if not group_name:
            for pattern in OG_TITLE_PATTERNS:
                og_match = pattern.search(html)
                if og_match:
                    potential_name = og_match.group(1).strip()
                    if not potential_name.lower().startswith("telegram:"):
                        group_name = potential_name
                        source = "og:title"
                        break
        
        # 2.3 title 标签
        if not group_name:
            title_match = TITLE_PATTERN.search(html)
            if title_match:
                title = title_match.group(1).strip()
                if title and not title.lower().startswith("telegram"):
                    group_name = title
                    source = "title"
        
        # 3. 判断有效性
        
        # 3.1 有成员数 → 有效
        if member_count and member_count > 0:
            result.is_valid = True
            result.member_count = member_count
            result.group_name = group_name or f"群组({member_count}人)"
            logger.info(f"[{url}] 有效: {result.group_name}, 成员: {member_count}, 来源: {source}")
            return result
        
        # 3.2 检查无效标识
        for indicator in INVALID_INDICATORS:
            if indicator.lower() in html_lower:
                result.is_valid = False
                result.error_type = "invalid_group"
                result.error_message = indicator
                logger.info(f"[{url}] 无效: {indicator}")
                return result
        
        # 3.3 有群名（非联系页面格式）→ 有效
        if group_name:
            if group_name.lower().startswith("telegram: contact"):
                result.is_valid = False
                result.error_type = "invalid_group"
                result.error_message = "用户联系页面"
                logger.info(f"[{url}] 无效: 用户联系页面")
                return result
            
            result.is_valid = True
            result.group_name = group_name
            logger.info(f"[{url}] 有效: {group_name}, 来源: {source}")
            return result
        
        # 3.4 检测隐性限流：title是联系页面格式 + HTML长度正常 = 可能是限流
        title_match = TITLE_PATTERN.search(html)
        if title_match:
            title = title_match.group(1).strip()
            if title.lower().startswith("telegram: contact") and len(html) > 5000:
                # 这是 Telegram 的隐性限流，返回了简化页面
                result.is_valid = None  # 待重试
                result.error_type = "rate_limit_hidden"
                result.error_message = "疑似隐性限流(返回简化页面)"
                logger.warning(f"[{url}] 疑似限流: 返回简化页面 (title={title}, html_len={len(html)})")
                return result
        
        # 3.5 无法提取任何信息 → 无效
        result.is_valid = False
        result.error_type = "no_group_name"
        result.error_message = "无法提取群名"
        
        # 输出调试信息
        html_snippet = html[:500].replace('\n', ' ').replace('\r', '')
        logger.warning(f"[{url}] 无效: 无法提取群名 | HTML前500字符: {html_snippet}")
        
        return result
    
    def _save_debug_html(self, url: str, html: str, reason: str):
        """保存失败的 HTML 用于调试"""
        if not DEBUG_SAVE_FAILED_HTML:
            return
        try:
            DEBUG_HTML_DIR.mkdir(parents=True, exist_ok=True)
            # 从 URL 提取用户名
            username = url.split('/')[-1].split('?')[0]
            filename = f"{username}_{reason}_{int(time.time())}.html"
            filepath = DEBUG_HTML_DIR / filename
            filepath.write_text(html, encoding='utf-8')
            logger.debug(f"保存调试HTML: {filepath}")
        except Exception as e:
            logger.error(f"保存调试HTML失败: {e}")
    
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
                parsed_result = self._parse_response(response.text, response.status_code, url)
                # 如果验证失败，保存 HTML 用于调试
                if parsed_result.is_valid == False:
                    self._save_debug_html(url, response.text, parsed_result.error_type or "unknown")
                return parsed_result
            elif response.status_code == 404:
                result.is_valid = False
                result.error_type = "not_found"
                result.error_message = "页面不存在"
                logger.info(f"[{url}] 无效: 404 页面不存在")
            elif response.status_code == 429:
                result.is_valid = None  # 待重试
                result.error_type = "rate_limit"
                result.error_message = "请求过于频繁"
                logger.warning(f"[{url}] 错误: 429 请求过于频繁")
            elif response.status_code in [403, 503]:
                result.is_valid = None
                result.error_type = "blocked"
                result.error_message = f"被封禁或服务不可用: {response.status_code}"
                logger.warning(f"[{url}] 错误: {response.status_code} 被封禁")
            else:
                result.is_valid = None
                result.error_type = "http_error"
                result.error_message = f"HTTP错误: {response.status_code}"
                logger.warning(f"[{url}] 错误: HTTP {response.status_code}")
                
        except httpx.TimeoutException:
            result.response_time_ms = int((time.time() - start_time) * 1000)
            result.error_type = "timeout"
            result.error_message = "请求超时"
            logger.warning(f"[{url}] 错误: 请求超时")
        except httpx.ConnectError as e:
            result.response_time_ms = int((time.time() - start_time) * 1000)
            result.error_type = "connect_error"
            result.error_message = f"连接错误: {str(e)[:200]}"
            logger.warning(f"[{url}] 错误: 连接失败")
        except Exception as e:
            result.response_time_ms = int((time.time() - start_time) * 1000)
            result.error_type = "unknown_error"
            result.error_message = f"未知错误: {str(e)[:200]}"
            logger.exception(f"[{url}] 错误: 未知异常")
        
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
