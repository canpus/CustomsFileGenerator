# -*- coding: utf-8 -*-
"""树状编辑器 — 详情面板 mixin.

包含选中节点后右侧详情表单的显示、字段构建与保存方法。
"""

from __future__ import annotations

import logging
from tkinter import messagebox
from typing import TYPE_CHECKING, Any

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

if TYPE_CHECKING:
    from src.gui.pages.tree_editor_page import TreeEditorPage

logger = logging.getLogger(__name__)


class TreeDetailMixin:
    """详情面板方法 mixin.

    假设 self 提供：
    - self._pallets, self._detail_frame, self._detail_vars, self._detail_title_var
    - self._selected_* 系列属性
    - self.app（来自 PageBase）
    - self._add_carton(), self._add_product()（来自 TreeDataMixin）
    - self._refresh_tree(), self._update_stats()（来自 TreeDataMixin）
    """

    _pallets: list[dict[str, Any]]
    _detail_frame: ttk.Frame | None
    _detail_vars: dict[str, Any]
    _detail_title_var: ttk.StringVar
    _selected_pallet_idx: int
    _selected_carton_idx: int
    _selected_product_idx: int
    app: object

    # ==================== 详情表单展示 ====================

    def _show_pallet_detail(self: TreeEditorPage) -> None:
        """显示托盘详情表单."""
        self._clear_detail_frame()

        idx = self._selected_pallet_idx
        if idx < 0 or idx >= len(self._pallets):
            return

        pallet = self._pallets[idx]
        self._detail_title_var.set(f"📦 托盘 #{pallet.get('pallet_no', '?')} 属性")

        self._add_detail_field("托盘编号", "pallet_no", str(pallet.get("pallet_no", "")))
        self._add_detail_field("长度 (m)", "length_m", str(pallet.get("length_m", "")))
        self._add_detail_field("宽度 (m)", "width_m", str(pallet.get("width_m", "")))
        self._add_detail_field("高度 (m)", "height_m", str(pallet.get("height_m", "")))
        self._add_detail_field("托盘自重 (kg)", "pallet_weight_kg", str(pallet.get("pallet_weight_kg", "0")))

        self._add_save_button("pallet", idx)

        ttk.Button(
            self._detail_frame,
            text="+ 在此托盘下新增纸箱",
            bootstyle="info-outline",
            command=lambda: self._add_carton(),
        ).pack(padx=15, pady=(10, 5), fill=X)

    def _show_carton_detail(self: TreeEditorPage) -> None:
        """显示纸箱详情表单."""
        self._clear_detail_frame()

        pi, ci = self._selected_pallet_idx, self._selected_carton_idx
        if pi < 0 or pi >= len(self._pallets):
            return

        cartons = self._pallets[pi].get("cartons", [])
        if ci < 0 or ci >= len(cartons):
            return

        carton = cartons[ci]
        self._detail_title_var.set(f"📋 纸箱 {carton.get('carton_label', '?')} 属性")

        self._add_detail_field("纸箱标签", "carton_label", str(carton.get("carton_label", "")))
        self._add_detail_checkbox("批量纸箱", "is_batch", carton.get("is_batch", False))
        self._add_detail_field("批量数量", "batch_count", str(carton.get("batch_count", 1)))
        self._add_detail_field("长度 (cm)", "length_cm", str(carton.get("length_cm", "")))
        self._add_detail_field("宽度 (cm)", "width_cm", str(carton.get("width_cm", "")))
        self._add_detail_field("高度 (cm)", "height_cm", str(carton.get("height_cm", "")))
        self._add_detail_field("毛重 (kg)", "gross_weight_kg", str(carton.get("gross_weight_kg", "")))

        self._add_save_button("carton", pi, ci)

        ttk.Button(
            self._detail_frame,
            text="+ 在此纸箱下新增商品",
            bootstyle="info-outline",
            command=lambda: self._add_product(),
        ).pack(padx=15, pady=(10, 5), fill=X)

    def _show_product_detail(self: TreeEditorPage) -> None:
        """显示商品详情表单."""
        self._clear_detail_frame()

        pi, ci, pri = self._selected_pallet_idx, self._selected_carton_idx, self._selected_product_idx
        if pi < 0 or pi >= len(self._pallets):
            return

        cartons = self._pallets[pi].get("cartons", [])
        if ci < 0 or ci >= len(cartons):
            return

        products = cartons[ci].get("products", [])
        if pri < 0 or pri >= len(products):
            return

        product = products[pri]
        self._detail_title_var.set(f"📄 商品 #{product.get('seq_no', '?')} 属性")

        self._add_detail_field("序号", "seq_no", str(product.get("seq_no", "")))
        self._add_detail_field("商品名称 *", "product_name", str(product.get("product_name", "")))
        self._add_detail_field("规格型号", "specification", str(product.get("specification", "")))
        self._add_detail_field("HS 编码 *", "hs_code", str(product.get("hs_code", "")))
        self._add_detail_field("申报要素", "declaration_elements", str(product.get("declaration_elements", "")))
        self._add_detail_field("计量单位", "unit", str(product.get("unit", "Roll")))
        self._add_detail_field("每箱数量", "qty_per_carton", str(product.get("qty_per_carton", "1")))
        self._add_detail_field("单价 (USD)", "unit_price", str(product.get("unit_price", "0")))
        self._add_detail_field("币种", "currency", str(product.get("currency", "USD")))
        self._add_detail_field("单件净重 (kg)", "net_weight_per_unit_kg", str(product.get("net_weight_per_unit_kg", "0")))
        self._add_detail_field("目的国", "destination_country", str(product.get("destination_country", "")))

        self._add_save_button("product", pi, ci, pri)

    # ==================== 详情框架工具方法 ====================

    def _clear_detail_frame(self: TreeEditorPage) -> None:
        """清空详情框架."""
        if self._detail_frame is None:
            return
        self._detail_vars.clear()
        for widget in self._detail_frame.winfo_children():
            widget.destroy()

    def _add_detail_field(self: TreeEditorPage, label: str, key: str, value: str) -> None:
        """添加详情字段."""
        if self._detail_frame is None:
            return

        row = ttk.Frame(self._detail_frame)
        row.pack(fill=X, padx=15, pady=3)

        ttk.Label(row, text=label, font=self.app.get_font(size=10), width=20, anchor=W).pack(side=LEFT)

        var = ttk.StringVar(value=value)
        entry = ttk.Entry(row, textvariable=var)
        entry.pack(side=LEFT, fill=X, expand=YES, padx=(5, 0))
        self._detail_vars[key] = var

    def _add_detail_checkbox(self: TreeEditorPage, label: str, key: str, checked: bool) -> None:
        """添加详情复选框."""
        if self._detail_frame is None:
            return

        row = ttk.Frame(self._detail_frame)
        row.pack(fill=X, padx=15, pady=3)

        ttk.Label(row, text=label, font=self.app.get_font(size=10), width=20, anchor=W).pack(side=LEFT)

        var = ttk.IntVar(value=1 if checked else 0)
        cb = ttk.Checkbutton(row, variable=var, bootstyle="primary-round-toggle")
        cb.pack(side=LEFT, padx=(5, 0))
        self._detail_vars[key] = var

    def _add_save_button(self: TreeEditorPage, level: str, pi: int, ci: int = -1, pri: int = -1) -> None:
        """添加保存按钮."""
        if self._detail_frame is None:
            return

        ttk.Separator(self._detail_frame, orient=HORIZONTAL).pack(fill=X, padx=10, pady=(10, 5))

        ttk.Button(
            self._detail_frame,
            text="💾 保存修改",
            bootstyle="success",
            command=lambda: self._save_detail(level, pi, ci, pri),
        ).pack(padx=15, pady=(0, 10), fill=X)

    def _save_detail(self: TreeEditorPage, level: str, pi: int, ci: int = -1, pri: int = -1) -> None:
        """保存详情修改."""
        try:
            if level == "pallet":
                target = self._pallets[pi]
            elif level == "carton":
                target = self._pallets[pi]["cartons"][ci]
            elif level == "product":
                target = self._pallets[pi]["cartons"][ci]["products"][pri]
            else:
                return

            for key, var in self._detail_vars.items():
                if isinstance(var, ttk.IntVar):
                    target[key] = bool(var.get())
                else:
                    val = var.get().strip()
                    if key in (
                        "length_m", "width_m", "height_m", "pallet_weight_kg",
                        "length_cm", "width_cm", "height_cm", "gross_weight_kg",
                        "unit_price", "qty_per_carton", "net_weight_per_unit_kg",
                    ):
                        try:
                            target[key] = float(val) if val else 0.0
                        except ValueError:
                            target[key] = 0.0
                    elif key in ("seq_no", "batch_count", "pallet_no"):
                        try:
                            target[key] = int(val) if val else 0
                        except ValueError:
                            target[key] = 0
                    else:
                        target[key] = val

            self._refresh_tree()
            self._update_stats()
            self.app.set_status(f"已保存 {level} 修改")
            logger.info("保存 %s 修改: pi=%d, ci=%d, pri=%d", level, pi, ci, pri)

        except Exception as e:
            logger.exception("[错误]: 保存详情失败")
            messagebox.showerror("保存失败", f"[错误]: 保存修改失败\n[原因]: {e}")
