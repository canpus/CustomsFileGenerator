# -*- coding: utf-8 -*-
"""模板无损断言引擎 — 聚合入口.

生成文件后，检查生成文件的样式、格式、结构与模板是否一致。
支持断言分级（error/warning/info），规则由 config/assertion_rules.json 配置。

子模块拆分：
- assertion_data.py  : 数据结构 + 规则加载
- assertion_checks.py: 各维度断言检查函数
- 本模块             : assert_xlsx / assert_all_xlsx + 统一重导出
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict

import openpyxl

from config.constants import TEMPLATES_DIR
from src.generators.assertion_checks import (
    _assert_border,
    _assert_column_count,
    _assert_font,
    _assert_formula,
    _assert_merge_ranges,
)
from src.generators.assertion_data import (  # noqa: F401
    AssertionLevel,
    AssertionMessage,
    AssertionReport,
    BatchAssertionReport,
    _load_assertion_rules,
)

logger = logging.getLogger(__name__)


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
        rules: 完整的断言规则字典（可选）.

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

    template_filename: str = template_rules.get("file", f"template_{template_name}.xlsx")
    template_path: Path = TEMPLATES_DIR / template_filename

    if not template_path.exists():
        report.add("error", "general", f"模板文件不存在: {template_path}")
        return report

    try:
        gen_wb = openpyxl.load_workbook(generated_path)
        tpl_wb = openpyxl.load_workbook(template_path)

        gen_ws = gen_wb.active if gen_wb.active else gen_wb.worksheets[0]
        tpl_ws = tpl_wb.active if tpl_wb.active else tpl_wb.worksheets[0]

        _assert_font(gen_ws, tpl_ws, template_rules, report, template_name)
        _assert_border(gen_ws, tpl_ws, template_rules, report, template_name)
        _assert_merge_ranges(gen_ws, tpl_ws, template_rules, report, template_name)
        _assert_formula(gen_ws, template_rules, report, template_name)
        _assert_column_count(gen_ws, template_rules, report, template_name)

        gen_wb.close()
        tpl_wb.close()

    except Exception as e:
        report.add("error", "general", f"断言执行异常: {e}")
        logger.error(
            "[错误]: 断言 %s 模板时发生异常\n[原因]: %s\n[排查]: 请检查生成文件和模板文件是否损坏",
            template_name, e,
        )

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
# 依赖安装: pip install openpyxl
# 运行命令: pytest tests/test_template_assertion.py -v
# =============================
