# -*- coding: utf-8 -*-
"""模板无损断言引擎 — 阶段 7.2.

生成文件后，检查生成文件的样式、格式、结构与模板是否一致。
支持断言分级（error/warning/info），规则由 config/assertion_rules.json 配置。

当前实现 xlsx 断言，[待迁移] 阶段 6 完成后增加 docx 断言。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

from config.constants import ASSERTION_RULES_PATH, TEMPLATES_DIR

logger = logging.getLogger(__name__)


# ==================== 数据结构 ====================

AssertionLevel = Literal["error", "warning", "info"]


@dataclass
class AssertionMessage:
    """单条断言消息.

    Attributes:
        level: 严重级别（error/warning/info）.
        template_name: 模板名称.
        category: 断言类别（如 "font", "border", "merge_ranges"）.
        message: 中文描述.
        detail: 详细信息（如期望值 vs 实际值）.
    """

    level: AssertionLevel
    template_name: str
    category: str
    message: str
    detail: str = ""


@dataclass
class AssertionReport:
    """断言报告.

    Attributes:
        passed: 是否全部通过（无 error 级别消息）.
        template_name: 模板名称.
        messages: 所有断言消息.
        errors: error 级别消息.
        warnings: warning 级别消息.
        infos: info 级别消息.
    """

    template_name: str
    passed: bool = True
    messages: List[AssertionMessage] = field(default_factory=list)

    @property
    def errors(self) -> List[AssertionMessage]:
        return [m for m in self.messages if m.level == "error"]

    @property
    def warnings(self) -> List[AssertionMessage]:
        return [m for m in self.messages if m.level == "warning"]

    @property
    def infos(self) -> List[AssertionMessage]:
        return [m for m in self.messages if m.level == "info"]

    def add(
        self,
        level: AssertionLevel,
        category: str,
        message: str,
        detail: str = "",
    ) -> None:
        """添加一条断言消息."""
        if level == "error":
            self.passed = False
        self.messages.append(
            AssertionMessage(
                level=level,
                template_name=self.template_name,
                category=category,
                message=message,
                detail=detail,
            )
        )


@dataclass
class BatchAssertionReport:
    """批量断言报告（多模板汇总）.

    Attributes:
        passed: 是否全部通过.
        total: 模板总数.
        passed_count: 通过的模板数.
        failed_count: 失败的模板数.
        reports: 各模板的断言报告.
    """

    passed: bool = True
    total: int = 0
    passed_count: int = 0
    failed_count: int = 0
    reports: List[AssertionReport] = field(default_factory=list)


# ==================== 规则加载 ====================


def _load_assertion_rules() -> dict:
    """从 config/assertion_rules.json 加载断言规则.

    Returns:
        规则字典。若文件不存在或解析失败则返回空字典。
    """
    if not ASSERTION_RULES_PATH.exists():
        logger.warning(
            "[警告]: 断言规则文件不存在: %s，将使用内置默认规则",
            ASSERTION_RULES_PATH,
        )
        return {}

    try:
        with open(ASSERTION_RULES_PATH, "r", encoding="utf-8") as f:
            rules = json.load(f)
        logger.info("已加载断言规则: %s", ASSERTION_RULES_PATH)
        return rules
    except json.JSONDecodeError as e:
        logger.error(
            "[错误]: 断言规则文件 JSON 解析失败: %s\n[原因]: %s\n[排查]: 请检查 JSON 格式",
            ASSERTION_RULES_PATH, e,
        )
        return {}
    except Exception as e:
        logger.error(
            "[错误]: 读取断言规则文件失败: %s\n[原因]: %s\n[排查]: 请确认文件存在且有读取权限",
            ASSERTION_RULES_PATH, e,
        )
        return {}


# ==================== xlsx 断言逻辑 ====================


def _assert_font(
    ws: Worksheet,
    template_ws: Worksheet,
    rules: dict,
    report: AssertionReport,
    template_name: str,
) -> None:
    """断言字体样式.

    检查关键单元格的字体名称和字号是否与模板一致。

    Args:
        ws: 生成文件的工作表.
        template_ws: 模板工作表.
        rules: 断言规则.
        report: 断言报告（会被修改）.
        template_name: 模板名称.
    """
    font_rules: dict = rules.get("assertions", {}).get("font", {})
    if not font_rules:
        return

    check_cells: List[str] = font_rules.get("check_cells", [])
    expected_name: str = font_rules.get("expected", {}).get("name", "")
    tolerance: dict = font_rules.get("tolerance", {})
    level_str: str = font_rules.get("level", "warning")
    level: AssertionLevel = "warning" if level_str == "warning" else "error"

    for cell_ref in check_cells:
        try:
            gen_cell = ws[cell_ref]
            tpl_cell = template_ws[cell_ref]
        except Exception:
            continue

        # 检查字体名称
        gen_font_name: str = (gen_cell.font.name or "").strip() if gen_cell.font else ""
        tpl_font_name: str = (tpl_cell.font.name or "").strip() if tpl_cell.font else ""

        if expected_name and gen_font_name and gen_font_name != expected_name:
            name_exact: bool = tolerance.get("name", "exact") == "exact"
            if name_exact:
                report.add(
                    level,
                    "font_name",
                    f"单元格 {cell_ref} 字体名称不匹配",
                    f"期望: '{expected_name}', 实际: '{gen_font_name}'",
                )
            elif expected_name.lower() != gen_font_name.lower():
                report.add(
                    level,
                    "font_name",
                    f"单元格 {cell_ref} 字体名称不匹配",
                    f"期望: '{expected_name}', 实际: '{gen_font_name}'",
                )

        # 检查字号
        gen_size: float = gen_cell.font.size if gen_cell.font and gen_cell.font.size else 0.0
        tpl_size: float = tpl_cell.font.size if tpl_cell.font and tpl_cell.font.size else 0.0
        if tpl_size > 0 and gen_size > 0:
            size_tolerance: float = tolerance.get("size_pt", 0.5)
            if abs(gen_size - tpl_size) > size_tolerance:
                report.add(
                    level,
                    "font_size",
                    f"单元格 {cell_ref} 字号偏差超过容差",
                    f"模板: {tpl_size}pt, 生成: {gen_size}pt, 容差: ±{size_tolerance}pt",
                )


def _assert_border(
    ws: Worksheet,
    template_ws: Worksheet,
    rules: dict,
    report: AssertionReport,
    template_name: str,
) -> None:
    """断言边框样式.

    检查关键单元格是否有边框。
    """
    border_rules: dict = rules.get("assertions", {}).get("border", {})
    if not border_rules:
        return

    check_cells: List[str] = border_rules.get("check_cells", [])
    level_str: str = border_rules.get("level", "error")
    level: AssertionLevel = "error" if level_str == "error" else "warning"

    for cell_ref in check_cells:
        try:
            gen_cell = ws[cell_ref]
        except Exception:
            continue

        has_border: bool = (
            gen_cell.border is not None
            and (
                gen_cell.border.left is not None
                or gen_cell.border.right is not None
                or gen_cell.border.top is not None
                or gen_cell.border.bottom is not None
            )
        )

        if not has_border:
            report.add(
                level,
                "border",
                f"单元格 {cell_ref} 边框丢失",
                "边框丢失可能导致报关资料格式不合规",
            )


def _assert_merge_ranges(
    ws: Worksheet,
    template_ws: Worksheet,
    rules: dict,
    report: AssertionReport,
    template_name: str,
) -> None:
    """断言合并单元格区域.

    检查关键合并单元格是否保留。
    """
    merge_rules: dict = rules.get("assertions", {}).get("merge_ranges", {})
    if not merge_rules:
        return

    expected_ranges: List[str] = merge_rules.get("expected_ranges", [])
    level_str: str = merge_rules.get("level", "error")
    level: AssertionLevel = "error" if level_str == "error" else "warning"

    # 获取生成文件的所有合并范围（转为规范化字符串）
    gen_merged: set = set()
    for merged_range in ws.merged_cells.ranges:
        gen_merged.add(str(merged_range))

    for expected_range in expected_ranges:
        if expected_range not in gen_merged:
            report.add(
                level,
                "merge_range",
                f"合并单元格区域缺失: {expected_range}",
                "表头合并区域丢失，可能导致格式与模板不一致",
            )


def _assert_formula(
    ws: Worksheet,
    rules: dict,
    report: AssertionReport,
    template_name: str,
) -> None:
    """断言汇总公式.

    检查汇总行是否包含 SUM 公式。
    """
    formula_rules: dict = rules.get("assertions", {}).get("formula", {})
    if not formula_rules:
        return

    check_columns: List[str] = formula_rules.get("check_columns", [])
    expected_pattern: str = formula_rules.get("expected_pattern", "=SUM(")
    level_str: str = formula_rules.get("level", "info")
    level: AssertionLevel = "info" if level_str == "info" else "warning"

    found_formula: bool = False
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith(expected_pattern):
                found_formula = True
                break
        if found_formula:
            break

    if not found_formula:
        report.add(
            level,
            "formula",
            f"未找到 {expected_pattern} 汇总公式",
            "汇总行公式缺失，数据变更后汇总不会自动更新",
        )
    else:
        report.add(
            "info",
            "formula",
            "汇总公式检查通过",
        )


def _assert_column_count(
    ws: Worksheet,
    rules: dict,
    report: AssertionReport,
    template_name: str,
) -> None:
    """断言列数（使用 >= 比较，允许模板含额外空列）."""
    col_rules: dict = rules.get("assertions", {}).get("column_count", {})
    if not col_rules:
        return

    expected: int = col_rules.get("expected", 0)
    level_str: str = col_rules.get("level", "warning")
    level: AssertionLevel = "warning" if level_str == "warning" else "error"

    actual: int = ws.max_column or 0

    if actual < expected:
        report.add(
            level,
            "column_count",
            f"列数不足: 期望至少 {expected} 列, 实际 {actual} 列",
            "列数减少可能导致数据列缺失",
        )


# ==================== 公开 API ====================


def assert_xlsx(
    generated_path: Path,
    template_name: str,
    rules: dict | None = None,
) -> AssertionReport:
    """对生成的 xlsx 文件执行模板无损断言.

    检查字体、边框、合并单元格区域、公式和列数。
    xlsx 断言不影响生成流程——仅输出报告供人工或 CI 检查。

    Args:
        generated_path: 生成的 xlsx 文件路径.
        template_name: 模板名称（如 "packing"、"invoice"、"contract"）.
        rules: 完整的断言规则字典（可选，默认从 assertion_rules.json 加载）.

    Returns:
        AssertionReport 断言报告.

    Raises:
        FileNotFoundError: 生成文件或模板文件不存在时抛出.
    """
    if not generated_path.exists():
        raise FileNotFoundError(
            f"[错误]: 生成文件不存在: {generated_path}\n"
            f"[原因]: 生成器可能未成功输出文件\n"
            f"[排查]: 请检查生成器日志，确认文件已生成"
        )

    if rules is None:
        rules = _load_assertion_rules()

    template_rules: dict = rules.get("templates", {}).get(template_name, {})
    report: AssertionReport = AssertionReport(template_name=template_name)

    if not template_rules:
        report.add("info", "general", f"模板 {template_name} 无断言规则配置，跳过断言")
        return report

    # 加载模板文件
    template_filename: str = template_rules.get("file", f"template_{template_name}.xlsx")
    template_path: Path = TEMPLATES_DIR / template_filename

    if not template_path.exists():
        report.add(
            "error",
            "general",
            f"模板文件不存在: {template_path}",
        )
        return report

    try:
        gen_wb = openpyxl.load_workbook(generated_path)
        tpl_wb = openpyxl.load_workbook(template_path)

        gen_ws = gen_wb.active if gen_wb.active else gen_wb.worksheets[0]
        tpl_ws = tpl_wb.active if tpl_wb.active else tpl_wb.worksheets[0]

        # 执行各断言
        _assert_font(gen_ws, tpl_ws, template_rules, report, template_name)
        _assert_border(gen_ws, tpl_ws, template_rules, report, template_name)
        _assert_merge_ranges(gen_ws, tpl_ws, template_rules, report, template_name)
        _assert_formula(gen_ws, template_rules, report, template_name)
        _assert_column_count(gen_ws, template_rules, report, template_name)

        gen_wb.close()
        tpl_wb.close()

    except Exception as e:
        report.add(
            "error",
            "general",
            f"断言执行异常: {e}",
        )
        logger.error(
            "[错误]: 断言 %s 模板时发生异常\n[原因]: %s\n[排查]: 请检查生成文件和模板文件是否损坏",
            template_name, e,
        )

    # 汇总
    err_count: int = len(report.errors)
    warn_count: int = len(report.warnings)
    info_count: int = len(report.infos)

    logger.info(
        "断言完成 [%s]: errors=%d, warnings=%d, infos=%d, passed=%s",
        template_name, err_count, warn_count, info_count, report.passed,
    )

    return report


def assert_all_xlsx(
    output_paths: Dict[str, Path],
    rules: dict | None = None,
) -> BatchAssertionReport:
    """对所有生成的 xlsx 文件执行批量断言.

    Args:
        output_paths: {模板类型: 文件路径} 映射.
        rules: 完整的断言规则字典（可选）.

    Returns:
        BatchAssertionReport 批量断言报告.
    """
    if rules is None:
        rules = _load_assertion_rules()

    batch: BatchAssertionReport = BatchAssertionReport()
    batch.total = len(output_paths)

    for template_name, file_path in output_paths.items():
        try:
            report = assert_xlsx(file_path, template_name, rules)
        except Exception as e:
            report = AssertionReport(template_name=template_name)
            report.add("error", "general", f"断言失败: {e}")
            logger.error("[错误]: 断言 %s 失败: %s", template_name, e)

        batch.reports.append(report)
        if report.passed:
            batch.passed_count += 1
        else:
            batch.failed_count += 1
            batch.passed = False

    logger.info(
        "批量断言完成: passed=%d/%d, failed=%d/%d",
        batch.passed_count, batch.total,
        batch.failed_count, batch.total,
    )

    return batch


# ========== 运行说明 ==========
# 依赖安装: pip install openpyxl（已在 requirements.txt 中锁定版本）
# 运行命令: pytest tests/test_template_assertion.py -v
# 预期输出: 阶段 7 当前 5/7 项 PASSED（docx 断言暂缓）
# =============================
