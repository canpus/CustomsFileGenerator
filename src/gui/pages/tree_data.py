# -*- coding: utf-8 -*-
"""树状编辑器 — 数据操作 mixin.

包含节点增删克隆、Treeview 刷新、统计更新、展开/折叠。
数据导出（build_order_data）见 tree_export.py。
"""

from __future__ import annotations

import copy
import logging
from tkinter import messagebox
from typing import TYPE_CHECKING, Any

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

if TYPE_CHECKING:
    from src.gui.pages.tree_editor_page import TreeEditorPage

logger = logging.getLogger(__name__)


class TreeDataMixin:
    """树状编辑器的数据操作方法.

    假设 self 提供：
    - self._pallets, self._tree, self._product_seq
    - self._selected_* 系列属性
    - self._stats_var
    - self.app（来自 PageBase）
    - self._clear_detail_frame()（来自 TreeDetailMixin）
    - self.build_order_data()（来自 TreeExportMixin）
    """

    _pallets: list[dict[str, Any]]
    _tree: ttk.Treeview | None
    _product_seq: int
    _selected_pallet_idx: int
    _selected_carton_idx: int
    _selected_product_idx: int
    _selected_level: str
    _stats_var: ttk.StringVar
    app: object

    # ==================== 数据操作 ====================

    def _add_pallet(self: TreeEditorPage, data: dict[str, Any] | None = None) -> None:
        """新增托盘."""
        if data is None:
            pallet_no = len(self._pallets) + 1
            data = {
                "pallet_no": pallet_no,
                "length_m": 1.16, "width_m": 1.01, "height_m": 1.97,
                "pallet_weight_kg": 0.0, "cartons": [],
            }
        else:
            data = copy.deepcopy(data)
            data["pallet_no"] = len(self._pallets) + 1
            for c in data.get("cartons", []):
                for p in c.get("products", []):
                    p["seq_no"] = self._product_seq
                    self._product_seq += 1

        self._pallets.append(data)
        self._refresh_tree()
        self._update_stats()
        logger.info("新增托盘 #%d", data["pallet_no"])

    def _add_carton(self: TreeEditorPage, data: dict[str, Any] | None = None) -> None:
        """在当前选中的托盘下新增纸箱."""
        if self._selected_pallet_idx < 0:
            messagebox.showinfo("提示", "请先在左侧选择一个托盘，再新增纸箱。")
            return

        if data is None:
            data = {
                "carton_label": str(len(self._pallets[self._selected_pallet_idx]["cartons"]) + 1),
                "is_batch": False, "batch_count": 1,
                "length_cm": 32.0, "width_cm": 32.0, "height_cm": 34.0,
                "gross_weight_kg": 23.3, "products": [],
            }
        else:
            data = copy.deepcopy(data)
            data["carton_label"] = str(len(self._pallets[self._selected_pallet_idx]["cartons"]) + 1)
            for p in data.get("products", []):
                p["seq_no"] = self._product_seq
                self._product_seq += 1

        self._pallets[self._selected_pallet_idx]["cartons"].append(data)
        self._refresh_tree()
        self._update_stats()

    def _add_product(self: TreeEditorPage, data: dict[str, Any] | None = None) -> None:
        """在当前选中的纸箱下新增商品."""
        if self._selected_pallet_idx < 0 or self._selected_carton_idx < 0:
            messagebox.showinfo("提示", "请先在左侧选择一个纸箱，再新增商品。")
            return

        if data is None:
            seq = self._product_seq
            self._product_seq += 1
            data = {
                "seq_no": seq, "product_name": "", "specification": "",
                "hs_code": "", "declaration_elements": "",
                "unit": "Roll", "qty_per_carton": 1.0, "unit_price": 0.0,
                "currency": "USD", "net_weight_per_unit_kg": 0.0,
                "destination_country": "",
            }
        else:
            data = copy.deepcopy(data)
            data["seq_no"] = self._product_seq
            self._product_seq += 1

        cartons = self._pallets[self._selected_pallet_idx]["cartons"]
        cartons[self._selected_carton_idx]["products"].append(data)
        self._refresh_tree()
        self._update_stats()

    def _on_clone(self: TreeEditorPage) -> None:
        """克隆当前选中的节点."""
        if self._selected_level == "pallet" and self._selected_pallet_idx >= 0:
            src = self._pallets[self._selected_pallet_idx]
            self._add_pallet(src)
            messagebox.showinfo("克隆成功", f"已克隆托盘 #{src['pallet_no']}（含其下所有纸箱和商品）")

        elif self._selected_level == "carton" and self._selected_pallet_idx >= 0 and self._selected_carton_idx >= 0:
            src = self._pallets[self._selected_pallet_idx]["cartons"][self._selected_carton_idx]
            self._add_carton(src)
            messagebox.showinfo("克隆成功", "已克隆纸箱（含其中所有商品）")

        elif self._selected_level == "product" and self._selected_pallet_idx >= 0 and self._selected_carton_idx >= 0 and self._selected_product_idx >= 0:
            src = self._pallets[self._selected_pallet_idx]["cartons"][self._selected_carton_idx]["products"][self._selected_product_idx]
            self._add_product(src)
            messagebox.showinfo("克隆成功", "已克隆商品")

    def _on_delete_node(self: TreeEditorPage) -> None:
        """删除当前选中的节点."""
        if self._selected_level == "pallet" and self._selected_pallet_idx >= 0:
            pallet = self._pallets[self._selected_pallet_idx]
            if messagebox.askyesno("确认删除", f"确定要删除托盘 #{pallet['pallet_no']} 及其下所有纸箱和商品吗？"):
                del self._pallets[self._selected_pallet_idx]
                self._clear_selection()
                self._refresh_tree()
                self._update_stats()

        elif self._selected_level == "carton" and self._selected_pallet_idx >= 0 and self._selected_carton_idx >= 0:
            carton = self._pallets[self._selected_pallet_idx]["cartons"][self._selected_carton_idx]
            if messagebox.askyesno("确认删除", f"确定要删除纸箱 {carton['carton_label']} 及其下所有商品吗？"):
                del self._pallets[self._selected_pallet_idx]["cartons"][self._selected_carton_idx]
                self._clear_selection()
                self._refresh_tree()
                self._update_stats()

        elif self._selected_level == "product" and self._selected_pallet_idx >= 0 and self._selected_carton_idx >= 0 and self._selected_product_idx >= 0:
            products = self._pallets[self._selected_pallet_idx]["cartons"][self._selected_carton_idx]["products"]
            product = products[self._selected_product_idx]
            if messagebox.askyesno("确认删除", f"确定要删除商品 #{product['seq_no']} ({product.get('product_name', '未命名')}) 吗？"):
                del products[self._selected_product_idx]
                self._clear_selection()
                self._refresh_tree()
                self._update_stats()

    def _clear_selection(self: TreeEditorPage) -> None:
        """清除选中状态."""
        self._selected_pallet_idx = -1
        self._selected_carton_idx = -1
        self._selected_product_idx = -1
        self._selected_level = ""

    # ==================== Treeview 刷新 ====================

    def _refresh_tree(self: TreeEditorPage) -> None:
        """根据 _pallets 数据重建 Treeview."""
        if self._tree is None:
            return

        for item in self._tree.get_children():
            self._tree.delete(item)

        for pi, pallet in enumerate(self._pallets):
            pallet_id = f"p_{pi}"
            vol = pallet.get("length_m", 0) * pallet.get("width_m", 0) * pallet.get("height_m", 0)
            self._tree.insert(
                "", END, iid=pallet_id,
                text=f"📦 托盘 #{pallet.get('pallet_no', '?')}",
                values=(f"体积: {vol:.3f} m³", f"自重: {pallet.get('pallet_weight_kg', 0)} kg"),
                open=True,
            )

            for ci, carton in enumerate(pallet.get("cartons", [])):
                carton_id = f"p_{pi}_c_{ci}"
                label = carton.get("carton_label", "?")
                batch_info = f" × {carton.get('batch_count', 1)}" if carton.get("is_batch") else ""
                self._tree.insert(
                    pallet_id, END, iid=carton_id,
                    text=f"📋 纸箱 {label}{batch_info}",
                    values=(f"毛重: {carton.get('gross_weight_kg', 0)} kg",
                            f"尺寸: {carton.get('length_cm',0)}×{carton.get('width_cm',0)}×{carton.get('height_cm',0)} cm"),
                    open=False,
                )

                for pri, product in enumerate(carton.get("products", [])):
                    product_id = f"p_{pi}_c_{ci}_pr_{pri}"
                    self._tree.insert(
                        carton_id, END, iid=product_id,
                        text=f"📄 #{product.get('seq_no', '?')} {product.get('product_name', '未命名')[:20]}",
                        values=(f"HS: {product.get('hs_code', '?')}", f"单价: ${product.get('unit_price', 0):.2f}"),
                        open=False,
                    )

        for i, p in enumerate(self._pallets):
            p["pallet_no"] = i + 1

    def _update_stats(self: TreeEditorPage) -> None:
        """更新统计信息."""
        total_pallets = len(self._pallets)
        total_cartons = sum(len(p.get("cartons", [])) for p in self._pallets)
        total_products = sum(
            len(c.get("products", []))
            for p in self._pallets
            for c in p.get("cartons", [])
        )
        self._stats_var.set(f"托盘: {total_pallets} | 纸箱: {total_cartons} | 商品: {total_products}")

    def _expand_all(self: TreeEditorPage) -> None:
        """展开所有节点."""
        if self._tree is None:
            return
        for item in self._tree.get_children():
            self._tree.item(item, open=True)
            for child in self._tree.get_children(item):
                self._tree.item(child, open=True)

    def _collapse_all(self: TreeEditorPage) -> None:
        """折叠所有节点."""
        if self._tree is None:
            return
        for item in self._tree.get_children():
            self._tree.item(item, open=False)
            for child in self._tree.get_children(item):
                self._tree.item(child, open=False)
