# -*- coding: utf-8 -*-
"""生成历史仓库 — 从 repository.py 拆分.

记录每次一键生成的订单摘要，便于追溯。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.db.connection import get_connection
from src.models.order_data import OrderData, encode_order

logger = logging.getLogger(__name__)


class HistoryRepository:
    """生成历史仓库.

    记录每次一键生成的订单摘要，便于追溯。
    """

    @staticmethod
    def record(
        invoice_no: str,
        contract_no: str,
        customer_name: str,
        total_amount: float,
        total_pallets: int,
        total_cartons: int,
        generated_files: list[str] | None = None,
        order: OrderData | None = None,
        status: str = "success",
        error_message: str = "",
    ) -> int:
        """记录一次生成操作.

        Args:
            invoice_no: 发票号.
            contract_no: 合同号.
            customer_name: 客户名.
            total_amount: 总金额.
            total_pallets: 托盘总数.
            total_cartons: 纸箱总数.
            generated_files: 生成的文件名列表.
            order: 订单对象（可选，用于回溯）.
            status: 状态（success/partial/failed）.
            error_message: 错误信息.

        Returns:
            新记录的 ID.
        """
        files_json = json.dumps(generated_files or [], ensure_ascii=False)
        order_json_str = ""
        if order is not None:
            try:
                order_json_str = encode_order(order).decode("utf-8")
            except Exception:
                logger.exception("序列化订单快照失败，将不保存 order_json")

        conn = get_connection()
        try:
            cursor = conn.execute(
                """INSERT INTO history
                   (invoice_no, contract_no, customer_name, total_amount,
                    total_pallets, total_cartons, generated_files, order_json, status, error_message)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (invoice_no, contract_no, customer_name, total_amount,
                 total_pallets, total_cartons, files_json, order_json_str, status, error_message),
            )
            conn.commit()
            logger.info("记录生成历史: %s (ID=%d)", invoice_no, cursor.lastrowid)
            return cursor.lastrowid
        except Exception:
            conn.rollback()
            raise

    @staticmethod
    def list_recent(limit: int = 20) -> list[dict[str, Any]]:
        """列出最近的生成记录.

        Args:
            limit: 返回数量上限.

        Returns:
            历史记录列表（不含 order_json 字段）.
        """
        conn = get_connection()
        cursor = conn.execute(
            """SELECT id, invoice_no, contract_no, customer_name, total_amount,
                      total_pallets, total_cartons, generated_files, generated_at, status, error_message
               FROM history
               ORDER BY generated_at DESC
               LIMIT ?""",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_by_id(history_id: int) -> dict[str, Any] | None:
        """按 ID 查询历史记录（含完整 order_json）.

        Args:
            history_id: 历史记录 ID.

        Returns:
            历史记录字典，不存在则返回 None.
        """
        conn = get_connection()
        cursor = conn.execute(
            "SELECT * FROM history WHERE id = ?",
            (history_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    @staticmethod
    def clear_old(days: int = 90) -> int:
        """清理超过指定天数的旧记录.

        Args:
            days: 保留天数，默认 90 天.

        Returns:
            删除的记录数.
        """
        conn = get_connection()
        try:
            cursor = conn.execute(
                "DELETE FROM history WHERE generated_at < datetime('now', 'localtime', ?)",
                (f"-{days} days",),
            )
            conn.commit()
            deleted = cursor.rowcount
            if deleted > 0:
                logger.info("清理了 %d 条 %d 天前的历史记录", deleted, days)
            return deleted
        except Exception:
            conn.rollback()
            raise
