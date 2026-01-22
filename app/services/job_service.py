"""
TG群链接验证工具 - 任务管理服务
"""
import logging
from datetime import datetime
from typing import List, Optional

from app.db.sqlite import Database
from app.models.schemas import JobStatus, JobItemStatus, JobResponse, JobCreate

logger = logging.getLogger(__name__)


class JobService:
    """任务管理服务"""
    
    @staticmethod
    def create_job(name: str, link_ids: List[int] = None) -> JobResponse:
        """
        创建新任务
        
        Args:
            name: 任务名称
            link_ids: 链接ID列表，如果为None则使用所有未验证的链接
            
        Returns:
            JobResponse
        """
        # 如果没有指定链接，获取所有链接
        if link_ids is None:
            rows = Database.fetchall("SELECT id FROM links ORDER BY id")
            link_ids = [row['id'] for row in rows]
        
        if not link_ids:
            raise ValueError("没有可用的链接")
        
        total_count = len(link_ids)
        
        # 创建任务
        job_id = Database.insert(
            """INSERT INTO jobs (name, status, total_count, pending_count)
               VALUES (?, ?, ?, ?)""",
            (name, JobStatus.PENDING.value, total_count, total_count)
        )
        
        # 批量创建任务项
        items = [(job_id, link_id, JobItemStatus.PENDING.value) for link_id in link_ids]
        Database.insert_many(
            "INSERT INTO job_items (job_id, link_id, status) VALUES (?, ?, ?)",
            items
        )
        
        logger.info(f"创建任务: {name}, ID: {job_id}, 链接数: {total_count}")
        
        return JobService.get_job(job_id)
    
    @staticmethod
    def get_job(job_id: int) -> Optional[JobResponse]:
        """获取任务详情"""
        row = Database.fetchone("SELECT * FROM jobs WHERE id = ?", (job_id,))
        if not row:
            return None
        
        return JobResponse(
            id=row['id'],
            name=row['name'],
            status=JobStatus(row['status']),
            total_count=row['total_count'],
            pending_count=row['pending_count'],
            valid_count=row['valid_count'],
            invalid_count=row['invalid_count'],
            error_count=row['error_count'],
            created_at=row['created_at'],
            started_at=row['started_at'],
            completed_at=row['completed_at'],
            error_message=row['error_message']
        )
    
    @staticmethod
    def get_all_jobs(limit: int = 100, offset: int = 0) -> List[JobResponse]:
        """获取所有任务"""
        rows = Database.fetchall(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        )
        
        return [
            JobResponse(
                id=row['id'],
                name=row['name'],
                status=JobStatus(row['status']),
                total_count=row['total_count'],
                pending_count=row['pending_count'],
                valid_count=row['valid_count'],
                invalid_count=row['invalid_count'],
                error_count=row['error_count'],
                created_at=row['created_at'],
                started_at=row['started_at'],
                completed_at=row['completed_at'],
                error_message=row['error_message']
            )
            for row in rows
        ]
    
    @staticmethod
    def get_jobs_count() -> int:
        """获取任务总数"""
        row = Database.fetchone("SELECT COUNT(*) as count FROM jobs")
        return row['count'] if row else 0
    
    @staticmethod
    def update_job_status(job_id: int, status: JobStatus, error_message: str = None):
        """更新任务状态"""
        if status == JobStatus.RUNNING:
            Database.execute(
                "UPDATE jobs SET status = ?, started_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status.value, job_id)
            )
        elif status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
            Database.execute(
                "UPDATE jobs SET status = ?, completed_at = CURRENT_TIMESTAMP, error_message = ? WHERE id = ?",
                (status.value, error_message, job_id)
            )
        else:
            Database.execute(
                "UPDATE jobs SET status = ? WHERE id = ?",
                (status.value, job_id)
            )
        
        logger.info(f"任务 {job_id} 状态更新为: {status.value}")
    
    @staticmethod
    def update_job_counts(job_id: int, pending: int = None, valid: int = None, 
                          invalid: int = None, error: int = None):
        """更新任务计数"""
        updates = []
        params = []
        
        if pending is not None:
            updates.append("pending_count = ?")
            params.append(pending)
        if valid is not None:
            updates.append("valid_count = ?")
            params.append(valid)
        if invalid is not None:
            updates.append("invalid_count = ?")
            params.append(invalid)
        if error is not None:
            updates.append("error_count = ?")
            params.append(error)
        
        if updates:
            params.append(job_id)
            sql = f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?"
            Database.execute(sql, tuple(params))
    
    @staticmethod
    def increment_job_count(job_id: int, field: str, delta: int = 1):
        """增加任务计数"""
        valid_fields = ['pending_count', 'valid_count', 'invalid_count', 'error_count']
        if field not in valid_fields:
            raise ValueError(f"无效的字段: {field}")
        
        Database.execute(
            f"UPDATE jobs SET {field} = {field} + ? WHERE id = ?",
            (delta, job_id)
        )
    
    @staticmethod
    def get_pending_items(job_id: int, limit: int = 100) -> List[dict]:
        """获取待处理的任务项"""
        rows = Database.fetchall(
            """SELECT ji.id, ji.link_id, l.normalized_url, l.original_url
               FROM job_items ji
               JOIN links l ON ji.link_id = l.id
               WHERE ji.job_id = ? AND ji.status = ?
               ORDER BY ji.id
               LIMIT ?""",
            (job_id, JobItemStatus.PENDING.value, limit)
        )
        
        return [dict(row) for row in rows]
    
    @staticmethod
    def get_retry_items(job_id: int, limit: int = 100) -> List[dict]:
        """获取待重试的任务项"""
        rows = Database.fetchall(
            """SELECT ji.id, ji.link_id, l.normalized_url, l.original_url
               FROM job_items ji
               JOIN links l ON ji.link_id = l.id
               WHERE ji.job_id = ? AND ji.status = ?
               ORDER BY ji.id
               LIMIT ?""",
            (job_id, JobItemStatus.RETRY.value, limit)
        )
        
        return [dict(row) for row in rows]
    
    @staticmethod
    def get_retry_count(job_id: int) -> int:
        """获取待重试项数量"""
        row = Database.fetchone(
            "SELECT COUNT(*) as count FROM job_items WHERE job_id = ? AND status = ?",
            (job_id, JobItemStatus.RETRY.value)
        )
        return row['count'] if row else 0
    
    @staticmethod
    def reset_interrupted_jobs():
        """重置被中断的任务（服务器重启后调用）"""
        # 把 running 状态的任务改为 paused
        Database.execute(
            "UPDATE jobs SET status = ? WHERE status = ?",
            (JobStatus.PAUSED.value, JobStatus.RUNNING.value)
        )
        logger.info("已重置被中断的任务为暂停状态")
    
    @staticmethod
    def update_item_status(item_id: int, status: JobItemStatus):
        """更新任务项状态"""
        Database.execute(
            "UPDATE job_items SET status = ? WHERE id = ?",
            (status.value, item_id)
        )
    
    @staticmethod
    def save_result(job_id: int, link_id: int, result: dict):
        """保存验证结果"""
        Database.insert(
            """INSERT INTO results 
               (link_id, job_id, is_valid, group_name, member_count, description,
                http_status, error_type, error_message, response_time_ms, proxy_used)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                link_id,
                job_id,
                result.get('is_valid'),
                result.get('group_name'),
                result.get('member_count'),
                result.get('description'),
                result.get('http_status'),
                result.get('error_type'),
                result.get('error_message'),
                result.get('response_time_ms'),
                result.get('proxy_used')
            )
        )
    
    @staticmethod
    def get_job_stats(job_id: int) -> dict:
        """获取任务统计"""
        row = Database.fetchone(
            """SELECT 
                 COUNT(*) as total,
                 SUM(CASE WHEN is_valid = 1 THEN 1 ELSE 0 END) as valid,
                 SUM(CASE WHEN is_valid = 0 THEN 1 ELSE 0 END) as invalid,
                 SUM(CASE WHEN is_valid IS NULL THEN 1 ELSE 0 END) as error
               FROM results WHERE job_id = ?""",
            (job_id,)
        )
        
        return {
            'total': row['total'] or 0,
            'valid': row['valid'] or 0,
            'invalid': row['invalid'] or 0,
            'error': row['error'] or 0
        }
    
    @staticmethod
    def delete_job(job_id: int) -> bool:
        """删除任务（级联删除相关数据）"""
        job = JobService.get_job(job_id)
        if not job:
            return False
        
        # 只能删除已完成或已取消的任务
        if job.status in [JobStatus.RUNNING, JobStatus.PAUSED]:
            raise ValueError("不能删除正在运行或暂停的任务")
        
        # 删除结果
        Database.execute("DELETE FROM results WHERE job_id = ?", (job_id,))
        # 删除任务项
        Database.execute("DELETE FROM job_items WHERE job_id = ?", (job_id,))
        # 删除任务
        Database.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        
        logger.info(f"删除任务: {job_id}")
        return True
