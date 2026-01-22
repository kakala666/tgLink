"""
TG群链接验证工具 - 配置管理API
"""
import logging

from fastapi import APIRouter

from app import config
from app.models.schemas import ConfigResponse, ConfigUpdateRequest, MessageResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["配置"])


@router.get("/", response_model=ConfigResponse)
async def get_config():
    """获取当前配置"""
    return ConfigResponse(
        proxy_enabled=config.PROXY_ENABLED,
        clash_api_url=config.CLASH_API_URL,
        proxy_concurrency=config.PROXY_CONCURRENCY,
        direct_request_interval=config.DIRECT_REQUEST_INTERVAL,
        direct_concurrency=config.DIRECT_CONCURRENCY,
        rate_limit_bucket_size=config.RATE_LIMIT_BUCKET_SIZE,
        rate_limit_refill_rate=config.RATE_LIMIT_REFILL_RATE,
        block_detection_window=config.BLOCK_DETECTION_WINDOW,
        block_detection_threshold=config.BLOCK_DETECTION_THRESHOLD,
        request_timeout=config.REQUEST_TIMEOUT,
        request_retries=config.REQUEST_RETRIES
    )


@router.put("/", response_model=MessageResponse)
async def update_config(request: ConfigUpdateRequest):
    """
    更新配置
    
    注意: 配置更新只在内存中生效，重启后会恢复默认值
    如需永久修改，请编辑 config.py 文件
    """
    updated = []
    
    if request.proxy_enabled is not None:
        config.PROXY_ENABLED = request.proxy_enabled
        updated.append("proxy_enabled")
    
    if request.clash_api_url is not None:
        config.CLASH_API_URL = request.clash_api_url
        updated.append("clash_api_url")
    
    if request.proxy_concurrency is not None:
        config.PROXY_CONCURRENCY = request.proxy_concurrency
        updated.append("proxy_concurrency")
    
    if request.direct_request_interval is not None:
        config.DIRECT_REQUEST_INTERVAL = request.direct_request_interval
        updated.append("direct_request_interval")
    
    if request.direct_concurrency is not None:
        config.DIRECT_CONCURRENCY = request.direct_concurrency
        updated.append("direct_concurrency")
    
    if request.rate_limit_bucket_size is not None:
        config.RATE_LIMIT_BUCKET_SIZE = request.rate_limit_bucket_size
        updated.append("rate_limit_bucket_size")
    
    if request.rate_limit_refill_rate is not None:
        config.RATE_LIMIT_REFILL_RATE = request.rate_limit_refill_rate
        updated.append("rate_limit_refill_rate")
    
    if request.block_detection_window is not None:
        config.BLOCK_DETECTION_WINDOW = request.block_detection_window
        updated.append("block_detection_window")
    
    if request.block_detection_threshold is not None:
        config.BLOCK_DETECTION_THRESHOLD = request.block_detection_threshold
        updated.append("block_detection_threshold")
    
    if request.request_timeout is not None:
        config.REQUEST_TIMEOUT = request.request_timeout
        updated.append("request_timeout")
    
    if request.request_retries is not None:
        config.REQUEST_RETRIES = request.request_retries
        updated.append("request_retries")
    
    if updated:
        logger.info(f"配置已更新: {', '.join(updated)}")
        return MessageResponse(message=f"已更新: {', '.join(updated)}", success=True)
    else:
        return MessageResponse(message="无配置更新", success=True)


@router.post("/reset", response_model=MessageResponse)
async def reset_config():
    """重置配置为默认值（需要重启服务）"""
    return MessageResponse(
        message="请重启服务以恢复默认配置",
        success=True
    )


@router.get("/clash/status")
async def get_clash_status():
    """获取Clash连接状态"""
    from app.services.clash_client import ClashClient
    
    client = ClashClient()
    connected = await client.check_connection()
    
    if connected:
        proxies = await client.get_proxies()
        return {
            "connected": True,
            "proxy_count": len(proxies),
            "proxies": [{"name": p.name, "type": p.type, "alive": p.alive} for p in proxies[:10]]
        }
    else:
        return {
            "connected": False,
            "proxy_count": 0,
            "proxies": []
        }
