# -*- coding: utf-8 -*-
"""Excel 列名映射表 — 从 excel_importer.py 拆分.

提供中文/英文列名到 SSOT 字段标识的自动映射。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# 中文/英文列名 → OrderData 字段路径
# 键：Excel 中可能出现的列名（大小写不敏感）
# 值：对应的 SSOT 字段标识
_COLUMN_MAPPING: dict[str, str] = {
    # 订单元信息
    "发票号": "invoice_no",
    "invoice_no": "invoice_no",
    "invoice": "invoice_no",
    "合同号": "contract_no",
    "contract_no": "contract_no",
    "contract": "contract_no",
    "订单号": "order_no",
    "order_no": "order_no",
    "日期": "date",
    "date": "date",
    "运输方式": "transport_mode",
    "transport_mode": "transport_mode",
    "transport": "transport_mode",
    "船名航次": "vessel_flight",
    "vessel_flight": "vessel_flight",
    "提单号": "bill_of_lading_no",
    "bill_of_lading_no": "bill_of_lading_no",
    "贸易条款": "trade_term",
    "trade_term": "trade_term",
    "付款方式": "payment_term",
    "payment_term": "payment_term",
    "payment": "payment_term",
    "币种": "currency",
    "currency": "currency",
    "包装类型": "package_type",
    "package_type": "package_type",
    "原产国": "country_of_origin",
    "country_of_origin": "country_of_origin",
    "货品名称": "goods_summary",
    "goods_summary": "goods_summary",
    "goods": "goods_summary",
    # 客户信息
    "客户": "company_name_en",
    "客户名称": "company_name_en",
    "customer": "company_name_en",
    "company_name_en": "company_name_en",
    "客户中文名": "company_name_cn",
    "company_name_cn": "company_name_cn",
    "客户地址": "address",
    "address": "address",
    "联系人": "contact_person",
    "contact_person": "contact_person",
    "contact": "contact_person",
    "电话": "phone",
    "phone": "phone",
    "手机号": "mobile",
    "mobile": "mobile",
    "国家": "country",
    "country": "country",
    "目的地": "destination",
    "destination": "destination",
    "卸货港": "destination",
    # 境内信息
    "装运港": "export_port",
    "export_port": "export_port",
    "境内货源地": "domestic_source",
    "domestic_source": "domestic_source",
    "生产厂家": "manufacturer",
    "manufacturer": "manufacturer",
    "经营单位": "business_entity",
    "business_entity": "business_entity",
    "贸易方式": "trade_mode",
    "trade_mode": "trade_mode",
    "征免性质": "tax_nature",
    "tax_nature": "tax_nature",
    "结汇方式": "settlement_method",
    "settlement_method": "settlement_method",
    "退税": "tax_rebate",
    "tax_rebate": "tax_rebate",
    # 商品明细列
    "序号": "seq_no",
    "seq_no": "seq_no",
    "商品名称": "product_name",
    "product_name": "product_name",
    "product": "product_name",
    "品名": "product_name",
    "规格": "specification",
    "specification": "specification",
    "型号": "specification",
    "hs编码": "hs_code",
    "hs_code": "hs_code",
    "hs": "hs_code",
    "申报要素": "declaration_elements",
    "declaration_elements": "declaration_elements",
    "单位": "unit",
    "unit": "unit",
    "计量单位": "unit",
    "数量": "qty_per_carton",
    "qty_per_carton": "qty_per_carton",
    "qty": "qty_per_carton",
    "单价": "unit_price",
    "unit_price": "unit_price",
    "price": "unit_price",
    "净重": "net_weight_per_unit_kg",
    "net_weight_per_unit_kg": "net_weight_per_unit_kg",
    "单件净重": "net_weight_per_unit_kg",
    "nw": "net_weight_per_unit_kg",
    "目的国": "destination_country",
    "destination_country": "destination_country",
    # 托盘/纸箱列
    "托盘号": "pallet_no",
    "pallet_no": "pallet_no",
    "pallet": "pallet_no",
    "纸箱标签": "carton_label",
    "carton_label": "carton_label",
    "箱号": "carton_label",
    "箱数": "batch_count",
    "batch_count": "batch_count",
    "carton_qty": "batch_count",
    "是否批量": "is_batch",
    "is_batch": "is_batch",
    "batch": "is_batch",
    "纸箱长度": "length_cm",
    "length_cm": "length_cm",
    "纸箱宽度": "width_cm",
    "width_cm": "width_cm",
    "纸箱高度": "height_cm",
    "height_cm": "height_cm",
    "纸箱毛重": "gross_weight_kg",
    "gross_weight_kg": "gross_weight_kg",
    "gw": "gross_weight_kg",
    "托盘长度": "length_m",
    "length_m": "length_m",
    "托盘宽度": "width_m",
    "width_m": "width_m",
    "托盘高度": "height_m",
    "height_m": "height_m",
    "托盘自重": "pallet_weight_kg",
    "pallet_weight_kg": "pallet_weight_kg",
}

# 有效的贸易条款集合
_VALID_TRADE_TERMS: set[str] = {"FOB", "CIF", "CFR", "EXW", "DDP", "DAP"}

# 明细级字段（与订单级字段区分，由 detail_parser 处理）
DETAIL_FIELDS: set[str] = {
    "pallet_no", "length_m", "width_m", "height_m", "pallet_weight_kg",
    "carton_label", "length_cm", "width_cm", "height_cm", "gross_weight_kg",
    "is_batch", "batch_count",
    "seq_no", "product_name", "specification", "hs_code", "declaration_elements",
    "unit", "qty_per_carton", "unit_price", "net_weight_per_unit_kg",
    "destination_country", "currency",
}


def normalize_column_name(name: str | None) -> str:
    """标准化列名：去空格、转小写.

    Args:
        name: 原始列名.

    Returns:
        标准化后的列名.
    """
    if name is None:
        return ""
    return str(name).strip().lower()


def map_column_name(excel_col_name: str) -> tuple[str | None, bool]:
    """将 Excel 列名映射到 SSOT 字段标识.

    Args:
        excel_col_name: Excel 中的列名.

    Returns:
        (ssot_field, is_recognized) 元组.
        is_recognized=False 表示该列名无法映射，需标注 TODO.
    """
    key = normalize_column_name(excel_col_name)
    ssot_field = _COLUMN_MAPPING.get(key)
    if ssot_field is not None:
        return ssot_field, True
    return key, False  # 返回原始 key 供 TODO 标注


def normalize_trade_term(raw: str) -> str:
    """标准化贸易条款.

    Args:
        raw: 原始贸易条款字符串.

    Returns:
        标准化的 TradeTerm.

    Raises:
        ValueError: 无法识别的贸易条款.
    """
    upper = str(raw).strip().upper()
    if upper in _VALID_TRADE_TERMS:
        return upper
    # 尝试模糊匹配
    for valid in _VALID_TRADE_TERMS:
        if valid in upper:
            return valid
    logger.warning("无法识别的贸易条款: %s，默认使用 FOB", raw)
    return "FOB"
