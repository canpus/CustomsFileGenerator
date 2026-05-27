"""装箱单模板锚点扫描器."""

from __future__ import annotations

import logging

from openpyxl.worksheet.worksheet import Worksheet

from src.generators.anchor_core import (
    AnchorResult,
    _estimate_data_end_row,
    _find_row_by_keywords,
    _find_summary_rows,
    _load_rules,
)

logger = logging.getLogger(__name__)


def scan_packing_template(ws: Worksheet, rules: dict | None = None) -> AnchorResult:
    """扫描装箱单模板，定位数据起始行和汇总行.

    扫描流程：
    1. 在 8-30 行中查找标题行（关键词："序号"/"No."/"商品描述"）。
    2. 标题行 + 1 = 数据起始行。
    3. 在数据起始行之后查找汇总行（关键词："Total"/"合计"/"总"）。
    4. 估算数据预设结束行。

    Args:
        ws: 装箱单 Worksheet 对象。
        rules: 完整的规则字典（可选，默认从 template_rules.json 加载）。

    Returns:
        AnchorResult 扫描结果。
    """
    if rules is None:
        rules = _load_rules()

    template_rules: dict = rules.get("templates", {}).get("packing", {})
    scanner_config: dict = rules.get("scanner", {})
    search_limit: int = scanner_config.get("search_rows_limit", 30)

    result: AnchorResult = AnchorResult(template_name="packing")

    try:
        result.sheet_name = ws.title
    except Exception:
        result.sheet_name = "Sheet0"

    result.column_mapping = template_rules.get("column_mapping", {})
    result.summary_columns = template_rules.get("summary_columns", {})
    result.merge_ranges = template_rules.get("merge_ranges", [])

    # 查找标题行
    header_anchor: dict = template_rules.get("header_anchor", {})
    row_keywords: list[str] = header_anchor.get("row_keywords", ["序号", "No.", "QTY.", "Item"])
    col_keywords: list[str] = header_anchor.get(
        "col_keywords", ["商品描述", "Description", "Spec."]
    )

    search_start: int = max(template_rules.get("header_search_start", 6), 1)
    result.header_row = _find_row_by_keywords(
        ws,
        row_keywords,
        col_keywords,
        row_start=search_start,
        row_end=min(search_limit, 30),
        require_both=True,
    )

    if result.header_row <= 0:
        result.header_row = _find_row_by_keywords(
            ws,
            row_keywords,
            None,
            row_start=search_start,
            row_end=min(search_limit, 30),
        )

    # 计算数据起始行
    data_offset: int = template_rules.get("data_start_offset", 1)
    if result.header_row > 0:
        result.data_start_row = result.header_row + data_offset
    else:
        result.data_start_row = 8
        result.errors.append(
            f"[错误]: 装箱单模板标题行扫描失败，已使用默认数据起始行 {result.data_start_row}"
        )

    # 查找汇总行
    summary_anchor: dict = template_rules.get("summary_anchor", {})
    summary_row_keywords: list[str] = summary_anchor.get(
        "row_keywords", ["Total", "TOTAL", "合计", "总"]
    )
    summary_col_keywords: list[str] | None = summary_anchor.get("col_keywords")

    summary_search_start: int = max(result.data_start_row + 1, 10)
    result.summary_rows = _find_summary_rows(
        ws,
        summary_row_keywords,
        summary_col_keywords,
        row_start=summary_search_start,
        row_end=100,
    )

    if result.summary_rows:
        result.summary_row = result.summary_rows[0]
        result.data_end_row = _estimate_data_end_row(ws, result.data_start_row, result.summary_row)
    else:
        result.errors.append("[错误]: 装箱单模板汇总行扫描失败，未找到'Total'/'合计'等关键词")

    if not result.is_valid:
        result.errors.append("[错误]: 装箱单模板锚点扫描不完整，请确认模板是否与原厂一致")

    logger.info(
        "装箱单锚点扫描: header=%d, data_start=%d, data_end=%d, summary=%d, errors=%d",
        result.header_row,
        result.data_start_row,
        result.data_end_row,
        result.summary_row,
        len(result.errors),
    )
    return result
