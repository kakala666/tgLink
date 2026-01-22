"""
TG群链接验证工具 - SQLite数据库模块
"""
import sqlite3
import threading
from pathlib import Path
from contextlib import contextmanager
from typing import Generator, Optional
import logging

from app.config import DB_PATH

logger = logging.getLogger(__name__)

# 线程本地存储
_local = threading.local()

def get_connection() -> sqlite3.Connection:
    """获取当前线程的数据库连接"""
    if not hasattr(_local, 'connection') or _local.connection is None:
        _local.connection = create_connection()
    return _local.connection

def create_connection() -> sqlite3.Connection:
    """创建新的数据库连接"""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # 启用WAL模式，提升并发性能
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=10000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """数据库连接上下文管理器"""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"数据库错误: {e}")
        raise

def init_db():
    """初始化数据库，创建表结构"""
    schema_path = Path(__file__).parent / "schema.sql"
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = f.read()
    
    with get_db() as conn:
        conn.executescript(schema)
        logger.info("数据库初始化完成")

def close_connection():
    """关闭当前线程的数据库连接"""
    if hasattr(_local, 'connection') and _local.connection is not None:
        _local.connection.close()
        _local.connection = None

class Database:
    """数据库操作类"""
    
    @staticmethod
    def execute(sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """执行SQL语句"""
        with get_db() as conn:
            return conn.execute(sql, params)
    
    @staticmethod
    def executemany(sql: str, params_list: list) -> sqlite3.Cursor:
        """批量执行SQL语句"""
        with get_db() as conn:
            return conn.executemany(sql, params_list)
    
    @staticmethod
    def fetchone(sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """查询单条记录"""
        with get_db() as conn:
            cursor = conn.execute(sql, params)
            return cursor.fetchone()
    
    @staticmethod
    def fetchall(sql: str, params: tuple = ()) -> list:
        """查询多条记录"""
        with get_db() as conn:
            cursor = conn.execute(sql, params)
            return cursor.fetchall()
    
    @staticmethod
    def insert(sql: str, params: tuple = ()) -> int:
        """插入记录并返回ID"""
        with get_db() as conn:
            cursor = conn.execute(sql, params)
            return cursor.lastrowid
    
    @staticmethod
    def insert_many(sql: str, params_list: list) -> int:
        """批量插入记录"""
        with get_db() as conn:
            cursor = conn.executemany(sql, params_list)
            return cursor.rowcount
