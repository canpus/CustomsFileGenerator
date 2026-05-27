"""产品数据仓库 — 从 repository.py 拆分."""

from __future__ import annotations

import logging
import time
from typing import Any

from src.db.connection import get_connection

logger = logging.getLogger(__name__)


class ProductRepository:
    """产品数据仓库.

    提供产品信息的增删改查及 HS Code 搜索功能。
    """

    @staticmethod
    def insert(
        product_name: str,
        hs_code: str,
        unit: str,
        unit_price: float = 0.0,
        net_weight_per_unit_kg: float = 0.0,
        specification: str = "",
        declaration_elements: str = "",
        destination_country: str = "",
        currency: str = "USD",
    ) -> int:
        """新增产品.

        Args:
            product_name: 商品名称（必填）.
            hs_code: HS 编码（必填）.
            unit: 计量单位（必填）.
            unit_price: 单价.
            net_weight_per_unit_kg: 单件净重.
            specification: 规格型号.
            declaration_elements: 申报要素.
            destination_country: 目的国.
            currency: 币种.

        Returns:
            新产品的 ID.
        """
        conn = get_connection()
        try:
            cursor = conn.execute(
                """INSERT INTO products
                   (product_name, specification, hs_code, declaration_elements,
                    unit, unit_price, net_weight_per_unit_kg, destination_country, currency)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    product_name,
                    specification,
                    hs_code,
                    declaration_elements,
                    unit,
                    unit_price,
                    net_weight_per_unit_kg,
                    destination_country,
                    currency,
                ),
            )
            conn.commit()
            logger.info("新增产品: %s (ID=%d)", product_name, cursor.lastrowid)
            assert cursor.lastrowid is not None, "INSERT 后未获取 rowid"
            return cursor.lastrowid
        except Exception:
            conn.rollback()
            raise

    @staticmethod
    def get_by_id(product_id: int) -> dict[str, Any] | None:
        """按 ID 查询产品."""
        conn = get_connection()
        cursor = conn.execute(
            "SELECT * FROM products WHERE id = ? AND is_deleted = 0",
            (product_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    @staticmethod
    def search_by_hs_code(hs_code: str, limit: int = 20) -> list[dict[str, Any]]:
        """按 HS 编码模糊搜索.

        Args:
            hs_code: HS 编码（支持部分匹配）.
            limit: 返回数量上限.

        Returns:
            匹配的产品列表.
        """
        conn = get_connection()
        cursor = conn.execute(
            """SELECT * FROM products
               WHERE is_deleted = 0 AND hs_code LIKE ?
               ORDER BY product_name
               LIMIT ?""",
            (f"%{hs_code}%", limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def search_by_name(keyword: str, limit: int = 20) -> list[dict[str, Any]]:
        """按商品名称模糊搜索.

        Args:
            keyword: 搜索关键词.
            limit: 返回数量上限.

        Returns:
            匹配的产品列表.
        """
        conn = get_connection()
        cursor = conn.execute(
            """SELECT * FROM products
               WHERE is_deleted = 0 AND product_name LIKE ?
               ORDER BY product_name
               LIMIT ?""",
            (f"%{keyword}%", limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def list_all(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """分页列出所有未删除的产品."""
        conn = get_connection()
        cursor = conn.execute(
            "SELECT * FROM products WHERE is_deleted = 0 ORDER BY product_name LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def update(product_id: int, **fields: Any) -> bool:
        """更新产品信息."""
        if not fields:
            return False

        # 安全边界：updates 的 key 已经过 allowed set 白名单过滤，
        # 仅包含已知安全列名（product_name 等 9 个字段），
        # 不存在 SQL 注入风险。
        allowed = {
            "product_name",
            "specification",
            "hs_code",
            "declaration_elements",
            "unit",
            "unit_price",
            "net_weight_per_unit_kg",
            "destination_country",
            "currency",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return False

        updates["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [product_id]

        conn = get_connection()
        try:
            cursor = conn.execute(
                f"UPDATE products SET {set_clause} WHERE id = ? AND is_deleted = 0",
                values,
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            raise

    @staticmethod
    def delete(product_id: int) -> bool:
        """软删除产品."""
        conn = get_connection()
        try:
            cursor = conn.execute(
                "UPDATE products SET is_deleted = 1, updated_at = datetime('now', 'localtime') WHERE id = ?",
                (product_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            raise
