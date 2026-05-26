# -*- coding: utf-8 -*-
"""形式合同生成器（Contract Generator）— 阶段 5.

基于形式合同 XLSX 模板，根据订单数据动态生成合同文件。
按商品类型聚合（与发票逻辑一致），集成 num2words 金额大写。

参考：plan_v6.md 附录 B.3 形式合同模板字段映射表。
"""

from __future__ import annotations

import logging
from pathlib import Path

from openpyxl.worksheet.worksheet import Worksheet

from config.constants import TEMPLATE_CONTRACT_PATH
from src.generators.base_generator import BaseGenerator
from src.generators.invoice_generator import (
    _amount_to_english_upper,
    flatten_for_invoice,
)
from src.generators.template_anchor_scanner import AnchorResult, scan_contract_template
from src.generators.xlsx_utils import safe_write_cell, update_sum_formula
from src.models.order_data import OrderData

logger = logging.getLogger(__name__)


# ==================== 数据展平：与发票相同（按商品聚合） ====================

# 合同与发票使用相同的聚合逻辑
flatten_for_contract = flatten_for_invoice


# ==================== ContractGenerator 类 ====================


class ContractGenerator(BaseGenerator):
    """形式合同生成器.

    负责将 OrderData 填充到形式合同 XLSX 模板中，产出最终合同文件。

    使用方式：
        gen = ContractGenerator()
        output_path = gen.generate(order, output_dir, progress_callback)
    """

    def _get_default_template_path(self) -> Path:
        return TEMPLATE_CONTRACT_PATH

    def _get_template_type(self) -> str:
        return "contract"

    def _get_display_name(self) -> str:
        return "形式合同"

    def _scan_anchor(self, ws: Worksheet) -> AnchorResult:
        """扫描合同模板锚点."""
        return scan_contract_template(ws)

    def _flatten_data(self, order: OrderData) -> list[dict]:
        """聚合商品数据为合同行（与发票逻辑一致）."""
        return flatten_for_contract(order)

    # ---- 表头填充 ----

    def _fill_header(self, ws: Worksheet, order: OrderData) -> None:
        """填充合同表头信息.

        实际模板结构（基于 template_contract.xlsx 实测）：
        - C3:G3：买方公司名（抬头人，合并单元格区域）
        - C4：发票号
        - G4：日期
        - C5：合同号
        - C6：订单号
        - D6:G6：发货口岸 (From ... To ...)

        注意：使用 safe_write_cell，MergedCell 会被自动重定向到合并区域左上角.
        """
        meta = order.order_meta
        cust = order.customer
        origin = order.origin

        # C3:G3 - 买方抬头（客户公司全称）
        safe_write_cell(ws, 3, "C", f"To: {cust.company_name_en}")

        # C4 - 发票号
        safe_write_cell(ws, 4, "C", f"Invoice No.: {meta.invoice_no}")

        # G4 - 日期
        safe_write_cell(ws, 4, "G", f"Date: {meta.date}")

        # C5 - 合同号
        safe_write_cell(ws, 5, "C", f"Contract No.: {meta.contract_no}")

        # C6 - 订单号
        if meta.order_no:
            safe_write_cell(ws, 6, "C", f"Order No.: {meta.order_no}")

        # D6:G6 - 发货口岸
        export_port: str = origin.export_port or "Shenzhen"
        destination: str = cust.destination or cust.country
        safe_write_cell(
            ws, 6, "D",
            f"From {export_port} To {destination}",
        )

        logger.info("合同表头填充完成")

    # ---- 明细填充 ----

    def _fill_data_rows(
        self,
        ws: Worksheet,
        data_start_row: int,
        rows: list[dict],
        anchor: AnchorResult,
    ) -> None:
        """逐行填充合同商品明细.

        列映射（A-G）:
        A = No.（序号）
        B = Product（商品名称）
        C = Specification（规格）
        D = Unit（单位）
        E = Qty（总数量）
        F = Unit Price（单价）
        G = Amount（金额 = Qty × Unit Price）

        Args:
            ws: 合同工作表.
            data_start_row: 数据起始行号.
            rows: 聚合后的行数据列表.
            anchor: 锚点扫描结果.
        """
        for idx, row_data in enumerate(rows):
            target_row: int = data_start_row + idx

            # A: 序号
            safe_write_cell(ws, target_row, "A", row_data["seq_no"])
            # B: 商品名称
            safe_write_cell(ws, target_row, "B", row_data["product_name"])
            # C: 规格
            safe_write_cell(ws, target_row, "C", row_data["specification"])
            # D: 单位
            safe_write_cell(ws, target_row, "D", row_data["unit"])
            # E: 数量
            safe_write_cell(ws, target_row, "E", row_data["total_qty"])
            # F: 单价
            safe_write_cell(ws, target_row, "F", row_data["unit_price"])
            # G: 金额
            safe_write_cell(ws, target_row, "G", row_data["amount"])

            # 金额列保留 2 位小数格式
            cell_g = ws.cell(row=target_row, column=7)
            if isinstance(cell_g.value, (int, float)):
                cell_g.number_format = "0.00"

        logger.info(
            "合同明细填充完成: %d 行 (第 %d 行 → 第 %d 行)",
            len(rows),
            data_start_row,
            data_start_row + len(rows) - 1,
        )

    # ---- 汇总公式修正 ----

    def _fix_summary_formulas(
        self, ws: Worksheet, anchor: AnchorResult, new_data_end: int
    ) -> None:
        """修正合同汇总行的 SUM 公式范围 + 填写入大写金额.

        G 列 = SUM(G{data_start}:G{new_data_end}) 修正范围。
        大写金额行 = "SAY: USD ... ONLY" 填入 A 列。

        行数调整后重新定位实际汇总行。

        Args:
            ws: 合同工作表.
            anchor: 锚点扫描结果.
            new_data_end: 新的数据结束行号.
        """
        # 修正 G 列 SUM 公式
        update_sum_formula(ws, "G", anchor.data_start_row, new_data_end)

        # 在 new_data_end 之后重新定位实际汇总行
        actual_summary_row: int = self._find_actual_summary_row(
            ws, anchor.data_start_row, new_data_end
        )

        # 计算总金额
        total_amount: float = 0.0
        for row_idx in range(anchor.data_start_row, new_data_end + 1):
            try:
                val = ws.cell(row=row_idx, column=7).value
                if isinstance(val, (int, float)):
                    total_amount += float(val)
            except Exception:
                pass
        total_amount = round(total_amount, 2)

        # 大写金额
        amount_upper: str = _amount_to_english_upper(total_amount)

        # 大写金额行 = 实际汇总行 + 1
        upper_row: int = actual_summary_row + 1

        # 填入大写金额
        safe_write_cell(
            ws, upper_row, "A",
            f"SAY: {amount_upper} ONLY",
        )

        logger.info(
            "合同汇总修正完成: 总金额=%.2f, 实际汇总行=%d, 大写=%s",
            total_amount, actual_summary_row, amount_upper,
        )

    @staticmethod
    def _find_actual_summary_row(
        ws: Worksheet, data_start_row: int, new_data_end: int
    ) -> int:
        """在数据区域之后查找实际的汇总行.

        从 new_data_end + 1 开始向后扫描，查找包含
        "Total"/"TOTAL"/"合计" 等关键词的行。

        Args:
            ws: 工作表.
            data_start_row: 数据起始行.
            new_data_end: 数据结束行.

        Returns:
            实际汇总行号。若未找到，返回 new_data_end + 1.
        """
        from src.generators.template_anchor_scanner import _find_summary_rows

        search_start: int = max(new_data_end + 1, data_start_row + 2)
        # 搜索范围扩大到 100 行 — 汇总行可能远离数据区
        summary_rows = _find_summary_rows(
            ws,
            ["Total", "TOTAL", "TOTAL QTY", "合计", "总金额"],
            None,
            row_start=search_start,
            row_end=search_start + 100,
        )

        if summary_rows:
            return summary_rows[0]

        logger.warning(
            "[警告]: 未找到实际汇总行，降级使用 new_data_end + 1 = %d",
            new_data_end + 1,
        )
        return new_data_end + 1


# ========== 运行说明 ==========
# 依赖安装: pip install openpyxl msgspec num2words
# 运行命令: 由 orchestrator 统一调用，不直接运行此模块
# 测试命令: python -m pytest tests/test_contract_generator.py -v
# =============================
