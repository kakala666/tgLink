"""
TG群链接验证工具 - 导入服务
负责文件上传、链接解析、去重入库
"""
import re
import time
import logging
from pathlib import Path
from typing import Tuple, List, Optional, Generator
from dataclasses import dataclass

from app.config import UPLOAD_DIR
from app.db.sqlite import Database
from app.models.schemas import LinkType, ImportResponse, ImportProgressResponse

logger = logging.getLogger(__name__)

# Telegram链接正则表达式
TG_LINK_PATTERNS = [
    # https://t.me/username 或 https://t.me/+hash
    re.compile(r'https?://t\.me/(\+[a-zA-Z0-9_-]+|[a-zA-Z][a-zA-Z0-9_]{4,31})', re.IGNORECASE),
    # https://telegram.me/username
    re.compile(r'https?://telegram\.me/(\+[a-zA-Z0-9_-]+|[a-zA-Z][a-zA-Z0-9_]{4,31})', re.IGNORECASE),
    # https://t.me/joinchat/hash
    re.compile(r'https?://t\.me/joinchat/([a-zA-Z0-9_-]+)', re.IGNORECASE),
    # https://telegram.me/joinchat/hash
    re.compile(r'https?://telegram\.me/joinchat/([a-zA-Z0-9_-]+)', re.IGNORECASE),
]


@dataclass
class ParsedLink:
    """解析后的链接"""
    original_url: str
    normalized_url: str
    link_type: LinkType
    identifier: str


class ImportService:
    """导入服务"""
    
    @staticmethod
    def parse_link(url: str) -> Optional[ParsedLink]:
        """
        解析Telegram链接
        
        Args:
            url: 原始URL
            
        Returns:
            ParsedLink或None（如果不是有效的TG链接）
        """
        url = url.strip()
        if not url:
            return None
        
        # 尝试匹配各种模式
        for i, pattern in enumerate(TG_LINK_PATTERNS):
            match = pattern.search(url)
            if match:
                identifier = match.group(1)
                
                # 判断链接类型
                if i >= 2:  # joinchat模式
                    link_type = LinkType.JOINCHAT
                    normalized = f"https://t.me/joinchat/{identifier}"
                elif identifier.startswith('+'):
                    link_type = LinkType.JOINCHAT
                    normalized = f"https://t.me/{identifier}"
                else:
                    # 无法仅从URL判断是群组还是频道，标记为unknown
                    link_type = LinkType.UNKNOWN
                    normalized = f"https://t.me/{identifier.lower()}"
                    identifier = identifier.lower()
                
                return ParsedLink(
                    original_url=url,
                    normalized_url=normalized,
                    link_type=link_type,
                    identifier=identifier
                )
        
        return None
    
    @staticmethod
    def count_file_lines(filepath: Path) -> int:
        """计算文件行数"""
        count = 0
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for _ in f:
                count += 1
        return count
    
    @staticmethod
    def read_links_from_file(filepath: Path, batch_size: int = 10000) -> Generator[List[str], None, None]:
        """
        从文件读取链接（生成器，分批返回）
        
        Args:
            filepath: 文件路径
            batch_size: 每批行数
            
        Yields:
            每批的链接列表
        """
        batch = []
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if line:
                    batch.append(line)
                    if len(batch) >= batch_size:
                        yield batch
                        batch = []
        if batch:
            yield batch
    
    @classmethod
    def import_file(cls, filename: str, progress_callback=None) -> ImportResponse:
        """
        导入文件中的链接
        
        Args:
            filename: 上传后的文件名
            progress_callback: 进度回调函数，接收ImportProgressResponse
            
        Returns:
            ImportResponse
        """
        filepath = UPLOAD_DIR / filename
        if not filepath.exists():
            raise FileNotFoundError(f"文件不存在: {filename}")
        
        start_time = time.time()
        file_size = filepath.stat().st_size
        
        # 计算总行数
        total_lines = cls.count_file_lines(filepath)
        
        # 统计计数器
        processed_lines = 0
        valid_links = 0
        duplicate_links = 0
        invalid_lines = 0
        
        # 分批处理
        for batch in cls.read_links_from_file(filepath):
            parsed_links = []
            
            for line in batch:
                processed_lines += 1
                parsed = cls.parse_link(line)
                
                if parsed:
                    parsed_links.append(parsed)
                else:
                    invalid_lines += 1
            
            # 批量插入，处理去重
            if parsed_links:
                batch_valid, batch_dup = cls._insert_links_batch(parsed_links)
                valid_links += batch_valid
                duplicate_links += batch_dup
            
            # 回调进度
            if progress_callback:
                progress = ImportProgressResponse(
                    filename=filename,
                    processed_lines=processed_lines,
                    total_lines=total_lines,
                    valid_links=valid_links,
                    duplicate_links=duplicate_links,
                    invalid_lines=invalid_lines,
                    progress=processed_lines / total_lines * 100 if total_lines > 0 else 0
                )
                progress_callback(progress)
        
        elapsed = time.time() - start_time
        
        # 记录导入日志
        Database.insert(
            """INSERT INTO import_logs 
               (filename, file_size, total_lines, valid_links, duplicate_links, invalid_lines)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (filename, file_size, total_lines, valid_links, duplicate_links, invalid_lines)
        )
        
        logger.info(f"导入完成: {filename}, 有效链接: {valid_links}, 重复: {duplicate_links}, 无效: {invalid_lines}")
        
        return ImportResponse(
            filename=filename,
            file_size=file_size,
            total_lines=total_lines,
            valid_links=valid_links,
            duplicate_links=duplicate_links,
            invalid_lines=invalid_lines,
            elapsed_seconds=elapsed
        )
    
    @staticmethod
    def _insert_links_batch(links: List[ParsedLink]) -> Tuple[int, int]:
        """
        批量插入链接，处理去重
        
        Returns:
            (新增数量, 重复数量)
        """
        if not links:
            return 0, 0
        
        # 使用INSERT OR IGNORE处理唯一约束
        sql = """INSERT OR IGNORE INTO links 
                 (original_url, normalized_url, link_type, identifier)
                 VALUES (?, ?, ?, ?)"""
        
        params = [(link.original_url, link.normalized_url, link.link_type.value, link.identifier) 
                  for link in links]
        
        inserted = Database.insert_many(sql, params)
        duplicates = len(links) - inserted
        
        return inserted, duplicates
    
    @staticmethod
    def get_all_link_ids() -> List[int]:
        """获取所有链接ID"""
        rows = Database.fetchall("SELECT id FROM links ORDER BY id")
        return [row['id'] for row in rows]
    
    @staticmethod
    def get_unverified_link_ids(job_id: int = None) -> List[int]:
        """获取未验证的链接ID"""
        if job_id:
            # 获取指定任务中待验证的链接
            sql = """SELECT link_id FROM job_items 
                     WHERE job_id = ? AND status = 'pending'
                     ORDER BY id"""
            rows = Database.fetchall(sql, (job_id,))
        else:
            # 获取从未验证过的链接
            sql = """SELECT id FROM links 
                     WHERE id NOT IN (SELECT DISTINCT link_id FROM results)
                     ORDER BY id"""
            rows = Database.fetchall(sql)
        
        return [row[0] for row in rows]
    
    @staticmethod
    def get_link_by_id(link_id: int) -> Optional[dict]:
        """根据ID获取链接"""
        row = Database.fetchone("SELECT * FROM links WHERE id = ?", (link_id,))
        return dict(row) if row else None
    
    @staticmethod
    def get_links_by_ids(link_ids: List[int]) -> List[dict]:
        """批量获取链接"""
        if not link_ids:
            return []
        
        placeholders = ','.join('?' * len(link_ids))
        sql = f"SELECT * FROM links WHERE id IN ({placeholders})"
        rows = Database.fetchall(sql, tuple(link_ids))
        return [dict(row) for row in rows]
    
    @staticmethod
    def get_total_link_count() -> int:
        """获取链接总数"""
        row = Database.fetchone("SELECT COUNT(*) as count FROM links")
        return row['count'] if row else 0
