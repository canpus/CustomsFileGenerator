# -*- coding: utf-8 -*-
"""Excel 订单数据导入器 — 阶段 8.1.

读取用户上传的订单 Excel 表格，通过列名匹配自动映射到 SSOT 字段，
自动计算托盘体积、汇总总毛重/总净重/总体积/总金额，输出完整的 OrderData 对象。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import openpyxl

from src.models.order_data import (
    Carton,
    Customer,
    OrderData,
    OrderMeta,
    Origin,
    Pallet,
    Product,
    Totals,
    TradeTerm,
)

logger = logging.getLogger(__name__)

# ==================== 列名映射表 ====================

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


def _normalize_column_name(name: str) -> str:
    """标准化列名：去空格、转小写.

    Args:
        name: 原始列名.

    Returns:
        标准化后的列名.
    """
    if name is None:
        return ""
    return str(name).strip().lower()


def _map_column_name(excel_col_name: str) -> tuple[str | None, bool]:
    """将 Excel 列名映射到 SSOT 字段标识.

    Args:
        excel_col_name: Excel 中的列名.

    Returns:
        (ssot_field, is_recognized) 元组.
        is_recognized=False 表示该列名无法映射，需标注 TODO.
    """
    key = _normalize_column_name(excel_col_name)
    ssot_field = _COLUMN_MAPPING.get(key)
    if ssot_field is not None:
        return ssot_field, True
    return key, False  # 返回原始 key 供 TODO 标注


# ==================== TradeTerm 标准化 ====================

_VALID_TRADE_TERMS: set[str] = {"FOB", "CIF", "CFR", "EXW", "DDP", "DAP"}


def _normalize_trade_term(raw: str) -> TradeTerm:
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
        return upper  # type: ignore[return-value]
    # 尝试模糊匹配
    for valid in _VALID_TRADE_TERMS:
        if valid in upper:
            return valid  # type: ignore[return-value]
    logger.warning("无法识别的贸易条款: %s，默认使用 FOB", raw)
    return "FOB"


# ==================== 数据提取辅助函数 ====================


def _safe_str(value: Any) -> str:
    """安全转换为字符串."""
    if value is None:
        return ""
    return str(value).strip()


def _safe_float(value: Any) -> float:
    """安全转换为浮点数."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _safe_int(value: Any) -> int:
    """安全转换为整数."""
    if value is None:
        return 0
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
        return 0


def _safe_bool(value: Any) -> bool:
    """安全转换为布尔值."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    return s in ("true", "yes", "1", "是", "y")


def _extract_field(row: dict[str, str], ssot_field: str, default: Any = "") -> Any:
    """从行数据中提取指定字段值.

    Args:
        row: 行数据字典（列名→值）.
        ssot_field: SSOT 字段标识.
        default: 默认值.

    Returns:
        提取的值.
    """
    return row.get(ssot_field, default)


# ==================== 主导入函数 ====================


def import_order_from_excel(
    excel_path: str | Path,
    sheet_name: str | None = None,
) -> tuple[OrderData, dict[str, list[str]]]:
    """从 Excel 表格导入订单数据并生成 OrderData.

    自动识别列名、映射字段、计算汇总数据。

    支持两种 Excel 格式：
        A. 双 Sheet 格式：
            - Sheet1 "订单信息"：订单元信息 + 客户信息（键值对形式）
            - Sheet2 "商品明细"：托盘-纸箱-商品明细行
        B. 单 Sheet 格式（推荐）：
            - 表头行含所有列名，每行是一条商品-纸箱-托盘记录

    Args:
        excel_path: Excel 文件路径.
        sheet_name: 指定工作表名称，默认使用第一个 Sheet.

    Returns:
        (OrderData, unmapped_columns) 元组。
        unmapped_columns: 无法自动映射的列名及其所在 Sheet，用于 TODO 标注.

    Raises:
        FileNotFoundError: Excel 文件不存在.
        ValueError: 数据格式不正确无法解析.
    """
    excel_path = Path(excel_path)
    if not excel_path.exists():
        raise FileNotFoundError(
            f"[错误]: Excel 文件不存在: {excel_path}\n"
            f"[原因]: 文件可能被移动、删除或路径拼写错误\n"
            f"[排查]: 请检查文件路径是否正确"
        )

    print(f"正在读取 Excel 文件: {excel_path.name}")
    unmapped: dict[str, list[str]] = {}

    try:
        wb = openpyxl.load_workbook(excel_path, data_only=True)
    except Exception as e:
        raise ValueError(
            f"[错误]: 无法打开 Excel 文件: {excel_path}\n"
            f"[原因]: 文件可能已损坏或格式不受支持\n"
            f"[排查]: 请确认文件为 .xlsx 格式，且未被其他程序独占打开\n"
            f"        原始错误: {e}"
        ) from e

    # 选择 Sheet
    if sheet_name:
        if sheet_name not in wb.sheetnames:
            raise ValueError(
                f"[错误]: 工作表 \"{sheet_name}\" 不存在\n"
                f"[原因]: 可用的工作表: {', '.join(wb.sheetnames)}\n"
                f"[排查]: 请指定正确的工作表名称"
            )
        ws = wb[sheet_name]
    else:
        ws = wb[wb.sheetnames[0]]

    print(f"  使用工作表: {ws.title} ({ws.max_row} 行 x {ws.max_column} 列)")

    # 自动判断格式
    if _is_kv_format(ws):
        print("  检测到键值对格式（订单信息 Sheet）")
        return _import_kv_format(wb, unmapped)
    else:
        print("  检测到明细行格式")
        return _import_detail_format(ws, unmapped)


def _is_kv_format(ws) -> bool:
    """判断是否为键值对格式（第一列为标签，第二列为值）.

    检测策略：
    - 如果表头行（第1行）有超过 8 个非空列，则判定为明细行格式（多列数据表）
    - 如果前两行中 A 列为字段标签且 B 列为对应值，则为 KV 格式
    - 否则默认为明细行格式
    """
    if ws.max_row < 2:
        return False

    # 规则 1: 如果第一行有超过 8 个非空单元格 → 明细行格式
    non_empty_cols_row1 = sum(
        1 for col_idx in range(1, ws.max_column + 1)
        if ws.cell(row=1, column=col_idx).value is not None
        and str(ws.cell(row=1, column=col_idx).value).strip()
    )
    if non_empty_cols_row1 > 8:
        return False

    # 规则 2: 检查前 5 行是否每行都像 KV 对（A 列=标签，B 列=值）
    detail_keywords = {"序号", "商品名称", "产品名称", "托盘号", "纸箱", "箱号",
                       "重量", "体积", "单价", "数量", "净重", "毛重", "规格", "HS"}

    kv_count = 0
    detail_count = 0
    for row_idx in range(1, min(ws.max_row + 1, 6)):
        col_a = str(ws.cell(row=row_idx, column=1).value or "").strip()
        col_b = str(ws.cell(row=row_idx, column=2).value or "").strip()

        if col_a and col_b:
            if any(kw in col_a for kw in detail_keywords):
                detail_count += 1
            else:
                kv_count += 1
        elif not col_a and col_b:
            # A 列为空但 B 列有值 → 不是 KV 格式
            detail_count += 1

    # 如果有商品明细关键词，判定为明细行格式
    if detail_count >= 2:
        return False

    return kv_count >= 3


def _import_kv_format(wb, unmapped: dict[str, list[str]]) -> tuple[OrderData, dict[str, list[str]]]:
    """双 Sheet 格式导入：订单信息 Sheet + 商品明细 Sheet."""
    # 读取订单信息 Sheet
    ws_info = wb[wb.sheetnames[0]]
    raw_info: dict[str, str] = {}

    for row_idx in range(1, ws_info.max_row + 1):
        key = _safe_str(ws_info.cell(row=row_idx, column=1).value)
        value = _safe_str(ws_info.cell(row=row_idx, column=2).value)
        if key and value:
            raw_info[key] = value

    # 映射订单信息
    order_info: dict[str, str] = {}
    for excel_col, value in raw_info.items():
        ssot_field, recognized = _map_column_name(excel_col)
        if recognized:
            order_info[ssot_field] = value
        else:
            sheet_key = f"Sheet1:{excel_col}"
            unmapped.setdefault(sheet_key, []).append(excel_col)
            logger.warning("TODO:待确认 — 无法映射的列: %s = %s", excel_col, value)

    # 构造 OrderMeta
    order_meta = OrderMeta(
        invoice_no=order_info.get("invoice_no", ""),
        contract_no=order_info.get("contract_no", ""),
        date=order_info.get("date", ""),
        trade_term=_normalize_trade_term(order_info.get("trade_term", "FOB")),
        payment_term=order_info.get("payment_term", ""),
        country_of_origin=order_info.get("country_of_origin", "China"),
        order_no=order_info.get("order_no", ""),
        transport_mode=order_info.get("transport_mode", "海运"),
        vessel_flight=order_info.get("vessel_flight", ""),
        bill_of_lading_no=order_info.get("bill_of_lading_no", ""),
        currency=order_info.get("currency", "USD"),
        package_type=order_info.get("package_type", "pallet"),
        goods_summary=order_info.get("goods_summary", ""),
    )

    # 构造 Customer
    customer = Customer(
        company_name_en=order_info.get("company_name_en", ""),
        country=order_info.get("country", ""),
        company_name_cn=order_info.get("company_name_cn", ""),
        address=order_info.get("address", ""),
        contact_person=order_info.get("contact_person", ""),
        phone=order_info.get("phone", ""),
        mobile=order_info.get("mobile", ""),
        destination=order_info.get("destination", ""),
    )

    # 构造 Origin
    origin = Origin(
        export_port=order_info.get("export_port", ""),
        domestic_source=order_info.get("domestic_source", "深圳特区"),
        manufacturer=order_info.get("manufacturer", "长园长通新材料股份有限公司"),
        business_entity=order_info.get("business_entity", "长园长通新材料股份有限公司"),
        trade_mode=order_info.get("trade_mode", "一般贸易"),
        tax_nature=order_info.get("tax_nature", "一般征税"),
        settlement_method=order_info.get("settlement_method", "电汇"),
        tax_rebate=order_info.get("tax_rebate", "申请退税"),
    )

    # 读取商品明细 Sheet
    if len(wb.sheetnames) < 2:
        raise ValueError(
            "[错误]: 键值对格式需要第二个工作表（商品明细）\n"
            "[原因]: 当前 Excel 仅包含订单信息 Sheet，缺少商品明细\n"
            "[排查]: 请在同一个 Excel 文件中添加第二个工作表，包含托盘-纸箱-商品明细"
        )

    ws_detail = wb[wb.sheetnames[1]]
    pallets, unmapped_detail = _parse_detail_sheet(ws_detail)
    for k, v in unmapped_detail.items():
        unmapped.setdefault(k, []).extend(v)

    # 自动计算汇总
    totals = _compute_totals(pallets)

    order = OrderData(
        order_meta=order_meta,
        customer=customer,
        pallets=pallets,
        totals=totals,
        origin=origin,
    )

    wb.close()
    return order, unmapped


def _import_detail_format(ws, unmapped: dict[str, list[str]]) -> tuple[OrderData, dict[str, list[str]]]:
    """单 Sheet 格式导入：所有数据在一个 Sheet 内."""
    pallets, unmapped_detail = _parse_detail_sheet(ws)

    # 从表头解析：读取第一行各列，映射到的 ssot_field
    # 然后区分 order 级字段和 detail 级字段
    # order 级字段 = 每行值相同（如发票号、客户名等），从第一数据行取值
    # detail 级字段 = 每行值不同（商品名、数量等），在 _parse_detail_sheet 中处理

    # 从第一行提取所有列头映射
    all_headers: list[tuple[str | None, bool, int]] = []
    for col_idx in range(1, ws.max_column + 1):
        header_val = _safe_str(ws.cell(row=1, column=col_idx).value)
        if header_val:
            ssot_field, recognized = _map_column_name(header_val)
            all_headers.append((ssot_field, recognized, col_idx))
        else:
            all_headers.append((None, False, col_idx))

    # detail 级字段（与 _parse_detail_sheet 使用的相同）
    detail_fields = {
        "pallet_no", "length_m", "width_m", "height_m", "pallet_weight_kg",
        "carton_label", "length_cm", "width_cm", "height_cm", "gross_weight_kg",
        "is_batch", "batch_count",
        "seq_no", "product_name", "specification", "hs_code", "declaration_elements",
        "unit", "qty_per_carton", "unit_price", "net_weight_per_unit_kg",
        "destination_country", "currency",
    }

    # 从第一数据行提取 order 级字段
    order_info: dict[str, Any] = {}
    for ssot_field, recognized, col_idx in all_headers:
        if not recognized or ssot_field is None:
            continue
        if ssot_field in detail_fields:
            continue  # detail 字段由 _parse_detail_sheet 处理
        cell_val = _safe_str(ws.cell(row=2, column=col_idx).value)
        if cell_val:
            order_info[ssot_field] = cell_val

    order_meta = OrderMeta(
        invoice_no=order_info.get("invoice_no", "IMPORTED"),
        contract_no=order_info.get("contract_no", ""),
        date=order_info.get("date", ""),
        trade_term=_normalize_trade_term(order_info.get("trade_term", "FOB")),
        payment_term=order_info.get("payment_term", ""),
        country_of_origin=order_info.get("country_of_origin", "China"),
    )

    customer = Customer(
        company_name_en=order_info.get("company_name_en", ""),
        country=order_info.get("country", ""),
        company_name_cn=order_info.get("company_name_cn", ""),
        address=order_info.get("address", ""),
        contact_person=order_info.get("contact_person", ""),
        phone=order_info.get("phone", ""),
        mobile=order_info.get("mobile", ""),
        destination=order_info.get("destination", ""),
    )

    # 构造 Origin
    origin = Origin(
        export_port=order_info.get("export_port", ""),
        domestic_source=order_info.get("domestic_source", "深圳特区"),
        manufacturer=order_info.get("manufacturer", "长园长通新材料股份有限公司"),
        business_entity=order_info.get("business_entity", "长园长通新材料股份有限公司"),
        trade_mode=order_info.get("trade_mode", "一般贸易"),
        tax_nature=order_info.get("tax_nature", "一般征税"),
        settlement_method=order_info.get("settlement_method", "电汇"),
        tax_rebate=order_info.get("tax_rebate", "申请退税"),
    )

    totals = _compute_totals(pallets)

    order = OrderData(
        order_meta=order_meta,
        customer=customer,
        pallets=pallets,
        totals=totals,
        origin=origin,
    )

    for k, v in unmapped_detail.items():
        unmapped.setdefault(k, []).extend(v)

    return order, unmapped


def _parse_detail_sheet(ws) -> tuple[list[Pallet], dict[str, list[str]]]:
    """解析明细工作表：提取列头 → 逐行读取 → 按托盘分组.

    Args:
        ws: openpyxl 工作表.

    Returns:
        (pallets, unmapped) 元组.
    """
    unmapped: dict[str, list[str]] = {}

    # 读取表头行（第 1 行）
    headers: list[tuple[str | None, bool, str]] = []  # (ssot_field, recognized, original_name)
    for col_idx in range(1, ws.max_column + 1):
        header_val = _safe_str(ws.cell(row=1, column=col_idx).value)
        if header_val:
            ssot_field, recognized = _map_column_name(header_val)
            headers.append((ssot_field, recognized, header_val))
        else:
            headers.append((None, False, ""))

    if not any(h[0] for h in headers):
        raise ValueError(
            "[错误]: 无法识别 Excel 表头\n"
            "[原因]: 第一行未找到可映射的列名\n"
            "[排查]: 请确保第一行为表头行，包含如\"产品名称\"、\"HS编码\"等列名"
        )

    # 记录无法识别的列
    for ssot_field, recognized, original_name in headers:
        if not recognized and ssot_field and original_name:
            unmapped.setdefault(f"列:{original_name}", []).append(original_name)

    # 逐行读取数据
    rows: list[dict[str, Any]] = []
    for row_idx in range(2, ws.max_row + 1):
        row_data: dict[str, Any] = {}
        all_empty = True
        for col_idx, (ssot_field, recognized, original_name) in enumerate(headers, start=1):
            if ssot_field is None:
                continue
            cell_val = ws.cell(row=row_idx, column=col_idx).value
            if cell_val is not None and str(cell_val).strip():
                all_empty = False
            row_data[ssot_field] = cell_val
        if not all_empty:
            rows.append(row_data)

    if not rows:
        raise ValueError(
            "[错误]: 未找到任何数据行\n"
            "[原因]: Excel 只有表头行，没有商品明细数据\n"
            "[排查]: 请确认 Excel 中至少包含一行商品明细数据"
        )

    # 按托盘号分组
    pallet_groups: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        p_no = _safe_int(_extract_field(row, "pallet_no"))
        if p_no <= 0:
            p_no = 1  # 默认托盘 1
        pallet_groups.setdefault(p_no, []).append(row)

    # 构造 Pallet 列表
    pallets: list[Pallet] = []
    for p_no in sorted(pallet_groups.keys()):
        group = pallet_groups[p_no]
        cartons = _build_cartons_from_rows(group)
        if not cartons:
            continue

        # 从第一行获取托盘尺寸
        first = group[0]
        length_m = _safe_float(_extract_field(first, "length_m"))
        width_m = _safe_float(_extract_field(first, "width_m"))
        height_m = _safe_float(_extract_field(first, "height_m"))
        pallet_weight = _safe_float(_extract_field(first, "pallet_weight_kg"))

        if length_m <= 0 or width_m <= 0 or height_m <= 0:
            # 自动从纸箱尺寸推算（不精确但兜底）
            length_m = 1.16
            width_m = 1.01
            height_m = 2.0
            logger.warning("托盘 %d 尺寸未提供/为零，使用默认值 %s×%s×%s", p_no, length_m, width_m, height_m)

        pallets.append(
            Pallet(
                pallet_no=p_no,
                length_m=length_m,
                width_m=width_m,
                height_m=height_m,
                pallet_weight_kg=pallet_weight,
                cartons=cartons,
            )
        )

    return pallets, unmapped


def _build_cartons_from_rows(rows: list[dict[str, Any]]) -> list[Carton]:
    """从同一托盘的明细行构造 Carton 列表.

    支持两种数据格式：
    1. 每行 = 一个纸箱（含一种商品）
    2. 每行 = 一个纸箱分组（is_batch=True 时按 batch_count 展开）
    """
    cartons: list[Carton] = []

    # 按 carton_label 分组
    carton_groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        label = _safe_str(_extract_field(row, "carton_label"))
        if not label:
            label = "auto"
        carton_groups.setdefault(label, []).append(row)

    for label, group in carton_groups.items():
        products: list[Product] = []
        first_row = group[0]

        is_batch = _safe_bool(_extract_field(first_row, "is_batch"))
        batch_count = _safe_int(_extract_field(first_row, "batch_count", 1))
        length_cm = _safe_float(_extract_field(first_row, "length_cm", 32.0))
        width_cm = _safe_float(_extract_field(first_row, "width_cm", 32.0))
        height_cm = _safe_float(_extract_field(first_row, "height_cm", 34.0))
        gross_weight_kg = _safe_float(_extract_field(first_row, "gross_weight_kg"))

        # 填充商品
        seq_counter = 1
        for row in group:
            product_name = _safe_str(_extract_field(row, "product_name"))
            if not product_name:
                continue

            products.append(
                Product(
                    seq_no=_safe_int(_extract_field(row, "seq_no", seq_counter)),
                    product_name=product_name,
                    hs_code=_safe_str(_extract_field(row, "hs_code")),
                    unit=_safe_str(_extract_field(row, "unit", "Roll")),
                    qty_per_carton=_safe_float(_extract_field(row, "qty_per_carton", 1)),
                    unit_price=_safe_float(_extract_field(row, "unit_price")),
                    net_weight_per_unit_kg=_safe_float(_extract_field(row, "net_weight_per_unit_kg")),
                    destination_country=_safe_str(_extract_field(row, "destination_country", "Turkey")),
                    specification=_safe_str(_extract_field(row, "specification")),
                    declaration_elements=_safe_str(_extract_field(row, "declaration_elements")),
                    currency=_safe_str(_extract_field(row, "currency", "USD")),
                )
            )
            seq_counter += 1

        if not products:
            continue

        cartons.append(
            Carton(
                carton_label=label,
                is_batch=is_batch,
                batch_count=max(batch_count, 1),
                length_cm=length_cm,
                width_cm=width_cm,
                height_cm=height_cm,
                gross_weight_kg=gross_weight_kg,
                products=products,
            )
        )

    return cartons


def _compute_totals(pallets: list[Pallet]) -> Totals:
    """从托盘列表自动计算汇总数据.

    Args:
        pallets: 托盘列表.

    Returns:
        汇总 Totals 对象.
    """
    total_pallets = len(pallets)
    total_cartons = 0
    total_gross_weight_kg = 0.0
    total_net_weight_kg = 0.0
    total_volume_cbm = 0.0
    total_amount = 0.0

    for pallet in pallets:
        # 托盘体积 = 长×宽×高
        pallet_volume = pallet.length_m * pallet.width_m * pallet.height_m
        total_volume_cbm += pallet_volume

        for carton in pallet.cartons:
            # batch_count 始终表示纸箱数量（is_batch=True 时表示同规格批量，否则为单箱）
            carton_count = max(carton.batch_count, 1)
            total_cartons += carton_count
            total_gross_weight_kg += carton.gross_weight_kg * carton_count

            for product in carton.products:
                net_weight = product.net_weight_per_unit_kg * product.qty_per_carton * carton_count
                total_net_weight_kg += net_weight
                total_amount += product.unit_price * product.qty_per_carton * carton_count

    return Totals(
        total_pallets=total_pallets,
        total_cartons=total_cartons,
        total_gross_weight_kg=round(total_gross_weight_kg, 3),
        total_net_weight_kg=round(total_net_weight_kg, 3),
        total_volume_cbm=round(total_volume_cbm, 3),
        total_amount=round(total_amount, 2),
    )


# ==================== 便捷函数 ====================


def quick_import(excel_path: str | Path) -> OrderData:
    """快速导入 Excel 订单（忽略未映射列）.

    Args:
        excel_path: Excel 文件路径.

    Returns:
        OrderData 对象.

    Raises:
        FileNotFoundError: 文件不存在.
        ValueError: 数据格式错误.
    """
    order, unmapped = import_order_from_excel(excel_path)
    if unmapped:
        for sheet, cols in unmapped.items():
            logger.info(
                "TODO:待确认 — %s 中有 %d 个列无法自动映射: %s",
                sheet, len(cols), ", ".join(cols),
            )
    return order


# ==================== 独立运行测试 ====================

if __name__ == "__main__":
    """独立测试：验证带真实数据的导入."""
    print("=" * 50)
    print("Excel 订单导入器 — 自检")
    print("=" * 50)

    import tempfile

    # 创建测试用 Excel 文件
    test_excel = Path(tempfile.mkdtemp(prefix="test_import_")) / "test_order.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "订单明细"

    # 表头
    headers = [
        "发票号", "合同号", "日期", "贸易条款", "付款方式", "币种", "原产国",
        "客户", "客户地址", "国家", "联系人", "电话", "目的地",
        "托盘号", "托盘长度", "托盘宽度", "托盘高度",
        "纸箱标签", "纸箱长度", "纸箱宽度", "纸箱高度", "纸箱毛重", "箱数",
        "序号", "商品名称", "规格", "HS编码", "单位", "数量", "单价", "净重", "目的国",
    ]
    for col_idx, h in enumerate(headers, start=1):
        ws.cell(row=1, column=col_idx, value=h)

    # 数据行
    data_row = [
        "20251202-01", "PO25-018", "2025-12-26", "FOB", "100% T/T IN ADVANCE", "USD", "China",
        "YARIMKURE INSAAT LTD. STI.", "Mutlukent Mahallesi, Ankara 85 Sitesi",
        "Turkey", "MR. Z.AYHAN ACAR", "90-312-2363217", "Ankara",
        1, 1.16, 1.01, 1.97,
        "1-45", 32, 32, 34, 23.3, 45,
        1, "50℃ Type 2A-1 Heat Shrink Sleeve", "330mm*2.0mm*30M",
        "3926909090", "Roll", 1, 85, 22.3, "Turkey",
    ]
    for col_idx, val in enumerate(data_row, start=1):
        ws.cell(row=2, column=col_idx, value=val)

    wb.save(test_excel)
    wb.close()
    print(f"测试文件: {test_excel}")

    try:
        order, unmapped = import_order_from_excel(test_excel)

        print(f"\n[导入结果]:")
        print(f"  发票号: {order.order_meta.invoice_no}")
        print(f"  合同号: {order.order_meta.contract_no}")
        print(f"  客户: {order.customer.company_name_en}")
        print(f"  托盘数: {order.totals.total_pallets}")
        print(f"  纸箱数: {order.totals.total_cartons}")
        print(f"  总毛重: {order.totals.total_gross_weight_kg:.3f} kg")
        print(f"  总净重: {order.totals.total_net_weight_kg:.3f} kg")
        print(f"  总体积: {order.totals.total_volume_cbm:.3f} m³")
        print(f"  总金额: {order.totals.total_amount:.2f} USD")

        # 验证自动计算
        pallet = order.pallets[0]
        expected_volume = 1.16 * 1.01 * 1.97
        print(f"\n[自动计算验证]:")
        print(f"  托盘体积: {expected_volume:.3f} ≈ {order.totals.total_volume_cbm:.3f}")
        assert abs(order.totals.total_volume_cbm - expected_volume) < 0.01, "体积计算错误"

        if unmapped:
            print(f"\n[TODO:待确认 — 无法识别的列]:")
            for sheet, cols in unmapped.items():
                print(f"  {sheet}: {', '.join(cols)}")
        else:
            print(f"\n✅ 所有列均已成功映射")

        print("\n🚀 Excel 导入器自检通过")

    except Exception as e:
        print(f"\n[错误]: 导入测试失败: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # 清理测试文件
        try:
            test_excel.unlink()
            test_excel.parent.rmdir()
        except Exception:
            pass
