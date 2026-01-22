"""
TG群链接验证工具 - 导入API
"""
import logging
import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from sse_starlette.sse import EventSourceResponse

from app.models.schemas import ImportRequest, ImportResponse, ImportProgressResponse, MessageResponse
from app.services.import_service import ImportService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/import", tags=["导入"])

# 存储导入进度
_import_progress = {}


@router.post("/start", response_model=ImportResponse)
async def start_import(request: ImportRequest, background_tasks: BackgroundTasks):
    """
    开始导入文件
    
    导入过程是同步的，会阻塞直到完成
    如需异步导入，请使用 /import/async 端点
    """
    try:
        result = ImportService.import_file(request.filename)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"导入失败: {e}")
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")


@router.post("/async", response_model=MessageResponse)
async def start_import_async(request: ImportRequest, background_tasks: BackgroundTasks):
    """
    异步开始导入文件
    
    返回后可通过 /import/progress/{filename} 查询进度
    或通过 /import/events/{filename} 获取SSE实时进度
    """
    filename = request.filename
    
    # 检查是否已在导入中
    if filename in _import_progress and _import_progress[filename].get('status') == 'running':
        raise HTTPException(status_code=400, detail="该文件正在导入中")
    
    # 初始化进度
    _import_progress[filename] = {
        'status': 'running',
        'progress': None
    }
    
    def run_import():
        try:
            def progress_callback(progress: ImportProgressResponse):
                _import_progress[filename]['progress'] = progress
            
            result = ImportService.import_file(filename, progress_callback)
            _import_progress[filename]['status'] = 'completed'
            _import_progress[filename]['result'] = result
        except Exception as e:
            _import_progress[filename]['status'] = 'failed'
            _import_progress[filename]['error'] = str(e)
    
    background_tasks.add_task(run_import)
    
    return MessageResponse(message=f"开始导入: {filename}", success=True)


@router.get("/progress/{filename}")
async def get_import_progress(filename: str):
    """获取导入进度"""
    if filename not in _import_progress:
        raise HTTPException(status_code=404, detail="未找到该导入任务")
    
    data = _import_progress[filename]
    
    return {
        "status": data['status'],
        "progress": data.get('progress'),
        "result": data.get('result'),
        "error": data.get('error')
    }


@router.get("/events/{filename}")
async def import_events(filename: str):
    """SSE实时导入进度"""
    
    async def event_generator():
        while True:
            if filename not in _import_progress:
                yield {
                    "event": "error",
                    "data": '{"error": "未找到该导入任务"}'
                }
                break
            
            data = _import_progress[filename]
            status = data['status']
            
            if status == 'running' and data.get('progress'):
                progress = data['progress']
                yield {
                    "event": "progress",
                    "data": progress.model_dump_json()
                }
            elif status == 'completed':
                result = data.get('result')
                yield {
                    "event": "completed",
                    "data": result.model_dump_json() if result else '{}'
                }
                break
            elif status == 'failed':
                yield {
                    "event": "error",
                    "data": f'{{"error": "{data.get("error", "未知错误")}"}}'
                }
                break
            
            await asyncio.sleep(0.5)
    
    return EventSourceResponse(event_generator())


@router.get("/stats")
async def get_import_stats():
    """获取导入统计"""
    total_links = ImportService.get_total_link_count()
    
    return {
        "total_links": total_links
    }
