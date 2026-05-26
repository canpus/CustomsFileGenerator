# -*- coding: utf-8 -*-
"""XLSX 工具库 — openpyxl 安全操作函数集.

提供行样式深拷贝、安全插入/删除、公式修正等底层操作，
所有函数均遵循"不修改传入参数"的数据不可变性原则。

阶段 3 核心模块，后续所有 xlsx 生成器（阶段 4/5）均依赖此模块。
"""

from __future__ import annotations

import copy
import logging
import re
from typing import List, Set, Tuple

import openpyxl
from openpyxl.cell.cell import Cell
from openpyxl.styles import Alignment, Border, Font, PatternFill, numbers
from openpyxl.utils import get_column_letter, range_boundaries
from openpyxl.worksheet.worksheet import Worksheet

logger = logging.getLogger(__name__)

# ==================== 常量 ====================

# SUM 公式正则：匹配 =SUM(列字母行号:列字母行号)
_SUM_FORMULA_PATTERN: re.Pattern = re.compile(
    r"=SUM\(([A-Z]+)(\d+):([A-Z]+)(\d+)\)",
    re.IGNORECASE,
)


# ==================== 样式深拷贝 ====================


def _copy_font(src: Font | None) -> Font:
    """安全拷贝 Font 对象（属性级拷贝，避免 deepcopy 递归超限）."""
    if src is None:
        return Font()
    return Font(
        name=src.name,
        size=src.size,
        bold=src.bold,
        italic=src.italic,
        underline=src.underline,
        strike=src.strike,
        color=copy.copy(src.color) if src.color else None,
        charset=src.charset,
        family=src.family,
    )


def _copy_border(src: Border | None) -> Border:
    """安全拷贝 Border 对象（属性级拷贝）."""
    if src is None:
        return Border()
    return Border(
        left=copy.copy(src.left) if src.left else None,
        right=copy.copy(src.right) if src.right else None,
        top=copy.copy(src.top) if src.top else None,
        bottom=copy.copy(src.bottom) if src.bottom else None,
        diagonal=copy.copy(src.diagonal) if src.diagonal else None,
        outline=src.outline,
        diagonalUp=src.diagonalUp,
        diagonalDown=src.diagonalDown,
    )


def _copy_fill(src: PatternFill | None) -> PatternFill:
    """安全拷贝 Fill 对象（属性级拷贝）."""
    if src is None:
        return PatternFill()
    return PatternFill(
        fill_type=src.fill_type,
        start_color=copy.copy(src.start_color) if src.start_color else None,
        end_color=copy.copy(src.end_color) if src.end_color else None,
        patternType=src.patternType,
    )


def _copy_alignment(src: Alignment | None) -> Alignment:
    """安全拷贝 Alignment 对象（属性级拷贝）."""
    if src is None:
        return Alignment()
    return Alignment(
        horizontal=src.horizontal,
        vertical=src.vertical,
        wrap_text=src.wrap_text,
        shrink_to_fit=src.shrink_to_fit,
        indent=src.indent,
        text_rotation=src.text_rotation,
    )


def _copy_number_format(src: str | None) -> str:
    """安全拷贝数字格式字符串."""
    if src is None:
        return "General"
    return src


# ==================== 公开 API ====================


def clone_row_style(ws: Worksheet, source_row: int, target_row: int) -> None:
    """将源行的所有样式深拷贝到目标行.

    拷贝范围：font, border, fill, alignment, number_format。
    不对源行做任何修改。每列独立拷贝，空单元格自动跳过。

    Args:
        ws: openpyxl Worksheet 对象。
        source_row: 源行号（1-based）。
        target_row: 目标行号（1-based）。

    Raises:
        ValueError: 行号 ≤ 0 时抛出。
    """
    if source_row <= 0 or target_row <= 0:
        raise ValueError(
            f"[错误]: 行号必须为正整数，source_row={source_row}, target_row={target_row}"
        )

    max_col: int = ws.max_column or 1

    for col_idx in range(1, max_col + 1):
        try:
            src_cell: Cell | None = ws.cell(row=source_row, column=col_idx)
            tgt_cell: Cell | None = ws.cell(row=target_row, column=col_idx)

            if src_cell is None:
                continue

            # 深拷贝各样式属性
            tgt_cell.font = _copy_font(src_cell.font)
            tgt_cell.border = _copy_border(src_cell.border)
            tgt_cell.fill = _copy_fill(src_cell.fill)
            tgt_cell.alignment = _copy_alignment(src_cell.alignment)
            tgt_cell.number_format = _copy_number_format(src_cell.number_format)
        except Exception as e:
            logger.warning(
                "[警告]: 克隆行样式时出错 row=%d col=%d: %s", target_row, col_idx, e
            )


def insert_rows_with_style(
    ws: Worksheet, anchor_row: int, count: int
) -> None:
    """在锚点行之后插入 N 行，并为每一行复制锚点行的样式.

    插入后锚点行位置保持不变，新行从 anchor_row+1 开始依次排列。

    Args:
        ws: Worksheet 对象。
        anchor_row: 锚点行号（1-based），新行插入其后。
        count: 要插入的行数。

    Raises:
        ValueError: count ≤ 0 或 anchor_row ≤ 0 时抛出。
    """
    if count <= 0:
        raise ValueError(f"[错误]: 插入行数必须为正整数，count={count}")
    if anchor_row <= 0:
        raise ValueError(f"[错误]: 锚点行号必须为正整数，anchor_row={anchor_row}")

    for i in range(count):
        insert_row_idx: int = anchor_row + 1 + i
        ws.insert_rows(insert_row_idx)
        clone_row_style(ws, anchor_row, insert_row_idx)
        logger.debug("已在第 %d 行后插入一行并复制样式", anchor_row + i)


def get_merged_ranges_in_row(ws: Worksheet, row: int) -> List[openpyxl.worksheet.cell_range.MultiCellRange]:
    """获取指定行所涉及的所有合并单元格范围.

    使用 openpyxl 内部 merged_cells.ranges 属性遍历，
    返回与该行有交集的所有合并范围。

    Args:
        ws: Worksheet 对象。
        row: 行号（1-based）。

    Returns:
        与该行有交集的合并单元格范围列表。
    """
    merged_ranges: list = []
    for merged_range in ws.merged_cells.ranges:
        try:
            # merged_range 格式如 'B8:C8'
            bounds = range_boundaries(str(merged_range))
            # bounds = (min_col, min_row, max_col, max_row) - 都是 1-based
            min_row, max_row = int(bounds[1]), int(bounds[3])
            if min_row <= row <= max_row:
                merged_ranges.append(merged_range)
        except Exception as e:
            logger.warning("[警告]: 解析合并单元格范围失败: %s — %s", merged_range, e)
    return merged_ranges


def delete_rows_safely(ws: Worksheet, start_row: int, end_row: int) -> None:
    """逆序安全删除行.

    核心算法：
    1. 逆序遍历（从 end_row 到 start_row），避免正序删除导致行号偏移。
    2. 每行删除前自动 unmerge_cells，避免 openpyxl 崩溃。

    Args:
        ws: Worksheet 对象。
        start_row: 起始行号（1-based）。
        end_row: 结束行号（1-based，含）。

    Raises:
        ValueError: start_row > end_row 或行号 ≤ 0 时抛出。
    """
    if start_row <= 0 or end_row <= 0:
        raise ValueError(
            f"[错误]: 行号必须为正整数，start_row={start_row}, end_row={end_row}"
        )
    if start_row > end_row:
        raise ValueError(
            f"[错误]: start_row({start_row}) 不能大于 end_row({end_row})"
        )

    logger.info("开始安全删除行: 第 %d 行 → 第 %d 行（逆序）", start_row, end_row)

    for row in range(end_row, start_row - 1, -1):
        # 1. 检测并解除该行的所有合并单元格
        merged_ranges = get_merged_ranges_in_row(ws, row)
        for merged_range in merged_ranges:
            try:
                ws.unmerge_cells(str(merged_range))
                logger.debug("已解除合并单元格: %s", merged_range)
            except Exception as e:
                logger.warning(
                    "[警告]: 解除合并单元格失败 %s: %s", merged_range, e
                )

        # 2. 删除该行
        ws.delete_rows(row)
        logger.debug("已删除第 %d 行", row)

    logger.info("安全删除完成: 共删除 %d 行", end_row - start_row + 1)


def update_sum_formula(
    ws: Worksheet, col_letter: str, start_row: int, end_row: int
) -> None:
    """修正指定列的 SUM 公式范围.

    扫描工作表中所有公式单元格，找到匹配的 SUM 公式并替换为新范围。

    Args:
        ws: Worksheet 对象。
        col_letter: 列字母（如 "G"）。
        start_row: 新的起始行号。
        end_row: 新的结束行号。

    Returns:
        None（直接修改 ws 中匹配的公式单元格）。

    Raises:
        ValueError: 列字母无效时抛出。
    """
    if not col_letter or not col_letter.isalpha():
        raise ValueError(f"[错误]: 无效的列字母: {col_letter!r}")

    new_formula: str = f"=SUM({col_letter}{start_row}:{col_letter}{end_row})"
    updated_count: int = 0

    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith("="):
                match = _SUM_FORMULA_PATTERN.match(cell.value)
                if match:
                    old_start_col: str = match.group(1)
                    old_end_col: str = match.group(3)
                    # 仅修正匹配列字母的 SUM 公式
                    if old_start_col.upper() == col_letter.upper():
                        old_formula: str = cell.value
                        cell.value = new_formula
                        updated_count += 1
                        logger.debug(
                            "公式修正: %s → %s (cell %s)",
                            old_formula,
                            new_formula,
                            cell.coordinate,
                        )

    if updated_count == 0:
        logger.warning(
            "[警告]: 未找到需要修正的 SUM 公式，col=%s, range=%s%d:%s%d",
            col_letter, col_letter, start_row, col_letter, end_row,
        )
    else:
        logger.info("公式修正完成: 共修正 %d 个 SUM 公式", updated_count)


def resize_data_rows(
    ws: Worksheet,
    data_start_row: int,
    data_end_row: int,
    target_row_count: int,
    anchor_row: int,
) -> int:
    """根据目标行数自动扩容/缩容数据区域.

    这是 delete_rows_safely + insert_rows_with_style 的高层封装，
    供各生成器在填充数据前调用。

    算法：
    1. 计算当前数据行数 = data_end_row - data_start_row + 1
    2. 如果当前行数 < 目标行数 → 在 data_end_row 之后插入差额行（复制锚点行样式）
    3. 如果当前行数 > 目标行数 → 逆序删除多余行

    Args:
        ws: Worksheet 对象。
        data_start_row: 数据起始行号。
        data_end_row: 当前数据结束行号（模板默认值）。
        target_row_count: 目标数据行数。
        anchor_row: 样式锚点行号（插入新行时复制该行样式）。

    Returns:
        新的数据结束行号（1-based）。

    Raises:
        ValueError: 参数无效时抛出。
    """
    if data_start_row <= 0 or data_end_row <= 0:
        raise ValueError(
            f"[错误]: 数据行号必须为正整数，start={data_start_row}, end={data_end_row}"
        )
    if target_row_count <= 0:
        raise ValueError(f"[错误]: 目标行数必须为正整数，target={target_row_count}")
    if data_start_row > data_end_row:
        raise ValueError(
            f"[错误]: 数据起始行({data_start_row}) > 结束行({data_end_row})"
        )

    current_count: int = data_end_row - data_start_row + 1
    diff: int = target_row_count - current_count

    logger.info(
        "数据行调整: 当前 %d 行 → 目标 %d 行 (diff=%+d)",
        current_count, target_row_count, diff,
    )

    if diff > 0:
        # 扩容：在数据结束行之后插入新行
        insert_rows_with_style(ws, data_end_row, diff)
        new_data_end: int = data_end_row + diff
        logger.info(
            "已扩容: 在 %d 行后插入 %d 行，新结束行=%d",
            data_end_row, diff, new_data_end,
        )
        return new_data_end
    elif diff < 0:
        # 缩容：逆序删除多余行（保留前 target_row_count 行）
        delete_start: int = data_start_row + target_row_count
        delete_rows_safely(ws, delete_start, data_end_row)
        new_data_end: int = delete_start - 1
        logger.info(
            "已缩容: 删除 %d 行（%d→%d），新结束行=%d",
            -diff, delete_start, data_end_row, new_data_end,
        )
        return new_data_end
    else:
        logger.info("数据行数无需调整（%d 行）", current_count)
        return data_end_row


def safe_write_cell(
    ws: Worksheet, row: int, col: int | str, value, preserve_style: bool = True
) -> None:
    """安全写入单元格值，保留原有样式.

    Args:
        ws: Worksheet 对象。
        row: 行号（1-based）。
        col: 列号（int）或列字母（str，如 "A"）。
        value: 要写入的值。
        preserve_style: 是否保留目标单元格原有样式（默认 True）。
    """
    # 将列字母转换为列索引
    if isinstance(col, str):
        col = openpyxl.utils.column_index_from_string(col)

    cell: Cell = ws.cell(row=row, column=col)

    # 如果目标是合并单元格（MergedCell），则获取合并区域左上角实际 Cell
    from openpyxl.cell.cell import MergedCell

    if isinstance(cell, MergedCell):
        # 遍历合并区域，找到包含此单元格的区域
        for merged_range in ws.merged_cells.ranges:
            bounds = openpyxl.utils.range_boundaries(str(merged_range))
            min_col, min_row, max_col, max_row = int(bounds[0]), int(bounds[1]), int(bounds[2]), int(bounds[3])
            if min_row <= row <= max_row and min_col <= col <= max_col:
                cell = ws.cell(row=min_row, column=min_col)
                break
        else:
            # 未找到合并区域，这不是预期情况，但仍尝试写入
            pass

    if not preserve_style:
        cell.value = value
        return

    # 先保存原有样式（属性级拷贝避免 openpyxl 代理对象 deepcopy 递归），再写入值
    saved_font = _copy_font(cell.font)
    saved_border = _copy_border(cell.border)
    saved_fill = _copy_fill(cell.fill)
    saved_alignment = _copy_alignment(cell.alignment)
    saved_number_format = _copy_number_format(cell.number_format)

    cell.value = value

    # 恢复样式
    cell.font = saved_font
    if saved_border:
        cell.border = saved_border
    if saved_fill:
        cell.fill = saved_fill
    if saved_alignment:
        cell.alignment = saved_alignment
    if saved_number_format:
        cell.number_format = saved_number_format


def get_column_index(col_letter: str) -> int:
    """将列字母转换为列索引（1-based）.

    Args:
        col_letter: 列字母，如 "A", "AB"。

    Returns:
        列索引（1-based）。

    Raises:
        ValueError: 列字母无效时抛出。
    """
    if not col_letter or not col_letter.isalpha():
        raise ValueError(f"[错误]: 无效的列字母: {col_letter!r}")
    return openpyxl.utils.column_index_from_string(col_letter)


# ========== 运行说明 ==========
# 依赖安装：pip install openpyxl（已在 requirements.txt 中锁定版本）
# 运行命令：pytest tests/test_xlsx_utils.py -v
# 预期输出：9 项测试全部 PASSED
# =============================
