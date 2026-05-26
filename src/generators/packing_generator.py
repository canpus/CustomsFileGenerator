# -*- coding: utf-8 -*-
"""装箱单生成器（Packing Generator）— 阶段 4.

基于装箱单 XLSX 模板，根据订单数据动态生成装箱单文件。
核心流程：沙箱复制 → 锚点扫描 → 缩容/扩容 → 填充表头 → 填充明细 → 修正公式。

参考：plan_v6.md 附录 B.1 装箱单模板字段映射表。
"""

from __future__ import annotations

import copy
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Callable

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

from config.constants import (
    FILE_PREFIX_MAP,
    OUTPUT_DIR,
    TEMPLATE_PACKING_PATH,
)
from src.generators.template_anchor_scanner import (
    AnchorResult,
    scan_packing_template,
)
from src.generators.xlsx_utils import (
    resize_data_rows,
    safe_write_cell,
    update_sum_formula,
)
from src.models.order_data import (
    Carton,
    OrderData,
    Pallet,
    Product,
)

logger = logging.getLogger(__name__)


# ==================== 数据展平：OrderData → 装箱单行数据 ====================


def flatten_for_packing(order: OrderData) -> list[dict]:
    """将 OrderData 展平为装箱单行数据列表.

    装箱单每行对应一个（托盘, 纸箱, 商品）三元组。
    批量纸箱（is_batch=True）只生成一行, batch_count 填入"箱数"列。

    每行字典包含以下键：
        seq_no:           序号（全局递增，从 1 开始）
        pallet_no:        托盘号
        product_name:     商品名称
        specification:    规格型号
        unit:             计量单位
        qty_per_carton:   每箱数量
        carton_count:     箱数（批量纸箱为 batch_count）
        net_weight:       本行总净重（kg）= net_weight_per_unit × qty_per_carton × carton_count
        gross_weight:     本行总毛重（kg）= 纸箱毛重 × carton_count
        volume:           本行总体积（m³）= (长×宽×高)/1e6 × carton_count

    Args:
        order: 订单数据对象.

    Returns:
        展平后的行数据列表，按托盘号、商品序号排序.

    Raises:
        ValueError: order 为 None 或 pallets 为空时抛出.
    """
    if order is None:
        raise ValueError("[错误]: order 为 None, 无法展平数据")

    if not order.pallets:
        raise ValueError("[错误]: 订单无托盘数据, 无法生成装箱单")

    rows: list[dict] = []
    seq: int = 0

    for pallet in order.pallets:
        for carton in pallet.cartons:
            # 有效箱数（批量纸箱按 batch_count，否则为 1）
            effective_carton_count: int = (
                carton.batch_count if carton.is_batch else 1
            )

            # 单箱体积 m³ = 长(cm) × 宽(cm) × 高(cm) / 1,000,000
            single_carton_volume: float = (
                carton.length_cm * carton.width_cm * carton.height_cm / 1_000_000.0
            )

            for product in carton.products:
                seq += 1

                # 本行总净重 = 单件净重 × 每箱数量 × 箱数
                row_net_weight: float = (
                    product.net_weight_per_unit_kg
                    * product.qty_per_carton
                    * effective_carton_count
                )

                # 本行总毛重 = 单箱毛重 × 箱数
                row_gross_weight: float = (
                    carton.gross_weight_kg * effective_carton_count
                )

                # 本行总体积 = 单箱体积 × 箱数
                row_volume: float = single_carton_volume * effective_carton_count

                rows.append({
                    "seq_no": seq,
                    "pallet_no": pallet.pallet_no,
                    "product_name": product.product_name,
                    "specification": product.specification,
                    "unit": product.unit,
                    "qty_per_carton": product.qty_per_carton,
                    "carton_count": effective_carton_count,
                    "net_weight": round(row_net_weight, 3),
                    "gross_weight": round(row_gross_weight, 3),
                    "volume": round(row_volume, 4),
                })

    logger.info("装箱单数据展平完成: 共 %d 行", len(rows))
    return rows


# ==================== PackingGenerator 类 ====================


class PackingGenerator:
    """装箱单生成器.

    负责将 OrderData 填充到装箱单 XLSX 模板中，产出最终装箱单文件。

    使用方式：
        gen = PackingGenerator()
        output_path = gen.generate(order, output_dir, progress_callback)
    """

    def __init__(self, template_path: str | Path | None = None):
        """初始化装箱单生成器.

        Args:
            template_path: 装箱单模板路径，默认使用 config/constants 中的路径.
        """
        self._template_path: Path = (
            Path(template_path) if template_path else TEMPLATE_PACKING_PATH
        )

    # ---- 公开 API ----

    def generate(
        self,
        order: OrderData,
        output_dir: str | Path | None = None,
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> Path:
        """生成装箱单文件.

        完整流程：
        1. 校验 order 非空
        2. 展平数据
        3. 沙箱复制模板
        4. 锚点扫描
        5. 行数调整（扩容/缩容）
        6. 填充表头
        7. 填充明细行
        8. 更新汇总公式
        9. 保存到输出目录

        Args:
            order: 订单数据.
            output_dir: 输出目录，默认为 config/constants.OUTPUT_DIR.
            progress_callback: 进度回调，签名为 (step_description: str, progress: float 0-1).

        Returns:
            生成的装箱单文件路径.

        Raises:
            ValueError: 订单数据无效时抛出.
            FileNotFoundError: 模板文件不存在时抛出.
        """
        # ---- 步骤 0：入口断言 ----
        if order is None:
            raise ValueError("[错误]: 订单数据为 None, 无法生成装箱单")
        if not order.pallets:
            raise ValueError("[错误]: 订单无托盘数据, 无法生成装箱单")

        # ---- 步骤 1：展平数据 ----
        self._report_progress(progress_callback, "正在解析订单数据...", 0.05)
        rows: list[dict] = flatten_for_packing(order)
        target_row_count: int = len(rows)

        logger.info(
            "开始生成装箱单: 发票号=%s, 托盘数=%d, 明细行数=%d",
            order.order_meta.invoice_no,
            len(order.pallets),
            target_row_count,
        )

        # ---- 步骤 2：沙箱复制模板到临时目录 ----
        self._report_progress(progress_callback, "正在准备模板...", 0.10)
        sandbox_path: Path = self._create_sandbox_copy()

        try:
            wb = openpyxl.load_workbook(sandbox_path)
            ws: Worksheet = wb.active if wb.active else wb.worksheets[0]

            # ---- 步骤 3：锚点扫描 ----
            self._report_progress(progress_callback, "正在扫描模板锚点...", 0.15)
            anchor: AnchorResult = scan_packing_template(ws)

            if not anchor.is_valid:
                error_details: str = "; ".join(anchor.errors)
                raise ValueError(
                    f"[错误]: 装箱单模板锚点扫描失败\n"
                    f"[原因]: {error_details}\n"
                    f"[排查]: 请确认模板文件是否与原厂一致，"
                    f"或从 src/assets/backup_templates/ 恢复出厂模板"
                )

            logger.info(
                "锚点扫描成功: data_start=%d, data_end=%d, summary=%d",
                anchor.data_start_row, anchor.data_end_row, anchor.summary_row,
            )

            # ---- 步骤 4：行数调整 ----
            self._report_progress(progress_callback, "正在调整数据行数...", 0.20)
            new_data_end: int = resize_data_rows(
                ws,
                anchor.data_start_row,
                anchor.data_end_row,
                target_row_count,
                anchor.data_start_row,
            )
            logger.info("数据行调整完成: 新结束行=%d", new_data_end)

            # ---- 步骤 5：填充表头 ----
            self._report_progress(progress_callback, "正在填充表头信息...", 0.30)
            self._fill_header(ws, order)

            # ---- 步骤 6：填充明细行 ----
            self._report_progress(progress_callback, "正在填充商品明细...", 0.40)
            self._fill_data_rows(ws, anchor.data_start_row, rows, anchor)

            # ---- 步骤 7：更新汇总公式 ----
            self._report_progress(progress_callback, "正在更新汇总公式...", 0.80)
            self._fix_summary_formulas(ws, anchor, new_data_end)

            # ---- 步骤 8：保存到输出目录 ----
            self._report_progress(progress_callback, "正在保存文件...", 0.90)
            output_path: Path = self._resolve_output_path(order, output_dir)
            wb.save(output_path)
            wb.close()

            logger.info("装箱单已生成: %s", output_path)
            self._report_progress(progress_callback, "装箱单生成完成", 1.0)

            return output_path

        except Exception:
            # 确保出错时关闭工作簿
            try:
                wb.close()
            except Exception:
                pass
            raise
        finally:
            # 清理沙箱临时文件
            self._cleanup_sandbox(sandbox_path)

    # ---- 私有方法 ----

    def _create_sandbox_copy(self) -> Path:
        """在临时目录创建模板的沙箱副本.

        Returns:
            沙箱副本的路径.

        Raises:
            FileNotFoundError: 模板文件不存在时抛出.
        """
        if not self._template_path.exists():
            raise FileNotFoundError(
                f"[错误]: 装箱单模板文件不存在: {self._template_path}\n"
                f"[原因]: 模板文件可能被删除、移动或改名\n"
                f"[排查]: 请将 template_packing.xlsx 放入 templates/ 目录"
            )

        temp_dir: str = tempfile.gettempdir()
        sandbox_name: str = f"packing_sandbox_{id(self)}.xlsx"
        sandbox_path: Path = Path(temp_dir) / sandbox_name
        shutil.copy2(self._template_path, sandbox_path)
        logger.debug("沙箱副本已创建: %s", sandbox_path)
        return sandbox_path

    @staticmethod
    def _cleanup_sandbox(sandbox_path: Path) -> None:
        """清理沙箱临时文件."""
        try:
            if sandbox_path.exists():
                sandbox_path.unlink(missing_ok=True)
                logger.debug("沙箱副本已清理: %s", sandbox_path)
        except Exception as e:
            logger.warning("[警告]: 清理沙箱文件失败: %s — %s", sandbox_path, e)

    def _fill_header(self, ws: Worksheet, order: OrderData) -> None:
        """填充装箱单表头信息.

        实际模板结构（基于 template_packing.xlsx 实测）：
        - D3:K3：客户抬头（合并单元格区域）
        - A4:C4："Invoice No. 发票号"（合并），后方填发票号
        - F4:H4："Date日期:"（合并），后方填日期
        - A5:C5："Contact No. 合同号"（合并），后方填合同号
        - F5:H5："Payment付款方式:"（合并），后方填付款方式
        - A6:C6："Country of origin产地:"（合并），后方填产地
        - F6:H6："Destination 目的地:"（合并），后方填目的地

        注意：使用 safe_write_cell，MergedCell 会被自动重定向到合并区域左上角.
        """
        customer_name: str = (
            order.customer.company_name_en or order.customer.company_name_cn
        )
        # D3:K3 合并区域 - 客户抬头
        safe_write_cell(ws, 3, "D", customer_name)

        # A4:C4 合并区域 - 发票号（追加在标签后）
        safe_write_cell(ws, 4, "A",
                        f"Invoice No. 发票号: {order.order_meta.invoice_no}")
        # F4:H4 合并区域 - 日期
        safe_write_cell(ws, 4, "F",
                        f"Date日期: {order.order_meta.date}")

        # A5:C5 合并区域 - 合同号
        safe_write_cell(ws, 5, "A",
                        f"Contact No. 合同号: {order.order_meta.contract_no}")
        # F5:H5 合并区域 - 付款方式
        safe_write_cell(ws, 5, "F",
                        f"Payment付款方式: {order.order_meta.payment_term}")

        # A6:C6 合并区域 - 产地
        safe_write_cell(ws, 6, "A",
                        f"Country of origin产地: {order.order_meta.country_of_origin}")
        # F6:H6 合并区域 - 目的地
        destination: str = order.customer.destination or order.customer.country
        safe_write_cell(ws, 6, "F",
                        f"Destination 目的地: {destination}")

        logger.info("装箱单表头填充完成")

    def _fill_data_rows(
        self,
        ws: Worksheet,
        data_start_row: int,
        rows: list[dict],
        anchor: AnchorResult,
    ) -> None:
        """逐行填充商品明细.

        实际模板列映射 (基于 template_packing.xlsx 实测):
        A=seq_no(No.), B:C=product_name(Item Description, 合并),
        D=specification(Spec.), E=unit(Unit),
        F=qty_per_carton(QTY./Ctn), G=package_no(Package No.),
        H=pallet_no(Pallet No.), I=net_weight(N.W./Kg),
        J=gross_weight(G.W/kg), K=volume(Volume/M3)

        注意：本模板中 G 列 = Package No.（包号），没有直接的"箱数"列。
        我们将 carton_count 写入 G 列（Package No.），这与真实订单数据中
        将此列用于表示箱数的方法一致。

        Args:
            ws: 装箱单工作表.
            data_start_row: 数据起始行号.
            rows: 展平后的行数据列表.
            anchor: 锚点扫描结果.
        """
        for idx, row_data in enumerate(rows):
            target_row: int = data_start_row + idx

            # A: 序号 (No.)
            safe_write_cell(ws, target_row, "A", row_data["seq_no"])
            # B: 商品名称 (Item Description), 合并列 B:C 只写入 B 列
            safe_write_cell(ws, target_row, "B", row_data["product_name"])
            # D: 规格 (Spec.)
            safe_write_cell(ws, target_row, "D", row_data["specification"])
            # E: 单位 (Unit)
            safe_write_cell(ws, target_row, "E", row_data["unit"])
            # F: 每箱数量 (QTY. / Ctn)
            safe_write_cell(ws, target_row, "F", row_data["qty_per_carton"])
            # G: 箱数 (Package No. 列 — 模板实际将此列用于表示箱数)
            safe_write_cell(ws, target_row, "G", row_data["carton_count"])
            # H: 托盘号 (Pallet No.)
            safe_write_cell(ws, target_row, "H", row_data["pallet_no"])
            # I: 净重 kg (N.W./Kg) — 不保留旧 number_format，避免时间/日期格式
            safe_write_cell(ws, target_row, "I", row_data["net_weight"], preserve_style=True)
            # 写入数值后强制清除可能遗留的非数值格式
            cell_i = ws.cell(row=target_row, column=9)
            if cell_i.value is not None and isinstance(cell_i.value, (int, float)):
                cell_i.number_format = "0.000"
            # J: 毛重 kg (G.W/kg)
            safe_write_cell(ws, target_row, "J", row_data["gross_weight"], preserve_style=True)
            cell_j = ws.cell(row=target_row, column=10)
            if cell_j.value is not None and isinstance(cell_j.value, (int, float)):
                cell_j.number_format = "0.000"
            # K: 体积 m³ (Volume/M3)
            safe_write_cell(ws, target_row, "K", row_data["volume"], preserve_style=True)
            cell_k = ws.cell(row=target_row, column=11)
            if cell_k.value is not None and isinstance(cell_k.value, (int, float)):
                cell_k.number_format = "0.0000"

        logger.info(
            "装箱单明细填充完成: %d 行 (第 %d 行 → 第 %d 行)",
            len(rows), data_start_row, data_start_row + len(rows) - 1,
        )

    def _fix_summary_formulas(
        self, ws: Worksheet, anchor: AnchorResult, new_data_end: int
    ) -> None:
        """修正汇总行的 SUM 公式范围.

        模板汇总行（第 58 行）实际公式列：
        G58=SUM(G8:G57) → 总箱数（Package No. 列之和）
        I58=SUM(I8:I57) → 总净重
        J58=SUM(J8:J57) → 总毛重
        K58=SUM(K8:K57) → 总体积

        Args:
            ws: 装箱单工作表.
            anchor: 锚点扫描结果.
            new_data_end: 新的数据结束行号.
        """
        # 仅修正实际存在 SUM 公式的列
        formula_columns: list[str] = ["G", "I", "J", "K"]

        for col_letter in formula_columns:
            update_sum_formula(
                ws, col_letter, anchor.data_start_row, new_data_end
            )

        logger.info("汇总公式已修正: 范围 %d→%d", anchor.data_start_row, new_data_end)

    def _resolve_output_path(
        self, order: OrderData, output_dir: str | Path | None
    ) -> Path:
        """确定输出文件路径.

        命名规则：{输出目录}/装箱单_{发票号}.xlsx

        Args:
            order: 订单数据.
            output_dir: 指定输出目录，None 则使用默认.

        Returns:
            输出文件路径（确保父目录存在）.
        """
        out_dir: Path = Path(output_dir) if output_dir else OUTPUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)

        invoice_no: str = order.order_meta.invoice_no.replace("/", "-").replace("\\", "-")
        filename: str = f"{FILE_PREFIX_MAP['packing']}_{invoice_no}.xlsx"
        return out_dir / filename

    @staticmethod
    def _report_progress(
        callback: Callable[[str, float], None] | None,
        description: str,
        progress: float,
    ) -> None:
        """安全的进度回调."""
        if callback:
            try:
                callback(description, progress)
            except Exception as e:
                logger.warning("[警告]: 进度回调执行失败: %s", e)


# ========== 运行说明 ==========
# 依赖安装: pip install openpyxl msgspec
# 运行命令: 由 orchestrator 统一调用，不直接运行此模块
# 测试命令: python -m pytest tests/test_packing_generator.py -v
# =============================
