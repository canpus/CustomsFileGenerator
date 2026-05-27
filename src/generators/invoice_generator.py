# -*- coding: utf-8 -*-
"""形式发票生成器（Invoice Generator）— 阶段 5.

基于形式发票 XLSX 模板，根据订单数据动态生成发票文件。
按商品类型聚合（相同名称 + 相同规格 + 相同单价合并为一行），
集成 num2words 将总金额转换为英文大写。

参考：plan_v6.md 附录 B.2 形式发票模板字段映射表。
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path

from openpyxl.worksheet.worksheet import Worksheet

from config.constants import TEMPLATE_INVOICE_PATH
from src.generators.base_generator import BaseGenerator
from src.generators.template_anchor_scanner import AnchorResult, scan_invoice_template
from src.generators.xlsx_utils import safe_write_cell, update_sum_formula
from src.models.order_data import Carton, OrderData, Pallet, Product

logger = logging.getLogger(__name__)


# ==================== 数据展平：按商品聚合 ====================


def _compute_effective_carton_count(carton: Carton) -> int:
    """计算纸箱的有效数量.

    Args:
        carton: 纸箱数据.

    Returns:
        有效箱数：批量纸箱为 batch_count，否则为 1.
    """
    return carton.batch_count if carton.is_batch else 1


def flatten_for_invoice(order: OrderData) -> list[dict]:
    """将 OrderData 按商品类型聚合为发票行数据列表.

    聚合键：（product_name, specification, unit_price）。
    同一商品在不同托盘/纸箱中的数量与金额汇总到一行。

    每行字典包含以下键：
        seq_no:         序号（全局递增，从 1 开始）
        product_name:   商品名称
        specification:  规格型号
        unit:           计量单位
        total_qty:      总数量（所有纸箱中 qty_per_carton × 有效箱数 之和）
        unit_price:     单价
        amount:         金额（total_qty × unit_price）

    Args:
        order: 订单数据对象.

    Returns:
        按商品聚合后的行数据列表.

    Raises:
        ValueError: order 为 None 或 pallets 为空时抛出.
    """
    if order is None:
        raise ValueError("[错误]: order 为 None, 无法展平发票数据")

    if not order.pallets:
        raise ValueError("[错误]: 订单无托盘数据, 无法生成发票")

    # 聚合字典：key = (product_name, specification, unit_price)
    agg: dict[tuple[str, str, float], dict] = {}

    for pallet in order.pallets:
        for carton in pallet.cartons:
            effective_count: int = _compute_effective_carton_count(carton)
            for product in carton.products:
                key: tuple[str, str, float] = (
                    product.product_name,
                    product.specification,
                    product.unit_price,
                )

                if key not in agg:
                    agg[key] = {
                        "product_name": product.product_name,
                        "specification": product.specification,
                        "unit": product.unit,
                        "total_qty": 0.0,
                        "unit_price": product.unit_price,
                        "amount": 0.0,
                    }

                line_qty: float = product.qty_per_carton * effective_count
                agg[key]["total_qty"] += line_qty

    # 按添加顺序排列（保持稳定性）
    rows: list[dict] = []
    for seq, item in enumerate(agg.values(), start=1):
        item["seq_no"] = seq
        item["amount"] = round(item["total_qty"] * item["unit_price"], 2)
        rows.append(item)

    logger.info("发票数据聚合完成: 共 %d 行（%d 种商品）", len(rows), len(agg))
    return rows


# ==================== InvoiceGenerator 类 ====================


class InvoiceGenerator(BaseGenerator):
    """形式发票生成器.

    负责将 OrderData 填充到形式发票 XLSX 模板中，产出最终发票文件。

    使用方式：
        gen = InvoiceGenerator()
        output_path = gen.generate(order, output_dir, progress_callback)
    """

    def _get_default_template_path(self) -> Path:
        return TEMPLATE_INVOICE_PATH

    def _get_template_type(self) -> str:
        return "invoice"

    def _get_display_name(self) -> str:
        return "形式发票"

    def _scan_anchor(self, ws: Worksheet) -> AnchorResult:
        """扫描发票模板锚点."""
        return scan_invoice_template(ws)

    def _flatten_data(self, order: OrderData) -> list[dict]:
        """聚合商品数据为发票行."""
        return flatten_for_invoice(order)

    # ---- 表头填充 ----

    def _fill_header(self, ws: Worksheet, order: OrderData) -> None:
        """填充发票表头信息.

        实际模板结构（基于 template_invoice.xlsx 实测）：
        - D6:F6：日期 (Date: MMMM DDth, YYYY)
        - B7:F7：发票号 (Invoice No.)
        - B8:F8：货品名称 (Goods Summary)
        - B9:F9：客户公司名（合并）
        - B10:F10：客户地址（合并）
        - B11：联系人
        - E11:F11：电话（合并）
        - B12：装运港
        - E12:F12：手机号（合并）
        - B13：合同号
        - E13:F13：卸货港/目的地（合并）

        注意：使用 safe_write_cell，MergedCell 会被自动重定向到合并区域左上角.
        """
        meta = order.order_meta
        cust = order.customer

        # D6:F6 - 日期（模板已有标签，只写值）
        safe_write_cell(ws, 6, "D", meta.date)

        # B7:F7 - 发票号
        safe_write_cell(ws, 7, "B", meta.invoice_no)

        # B8:F8 - 货品名称
        goods: str = meta.goods_summary or self._build_goods_summary(order)
        safe_write_cell(ws, 8, "B", goods)

        # B9:F9 - 客户公司名
        safe_write_cell(ws, 9, "B", cust.company_name_en)

        # B10:F10 - 客户地址
        if cust.address:
            safe_write_cell(ws, 10, "B", cust.address)

        # B11 - 联系人（模板已有 "Attn:" 标签）
        if cust.contact_person:
            safe_write_cell(ws, 11, "B", cust.contact_person)

        # E11:F11 - 电话（模板已有 "Tel:" 标签）
        if cust.phone:
            safe_write_cell(ws, 11, "E", cust.phone)

        # B12 - 装运港（模板已有 "Port of Loading:" 标签）
        origin = order.origin
        if origin.export_port:
            safe_write_cell(ws, 12, "B", origin.export_port)

        # E12:F12 - 手机号（模板已有 "Mobile:" 标签）
        if cust.mobile:
            safe_write_cell(ws, 12, "E", cust.mobile)

        # B13 - 合同号（模板已有 "Contract No.:" 标签）
        safe_write_cell(ws, 13, "B", meta.contract_no)

        # E13:F13 - 卸货港/目的地（模板已有 "Port of Discharge:" 标签）
        destination: str = cust.destination or cust.country
        safe_write_cell(ws, 13, "E", destination)

        logger.info("发票表头填充完成")

    @staticmethod
    def _build_goods_summary(order: OrderData) -> str:
        """根据订单数据自动生成货品名称摘要.

        将所有商品名称去重后拼接，最多取前 3 个。

        Args:
            order: 订单数据.

        Returns:
            货品名称摘要字符串.
        """
        names: list[str] = []
        seen: set[str] = set()
        for pallet in order.pallets:
            for carton in pallet.cartons:
                for product in carton.products:
                    if product.product_name not in seen:
                        seen.add(product.product_name)
                        names.append(product.product_name)
                        if len(names) >= 3:
                            break
                if len(names) >= 3:
                    break
            if len(names) >= 3:
                break
        return "; ".join(names) if names else "GOODS"

    # ---- 明细填充 ----

    def _fill_data_rows(
        self,
        ws: Worksheet,
        data_start_row: int,
        rows: list[dict],
        anchor: AnchorResult,
    ) -> None:
        """逐行填充发票商品明细.

        列映射（A-F）:
        A = Product（商品名称）
        B = Specification（规格）
        C = Unit（单位）
        D = Qty（总数量）
        E = Unit Price（单价）
        F = Amount（金额 = Qty × Unit Price）

        Args:
            ws: 发票工作表.
            data_start_row: 数据起始行号.
            rows: 聚合后的行数据列表.
            anchor: 锚点扫描结果.
        """
        for idx, row_data in enumerate(rows):
            target_row: int = data_start_row + idx

            # A: 商品名称
            safe_write_cell(ws, target_row, "A", row_data["product_name"])
            # B: 规格
            safe_write_cell(ws, target_row, "B", row_data["specification"])
            # C: 单位
            safe_write_cell(ws, target_row, "C", row_data["unit"])
            # D: 数量
            safe_write_cell(ws, target_row, "D", row_data["total_qty"])
            # E: 单价
            safe_write_cell(ws, target_row, "E", row_data["unit_price"])
            # F: 金额
            safe_write_cell(ws, target_row, "F", row_data["amount"])

            # 金额列保留 2 位小数格式
            cell_f = ws.cell(row=target_row, column=6)
            if isinstance(cell_f.value, (int, float)):
                cell_f.number_format = "0.00"

        logger.info(
            "发票明细填充完成: %d 行 (第 %d 行 → 第 %d 行)",
            len(rows),
            data_start_row,
            data_start_row + len(rows) - 1,
        )

    # ---- 汇总公式修正 ----

    def _fix_summary_formulas(
        self, ws: Worksheet, anchor: AnchorResult, new_data_end: int
    ) -> None:
        """修正发票汇总行的 SUM 公式范围 + 填写入大写金额.

        F 列 = SUM(F{data_start}:F{new_data_end}) 修正范围。
        大写金额行 = "SAY: USD ... ONLY" 填入 A 列。

        行数调整后，锚点的 summary_row 不再准确——
        需根据 new_data_end 重新扫描实际汇总行位置。

        Args:
            ws: 发票工作表.
            anchor: 锚点扫描结果.
            new_data_end: 新的数据结束行号.
        """
        # 修正 F 列 SUM 公式
        update_sum_formula(ws, "F", anchor.data_start_row, new_data_end)

        # 在 new_data_end 之后重新定位实际汇总行（含 "Total"/"TOTAL" 关键词）
        actual_summary_row: int = self._find_actual_summary_row(
            ws, anchor, keywords=["TOTAL", "Total", "合计"]
        )

        # 计算总金额
        total_amount: float = 0.0
        for row_idx in range(anchor.data_start_row, new_data_end + 1):
            try:
                val = ws.cell(row=row_idx, column=6).value
                if isinstance(val, (int, float)):
                    total_amount += float(val)
            except Exception:
                pass
        total_amount = round(total_amount, 2)

        # 大写金额
        amount_upper: str = _amount_to_english_upper(total_amount)

        # 大写金额行 = 实际汇总行 + 1
        upper_row: int = actual_summary_row + 1

        # 填入大写金额（合并区域 A:F 仅写入 A 列）
        safe_write_cell(
            ws, upper_row, "A",
            f"SAY: {amount_upper} ONLY",
        )

        logger.info(
            "发票汇总修正完成: 总金额=%.2f, 实际汇总行=%d, 大写=%s",
            total_amount, actual_summary_row, amount_upper,
        )



# ==================== num2words 金额大写 ====================


def _amount_to_english_upper(amount: float) -> str:
    """将浮点金额转换为英文大写字符串.

    使用 num2words 库将数字转为英文单词，格式与银行大写一致。
    移除 num2words 默认添加的逗号和多余的 "AND"。
    示例：
        1900.00   → "USD ONE THOUSAND NINE HUNDRED"
        1234567.89 → "USD ONE MILLION TWO HUNDRED THIRTY-FOUR THOUSAND FIVE HUNDRED SIXTY-SEVEN AND CENTS EIGHTY-NINE"

    Args:
        amount: 金额（浮点数）.

    Returns:
        英文大写金额字符串，不含币种前缀.
    """
    try:
        from num2words import num2words

        # 整数部分
        integer_part: int = int(amount)
        cents_part: int = round((amount - integer_part) * 100)

        integer_words: str = num2words(integer_part).upper()
        # 移除 num2words 默认添加的逗号
        integer_words = integer_words.replace(",", "")
        # 移除多余的 " AND "（num2words 在百位和十位之间插入 AND）
        # 例如 "TWO HUNDRED AND THIRTY-FOUR" → "TWO HUNDRED THIRTY-FOUR"
        integer_words = integer_words.replace(" AND ", " ")

        if cents_part > 0:
            cents_words: str = num2words(cents_part).upper()
            cents_words = cents_words.replace(",", "")
            return f"USD {integer_words} AND CENTS {cents_words}"
        else:
            return f"USD {integer_words}"
    except ImportError:
        logger.error(
            "[错误]: num2words 未安装，金额大写转换不可用\n"
            "[原因]: 缺少运行时依赖\n"
            "[排查]: 执行 pip install num2words==0.5.14"
        )
        return f"USD {amount:,.2f}"
    except Exception:
        logger.exception(
            "[错误]: 金额大写转换失败\n"
            "[原因]: num2words 内部错误，金额=%.2f\n"
            "[排查]: 请检查金额数值是否在合理范围内",
            amount,
        )
        raise ValueError(
            f"金额大写转换失败: {amount}, 请检查 num2words 版本和金额数值"
        ) from None


# ========== 运行说明 ==========
# 依赖安装: pip install openpyxl msgspec num2words
# 运行命令: 由 orchestrator 统一调用，不直接运行此模块
# 测试命令: python -m pytest tests/test_invoice_generator.py -v
# =============================
