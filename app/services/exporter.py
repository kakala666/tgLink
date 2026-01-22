"""
TG群链接验证工具 - CSV导出服务
"""
import io
import csv
import logging
from pathlib import Path
from typing import List, Optional, Generator

from app import config
from app.db.sqlite import Database

logger = logging.getLogger(__name__)


class ExportService:
    """导出服务"""
    
    @staticmethod
    def export_job_results(
        job_id: int,
        valid_only: bool = False,
        include_errors: bool = False
    ) -> Generator[str, None, None]:
        """
        导出任务结果为CSV（生成器，流式输出）
        
        Args:
            job_id: 任务ID
            valid_only: 只导出有效链接
            include_errors: 包含错误信息列
            
        Yields:
            CSV行
        """
        # 构建查询条件
        conditions = ["r.job_id = ?"]
        params = [job_id]
        
        if valid_only:
            conditions.append("r.is_valid = 1")
        
        where_clause = " AND ".join(conditions)
        
        # 查询数据
        sql = f"""
            SELECT 
                l.original_url,
                l.normalized_url,
                r.is_valid,
                r.group_name,
                r.member_count,
                r.description,
                r.http_status,
                r.error_type,
                r.error_message,
                r.verified_at
            FROM results r
            JOIN links l ON r.link_id = l.id
            WHERE {where_clause}
            ORDER BY r.id
        """
        
        rows = Database.fetchall(sql, tuple(params))
        
        # 写入CSV
        output = io.StringIO()
        
        # 确定列
        if include_errors:
            fieldnames = [
                '原始链接', '标准链接', '是否有效', '群名', 
                '成员数', '描述', 'HTTP状态', '错误类型', '错误信息', '验证时间'
            ]
        else:
            fieldnames = ['原始链接', '标准链接', '是否有效', '群名', '成员数', '描述', '验证时间']
        
        writer = csv.writer(output, delimiter=config.EXPORT_DELIMITER)
        
        # 写入表头
        writer.writerow(fieldnames)
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)
        
        # 写入数据
        for row in rows:
            is_valid = '有效' if row['is_valid'] else ('无效' if row['is_valid'] is not None else '未知')
            
            if include_errors:
                data = [
                    row['original_url'],
                    row['normalized_url'],
                    is_valid,
                    row['group_name'] or '',
                    row['member_count'] or '',
                    row['description'] or '',
                    row['http_status'] or '',
                    row['error_type'] or '',
                    row['error_message'] or '',
                    row['verified_at'] or ''
                ]
            else:
                data = [
                    row['original_url'],
                    row['normalized_url'],
                    is_valid,
                    row['group_name'] or '',
                    row['member_count'] or '',
                    row['description'] or '',
                    row['verified_at'] or ''
                ]
            
            writer.writerow(data)
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)
    
    @staticmethod
    def export_to_file(
        job_id: int,
        filepath: Path,
        valid_only: bool = False,
        include_errors: bool = False
    ) -> int:
        """
        导出任务结果到文件
        
        Args:
            job_id: 任务ID
            filepath: 输出文件路径
            valid_only: 只导出有效链接
            include_errors: 包含错误信息列
            
        Returns:
            导出的行数
        """
        count = 0
        
        with open(filepath, 'w', encoding=config.EXPORT_ENCODING, errors='replace', newline='') as f:
            for chunk in ExportService.export_job_results(job_id, valid_only, include_errors):
                f.write(chunk)
                count += 1
        
        logger.info(f"导出完成: {filepath}, 共 {count - 1} 条记录")  # -1 去掉表头
        return count - 1
    
    @staticmethod
    def get_export_stats(job_id: int) -> dict:
        """获取导出统计信息"""
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
    def export_all_valid_links() -> Generator[str, None, None]:
        """导出所有有效链接（去重）"""
        sql = """
            SELECT DISTINCT
                l.original_url,
                l.normalized_url,
                r.group_name,
                r.member_count,
                r.description
            FROM results r
            JOIN links l ON r.link_id = l.id
            WHERE r.is_valid = 1
            ORDER BY l.id
        """
        
        rows = Database.fetchall(sql)
        
        output = io.StringIO()
        fieldnames = ['原始链接', '标准链接', '群名', '成员数', '描述']
        writer = csv.writer(output, delimiter=config.EXPORT_DELIMITER)
        
        # 写入表头
        writer.writerow(fieldnames)
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)
        
        # 写入数据
        for row in rows:
            data = [
                row['original_url'],
                row['normalized_url'],
                row['group_name'] or '',
                row['member_count'] or '',
                row['description'] or ''
            ]
            writer.writerow(data)
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)
