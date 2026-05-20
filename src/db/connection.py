# -*- coding: utf-8 -*-
"""报关资料自动生成系统 — SQLite 数据库连接管理器.

提供线程安全的 SQLite 连接管理，启用 WAL 模式，自动建表。
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from config.constants import DATABASE_PATH

logger = logging.getLogger(__name__)

# ==================== 模块级常量 ====================

# schema.sql 文件路径
_SCHEMA_PATH: Path = Path(__file__).resolve().parent / "schema.sql"

# 连接重试配置
_MAX_RETRIES: int = 3
_RETRY_DELAY_SECONDS: float = 0.5

# 每个线程持有自己的连接，线程安全
_thread_local: threading.local = threading.local()


# ==================== 初始化 ====================


def _ensure_data_dir() -> None:
    """确保数据库文件所在目录存在."""
    data_dir = DATABASE_PATH.parent
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        msg = (
            f"[错误]: 无法创建数据库目录 {data_dir}\n"
            f"[原因]: {e}\n"
            f"[排查]: 请检查磁盘空间和目录写入权限"
        )
        logger.error(msg)
        raise RuntimeError(msg) from e


def _load_schema(conn: sqlite3.Connection) -> None:
    """从 schema.sql 加载并执行建表语句.

    Args:
        conn: 已打开的数据库连接.
    """
    if not _SCHEMA_PATH.exists():
        msg = (
            f"[错误]: 数据库建表脚本不存在: {_SCHEMA_PATH}\n"
            f"[原因]: 项目文件不完整，schema.sql 可能被误删\n"
            f"[排查]: 请检查 src/db/schema.sql 文件是否存在"
        )
        logger.error(msg)
        raise FileNotFoundError(msg)

    schema_sql: str
    try:
        schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    except OSError as e:
        msg = (
            f"[错误]: 无法读取建表脚本 {_SCHEMA_PATH}\n"
            f"[原因]: {e}\n"
            f"[排查]: 检查文件权限和磁盘状态"
        )
        logger.error(msg)
        raise RuntimeError(msg) from e

    try:
        conn.executescript(schema_sql)
        conn.commit()
        logger.info("数据库表结构初始化完成: %s", DATABASE_PATH)
    except sqlite3.Error as e:
        msg = (
            f"[错误]: 建表脚本执行失败\n"
            f"[原因]: {e}\n"
            f"[排查]: 检查 src/db/schema.sql 中 SQL 语法是否正确"
        )
        logger.error(msg)
        raise RuntimeError(msg) from e


# ==================== 连接获取 ====================


def get_connection() -> sqlite3.Connection:
    """获取当前线程的数据库连接（自动创建、初始化、启用 WAL）.

    每个线程持有独立连接，线程安全。

    Returns:
        sqlite3.Connection: 已初始化的数据库连接.
    """
    conn = getattr(_thread_local, "connection", None)

    if conn is None:
        _ensure_data_dir()

        _thread_local.connection = _create_connection_with_retry()
        conn = _thread_local.connection
        logger.info("已为线程 %s 创建数据库连接", threading.current_thread().name)

    return conn


def _create_connection_with_retry() -> sqlite3.Connection:
    """带重试机制的数据库连接创建.

    Returns:
        sqlite3.Connection: 已配置 WAL 模式并建表的连接.

    Raises:
        RuntimeError: 重试耗尽仍无法连接时抛出.
    """
    last_error: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            conn = sqlite3.connect(
                str(DATABASE_PATH),
                check_same_thread=False,
                timeout=10.0,
            )
            # 启用 WAL 模式（提高并发读写性能）
            conn.execute("PRAGMA journal_mode=WAL")
            # 启用外键约束
            conn.execute("PRAGMA foreign_keys=ON")
            # 设置行工厂为 sqlite3.Row（方便按列名访问）
            conn.row_factory = sqlite3.Row

            # 自动建表
            _load_schema(conn)

            return conn

        except sqlite3.Error as e:
            last_error = e
            if attempt < _MAX_RETRIES:
                logger.warning(
                    "数据库连接失败（第 %d/%d 次），%s 后重试...",
                    attempt, _MAX_RETRIES, _RETRY_DELAY_SECONDS,
                )
                time.sleep(_RETRY_DELAY_SECONDS)

    msg = (
        f"[错误]: 数据库连接失败（已重试 {_MAX_RETRIES} 次）\n"
        f"[原因]: {last_error}\n"
        f"[排查]: "
        f"1. 检查磁盘空间是否充足\n"
        f"2. 检查 {DATABASE_PATH.parent} 目录是否有写入权限\n"
        f"3. 确认没有其他进程锁定数据库文件"
    )
    logger.error(msg)
    raise RuntimeError(msg) from last_error


def close_connection() -> None:
    """关闭当前线程的数据库连接."""
    conn = getattr(_thread_local, "connection", None)
    if conn is not None:
        try:
            conn.close()
            logger.info("已关闭线程 %s 的数据库连接", threading.current_thread().name)
        except sqlite3.Error as e:
            logger.warning("关闭数据库连接时出错: %s", e)
        finally:
            _thread_local.connection = None


def close_all_connections() -> None:
    """关闭所有线程的数据库连接（程序退出时调用）."""
    close_connection()


# ==================== 便捷函数 ====================


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """数据库连接的上下文管理器.

    自动提交/回滚，使用完毕后不关闭连接（连接由线程持有复用）.

    Yields:
        sqlite3.Connection: 数据库连接.
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def get_db_path() -> Path:
    """获取数据库文件路径.

    Returns:
        Path: 数据库文件的完整路径.
    """
    return DATABASE_PATH
