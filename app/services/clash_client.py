"""
TG群链接验证工具 - Clash API客户端
用于获取代理列表和切换代理
"""
import logging
from typing import List, Optional
from dataclasses import dataclass

import httpx

from app import config

logger = logging.getLogger(__name__)


@dataclass
class ProxyInfo:
    """代理信息"""
    name: str
    type: str
    alive: bool
    delay: Optional[int] = None


class ClashClient:
    """Clash API客户端"""
    
    def __init__(self, api_url: str = None, secret: str = None):
        """
        初始化客户端
        
        Args:
            api_url: Clash API地址
            secret: API密钥
        """
        self.api_url = (api_url or config.CLASH_API_URL).rstrip('/')
        self.secret = secret or config.CLASH_API_SECRET
        self.timeout = httpx.Timeout(10.0)
    
    def _get_headers(self) -> dict:
        """获取请求头"""
        headers = {"Content-Type": "application/json"}
        if self.secret:
            headers["Authorization"] = f"Bearer {self.secret}"
        return headers
    
    async def get_proxies(self) -> List[ProxyInfo]:
        """
        获取所有代理
        
        Returns:
            代理列表
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.api_url}/proxies",
                    headers=self._get_headers()
                )
                response.raise_for_status()
                
                data = response.json()
                proxies = []
                
                for name, info in data.get('proxies', {}).items():
                    proxy_type = info.get('type', '')
                    
                    # 只返回可用的代理类型
                    if proxy_type in ['Shadowsocks', 'VMess', 'VLESS', 'Trojan', 'HTTP', 'SOCKS5']:
                        proxies.append(ProxyInfo(
                            name=name,
                            type=proxy_type,
                            alive=info.get('alive', True),
                            delay=info.get('history', [{}])[-1].get('delay')
                        ))
                
                return proxies
                
        except Exception as e:
            logger.error(f"获取Clash代理列表失败: {e}")
            return []
    
    async def get_proxy_group(self, group_name: str = "GLOBAL") -> Optional[dict]:
        """获取代理组信息"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.api_url}/proxies/{group_name}",
                    headers=self._get_headers()
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"获取代理组 {group_name} 失败: {e}")
            return None
    
    async def switch_proxy(self, group_name: str, proxy_name: str) -> bool:
        """
        切换代理
        
        Args:
            group_name: 代理组名
            proxy_name: 代理名
            
        Returns:
            是否成功
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.put(
                    f"{self.api_url}/proxies/{group_name}",
                    headers=self._get_headers(),
                    json={"name": proxy_name}
                )
                response.raise_for_status()
                logger.info(f"切换代理: {group_name} -> {proxy_name}")
                return True
        except Exception as e:
            logger.error(f"切换代理失败: {e}")
            return False
    
    async def test_proxy_delay(self, proxy_name: str, url: str = "https://t.me", timeout: int = 5000) -> Optional[int]:
        """
        测试代理延迟
        
        Args:
            proxy_name: 代理名
            url: 测试URL
            timeout: 超时（毫秒）
            
        Returns:
            延迟（毫秒）或None
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.api_url}/proxies/{proxy_name}/delay",
                    headers=self._get_headers(),
                    params={"url": url, "timeout": timeout}
                )
                
                if response.status_code == 200:
                    return response.json().get('delay')
                return None
        except Exception as e:
            logger.debug(f"测试代理 {proxy_name} 延迟失败: {e}")
            return None
    
    async def get_alive_proxies(self) -> List[str]:
        """获取所有存活的代理名称"""
        proxies = await self.get_proxies()
        return [p.name for p in proxies if p.alive]
    
    async def check_connection(self) -> bool:
        """检查与Clash的连接"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.api_url}/version",
                    headers=self._get_headers()
                )
                return response.status_code == 200
        except Exception:
            return False


class ProxyRotator:
    """代理轮换器"""
    
    def __init__(self, clash_client: ClashClient):
        """
        初始化轮换器
        
        Args:
            clash_client: Clash客户端
        """
        self.client = clash_client
        self.proxies: List[str] = []
        self.current_index = 0
    
    async def refresh_proxies(self):
        """刷新代理列表"""
        self.proxies = await self.client.get_alive_proxies()
        self.current_index = 0
        logger.info(f"刷新代理列表，共 {len(self.proxies)} 个可用代理")
    
    def get_next_proxy(self) -> Optional[str]:
        """获取下一个代理"""
        if not self.proxies:
            return None
        
        proxy = self.proxies[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.proxies)
        return proxy
    
    def get_proxy_url(self) -> str:
        """获取代理URL（用于httpx）"""
        # Clash的HTTP代理端口，默认7890
        return "http://127.0.0.1:7890"
    
    def remove_proxy(self, proxy_name: str):
        """移除故障代理"""
        if proxy_name in self.proxies:
            self.proxies.remove(proxy_name)
            logger.warning(f"移除故障代理: {proxy_name}，剩余 {len(self.proxies)} 个")
