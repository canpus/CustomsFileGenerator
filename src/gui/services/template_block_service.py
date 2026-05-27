"""模板块服务 — 分块模板的保存、加载、套用业务逻辑.

提供：
- 按类型保存/加载/删除数据块
- 将保存的数据块套用到当前订单数据
"""

from __future__ import annotations

import logging
from typing import Any

from src.db.template_block_repository import TemplateBlockRepository

logger = logging.getLogger(__name__)

# 各 block_type 对应的数据字段集合
# order_full 为整单模板，不限定字段范围（空集合表示"不限制"）
BLOCK_FIELDS_MAP: dict[str, set[str]] = {
    "customer": {
        "company_name_en",
        "company_name_cn",
        "country",
        "address",
        "contact_person",
        "phone",
        "mobile",
        "destination",
    },
    "shipping": {
        "export_port",
        "package_type",
        "transport_mode",
        "vessel_flight",
        "bill_of_lading_no",
        "trade_term",
        "payment_term",
        "currency",
        "declaration_elements_template",
    },
    "product_set": {
        "pallets",
    },
    "order_full": set(),
}


class TemplateBlockService:
    """模板块业务服务.

    对 TemplateBlockRepository 的封装，增加字段级别的套用逻辑。

    Usage:
        service = TemplateBlockService()
        service.save_block("customer", "美国客户A", customer_data, "常客")
        blocks = service.load_blocks("customer")
        service.apply_block(block_id, current_order_data, {"company_name_en", "country"})
    """

    # ==================== 保存 / 加载 / 删除 ====================

    @staticmethod
    def save_block(
        block_type: str,
        block_name: str,
        data: dict[str, Any],
        description: str = "",
    ) -> int:
        """保存一个数据块.

        Args:
            block_type: 块类型.
            block_name: 块名称.
            data: 数据字典.
            description: 备注.

        Returns:
            新块的 ID.
        """
        return TemplateBlockRepository.save(block_type, block_name, data, description)

    @staticmethod
    def load_blocks(block_type: str) -> list[dict[str, Any]]:
        """按类型列出所有数据块.

        Args:
            block_type: 块类型.

        Returns:
            块元信息列表.
        """
        return TemplateBlockRepository.list_by_type(block_type)

    @staticmethod
    def delete_block(block_id: int) -> bool:
        """软删除数据块.

        Args:
            block_id: 块 ID.

        Returns:
            是否删除成功.
        """
        return TemplateBlockRepository.delete(block_id)

    @staticmethod
    def get_block(block_id: int) -> dict[str, Any] | None:
        """获取单个数据块的完整信息（含数据）.

        Args:
            block_id: 块 ID.

        Returns:
            块完整信息，不存在时返回 None.
        """
        return TemplateBlockRepository.load(block_id)

    # ==================== 套用模板 ====================

    @staticmethod
    def apply_block(
        block: dict[str, Any],
        target_data: dict[str, Any],
        fields: set[str] | None = None,
    ) -> dict[str, Any]:
        """将保存的数据块套用到目标订单数据.

        注意：不会修改传入的 target_data，返回新字典。

        Args:
            block: 从 get_block() 获取的块数据.
            target_data: 当前订单数据字典（collect_data() 的格式）.
            fields: 要套用的字段集合，None 表示套用全部字段.

        Returns:
            套用后的新数据字典.
        """
        import copy

        result: dict[str, Any] = copy.deepcopy(target_data)
        block_data: dict[str, Any] = block.get("block_data", {})
        block_type: str = block.get("block_type", "")

        if not block_data:
            return result

        # 确定可套用的字段集
        allowed: set[str] = BLOCK_FIELDS_MAP.get(block_type, set())
        if fields is not None:
            allowed = allowed & fields if allowed else fields

        if block_type == "customer":
            if "customer" not in result:
                result["customer"] = {}
            for k, v in block_data.items():
                if not allowed or k in allowed:
                    result["customer"][k] = v

        elif block_type == "shipping":
            if "order_meta" not in result:
                result["order_meta"] = {}
            if "origin" not in result:
                result["origin"] = {}
            for k, v in block_data.items():
                if not allowed or k in allowed:
                    # 运输相关字段放入 order_meta
                    if k in {
                        "transport_mode",
                        "vessel_flight",
                        "bill_of_lading_no",
                        "trade_term",
                        "payment_term",
                        "currency",
                        "declaration_elements_template",
                        "package_type",
                    }:
                        result["order_meta"][k] = v
                    # 发货相关字段放入 origin
                    elif k in {"export_port"}:
                        result["origin"][k] = v

        elif block_type == "order_full":
            if fields is None:
                # 整单覆盖
                for section in ("order_meta", "customer", "origin", "shipping"):
                    if section in block_data:
                        if section not in result:
                            result[section] = {}
                        result[section].update(block_data[section])
            else:
                # 按字段选择性套用
                section_map: dict[str, str] = {
                    "invoice_no": "order_meta",
                    "contract_no": "order_meta",
                    "date": "order_meta",
                    "order_no": "order_meta",
                    "transport_mode": "order_meta",
                    "vessel_flight": "order_meta",
                    "bill_of_lading_no": "order_meta",
                    "trade_term": "order_meta",
                    "payment_term": "order_meta",
                    "currency": "order_meta",
                    "country_of_origin": "order_meta",
                    "goods_summary": "order_meta",
                    "declaration_elements_template": "order_meta",
                    "package_type": "order_meta",
                    "company_name_en": "customer",
                    "company_name_cn": "customer",
                    "country": "customer",
                    "address": "customer",
                    "contact_person": "customer",
                    "phone": "customer",
                    "mobile": "customer",
                    "destination": "customer",
                    "export_port": "origin",
                    "domestic_source": "origin",
                    "manufacturer": "origin",
                    "business_entity": "origin",
                    "trade_mode": "origin",
                    "tax_nature": "origin",
                    "settlement_method": "origin",
                    "tax_rebate": "origin",
                }
                for field in fields:
                    section = section_map.get(field)
                    if section is None:
                        continue
                    if section not in result:
                        result[section] = {}
                    # 从 order_meta / customer / origin 中查找
                    for src_section in ("order_meta", "customer", "origin"):
                        if field in block_data.get(src_section, {}):
                            result[section][field] = block_data[src_section][field]
                            break

        return result

    @staticmethod
    def get_block_type_label(block_type: str) -> str:
        """获取块类型的中文标签.

        Args:
            block_type: 块类型代码.

        Returns:
            中文标签.
        """
        labels: dict[str, str] = {
            "customer": "客户信息",
            "product_set": "商品信息",
            "shipping": "运输与发货信息",
            "order_full": "整单模板",
        }
        return labels.get(block_type, block_type)
