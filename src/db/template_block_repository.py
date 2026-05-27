# -*- coding: utf-8 -*-
"""分块模板仓库 — 管理 template_blocks 表的 CRUD 操作.

支持按 block_type 分类存储和检索可复用数据块。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.db.connection import get_connection

logger = logging.getLogger(__name__)

# 合法的 block_type 枚举值
VALID_BLOCK_TYPES: frozenset[str] = frozenset({"customer", "product_set", "shipping", "order_full"})


class TemplateBlockRepository:
    """分块模板仓库.

    将客户/商品/装运/整单等数据块序列化为 JSON 存入 SQLite。
    """

    @staticmethod
    def save(
        block_type: str,
        block_name: str,
        block_data: dict[str, Any],
        description: str = "",
    ) -> int:
        """保存一个数据块.

        Args:
            block_type: 块类型（customer / product_set / shipping / order_full）.
            block_name: 块名称.
            block_data: 要保存的数据字典.
            description: 备注描述.

        Returns:
            新块的 ID.

        Raises:
            ValueError: block_type 不合法时抛出.
        """
        if block_type not in VALID_BLOCK_TYPES:
            raise ValueError(
                f"[错误]: 非法的块类型 '{block_type}'\n"
                f"[原因]: block_type 必须是 {sorted(VALID_BLOCK_TYPES)} 之一\n"
                f"[排查]: 请使用合法的块类型"
            )

        block_json: str
        try:
            block_json = json.dumps(block_data, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            logger.exception("序列化模板数据块失败")
            raise ValueError(
                f"[错误]: 数据块序列化失败\n"
                f"[原因]: {e}\n"
                f"[排查]: 请确认数据中不包含不可序列化的对象"
            ) from e

        conn = get_connection()
        try:
            cursor = conn.execute(
                """INSERT INTO template_blocks
                   (block_type, block_name, block_json, description)
                   VALUES (?, ?, ?, ?)""",
                (block_type, block_name, block_json, description),
            )
            conn.commit()
            logger.info("保存分块模板: %s / %s (ID=%d)", block_type, block_name, cursor.lastrowid)
            return cursor.lastrowid
        except Exception:
            conn.rollback()
            raise

    @staticmethod
    def load(block_id: int) -> dict[str, Any] | None:
        """加载指定 ID 的数据块.

        Args:
            block_id: 块 ID.

        Returns:
            包含 block_type, block_name, block_data, description 的字典，
            不存在时返回 None.
        """
        conn = get_connection()
        cursor = conn.execute(
            "SELECT * FROM template_blocks WHERE id = ? AND is_deleted = 0",
            (block_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        try:
            block_data: dict[str, Any] = json.loads(row["block_json"])
        except json.JSONDecodeError as e:
            logger.exception("反序列化分块模板 ID=%d 失败", block_id)
            raise ValueError(
                f"[错误]: 分块模板 ID={block_id} 数据已损坏\n"
                f"[原因]: {e}\n"
                f"[排查]: 请删除该分块模板并重新保存"
            ) from e

        return {
            "id": row["id"],
            "block_type": row["block_type"],
            "block_name": row["block_name"],
            "block_data": block_data,
            "description": row["description"] or "",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def list_by_type(
        block_type: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """按类型列出所有未删除的数据块.

        Args:
            block_type: 块类型.
            limit: 返回数量上限.
            offset: 分页偏移.

        Returns:
            块元信息列表（不含 block_json 字段以减少内存占用）.
        """
        if block_type not in VALID_BLOCK_TYPES:
            return []

        conn = get_connection()
        cursor = conn.execute(
            """SELECT id, block_type, block_name, description, created_at, updated_at
               FROM template_blocks
               WHERE block_type = ? AND is_deleted = 0
               ORDER BY updated_at DESC
               LIMIT ? OFFSET ?""",
            (block_type, limit, offset),
        )
        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def search(
        block_type: str | None,
        keyword: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """按名称模糊搜索数据块.

        Args:
            block_type: 块类型，None 表示搜索所有类型.
            keyword: 搜索关键词.
            limit: 返回数量上限.

        Returns:
            匹配的块列表.
        """
        conn = get_connection()
        like = f"%{keyword}%"

        if block_type is not None and block_type in VALID_BLOCK_TYPES:
            cursor = conn.execute(
                """SELECT id, block_type, block_name, description, created_at, updated_at
                   FROM template_blocks
                   WHERE block_type = ? AND is_deleted = 0 AND block_name LIKE ?
                   ORDER BY updated_at DESC
                   LIMIT ?""",
                (block_type, like, limit),
            )
        else:
            cursor = conn.execute(
                """SELECT id, block_type, block_name, description, created_at, updated_at
                   FROM template_blocks
                   WHERE is_deleted = 0 AND block_name LIKE ?
                   ORDER BY updated_at DESC
                   LIMIT ?""",
                (like, limit),
            )
        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def delete(block_id: int) -> bool:
        """软删除数据块.

        Args:
            block_id: 块 ID.

        Returns:
            是否删除成功.
        """
        conn = get_connection()
        try:
            cursor = conn.execute(
                "UPDATE template_blocks SET is_deleted = 1, updated_at = datetime('now', 'localtime') WHERE id = ?",
                (block_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            raise
