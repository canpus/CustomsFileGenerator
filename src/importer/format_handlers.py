"""Excel 导入 — 格式处理器.

包含键值对格式和明细行格式的解析函数。
"""

from __future__ import annotations

import logging
from typing import Any, cast

from config.constants import TradeTerm, TransportModeCN
from src.importer.column_mapper import (
    DETAIL_FIELDS,
    map_column_name,
    normalize_trade_term,
)
from src.importer.detail_parser import (
    compute_totals,
    parse_detail_sheet,
    safe_str,
)
from src.models.order_data import Customer, OrderData, OrderMeta, Origin, PackageType

logger = logging.getLogger(__name__)


def _is_kv_format(ws) -> bool:
    """判断是否为键值对格式（第一列为标签，第二列为值）.

    检测策略：
    - 如果表头行（第1行）有超过 8 个非空列，则判定为明细行格式
    - 如果前两行中 A 列为字段标签且 B 列为对应值，则为 KV 格式
    - 否则默认为明细行格式
    """
    if ws.max_row < 2:
        return False

    non_empty_cols_row1 = sum(
        1
        for col_idx in range(1, ws.max_column + 1)
        if ws.cell(row=1, column=col_idx).value is not None
        and str(ws.cell(row=1, column=col_idx).value).strip()
    )
    if non_empty_cols_row1 > 8:
        return False

    detail_keywords = {
        "序号",
        "商品名称",
        "产品名称",
        "托盘号",
        "纸箱",
        "箱号",
        "重量",
        "体积",
        "单价",
        "数量",
        "净重",
        "毛重",
        "规格",
        "HS",
    }

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
            detail_count += 1

    if detail_count >= 2:
        return False

    return kv_count >= 3


def _import_kv_format(wb, unmapped: dict[str, list[str]]) -> tuple[OrderData, dict[str, list[str]]]:
    """双 Sheet 格式导入：订单信息 Sheet + 商品明细 Sheet."""
    ws_info = wb[wb.sheetnames[0]]
    raw_info: dict[str, str] = {}

    for row_idx in range(1, ws_info.max_row + 1):
        key = safe_str(ws_info.cell(row=row_idx, column=1).value)
        value = safe_str(ws_info.cell(row=row_idx, column=2).value)
        if key and value:
            raw_info[key] = value

    order_info: dict[str, str] = {}
    for excel_col, value in raw_info.items():
        ssot_field, recognized = map_column_name(excel_col)
        if recognized and ssot_field is not None:
            order_info[ssot_field] = value
        else:
            sheet_key = f"Sheet1:{excel_col}"
            unmapped.setdefault(sheet_key, []).append(excel_col)
            logger.warning("TODO:待确认 — 无法映射的列: %s = %s", excel_col, value)

    order_meta = OrderMeta(
        invoice_no=order_info.get("invoice_no", ""),
        contract_no=order_info.get("contract_no", ""),
        date=order_info.get("date", ""),
        trade_term=TradeTerm(normalize_trade_term(order_info.get("trade_term", "FOB"))),
        payment_term=order_info.get("payment_term", ""),
        country_of_origin=order_info.get("country_of_origin", "China"),
        order_no=order_info.get("order_no", ""),
        transport_mode=TransportModeCN(order_info.get("transport_mode", "海运")),
        vessel_flight=order_info.get("vessel_flight", ""),
        bill_of_lading_no=order_info.get("bill_of_lading_no", ""),
        currency=order_info.get("currency", "USD"),
        package_type=cast(PackageType, order_info.get("package_type", "pallet")),
        goods_summary=order_info.get("goods_summary", ""),
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

    if len(wb.sheetnames) < 2:
        raise ValueError(
            "[错误]: 键值对格式需要第二个工作表（商品明细）\n"
            "[原因]: 当前 Excel 仅包含订单信息 Sheet，缺少商品明细\n"
            "[排查]: 请在同一个 Excel 文件中添加第二个工作表，包含托盘-纸箱-商品明细"
        )

    ws_detail = wb[wb.sheetnames[1]]
    pallets, unmapped_detail = parse_detail_sheet(ws_detail)
    for k, v in unmapped_detail.items():
        unmapped.setdefault(k, []).extend(v)

    totals = compute_totals(pallets)

    order = OrderData(
        order_meta=order_meta,
        customer=customer,
        pallets=pallets,
        totals=totals,
        origin=origin,
    )

    wb.close()
    return order, unmapped


def _import_detail_format(
    ws, unmapped: dict[str, list[str]]
) -> tuple[OrderData, dict[str, list[str]]]:
    """单 Sheet 格式导入：所有数据在一个 Sheet 内."""
    pallets, unmapped_detail = parse_detail_sheet(ws)

    all_headers: list[tuple[str | None, bool, int]] = []
    for col_idx in range(1, ws.max_column + 1):
        header_val = safe_str(ws.cell(row=1, column=col_idx).value)
        if header_val:
            ssot_field, recognized = map_column_name(header_val)
            all_headers.append((ssot_field, recognized, col_idx))
        else:
            all_headers.append((None, False, col_idx))

    order_info: dict[str, Any] = {}
    for ssot_field, recognized, col_idx in all_headers:
        if not recognized or ssot_field is None:
            continue
        if ssot_field in DETAIL_FIELDS:
            continue
        cell_val = safe_str(ws.cell(row=2, column=col_idx).value)
        if cell_val:
            order_info[ssot_field] = cell_val

    order_meta = OrderMeta(
        invoice_no=order_info.get("invoice_no", "IMPORTED"),
        contract_no=order_info.get("contract_no", ""),
        date=order_info.get("date", ""),
        trade_term=TradeTerm(normalize_trade_term(order_info.get("trade_term", "FOB"))),
        payment_term=order_info.get("payment_term", ""),
        country_of_origin=order_info.get("country_of_origin", "China"),
        order_no=order_info.get("order_no", ""),
        transport_mode=TransportModeCN(order_info.get("transport_mode", "海运")),
        vessel_flight=order_info.get("vessel_flight", ""),
        bill_of_lading_no=order_info.get("bill_of_lading_no", ""),
        currency=order_info.get("currency", "USD"),
        package_type=cast(PackageType, order_info.get("package_type", "pallet")),
        goods_summary=order_info.get("goods_summary", ""),
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

    totals = compute_totals(pallets)

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
