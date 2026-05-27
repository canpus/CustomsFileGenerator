# -*- coding: utf-8 -*-
"""报关资料自动生成系统 — Repository 数据访问层.

实现客户/产品/模板/历史的 CRUD 操作，所有查询使用参数化查询。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from src.db.connection import get_connection
from src.models.order_data import OrderData, encode_order, decode_order

logger = logging.getLogger(__name__)


# ==================== CustomerRepository 客户仓库 ====================


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


# ==================== ProductRepository 产品仓库 ====================


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
                (product_name, specification, hs_code, declaration_elements,
                 unit, unit_price, net_weight_per_unit_kg, destination_country, currency),
            )
            conn.commit()
            logger.info("新增产品: %s (ID=%d)", product_name, cursor.lastrowid)
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
            "product_name", "specification", "hs_code", "declaration_elements",
            "unit", "unit_price", "net_weight_per_unit_kg", "destination_country", "currency",
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


# ==================== TemplateRepository 模板仓库 ====================


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

        # 提取冗余字段便于搜索
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
                (template_name, order_json_str, description, invoice_no, customer_name, product_count),
            )
            conn.commit()
            logger.info("保存模板: %s (ID=%d)", template_name, cursor.lastrowid)
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
        except Exception:
            logger.exception("反序列化模板 ID=%d 失败", template_id)
            raise ValueError(
                f"[错误]: 模板 ID={template_id} 数据已损坏，无法加载\n"
                f"[原因]: 数据库中存储的 JSON 数据无法解析\n"
                f"[排查]: 请删除该模板并重新保存"
            )

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


# ==================== HistoryRepository 历史仓库 ====================


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
