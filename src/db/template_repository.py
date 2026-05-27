"""订单模板仓库 — 从 repository.py 拆分.

将 OrderData 对象序列化为 JSON 存入 SQLite。
"""

from __future__ import annotations

import logging
from typing import Any

from src.db.connection import get_connection
from src.models.order_data import OrderData, decode_order, encode_order

logger = logging.getLogger(__name__)


class TemplateRepository:
    """订单模板仓库.

    将 OrderData 对象序列化为 JSON 存入 SQLite。
    """

    @staticmethod
    def save(order: OrderData, template_name: str, description: str = "") -> int:
        """保存订单为模板.

        Args:
            order: OrderData 实例.
            template_name: 模板名称.
            description: 模板描述.

        Returns:
            新模板的 ID.
        """
        order_json_str: str
        try:
            order_json_str = encode_order(order).decode("utf-8")
        except Exception:
            logger.exception("序列化 OrderData 失败")
            raise

        customer_name = order.customer.company_name_en
        invoice_no = order.order_meta.invoice_no
        product_count = sum(
            len(carton.products) for pallet in order.pallets for carton in pallet.cartons
        )

        conn = get_connection()
        try:
            cursor = conn.execute(
                """INSERT INTO order_templates
                   (template_name, order_json, description, invoice_no, customer_name, product_count)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    template_name,
                    order_json_str,
                    description,
                    invoice_no,
                    customer_name,
                    product_count,
                ),
            )
            conn.commit()
            logger.info("保存模板: %s (ID=%d)", template_name, cursor.lastrowid)
            assert cursor.lastrowid is not None, "INSERT 后未获取 rowid"
            return cursor.lastrowid
        except Exception:
            conn.rollback()
            raise

    @staticmethod
    def load(template_id: int) -> OrderData | None:
        """加载指定 ID 的订单模板.

        Args:
            template_id: 模板 ID.

        Returns:
            OrderData 对象，不存在则返回 None.
        """
        conn = get_connection()
        cursor = conn.execute(
            "SELECT * FROM order_templates WHERE id = ? AND is_deleted = 0",
            (template_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        try:
            order = decode_order(row["order_json"])
            logger.info("加载模板 ID=%d: %s", template_id, row["template_name"])
            return order
        except Exception as err:
            logger.exception("反序列化模板 ID=%d 失败", template_id)
            raise ValueError(
                f"[错误]: 模板 ID={template_id} 数据已损坏，无法加载\n"
                f"[原因]: 数据库中存储的 JSON 数据无法解析\n"
                f"[排查]: 请删除该模板并重新保存"
            ) from err

    @staticmethod
    def list_all(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """分页列出所有未删除的模板.

        Returns:
            模板元信息列表（不含 order_json 字段以减少内存占用）.
        """
        conn = get_connection()
        cursor = conn.execute(
            """SELECT id, template_name, description, invoice_no, customer_name,
                      product_count, created_at, updated_at
               FROM order_templates
               WHERE is_deleted = 0
               ORDER BY updated_at DESC
               LIMIT ? OFFSET ?""",
            (limit, offset),
        )
        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def search(keyword: str, limit: int = 20) -> list[dict[str, Any]]:
        """按模板名称或客户名模糊搜索模板.

        Args:
            keyword: 搜索关键词.
            limit: 返回数量上限.

        Returns:
            匹配的模板列表.
        """
        conn = get_connection()
        like = f"%{keyword}%"
        cursor = conn.execute(
            """SELECT id, template_name, description, invoice_no, customer_name,
                      product_count, created_at, updated_at
               FROM order_templates
               WHERE is_deleted = 0
                 AND (template_name LIKE ? OR customer_name LIKE ?)
               ORDER BY updated_at DESC
               LIMIT ?""",
            (like, like, limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def delete(template_id: int) -> bool:
        """软删除模板."""
        conn = get_connection()
        try:
            cursor = conn.execute(
                "UPDATE order_templates SET is_deleted = 1, updated_at = datetime('now', 'localtime') WHERE id = ?",
                (template_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            raise
