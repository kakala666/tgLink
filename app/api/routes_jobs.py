"""
TG群链接验证工具 - 任务管理API
"""
import logging

from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    JobCreate, JobResponse, JobListResponse, JobProgressResponse,
    MessageResponse, JobStatus
)
from app.services.job_service import JobService
from app.workers.runner import task_runner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["任务"])


@router.post("/create", response_model=JobResponse)
async def create_job(request: JobCreate):
    """创建新任务"""
    try:
        job = JobService.create_job(request.name, request.link_ids)
        return job
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"创建任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")


@router.get("/list", response_model=JobListResponse)
async def list_jobs(limit: int = 100, offset: int = 0):
    """获取任务列表"""
    jobs = JobService.get_all_jobs(limit, offset)
    total = JobService.get_jobs_count()
    
    return JobListResponse(jobs=jobs, total=total)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: int):
    """获取任务详情"""
    job = JobService.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


@router.get("/{job_id}/progress", response_model=JobProgressResponse)
async def get_job_progress(job_id: int):
    """获取任务进度"""
    job = JobService.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 获取运行器统计
    stats = task_runner.get_runner_stats(job_id)
    
    # 计算进度
    total = job.total_count
    pending = job.pending_count
    processed = total - pending
    progress = (processed / total * 100) if total > 0 else 0
    
    speed = stats.speed if stats else 0
    eta = stats.eta_seconds if stats else None
    
    return JobProgressResponse(
        job_id=job_id,
        status=job.status,
        total_count=total,
        pending_count=pending,
        valid_count=job.valid_count,
        invalid_count=job.invalid_count,
        error_count=job.error_count,
        progress=progress,
        speed=speed,
        eta_seconds=eta
    )


@router.post("/{job_id}/start", response_model=MessageResponse)
async def start_job(job_id: int):
    """启动任务"""
    job = JobService.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    success = await task_runner.start_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="无法启动任务")
    
    return MessageResponse(message="任务已启动", success=True)


@router.post("/{job_id}/pause", response_model=MessageResponse)
async def pause_job(job_id: int):
    """暂停任务"""
    success = await task_runner.pause_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="无法暂停任务")
    
    return MessageResponse(message="任务已暂停", success=True)


@router.post("/{job_id}/resume", response_model=MessageResponse)
async def resume_job(job_id: int):
    """继续任务"""
    success = await task_runner.resume_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="无法继续任务")
    
    return MessageResponse(message="任务已继续", success=True)


@router.post("/{job_id}/stop", response_model=MessageResponse)
async def stop_job(job_id: int):
    """停止任务"""
    success = await task_runner.stop_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="无法停止任务")
    
    return MessageResponse(message="任务停止中", success=True)


@router.delete("/{job_id}", response_model=MessageResponse)
async def delete_job(job_id: int):
    """删除任务"""
    try:
        success = JobService.delete_job(job_id)
        if not success:
            raise HTTPException(status_code=404, detail="任务不存在")
        return MessageResponse(message="任务已删除", success=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"删除任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除任务失败: {str(e)}")
