# -*- coding: utf-8 -*-
"""客户数据仓库 — 从 repository.py 拆分."""

from __future__ import annotations

import logging
import time
from typing import Any

from src.db.connection import get_connection

logger = logging.getLogger(__name__)


class CustomerRepository:
    """客户数据仓库.

    提供客户信息的增删改查及模糊搜索功能。
    所有删除为软删除（is_deleted=1），支持恢复。
    """

    @staticmethod
    def insert(
        company_name_en: str,
        country: str,
        company_name_cn: str = "",
        address: str = "",
        contact_person: str = "",
        phone: str = "",
        mobile: str = "",
        destination: str = "",
    ) -> int:
        """新增客户.

        Args:
            company_name_en: 客户公司英文名（必填）.
            country: 国家（必填）.
            company_name_cn: 中文名.
            address: 地址.
            contact_person: 联系人.
            phone: 电话.
            mobile: 手机号.
            destination: 目的地.

        Returns:
            新客户的 ID.
        """
        conn = get_connection()
        try:
            cursor = conn.execute(
                """INSERT INTO customers
                   (company_name_en, company_name_cn, country, address,
                    contact_person, phone, mobile, destination)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (company_name_en, company_name_cn, country, address,
                 contact_person, phone, mobile, destination),
            )
            conn.commit()
            logger.info("新增客户: %s (ID=%d)", company_name_en, cursor.lastrowid)
            return cursor.lastrowid
        except Exception:
            conn.rollback()
            raise

    @staticmethod
    def get_by_id(customer_id: int) -> dict[str, Any] | None:
        """按 ID 查询客户.

        Args:
            customer_id: 客户 ID.

        Returns:
            客户字典，不存在则返回 None.
        """
        conn = get_connection()
        cursor = conn.execute(
            "SELECT * FROM customers WHERE id = ? AND is_deleted = 0",
            (customer_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    @staticmethod
    def search(keyword: str, limit: int = 20) -> list[dict[str, Any]]:
        """模糊搜索客户（按公司英文名、中文名、国家）.

        Args:
            keyword: 搜索关键词.
            limit: 返回数量上限.

        Returns:
            匹配的客户列表.
        """
        conn = get_connection()
        like = f"%{keyword}%"
        cursor = conn.execute(
            """SELECT * FROM customers
               WHERE is_deleted = 0
                 AND (company_name_en LIKE ? OR company_name_cn LIKE ? OR country LIKE ?)
               ORDER BY company_name_en
               LIMIT ?""",
            (like, like, like, limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def list_all(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """分页列出所有未删除的客户.

        Args:
            limit: 每页数量.
            offset: 偏移量.

        Returns:
            客户列表.
        """
        conn = get_connection()
        cursor = conn.execute(
            "SELECT * FROM customers WHERE is_deleted = 0 ORDER BY company_name_en LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def update(customer_id: int, **fields: Any) -> bool:
        """更新客户信息.

        Args:
            customer_id: 客户 ID.
            **fields: 要更新的字段名和值.

        Returns:
            True 表示更新成功，False 表示 ID 不存在.
        """
        if not fields:
            return False

        # 安全边界：updates 的 key 已经过 allowed set 白名单过滤，
        # 仅包含已知安全列名（company_name_en 等 8 个字段），
        # 不存在 SQL 注入风险。
        allowed = {
            "company_name_en", "company_name_cn", "country", "address",
            "contact_person", "phone", "mobile", "destination",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return False

        updates["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [customer_id]

        conn = get_connection()
        try:
            cursor = conn.execute(
                f"UPDATE customers SET {set_clause} WHERE id = ? AND is_deleted = 0",
                values,
            )
            conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                logger.info("更新客户 ID=%d: %s", customer_id, list(updates.keys()))
            return updated
        except Exception:
            conn.rollback()
            raise

    @staticmethod
    def delete(customer_id: int) -> bool:
        """软删除客户.

        Args:
            customer_id: 客户 ID.

        Returns:
            True 表示删除成功.
        """
        conn = get_connection()
        try:
            cursor = conn.execute(
                "UPDATE customers SET is_deleted = 1, updated_at = datetime('now', 'localtime') WHERE id = ?",
                (customer_id,),
            )
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info("软删除客户 ID=%d", customer_id)
            return deleted
        except Exception:
            conn.rollback()
            raise
