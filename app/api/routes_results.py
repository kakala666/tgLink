"""
TG群链接验证工具 - 结果查询和导出API
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app import config
from app.models.schemas import ResultListResponse, ResultStatsResponse
from app.services.exporter import ExportService
from app.db.sqlite import Database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/results", tags=["结果"])


@router.get("/{job_id}", response_model=ResultListResponse)
async def get_job_results(
    job_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    valid_only: bool = False,
    invalid_only: bool = False
):
    """获取任务结果列表"""
    offset = (page - 1) * page_size
    
    # 构建查询条件
    conditions = ["r.job_id = ?"]
    params = [job_id]
    
    if valid_only:
        conditions.append("r.is_valid = 1")
    elif invalid_only:
        conditions.append("r.is_valid = 0")
    
    where_clause = " AND ".join(conditions)
    
    # 查询总数
    count_sql = f"SELECT COUNT(*) as count FROM results r WHERE {where_clause}"
    count_row = Database.fetchone(count_sql, tuple(params))
    total = count_row['count'] if count_row else 0
    
    # 查询数据
    sql = f"""
        SELECT 
            r.id, r.link_id, r.job_id,
            l.original_url, l.normalized_url,
            r.is_valid, r.group_name, r.member_count, r.description,
            r.http_status, r.error_type, r.error_message,
            r.response_time_ms, r.verified_at
        FROM results r
        JOIN links l ON r.link_id = l.id
        WHERE {where_clause}
        ORDER BY r.id DESC
        LIMIT ? OFFSET ?
    """
    
    rows = Database.fetchall(sql, tuple(params + [page_size, offset]))
    
    results = []
    for row in rows:
        results.append({
            "id": row['id'],
            "link_id": row['link_id'],
            "job_id": row['job_id'],
            "original_url": row['original_url'],
            "normalized_url": row['normalized_url'],
            "is_valid": row['is_valid'],
            "group_name": row['group_name'],
            "member_count": row['member_count'],
            "description": row['description'],
            "http_status": row['http_status'],
            "error_type": row['error_type'],
            "error_message": row['error_message'],
            "response_time_ms": row['response_time_ms'],
            "verified_at": row['verified_at']
        })
    
    return ResultListResponse(
        results=results,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{job_id}/stats", response_model=ResultStatsResponse)
async def get_job_stats(job_id: int):
    """获取任务统计"""
    stats = ExportService.get_export_stats(job_id)
    
    # 获取待处理数
    pending_row = Database.fetchone(
        "SELECT COUNT(*) as count FROM job_items WHERE job_id = ? AND status = 'pending'",
        (job_id,)
    )
    pending = pending_row['count'] if pending_row else 0
    
    return ResultStatsResponse(
        job_id=job_id,
        total=stats['total'],
        valid=stats['valid'],
        invalid=stats['invalid'],
        error=stats['error'],
        pending=pending
    )


@router.get("/{job_id}/export")
async def export_job_results(
    job_id: int,
    valid_only: bool = False,
    include_errors: bool = False
):
    """
    导出任务结果为CSV
    
    返回GB2312编码、Tab分隔的CSV文件
    """
    # 检查任务是否存在
    from app.services.job_service import JobService
    job = JobService.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    def generate():
        for chunk in ExportService.export_job_results(job_id, valid_only, include_errors):
            # 转换为GB2312编码
            try:
                yield chunk.encode(config.EXPORT_ENCODING, errors='replace')
            except Exception:
                yield chunk.encode('utf-8')
    
    filename = f"tg_links_{job_id}"
    if valid_only:
        filename += "_valid"
    filename += ".csv"
    
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.get("/export/all")
async def export_all_valid():
    """导出所有有效链接（去重）"""
    
    def generate():
        for chunk in ExportService.export_all_valid_links():
            try:
                yield chunk.encode(config.EXPORT_ENCODING, errors='replace')
            except Exception:
                yield chunk.encode('utf-8')
    
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="tg_links_all_valid.csv"'
        }
    )
