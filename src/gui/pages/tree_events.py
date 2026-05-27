# -*- coding: utf-8 -*-
"""树状编辑器 — 事件处理 mixin.

包含生成、导入 Excel、清空等按钮事件处理方法。
"""

from __future__ import annotations

import logging
from tkinter import messagebox
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.gui.pages.tree_editor_page import TreeEditorPage

logger = logging.getLogger(__name__)


class TreeEventsMixin:
    """树状编辑器的事件处理方法.

    作为 mixin 混入 TreeEditorPage，假设 self 提供以下属性：
    - self._pallets, self._product_seq
    - self.app（来自 PageBase）
    - self._refresh_tree(), self._update_stats(), self._clear_selection()（来自 TreeDataMixin）
    - self._clear_detail_frame()（来自 TreeUIMixin）
    - self.build_order_data()（来自 TreeDataMixin）
    """

    _pallets: list[dict[str, Any]]
    _product_seq: int
    app: object

    # ==================== 事件处理 ====================

    def _on_generate(self: TreeEditorPage) -> None:
        """点击一键生成按钮."""
        if not self._pallets:
            messagebox.showwarning("无商品数据", "请至少添加一个托盘和商品后再生成。")
            return

        empty_products: list[str] = []
        for p in self._pallets:
            for c in p.get("cartons", []):
                for pr in c.get("products", []):
                    if not pr.get("product_name", "").strip() or not pr.get("hs_code", "").strip():
                        empty_products.append(
                            f"托盘#{p.get('pallet_no')} 纸箱{c.get('carton_label')} 商品#{pr.get('seq_no')}"
                        )

        if empty_products:
            if not messagebox.askyesno(
                "商品信息不完整",
                f"以下 {len(empty_products)} 个商品缺少名称或 HS 编码：\n\n"
                f"  • {'\n  • '.join(empty_products[:5])}"
                f"{'  ...还有 ' + str(len(empty_products) - 5) + ' 个' if len(empty_products) > 5 else ''}"
                f"\n\n是否仍要继续生成？",
            ):
                return

        order = self.build_order_data()
        if order is None:
            return

        self.app.current_order = order
        self.app.switch_page("generate")

    def _on_import_excel(self: TreeEditorPage) -> None:
        """从 Excel 导入商品明细."""
        from tkinter import filedialog

        from src.importer.excel_importer import import_order_from_excel

        file_path: str = filedialog.askopenfilename(
            title="选择订单 Excel 文件",
            filetypes=[("Excel 文件", "*.xlsx *.xls"), ("所有文件", "*.*")],
        )

        if not file_path:
            return

        try:
            order, _ = import_order_from_excel(file_path)

            if order is None:
                messagebox.showerror("导入失败", "Excel 文件解析失败。")
                return

            self._pallets = []
            self._product_seq = 1

            for pallet in order.pallets:
                p_data = {
                    "pallet_no": pallet.pallet_no,
                    "length_m": pallet.length_m,
                    "width_m": pallet.width_m,
                    "height_m": pallet.height_m,
                    "pallet_weight_kg": pallet.pallet_weight_kg,
                    "cartons": [],
                }
                for carton in pallet.cartons:
                    c_data = {
                        "carton_label": carton.carton_label,
                        "is_batch": carton.is_batch,
                        "batch_count": carton.batch_count,
                        "length_cm": carton.length_cm,
                        "width_cm": carton.width_cm,
                        "height_cm": carton.height_cm,
                        "gross_weight_kg": carton.gross_weight_kg,
                        "products": [],
                    }
                    for product in carton.products:
                        pr_data = {
                            "seq_no": self._product_seq,
                            "product_name": product.product_name,
                            "specification": product.specification,
                            "hs_code": product.hs_code,
                            "declaration_elements": product.declaration_elements,
                            "unit": product.unit,
                            "qty_per_carton": product.qty_per_carton,
                            "unit_price": product.unit_price,
                            "currency": product.currency,
                            "net_weight_per_unit_kg": product.net_weight_per_unit_kg,
                            "destination_country": product.destination_country,
                        }
                        self._product_seq += 1
                        c_data["products"].append(pr_data)
                    p_data["cartons"].append(c_data)
                self._pallets.append(p_data)

            self._refresh_tree()
            self._update_stats()
            self.app.current_order = order

            messagebox.showinfo(
                "导入成功",
                f"商品明细已导入。\n\n"
                f"托盘: {len(self._pallets)} | "
                f"纸箱: {sum(len(p['cartons']) for p in self._pallets)} | "
                f"商品: {self._product_seq - 1}",
            )

        except Exception as e:
            logger.exception("[错误]: Excel 导入失败")
            messagebox.showerror("导入失败", f"[错误]: {e}")

    def _on_clear_all(self: TreeEditorPage) -> None:
        """清空所有托盘和商品."""
        if not self._pallets:
            return
        if messagebox.askyesno("确认清空", "确定要清空所有托盘、纸箱和商品数据吗？此操作不可撤销。"):
            self._pallets = []
            self._product_seq = 1
            self._clear_selection()
            self._refresh_tree()
            self._update_stats()
            self._clear_detail_frame()
            self.app.set_status("已清空所有商品数据")
