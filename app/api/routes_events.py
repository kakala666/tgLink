"""
TG群链接验证工具 - SSE实时事件API
"""
import json
import asyncio
import logging

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.services.job_service import JobService
from app.workers.runner import task_runner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events", tags=["事件"])


@router.get("/job/{job_id}")
async def job_events(job_id: int):
    """
    SSE实时任务进度
    
    事件类型:
    - progress: 进度更新
    - completed: 任务完成
    - paused: 任务暂停
    - error: 发生错误
    """
    
    async def event_generator():
        last_pending = None
        error_count = 0
        
        while True:
            try:
                # 获取任务信息
                job = JobService.get_job(job_id)
                if not job:
                    yield {
                        "event": "error",
                        "data": json.dumps({"error": "任务不存在"}, ensure_ascii=False)
                    }
                    break
                
                # 获取运行器统计
                stats = task_runner.get_runner_stats(job_id)
                
                # 计算进度
                total = job.total_count
                pending = job.pending_count
                processed = total - pending
                progress = (processed / total * 100) if total > 0 else 0
                
                speed = stats.speed if stats else 0
                eta = stats.eta_seconds if stats else None
                
                current_progress = {
                    "job_id": job_id,
                    "status": job.status.value,
                    "total_count": total,
                    "pending_count": pending,
                    "processed_count": processed,
                    "valid_count": job.valid_count,
                    "invalid_count": job.invalid_count,
                    "error_count": job.error_count,
                    "progress": round(progress, 2),
                    "speed": round(speed, 2),
                    "eta_seconds": eta
                }
                
                # 每次都发送进度（避免卡住）
                yield {
                    "event": "progress",
                    "data": json.dumps(current_progress, ensure_ascii=False)
                }
                
                # 检查任务状态
                if job.status.value == "completed":
                    yield {
                        "event": "completed",
                        "data": json.dumps({
                            "message": "任务完成",
                            "valid_count": job.valid_count,
                            "invalid_count": job.invalid_count,
                            "error_count": job.error_count
                        }, ensure_ascii=False)
                    }
                    break
                elif job.status.value == "paused":
                    yield {
                        "event": "paused",
                        "data": json.dumps({"message": "任务已暂停"}, ensure_ascii=False)
                    }
                elif job.status.value == "failed":
                    yield {
                        "event": "error",
                        "data": json.dumps({
                            "error": job.error_message or "任务失败"
                        }, ensure_ascii=False)
                    }
                    break
                elif job.status.value == "cancelled":
                    yield {
                        "event": "cancelled",
                        "data": json.dumps({"message": "任务已取消"}, ensure_ascii=False)
                    }
                    break
                
                error_count = 0
                last_pending = pending
                await asyncio.sleep(0.5)
                
            except Exception as e:
                error_count += 1
                logger.error(f"SSE事件生成错误: {e}")
                
                if error_count >= 3:
                    yield {
                        "event": "error",
                        "data": json.dumps({"error": str(e)}, ensure_ascii=False)
                    }
                    break
                
                await asyncio.sleep(1)
    
    return EventSourceResponse(event_generator())


@router.get("/system")
async def system_events():
    """
    SSE系统状态事件
    
    事件类型:
    - status: 系统状态更新
    - block_detected: 检测到阻止
    """
    
    async def event_generator():
        while True:
            try:
                # 获取运行中的任务
                from app.services.job_service import JobService
                from app.models.schemas import JobStatus
                
                running_jobs = []
                all_jobs = JobService.get_all_jobs(limit=10)
                
                for job in all_jobs:
                    if job.status in [JobStatus.RUNNING, JobStatus.PAUSED]:
                        stats = task_runner.get_runner_stats(job.id)
                        running_jobs.append({
                            "job_id": job.id,
                            "name": job.name,
                            "status": job.status.value,
                            "progress": round((job.total_count - job.pending_count) / job.total_count * 100, 2) if job.total_count > 0 else 0,
                            "speed": round(stats.speed, 2) if stats else 0
                        })
                
                # 获取阻止检测器状态
                block_status = None
                if task_runner.block_detector:
                    state = task_runner.block_detector.get_state()
                    block_status = {
                        "is_blocked": state.is_blocked,
                        "error_count": state.error_count,
                        "block_until": state.block_until
                    }
                
                yield {
                    "event": "status",
                    "data": json.dumps({
                        "running_jobs": running_jobs,
                        "block_status": block_status
                    }, ensure_ascii=False)
                }
                
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"系统SSE事件错误: {e}")
                await asyncio.sleep(5)
    
    return EventSourceResponse(event_generator())
