# -*- coding: utf-8 -*-
"""模板动态锚点扫描引擎.

扫描 XLSX 模板工作表的前 N 行，通过关键词匹配定位数据起始行和汇总行。
不依赖硬编码行号，模板行结构变更时无需修改代码。

阶段 3 核心模块，后续所有 xlsx 生成器均依赖此模块。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

from config.constants import TEMPLATE_RULES_PATH

logger = logging.getLogger(__name__)


# ==================== 数据类 ====================


@dataclass
class AnchorResult:
    """锚点扫描结果.

    Attributes:
        template_name: 模板名称（如 "packing"）。
        sheet_name: 工作表名称。
        header_row: 标题行号（1-based），未找到时为 -1。
        data_start_row: 数据起始行号（1-based），未找到时为 -1。
        data_end_row: 数据预设结束行号（模板默认值，1-based）。
        summary_row: 汇总行号（1-based），未找到时为 -1。
        summary_rows: 所有匹配的汇总行号列表。
        column_mapping: 列字母映射（如 {"seq_no": "A"}）。
        summary_columns: 汇总列映射。
        merge_ranges: 合并列范围列表。
        errors: 扫描过程中的警告/错误信息。
    """

    template_name: str
    sheet_name: str = ""
    header_row: int = -1
    data_start_row: int = -1
    data_end_row: int = -1
    summary_row: int = -1
    summary_rows: List[int] = field(default_factory=list)
    column_mapping: Dict[str, str] = field(default_factory=dict)
    summary_columns: Dict[str, str] = field(default_factory=dict)
    merge_ranges: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """锚点扫描是否成功（关键锚点均已定位）."""
        return (
            self.header_row > 0
            and self.data_start_row > 0
            and self.summary_row > 0
        )


# ==================== 规则加载 ====================


def _load_rules() -> dict:
    """从 config/template_rules.json 加载扫描规则.

    Returns:
        规则字典。若文件不存在或解析失败则返回空字典。

    注意：此函数不会因配置文件问题而崩溃，调用方应处理空规则情况。
    """
    if not TEMPLATE_RULES_PATH.exists():
        logger.warning(
            "[警告]: 锚点规则文件不存在: %s，将仅使用内置默认规则",
            TEMPLATE_RULES_PATH,
        )
        return {}

    try:
        with open(TEMPLATE_RULES_PATH, "r", encoding="utf-8") as f:
            rules = json.load(f)
        logger.info("已加载锚点扫描规则: %s", TEMPLATE_RULES_PATH)
        return rules
    except json.JSONDecodeError as e:
        logger.error(
            "[错误]: 锚点规则文件 JSON 解析失败: %s\n"
            "[原因]: %s\n"
            "[排查]: 请检查 %s 的 JSON 格式是否正确",
            TEMPLATE_RULES_PATH, e, TEMPLATE_RULES_PATH.name,
        )
        return {}
    except Exception as e:
        logger.error(
            "[错误]: 读取锚点规则文件失败: %s\n"
            "[原因]: %s\n"
            "[排查]: 请确认文件存在且有读取权限",
            TEMPLATE_RULES_PATH, e,
        )
        return {}


# ==================== 通用扫描逻辑 ====================


def _contains_keyword(cell_value, keywords: List[str]) -> bool:
    """检查单元格值是否包含任一关键词（不区分大小写）.

    Args:
        cell_value: 单元格值（可能是 str, int, float, None 等）。
        keywords: 关键词列表。

    Returns:
        匹配成功时返回 True。
    """
    if cell_value is None:
        return False
    text: str = str(cell_value).strip()
    if not text:
        return False
    text_lower: str = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def _find_row_by_keywords(
    ws: Worksheet,
    row_keywords: List[str],
    col_keywords: List[str] | None = None,
    row_start: int = 1,
    row_end: int = 30,
    require_both: bool = False,
) -> int:
    """在指定行范围内查找匹配关键词的行.

    扫描策略：
    1. 先按 row_keywords 匹配整行任意单元格。
    2. 若提供 col_keywords，优先返回同时满足 row + col 关键词的行。
    3. 若 require_both=True，必须同时满足两个条件。

    Args:
        ws: Worksheet 对象。
        row_keywords: 行级关键词列表。
        col_keywords: 列级关键词列表（可选，要求同行存在）。
        row_start: 扫描起始行（1-based）。
        row_end: 扫描结束行（1-based）。
        require_both: 是否强制要求 row + col 同时满足。

    Returns:
        匹配的行号（1-based），未找到返回 -1。
    """
    best_match: int = -1
    best_score: int = 0  # 2 = 同时满足 row+col，1 = 仅 row

    for row_idx in range(row_start, row_end + 1):
        row_ok: bool = False
        col_ok: bool = False

        for col_idx in range(1, (ws.max_column or 26) + 1):
            try:
                cell_value = ws.cell(row=row_idx, column=col_idx).value
            except Exception:
                continue

            if not row_ok and _contains_keyword(cell_value, row_keywords):
                row_ok = True

            if col_keywords and not col_ok and _contains_keyword(cell_value, col_keywords):
                col_ok = True

            if row_ok and (not col_keywords or col_ok):
                current_score: int = 2 if (row_ok and col_ok) else 1
                if current_score > best_score:
                    best_score = current_score
                    best_match = row_idx
                    if best_score == 2:
                        # 最佳匹配已找到，直接返回
                        return best_match

    if require_both and best_score < 2:
        return -1
    return best_match


def _find_summary_rows(
    ws: Worksheet,
    row_keywords: List[str],
    col_keywords: List[str] | None = None,
    row_start: int = 1,
    row_end: int = 100,
) -> List[int]:
    """查找汇总行（可能有多行）.

    扫描策略：
    1. 从 row_start 向下扫描，匹配包含关键词的行。
    2. 若提供 col_keywords，则要求同一行同时满足。
    3. 返回所有匹配的行号列表。

    Args:
        ws: Worksheet 对象。
        row_keywords: 汇总行关键词（如 ["Total", "TOTAL", "合计"]）。
        col_keywords: 汇总行列关键词（可选）。
        row_start: 扫描起始行。
        row_end: 扫描结束行。

    Returns:
        匹配的汇总行号列表。
    """
    matches: List[int] = []

    for row_idx in range(row_start, row_end + 1):
        row_ok: bool = False
        col_ok: bool = col_keywords is None  # 无列关键词时默认通过

        for col_idx in range(1, (ws.max_column or 26) + 1):
            try:
                cell_value = ws.cell(row=row_idx, column=col_idx).value
            except Exception:
                continue

            if isinstance(cell_value, str) and cell_value.startswith("="):
                # 公式单元格也算匹配（如 =SUM(...) 被视为包含 "SUM"）
                if _contains_keyword(cell_value, row_keywords):
                    row_ok = True

            if not row_ok and _contains_keyword(cell_value, row_keywords):
                row_ok = True

            if col_keywords and not col_ok and _contains_keyword(cell_value, col_keywords):
                col_ok = True

            if row_ok and col_ok:
                matches.append(row_idx)
                break

    return matches


def _estimate_data_end_row(ws: Worksheet, data_start_row: int, summary_row: int) -> int:
    """估算模板的数据预设结束行.

    在 data_start_row 和 summary_row 之间查找第一个空数据行（整行所有列均为空），
    则该行的上一行即为数据预设结束行。

    Args:
        ws: Worksheet 对象。
        data_start_row: 数据起始行。
        summary_row: 汇总行。

    Returns:
        数据预设结束行号。
    """
    max_col: int = ws.max_column or 1

    for row_idx in range(data_start_row, summary_row):
        all_empty: bool = True
        for col_idx in range(1, max_col + 1):
            try:
                if ws.cell(row=row_idx, column=col_idx).value is not None:
                    all_empty = False
                    break
            except Exception:
                continue
        if all_empty:
            return row_idx - 1

    # 未找到空行，返回汇总行的上一行
    return summary_row - 1


# ==================== 公开 API ====================


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

    # 1. 加载规则中的列映射和合并范围
    result.column_mapping = template_rules.get("column_mapping", {})
    result.summary_columns = template_rules.get("summary_columns", {})
    result.merge_ranges = template_rules.get("merge_ranges", [])

    # 2. 查找标题行
    header_anchor: dict = template_rules.get("header_anchor", {})
    row_keywords: List[str] = header_anchor.get("row_keywords", ["序号", "No."])
    col_keywords: List[str] = header_anchor.get("col_keywords", ["商品描述", "Description"])

    result.header_row = _find_row_by_keywords(
        ws, row_keywords, col_keywords,
        row_start=max(8, 1), row_end=min(search_limit, 30),
    )

    if result.header_row <= 0:
        # 宽松匹配：仅用行关键词
        result.header_row = _find_row_by_keywords(
            ws, row_keywords, None,
            row_start=5, row_end=min(search_limit, 30),
        )

    # 3. 计算数据起始行
    data_offset: int = template_rules.get("data_start_offset", 1)
    if result.header_row > 0:
        result.data_start_row = result.header_row + data_offset
    else:
        result.data_start_row = 8  # 默认值
        result.errors.append(
            f"[错误]: 装箱单模板标题行扫描失败，已使用默认数据起始行 {result.data_start_row}"
        )

    # 4. 查找汇总行
    summary_anchor: dict = template_rules.get("summary_anchor", {})
    summary_row_keywords: List[str] = summary_anchor.get(
        "row_keywords", ["Total", "TOTAL", "合计", "总"]
    )
    summary_col_keywords: List[str] | None = summary_anchor.get("col_keywords")

    summary_search_start: int = max(result.data_start_row + 1, 10)
    result.summary_rows = _find_summary_rows(
        ws, summary_row_keywords, summary_col_keywords,
        row_start=summary_search_start, row_end=100,
    )

    if result.summary_rows:
        result.summary_row = result.summary_rows[0]
        # 估算数据结束行
        result.data_end_row = _estimate_data_end_row(
            ws, result.data_start_row, result.summary_row
        )
    else:
        result.errors.append(
            "[错误]: 装箱单模板汇总行扫描失败，未找到'Total'/'合计'等关键词"
        )

    # 5. 状态汇总
    if not result.is_valid:
        result.errors.append(
            "[错误]: 装箱单模板锚点扫描不完整，请确认模板是否与原厂一致"
        )

    logger.info(
        "装箱单锚点扫描: header=%d, data_start=%d, data_end=%d, summary=%d, errors=%d",
        result.header_row, result.data_start_row,
        result.data_end_row, result.summary_row, len(result.errors),
    )
    return result


def scan_invoice_template(ws: Worksheet, rules: dict | None = None) -> AnchorResult:
    """扫描形式发票模板，定位数据起始行和汇总行.

    Args:
        ws: 发票 Worksheet 对象。
        rules: 完整的规则字典（可选）。

    Returns:
        AnchorResult 扫描结果。
    """
    if rules is None:
        rules = _load_rules()

    template_rules: dict = rules.get("templates", {}).get("invoice", {})
    scanner_config: dict = rules.get("scanner", {})
    search_limit: int = scanner_config.get("search_rows_limit", 30)

    result: AnchorResult = AnchorResult(template_name="invoice")

    try:
        result.sheet_name = ws.title
    except Exception:
        result.sheet_name = "Sheet0"

    result.column_mapping = template_rules.get("column_mapping", {})
    result.summary_columns = template_rules.get("summary_columns", {})

    # 1. 查找标题行
    header_anchor: dict = template_rules.get("header_anchor", {})
    row_keywords: List[str] = header_anchor.get("row_keywords", ["Product", "产品"])
    col_keywords: List[str] = header_anchor.get(
        "col_keywords", ["Specification", "Unit", "Qty"]
    )

    result.header_row = _find_row_by_keywords(
        ws, row_keywords, col_keywords,
        row_start=10, row_end=min(search_limit, 30),
    )

    if result.header_row <= 0:
        # 宽松匹配
        result.header_row = _find_row_by_keywords(
            ws, row_keywords, None,
            row_start=10, row_end=min(search_limit, 30),
        )

    # 2. 计算数据起始行
    data_offset: int = template_rules.get("data_start_offset", 1)
    if result.header_row > 0:
        result.data_start_row = result.header_row + data_offset
    else:
        result.data_start_row = 15  # 默认值
        result.errors.append(
            f"[错误]: 发票模板标题行扫描失败，已使用默认数据起始行 {result.data_start_row}"
        )

    # 3. 查找汇总行
    summary_anchor: dict = template_rules.get("summary_anchor", {})
    summary_row_keywords: List[str] = summary_anchor.get(
        "row_keywords", ["Total", "TOTAL", "合计", "总金额", "SAY"]
    )
    summary_col_keywords: List[str] | None = summary_anchor.get("col_keywords")

    summary_search_start: int = max(result.data_start_row + 1, 20)
    result.summary_rows = _find_summary_rows(
        ws, summary_row_keywords, summary_col_keywords,
        row_start=summary_search_start, row_end=100,
    )

    if result.summary_rows:
        result.summary_row = result.summary_rows[0]
        result.data_end_row = _estimate_data_end_row(
            ws, result.data_start_row, result.summary_row
        )
    else:
        result.errors.append(
            "[错误]: 发票模板汇总行扫描失败，未找到'Total'/'SAY'等关键词"
        )

    if not result.is_valid:
        result.errors.append(
            "[错误]: 发票模板锚点扫描不完整，请确认模板是否与原厂一致"
        )

    logger.info(
        "发票锚点扫描: header=%d, data_start=%d, data_end=%d, summary=%d, errors=%d",
        result.header_row, result.data_start_row,
        result.data_end_row, result.summary_row, len(result.errors),
    )
    return result


def scan_contract_template(ws: Worksheet, rules: dict | None = None) -> AnchorResult:
    """扫描形式合同模板，定位数据起始行和汇总行.

    Args:
        ws: 合同 Worksheet 对象。
        rules: 完整的规则字典（可选）。

    Returns:
        AnchorResult 扫描结果。
    """
    if rules is None:
        rules = _load_rules()

    template_rules: dict = rules.get("templates", {}).get("contract", {})
    scanner_config: dict = rules.get("scanner", {})
    search_limit: int = scanner_config.get("search_rows_limit", 30)

    result: AnchorResult = AnchorResult(template_name="contract")

    try:
        result.sheet_name = ws.title
    except Exception:
        result.sheet_name = "Sheet0"

    result.column_mapping = template_rules.get("column_mapping", {})
    result.summary_columns = template_rules.get("summary_columns", {})

    # 1. 查找标题行
    header_anchor: dict = template_rules.get("header_anchor", {})
    row_keywords: List[str] = header_anchor.get("row_keywords", ["No.", "Product", "序号"])
    col_keywords: List[str] = header_anchor.get(
        "col_keywords", ["Specification", "Unit", "Qty"]
    )

    result.header_row = _find_row_by_keywords(
        ws, row_keywords, col_keywords,
        row_start=5, row_end=min(search_limit, 30),
    )

    if result.header_row <= 0:
        result.header_row = _find_row_by_keywords(
            ws, row_keywords, None,
            row_start=5, row_end=min(search_limit, 30),
        )

    # 2. 计算数据起始行
    data_offset: int = template_rules.get("data_start_offset", 1)
    if result.header_row > 0:
        result.data_start_row = result.header_row + data_offset
    else:
        result.data_start_row = 8  # 默认值
        result.errors.append(
            f"[错误]: 合同模板标题行扫描失败，已使用默认数据起始行 {result.data_start_row}"
        )

    # 3. 查找汇总行
    summary_anchor: dict = template_rules.get("summary_anchor", {})
    summary_row_keywords: List[str] = summary_anchor.get(
        "row_keywords", ["Total", "TOTAL", "合计", "总金额", "SAY"]
    )
    summary_col_keywords: List[str] | None = summary_anchor.get("col_keywords")

    summary_search_start: int = max(result.data_start_row + 1, 10)
    result.summary_rows = _find_summary_rows(
        ws, summary_row_keywords, summary_col_keywords,
        row_start=summary_search_start, row_end=100,
    )

    if result.summary_rows:
        result.summary_row = result.summary_rows[0]
        result.data_end_row = _estimate_data_end_row(
            ws, result.data_start_row, result.summary_row
        )
    else:
        result.errors.append(
            "[错误]: 合同模板汇总行扫描失败，未找到'Total'/'SAY'等关键词"
        )

    if not result.is_valid:
        result.errors.append(
            "[错误]: 合同模板锚点扫描不完整，请确认模板是否与原厂一致"
        )

    logger.info(
        "合同锚点扫描: header=%d, data_start=%d, data_end=%d, summary=%d, errors=%d",
        result.header_row, result.data_start_row,
        result.data_end_row, result.summary_row, len(result.errors),
    )
    return result


def scan_template(
    template_path: str | Path, rules: dict | None = None
) -> AnchorResult:
    """通用模板扫描入口，根据文件名自动选择扫描策略.

    Args:
        template_path: 模板文件路径。
        rules: 完整的规则字典（可选）。

    Returns:
        AnchorResult 扫描结果。

    Raises:
        FileNotFoundError: 模板文件不存在时抛出。
        ValueError: 不支持的模板类型时抛出。
    """
    path = Path(template_path)

    if not path.exists():
        raise FileNotFoundError(
            f"[错误]: 模板文件不存在: {path}\n"
            f"[原因]: 文件可能已被移动、删除或改名\n"
            f"[排查]: 请将模板文件放入 templates/ 目录"
        )

    if rules is None:
        rules = _load_rules()

    try:
        wb = openpyxl.load_workbook(path)
        ws = wb.active if wb.active else wb.worksheets[0]
    except Exception as e:
        raise ValueError(
            f"[错误]: 无法打开模板文件: {path}\n"
            f"[原因]: {e}\n"
            f"[排查]: 请确认文件是否为有效的 .xlsx 格式"
        ) from e

    filename_lower: str = path.name.lower()

    try:
        if "packing" in filename_lower:
            result = scan_packing_template(ws, rules)
        elif "invoice" in filename_lower:
            result = scan_invoice_template(ws, rules)
        elif "contract" in filename_lower:
            result = scan_contract_template(ws, rules)
        else:
            raise ValueError(
                f"[错误]: 不支持的模板类型: {path.name}\n"
                f"[原因]: 模板文件名必须包含 'packing'、'invoice' 或 'contract'\n"
                f"[排查]: 请确认模板文件名符合命名规范"
            )
    finally:
        wb.close()

    return result


# ==================== 默认工作簿工厂 ====================


def _create_default_wb(template_type: str) -> openpyxl.Workbook:
    """当真实模板不可用时，构造一个符合规范结构的默认工作簿.

    在测试环境或无模板可用的降级场景中，此工厂方法构造一个与真实模板
    行结构完全一致的工作簿，确保锚点扫描和后续生成器能正常工作。

    工作簿结构（每种模板类型对应不同的行布局）：

    - packing:  标题行=第7行, 数据行=8~57(50行), 汇总行=58
    - invoice:  标题行=第14行, 数据行=15~64(50行), 汇总行=65
    - contract: 标题行=第7行, 数据行=8~57(50行), 汇总行=58

    Args:
        template_type: 模板类型，仅支持 "packing"、"invoice"、"contract"。

    Returns:
        openpyxl Workbook 对象（活动工作表已填充好标题行和汇总行）。

    Raises:
        ValueError: 不支持的模板类型。
    """
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    wb = openpyxl.Workbook()
    ws = wb.active

    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )
    header_font = Font(name="Arial", size=11, bold=True)
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    if template_type == "packing":
        ws.title = "Packing List"
        # 标题行（第 7 行）
        headers = ["序号", "商品描述", "", "规格", "单位", "单箱数量", "箱数", "托板号", "净重(kg)", "毛重(kg)", "体积(m³)"]
        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=7, column=col_idx)
            cell.value = h
            cell.font = copy.deepcopy(header_font)
            cell.alignment = copy.deepcopy(header_align)
            cell.border = copy.deepcopy(thin_border)
        # 合并 B7:C7
        ws.merge_cells("B7:C7")
        # 预留数据行 8~57（不填数据，只预设格式）
        # 汇总行（第 58 行）
        ws.cell(row=58, column=1).value = "总"
        ws.cell(row=58, column=7).value = "=SUM(G8:G57)"  # 总箱数
        ws.cell(row=58, column=9).value = "=SUM(I8:I57)"  # 总净重
        ws.cell(row=58, column=10).value = "=SUM(J8:J57)"  # 总毛重
        ws.cell(row=58, column=11).value = "=SUM(K8:K57)"  # 总体积
    elif template_type == "invoice":
        ws.title = "Proforma Invoice"
        headers = ["Product", "Specification", "Unit", "Qty", "Unit Price", "Amount"]
        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=14, column=col_idx)
            cell.value = h
            cell.font = copy.deepcopy(Font(name="Times New Roman", size=14, bold=True))
            cell.alignment = copy.deepcopy(header_align)
            cell.border = copy.deepcopy(thin_border)
        # 预留数据行 15~64
        # 汇总行（第 65 行）
        ws.cell(row=65, column=5).value = "TOTAL:"
        ws.cell(row=65, column=6).value = "=SUM(F15:F64)"
        # 大写金额行（第 66 行）
        ws.cell(row=66, column=1).value = "SAY: USD ... ONLY"
    elif template_type == "contract":
        ws.title = "Sales Contract"
        headers = ["No.", "Product", "Specification", "Unit", "Qty", "Unit Price", "Amount"]
        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=7, column=col_idx)
            cell.value = h
            cell.font = copy.deepcopy(Font(name="Times New Roman", size=14, bold=True))
            cell.alignment = copy.deepcopy(header_align)
            cell.border = copy.deepcopy(thin_border)
        # 预留数据行 8~57
        # 汇总行（第 58 行）
        ws.cell(row=58, column=6).value = "TOTAL:"
        ws.cell(row=58, column=7).value = "=SUM(G8:G57)"
        # 大写金额行（第 59 行）
        ws.cell(row=59, column=1).value = "SAY: USD ... ONLY"
    else:
        raise ValueError(
            f"[错误]: 不支持的模板类型: {template_type!r}\n"
            f"[原因]: 仅支持 'packing'、'invoice' 或 'contract'\n"
            f"[排查]: 请确认模板类型名称正确"
        )

    return wb


# ========== 运行说明 ==========
# 依赖安装：pip install openpyxl（已在 requirements.txt 中锁定版本）
# 运行命令：pytest tests/test_xlsx_utils.py -v
# 预期输出：9 项测试全部 PASSED（含锚点扫描测试 #6-#9）
# =============================
