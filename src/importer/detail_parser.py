"""Excel 明细行解析器 — 从 excel_importer.py 拆分.

将解析出的明细行按托盘-纸箱-商品三级结构构建 Pallet 列表，
并自动计算汇总数据。
"""

from __future__ import annotations

import logging
from typing import Any

from src.importer.column_mapper import map_column_name
from src.models.order_data import (
    Carton,
    Pallet,
    Product,
    Totals,
)

logger = logging.getLogger(__name__)


def safe_str(value: Any) -> str:
    """安全转换为字符串."""
    if value is None:
        return ""
    return str(value).strip()


def safe_float(value: Any) -> float:
    """安全转换为浮点数."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def safe_int(value: Any) -> int:
    """安全转换为整数."""
    if value is None:
        return 0
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
        return 0


def safe_bool(value: Any) -> bool:
    """安全转换为布尔值."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    return s in ("true", "yes", "1", "是", "y")


def extract_field(row: dict[str, str], ssot_field: str, default: Any = "") -> Any:
    """从行数据中提取指定字段值.

    Args:
        row: 行数据字典（列名→值）.
        ssot_field: SSOT 字段标识.
        default: 默认值.

    Returns:
        提取的值.
    """
    return row.get(ssot_field, default)


def parse_detail_sheet(ws) -> tuple[list[Pallet], dict[str, list[str]]]:
    """解析明细工作表：提取列头 → 逐行读取 → 按托盘分组.

    Args:
        ws: openpyxl 工作表.

    Returns:
        (pallets, unmapped) 元组.

    Raises:
        ValueError: 无法识别表头或无数据行时抛出.
    """
    unmapped: dict[str, list[str]] = {}

    # 读取表头行（第 1 行）
    headers: list[tuple[str | None, bool, str]] = []  # (ssot_field, recognized, original_name)
    for col_idx in range(1, ws.max_column + 1):
        header_val = safe_str(ws.cell(row=1, column=col_idx).value)
        if header_val:
            ssot_field, recognized = map_column_name(header_val)
            headers.append((ssot_field, recognized, header_val))
        else:
            headers.append((None, False, ""))

    if not any(h[0] for h in headers):
        raise ValueError(
            "[错误]: 无法识别 Excel 表头\n"
            "[原因]: 第一行未找到可映射的列名\n"
            '[排查]: 请确保第一行为表头行，包含如"产品名称"、"HS编码"等列名'
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
        for col_idx, (ssot_field, _recognized, _original_name) in enumerate(headers, start=1):
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
        p_no = safe_int(extract_field(row, "pallet_no"))
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
        length_m = safe_float(extract_field(first, "length_m"))
        width_m = safe_float(extract_field(first, "width_m"))
        height_m = safe_float(extract_field(first, "height_m"))
        pallet_weight = safe_float(extract_field(first, "pallet_weight_kg"))

        if length_m <= 0 or width_m <= 0 or height_m <= 0:
            # 自动从纸箱尺寸推算（不精确但兜底）
            length_m = 1.16
            width_m = 1.01
            height_m = 2.0
            logger.warning(
                "托盘 %d 尺寸未提供/为零，使用默认值 %s×%s×%s", p_no, length_m, width_m, height_m
            )

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
        label = safe_str(extract_field(row, "carton_label"))
        if not label:
            label = "auto"
        carton_groups.setdefault(label, []).append(row)

    for label, group in carton_groups.items():
        products: list[Product] = []
        first_row = group[0]

        is_batch = safe_bool(extract_field(first_row, "is_batch"))
        batch_count = safe_int(extract_field(first_row, "batch_count", 1))
        length_cm = safe_float(extract_field(first_row, "length_cm", 32.0))
        width_cm = safe_float(extract_field(first_row, "width_cm", 32.0))
        height_cm = safe_float(extract_field(first_row, "height_cm", 34.0))
        gross_weight_kg = safe_float(extract_field(first_row, "gross_weight_kg"))

        # 填充商品
        seq_counter = 1
        for row in group:
            product_name = safe_str(extract_field(row, "product_name"))
            if not product_name:
                continue

            products.append(
                Product(
                    seq_no=safe_int(extract_field(row, "seq_no", seq_counter)),
                    product_name=product_name,
                    hs_code=safe_str(extract_field(row, "hs_code")),
                    unit=safe_str(extract_field(row, "unit", "Roll")),
                    qty_per_carton=safe_float(extract_field(row, "qty_per_carton", 1)),
                    unit_price=safe_float(extract_field(row, "unit_price")),
                    net_weight_per_unit_kg=safe_float(extract_field(row, "net_weight_per_unit_kg")),
                    destination_country=safe_str(
                        extract_field(row, "destination_country", "Turkey")
                    ),
                    specification=safe_str(extract_field(row, "specification")),
                    declaration_elements=safe_str(extract_field(row, "declaration_elements")),
                    currency=safe_str(extract_field(row, "currency", "USD")),
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


def compute_totals(pallets: list[Pallet]) -> Totals:
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
        pallet_volume = pallet.length_m * pallet.width_m * pallet.height_m
        total_volume_cbm += pallet_volume

        for carton in pallet.cartons:
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
