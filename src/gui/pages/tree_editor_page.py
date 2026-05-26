# -*- coding: utf-8 -*-
"""托盘-纸箱-商品树状编辑器 — 阶段 9.3.

提供：
- 左侧 Treeview 显示三级结构（托盘 → 纸箱 → 商品）
- 选中节点时右侧显示对应属性表单
- 右键菜单：新增/克隆/删除 节点
- 支持批量纸箱输入（is_batch + batch_count）
- 底部操作栏：生成报关资料 / 返回上一步
"""

from __future__ import annotations

import copy
import logging
from tkinter import messagebox
from typing import Any

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

logger = logging.getLogger(__name__)

try:
    from src.gui.app import PageBase, GuiApp
except ImportError:
    PageBase = object
    GuiApp = object


class TreeEditorPage(PageBase):
    """托盘-纸箱-商品树状编辑器.

    维护运行时数据结构：
        self._pallets: list[dict] — 托盘列表
            - pallet_no, length_m, width_m, height_m, pallet_weight_kg
            - cartons: list[dict]
                - carton_label, is_batch, batch_count, length_cm, width_cm, height_cm, gross_weight_kg
                - products: list[dict]
                    - seq_no, product_name, specification, hs_code, declaration_elements
                    - unit, qty_per_carton, unit_price, currency
                    - net_weight_per_unit_kg, destination_country
    """

    def __init__(self, parent: ttk.Frame, app: GuiApp):
        """初始化.

        Args:
            parent: 父级容器.
            app: 主应用控制器.
        """
        super().__init__(parent, app)
        # 运行时数据
        self._pallets: list[dict[str, Any]] = []

        # Treeview 相关
        self._tree: ttk.Treeview | None = None
        self._context_menu: ttk.Menu | None = None

        # 右侧属性表单变量
        self._detail_vars: dict[str, ttk.StringVar] = {}
        self._detail_frame: ttk.Frame | None = None

        # 当前选中的节点
        self._selected_node_id: str = ""
        self._selected_level: str = ""  # "pallet" | "carton" | "product"
        self._selected_pallet_idx: int = -1
        self._selected_carton_idx: int = -1
        self._selected_product_idx: int = -1

        # 商品序号计数器
        self._product_seq: int = 1

    # ==================== 构建 UI ====================

    def build(self) -> None:
        """构建树状编辑器 UI."""
        self.frame = ttk.Frame(self.parent)
        self.frame.pack(fill=BOTH, expand=YES, padx=10, pady=10)

        # ---- 顶部标题栏 ----
        title_frame = ttk.Frame(self.frame)
        title_frame.pack(fill=X, padx=5, pady=(5, 10))

        ttk.Label(
            title_frame,
            text="📦 商品明细编辑（托盘 → 纸箱 → 商品）",
            font=self.app.get_heading_font(),
            bootstyle="primary",
        ).pack(side=LEFT)

        # 托盘数量统计
        self._stats_var = ttk.StringVar(value="托盘: 0 | 纸箱: 0 | 商品: 0")
        ttk.Label(
            title_frame,
            textvariable=self._stats_var,
            font=self.app.get_font(size=10),
            bootstyle="secondary",
        ).pack(side=RIGHT)

        # ---- 主内容区（左右分栏） ----
        content_paned = ttk.PanedWindow(self.frame, orient=HORIZONTAL)
        content_paned.pack(fill=BOTH, expand=YES)

        # 左侧：Treeview
        left_frame = ttk.Frame(content_paned)
        content_paned.add(left_frame, weight=2)

        self._build_tree_view(left_frame)

        # 右侧：详情表单
        right_frame = ttk.Frame(content_paned)
        content_paned.add(right_frame, weight=3)

        self._build_detail_panel(right_frame)

        # ---- 底部按钮栏 ----
        bottom = ttk.Frame(self.frame)
        bottom.pack(fill=X, padx=5, pady=(10, 5))

        ttk.Button(
            bottom,
            text="← 返回订单信息",
            bootstyle="secondary-outline",
            command=lambda: self.app.switch_page("order_info"),
        ).pack(side=LEFT)

        ttk.Button(
            bottom,
            text="🗑 清空所有商品",
            bootstyle="danger-outline",
            command=self._on_clear_all,
        ).pack(side=LEFT, padx=(10, 0))

        ttk.Button(
            bottom,
            text="从 Excel 导入商品明细...",
            bootstyle="info-outline",
            command=self._on_import_excel,
        ).pack(side=LEFT, padx=(10, 0))

        ttk.Button(
            bottom,
            text="一键生成报关资料 →",
            bootstyle="success",
            command=self._on_generate,
        ).pack(side=RIGHT)

        # 初始化右键菜单
        self._setup_context_menu()

    def _build_tree_view(self, parent: ttk.Frame) -> None:
        """构建左侧树状视图."""
        # 工具栏
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill=X, pady=(0, 5))

        ttk.Button(
            toolbar,
            text="+ 新增托盘",
            bootstyle="success-outline",
            command=lambda: self._add_pallet(),
        ).pack(side=LEFT, padx=(0, 5))

        ttk.Button(
            toolbar,
            text="展开全部",
            bootstyle="secondary-outline",
            command=lambda: self._expand_all(),
        ).pack(side=LEFT, padx=(0, 5))

        ttk.Button(
            toolbar,
            text="折叠全部",
            bootstyle="secondary-outline",
            command=lambda: self._collapse_all(),
        ).pack(side=LEFT)

        # Treeview + 滚动条
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=BOTH, expand=YES)

        columns = ("field", "value")
        self._tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="tree headings",
            height=20,
        )
        self._tree.heading("#0", text="结构")
        self._tree.heading("field", text="字段")
        self._tree.heading("value", text="值")
        self._tree.column("#0", width=200, stretch=False)
        self._tree.column("field", width=120, stretch=False)
        self._tree.column("value", width=150, stretch=True)

        # 滚动条
        tree_scroll = ttk.Scrollbar(tree_frame, orient=VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=tree_scroll.set)

        self._tree.pack(side=LEFT, fill=BOTH, expand=YES)
        tree_scroll.pack(side=RIGHT, fill=Y)

        # 绑定事件
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._tree.bind("<Button-3>", self._on_right_click)

    def _build_detail_panel(self, parent: ttk.Frame) -> None:
        """构建右侧详情表单面板."""
        # 提示标签
        self._detail_title_var = ttk.StringVar(value="选择左侧节点查看详情")
        ttk.Label(
            parent,
            textvariable=self._detail_title_var,
            font=self.app.get_font(bold=True, size=12),
            bootstyle="primary",
        ).pack(anchor=W, padx=10, pady=(10, 5))

        ttk.Separator(parent, orient=HORIZONTAL).pack(fill=X, padx=5)

        # 可滚动详情区
        canvas = ttk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient=VERTICAL, command=canvas.yview)

        self._detail_frame = ttk.Frame(canvas)
        self._detail_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=self._detail_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=LEFT, fill=BOTH, expand=YES, padx=5)
        scrollbar.pack(side=RIGHT, fill=Y)

        # 绑定鼠标滚轮
        def _on_wheel(event: Any) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # 默认显示提示
        ttk.Label(
            self._detail_frame,
            text="👈 从左侧树中选择一个节点，\n即可在此处查看和编辑详细信息。\n\n"
                 "• 选中托盘 → 编辑托盘尺寸和重量\n"
                 "• 选中纸箱 → 编辑纸箱尺寸和毛重\n"
                 "• 选中商品 → 编辑商品规格和价格",
            font=self.app.get_font(size=10),
            bootstyle="secondary",
            justify=LEFT,
        ).pack(padx=20, pady=20)

    # ==================== 右键菜单 ====================

    def _setup_context_menu(self) -> None:
        """设置右键菜单."""
        self._context_menu = ttk.Menu(self.frame, tearoff=0)
        self._context_menu.add_command(label="➕ 新增托盘", command=lambda: self._add_pallet())
        self._context_menu.add_command(label="➕ 新增纸箱", command=lambda: self._add_carton())
        self._context_menu.add_command(label="➕ 新增商品", command=lambda: self._add_product())
        self._context_menu.add_separator()
        self._context_menu.add_command(label="🐑 克隆当前节点", command=self._on_clone)
        self._context_menu.add_separator()
        self._context_menu.add_command(label="🗑 删除当前节点", command=self._on_delete_node)

    def _on_right_click(self, event: Any) -> None:
        """右键点击事件."""
        item = self._tree.identify_row(event.y)
        if item:
            self._tree.selection_set(item)
            self._on_tree_select(None)
        try:
            self._context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._context_menu.grab_release()

    # ==================== 数据操作 ====================

    def _add_pallet(self, data: dict[str, Any] | None = None) -> None:
        """新增托盘.

        Args:
            data: 已有托盘数据（克隆时用），为 None 则使用默认值.
        """
        if data is None:
            pallet_no = len(self._pallets) + 1
            data = {
                "pallet_no": pallet_no,
                "length_m": 1.16,
                "width_m": 1.01,
                "height_m": 1.97,
                "pallet_weight_kg": 0.0,
                "cartons": [],
            }
        else:
            data = copy.deepcopy(data)
            data["pallet_no"] = len(self._pallets) + 1
            # 重新编号纸箱内的商品
            for c in data.get("cartons", []):
                for p in c.get("products", []):
                    p["seq_no"] = self._product_seq
                    self._product_seq += 1

        self._pallets.append(data)
        self._refresh_tree()
        self._update_stats()
        logger.info("新增托盘 #%d", data["pallet_no"])

    def _add_carton(self, data: dict[str, Any] | None = None) -> None:
        """在当前选中的托盘下新增纸箱.

        Args:
            data: 已有纸箱数据（克隆时用），为 None 则使用默认值.
        """
        if self._selected_pallet_idx < 0:
            messagebox.showinfo("提示", "请先在左侧选择一个托盘，再新增纸箱。")
            return

        if data is None:
            data = {
                "carton_label": str(len(self._pallets[self._selected_pallet_idx]["cartons"]) + 1),
                "is_batch": False,
                "batch_count": 1,
                "length_cm": 32.0,
                "width_cm": 32.0,
                "height_cm": 34.0,
                "gross_weight_kg": 23.3,
                "products": [],
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

    def _add_product(self, data: dict[str, Any] | None = None) -> None:
        """在当前选中的纸箱下新增商品.

        Args:
            data: 已有商品数据（克隆时用），为 None 则使用默认值.
        """
        if self._selected_pallet_idx < 0 or self._selected_carton_idx < 0:
            messagebox.showinfo("提示", "请先在左侧选择一个纸箱，再新增商品。")
            return

        if data is None:
            seq = self._product_seq
            self._product_seq += 1
            data = {
                "seq_no": seq,
                "product_name": "",
                "specification": "",
                "hs_code": "",
                "declaration_elements": "",
                "unit": "Roll",
                "qty_per_carton": 1.0,
                "unit_price": 0.0,
                "currency": "USD",
                "net_weight_per_unit_kg": 0.0,
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

    def _on_clone(self) -> None:
        """克隆当前选中的节点."""
        if self._selected_level == "pallet" and self._selected_pallet_idx >= 0:
            src = self._pallets[self._selected_pallet_idx]
            self._add_pallet(src)
            messagebox.showinfo("克隆成功", f"已克隆托盘 #{src['pallet_no']}（含其下所有纸箱和商品）")

        elif self._selected_level == "carton" and self._selected_pallet_idx >= 0 and self._selected_carton_idx >= 0:
            src = self._pallets[self._selected_pallet_idx]["cartons"][self._selected_carton_idx]
            self._add_carton(src)
            messagebox.showinfo("克隆成功", f"已克隆纸箱（含其中所有商品）")

        elif self._selected_level == "product" and self._selected_pallet_idx >= 0 and self._selected_carton_idx >= 0 and self._selected_product_idx >= 0:
            src = self._pallets[self._selected_pallet_idx]["cartons"][self._selected_carton_idx]["products"][self._selected_product_idx]
            self._add_product(src)
            messagebox.showinfo("克隆成功", f"已克隆商品")

    def _on_delete_node(self) -> None:
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

    def _clear_selection(self) -> None:
        """清除选中状态."""
        self._selected_pallet_idx = -1
        self._selected_carton_idx = -1
        self._selected_product_idx = -1
        self._selected_level = ""

    # ==================== Treeview 刷新 ====================

    def _refresh_tree(self) -> None:
        """根据 _pallets 数据重建 Treeview."""
        if self._tree is None:
            return

        # 清空
        for item in self._tree.get_children():
            self._tree.delete(item)

        for pi, pallet in enumerate(self._pallets):
            pallet_id = f"p_{pi}"
            vol = pallet.get("length_m", 0) * pallet.get("width_m", 0) * pallet.get("height_m", 0)
            self._tree.insert(
                "",
                END,
                iid=pallet_id,
                text=f"📦 托盘 #{pallet.get('pallet_no', '?')}",
                values=(f"体积: {vol:.3f} m³", f"自重: {pallet.get('pallet_weight_kg', 0)} kg"),
                open=True,
            )

            for ci, carton in enumerate(pallet.get("cartons", [])):
                carton_id = f"p_{pi}_c_{ci}"
                label = carton.get("carton_label", "?")
                batch_info = f" × {carton.get('batch_count', 1)}" if carton.get("is_batch") else ""
                self._tree.insert(
                    pallet_id,
                    END,
                    iid=carton_id,
                    text=f"📋 纸箱 {label}{batch_info}",
                    values=(f"毛重: {carton.get('gross_weight_kg', 0)} kg", f"尺寸: {carton.get('length_cm',0)}×{carton.get('width_cm',0)}×{carton.get('height_cm',0)} cm"),
                    open=False,
                )

                for pri, product in enumerate(carton.get("products", [])):
                    product_id = f"p_{pi}_c_{ci}_pr_{pri}"
                    self._tree.insert(
                        carton_id,
                        END,
                        iid=product_id,
                        text=f"📄 #{product.get('seq_no', '?')} {product.get('product_name', '未命名')[:20]}",
                        values=(f"HS: {product.get('hs_code', '?')}", f"单价: ${product.get('unit_price', 0):.2f}"),
                        open=False,
                    )

        # 重新编号托盘
        for i, p in enumerate(self._pallets):
            p["pallet_no"] = i + 1

    def _update_stats(self) -> None:
        """更新统计信息."""
        total_pallets = len(self._pallets)
        total_cartons = sum(len(p.get("cartons", [])) for p in self._pallets)
        total_products = sum(
            len(c.get("products", []))
            for p in self._pallets
            for c in p.get("cartons", [])
        )
        self._stats_var.set(f"托盘: {total_pallets} | 纸箱: {total_cartons} | 商品: {total_products}")

    def _expand_all(self) -> None:
        """展开所有节点."""
        if self._tree is None:
            return
        for item in self._tree.get_children():
            self._tree.item(item, open=True)
            for child in self._tree.get_children(item):
                self._tree.item(child, open=True)

    def _collapse_all(self) -> None:
        """折叠所有节点."""
        if self._tree is None:
            return
        for item in self._tree.get_children():
            self._tree.item(item, open=False)
            for child in self._tree.get_children(item):
                self._tree.item(child, open=False)

    # ==================== 节点选择与详情 ====================

    def _on_tree_select(self, event: Any) -> None:
        """Treeview 节点选中事件."""
        if self._tree is None:
            return

        selection = self._tree.selection()
        if not selection:
            return

        item_id = selection[0]
        parts = item_id.split("_")

        # 解析选中节点位置
        try:
            if len(parts) == 2 and parts[0] == "p":
                # 托盘级别
                self._selected_pallet_idx = int(parts[1])
                self._selected_carton_idx = -1
                self._selected_product_idx = -1
                self._selected_level = "pallet"
                self._show_pallet_detail()

            elif len(parts) >= 4 and parts[0] == "p" and parts[2] == "c":
                self._selected_pallet_idx = int(parts[1])
                self._selected_carton_idx = int(parts[3])
                self._selected_product_idx = -1

                if len(parts) >= 6 and parts[4] == "pr":
                    # 商品级别
                    self._selected_product_idx = int(parts[5])
                    self._selected_level = "product"
                    self._show_product_detail()
                else:
                    # 纸箱级别
                    self._selected_level = "carton"
                    self._show_carton_detail()

        except (IndexError, ValueError) as e:
            logger.warning("[警告]: 解析 Treeview 节点 ID 失败: %s (%s)", item_id, e)

    def _show_pallet_detail(self) -> None:
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

        # 保存按钮
        self._add_save_button("pallet", idx)

        # 新增纸箱按钮
        ttk.Button(
            self._detail_frame,
            text="+ 在此托盘下新增纸箱",
            bootstyle="info-outline",
            command=lambda: self._add_carton(),
        ).pack(padx=15, pady=(10, 5), fill=X)

    def _show_carton_detail(self) -> None:
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

        # 新增商品按钮
        ttk.Button(
            self._detail_frame,
            text="+ 在此纸箱下新增商品",
            bootstyle="info-outline",
            command=lambda: self._add_product(),
        ).pack(padx=15, pady=(10, 5), fill=X)

    def _show_product_detail(self) -> None:
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

    def _clear_detail_frame(self) -> None:
        """清空详情框架."""
        if self._detail_frame is None:
            return
        self._detail_vars.clear()
        for widget in self._detail_frame.winfo_children():
            widget.destroy()

    def _add_detail_field(self, label: str, key: str, value: str) -> None:
        """添加详情字段.

        Args:
            label: 字段标签.
            key: 字段标识符（用于保存时读取）.
            value: 字段值.
        """
        if self._detail_frame is None:
            return

        row = ttk.Frame(self._detail_frame)
        row.pack(fill=X, padx=15, pady=3)

        ttk.Label(row, text=label, font=self.app.get_font(size=10), width=20, anchor=W).pack(side=LEFT)

        var = ttk.StringVar(value=value)
        entry = ttk.Entry(row, textvariable=var)
        entry.pack(side=LEFT, fill=X, expand=YES, padx=(5, 0))
        self._detail_vars[key] = var

    def _add_detail_checkbox(self, label: str, key: str, checked: bool) -> None:
        """添加详情复选框.

        Args:
            label: 字段标签.
            key: 字段标识符.
            checked: 是否勾选.
        """
        if self._detail_frame is None:
            return

        row = ttk.Frame(self._detail_frame)
        row.pack(fill=X, padx=15, pady=3)

        ttk.Label(row, text=label, font=self.app.get_font(size=10), width=20, anchor=W).pack(side=LEFT)

        var = ttk.IntVar(value=1 if checked else 0)
        cb = ttk.Checkbutton(row, variable=var, bootstyle="primary-round-toggle")
        cb.pack(side=LEFT, padx=(5, 0))
        self._detail_vars[key] = var

    def _add_save_button(self, level: str, pi: int, ci: int = -1, pri: int = -1) -> None:
        """添加保存按钮.

        Args:
            level: 节点级别.
            pi: 托盘索引.
            ci: 纸箱索引.
            pri: 商品索引.
        """
        if self._detail_frame is None:
            return

        ttk.Separator(self._detail_frame, orient=HORIZONTAL).pack(fill=X, padx=10, pady=(10, 5))

        ttk.Button(
            self._detail_frame,
            text="💾 保存修改",
            bootstyle="success",
            command=lambda: self._save_detail(level, pi, ci, pri),
        ).pack(padx=15, pady=(0, 10), fill=X)

    def _save_detail(self, level: str, pi: int, ci: int = -1, pri: int = -1) -> None:
        """保存详情修改.

        Args:
            level: 节点级别.
            pi: 托盘索引.
            ci: 纸箱索引.
            pri: 商品索引.
        """
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
                    # 尝试类型转换
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

    # ==================== 数据导出 ====================

    def collect_tree_data(self) -> list[dict[str, Any]]:
        """收集所有托盘/纸箱/商品数据.

        Returns:
            托盘列表（深拷贝）.
        """
        return copy.deepcopy(self._pallets)

    def build_order_data(self) -> Any | None:
        """从表单数据 + 树数据构建 OrderData 对象.

        Returns:
            OrderData 实例，构建失败返回 None.
        """
        from src.models.order_data import (
            Carton,
            Customer,
            OrderData,
            OrderMeta,
            Origin,
            Pallet,
            Product,
            Totals,
        )
        from src.models.validators import validate_order_consistency

        meta_data = self.app.current_order_data.get("order_meta", {})
        customer_data = self.app.current_order_data.get("customer", {})
        origin_data = self.app.current_order_data.get("origin", {})

        try:
            # 构建 OrderMeta
            order_meta = OrderMeta(
                invoice_no=meta_data.get("invoice_no", "UNKNOWN"),
                contract_no=meta_data.get("contract_no", "UNKNOWN"),
                date=meta_data.get("date", "2025-01-01"),
                trade_term=meta_data.get("trade_term", "FOB"),
                payment_term=meta_data.get("payment_term", "100% T/T IN ADVANCE"),
                country_of_origin=meta_data.get("country_of_origin", "China"),
                order_no=meta_data.get("order_no", ""),
                transport_mode=meta_data.get("transport_mode", "海运"),
                vessel_flight=meta_data.get("vessel_flight", ""),
                bill_of_lading_no=meta_data.get("bill_of_lading_no", ""),
                currency=meta_data.get("currency", "USD"),
                package_type=meta_data.get("package_type", "pallet"),
                goods_summary=meta_data.get("goods_summary", ""),
                declaration_elements_template=meta_data.get("declaration_elements_template", ""),
            )

            # 构建 Customer
            customer = Customer(
                company_name_en=customer_data.get("company_name_en", "UNKNOWN"),
                country=customer_data.get("country", "Unknown"),
                company_name_cn=customer_data.get("company_name_cn", ""),
                address=customer_data.get("address", ""),
                contact_person=customer_data.get("contact_person", ""),
                phone=customer_data.get("phone", ""),
                mobile=customer_data.get("mobile", ""),
                destination=customer_data.get("destination", ""),
            )

            # 构建 Origin
            origin = Origin(
                export_port=origin_data.get("export_port", ""),
                domestic_source=origin_data.get("domestic_source", "深圳特区"),
                manufacturer=origin_data.get("manufacturer", "长园长通新材料股份有限公司"),
                business_entity=origin_data.get("business_entity", "长园长通新材料股份有限公司"),
                trade_mode=origin_data.get("trade_mode", "一般贸易"),
                tax_nature=origin_data.get("tax_nature", "一般征税"),
                settlement_method=origin_data.get("settlement_method", "电汇"),
                tax_rebate=origin_data.get("tax_rebate", "申请退税"),
            )

            # 构建 Pallets
            pallets: list[Pallet] = []
            for p_data in self._pallets:
                cartons: list[Carton] = []
                for c_data in p_data.get("cartons", []):
                    products: list[Product] = []
                    for pr_data in c_data.get("products", []):
                        product = Product(
                            seq_no=pr_data.get("seq_no", 0),
                            product_name=pr_data.get("product_name", ""),
                            hs_code=pr_data.get("hs_code", ""),
                            unit=pr_data.get("unit", "Roll"),
                            qty_per_carton=float(pr_data.get("qty_per_carton", 0)),
                            unit_price=float(pr_data.get("unit_price", 0)),
                            net_weight_per_unit_kg=float(pr_data.get("net_weight_per_unit_kg", 0)),
                            destination_country=pr_data.get("destination_country", ""),
                            specification=pr_data.get("specification", ""),
                            declaration_elements=pr_data.get("declaration_elements", ""),
                            currency=pr_data.get("currency", "USD"),
                        )
                        products.append(product)

                    carton = Carton(
                        carton_label=c_data.get("carton_label", ""),
                        is_batch=bool(c_data.get("is_batch", False)),
                        batch_count=int(c_data.get("batch_count", 1)),
                        length_cm=float(c_data.get("length_cm", 0)),
                        width_cm=float(c_data.get("width_cm", 0)),
                        height_cm=float(c_data.get("height_cm", 0)),
                        gross_weight_kg=float(c_data.get("gross_weight_kg", 0)),
                        products=products,
                    )
                    cartons.append(carton)

                pallet = Pallet(
                    pallet_no=p_data.get("pallet_no", 0),
                    length_m=float(p_data.get("length_m", 0)),
                    width_m=float(p_data.get("width_m", 0)),
                    height_m=float(p_data.get("height_m", 0)),
                    pallet_weight_kg=float(p_data.get("pallet_weight_kg", 0)),
                    cartons=cartons,
                )
                pallets.append(pallet)

            # 计算汇总
            total_pallets = len(pallets)
            total_cartons = sum(
                c.batch_count if c.is_batch else 1
                for p in pallets for c in p.cartons
            )
            total_gross = sum(
                (c.gross_weight_kg * c.batch_count) if c.is_batch else c.gross_weight_kg
                for p in pallets for c in p.cartons
            )
            total_net = sum(
                pr.net_weight_per_unit_kg * pr.qty_per_carton
                * (c.batch_count if c.is_batch else 1)
                for p in pallets for c in p.cartons for pr in c.products
            )
            total_volume = sum(
                p.length_m * p.width_m * p.height_m
                for p in pallets
            )
            total_amount = sum(
                pr.unit_price * pr.qty_per_carton
                * (c.batch_count if c.is_batch else 1)
                for p in pallets for c in p.cartons for pr in c.products
            )

            totals = Totals(
                total_pallets=total_pallets,
                total_cartons=total_cartons,
                total_gross_weight_kg=round(total_gross, 3),
                total_net_weight_kg=round(total_net, 3),
                total_volume_cbm=round(total_volume, 3),
                total_amount=round(total_amount, 2),
            )

            order = OrderData(
                order_meta=order_meta,
                customer=customer,
                pallets=pallets,
                totals=totals,
                origin=origin,
            )

            # 校验
            report = validate_order_consistency(order)
            if report.errors:
                error_msgs = "\n  • ".join(f"[{m.code}] {m.message}" for m in report.errors)
                messagebox.showwarning(
                    "数据校验警告",
                    f"订单数据校验发现以下问题：\n\n  • {error_msgs}\n\n建议修正后再生成。\n是否仍要继续生成？",
                )

            return order

        except Exception as e:
            logger.exception("[错误]: 构建 OrderData 失败")
            messagebox.showerror(
                "数据构建失败",
                f"[错误]: 无法构建订单数据\n[原因]: {e}\n[排查]: 请检查商品明细是否填写完整",
            )
            return None

    # ==================== 事件处理 ====================

    def _on_generate(self) -> None:
        """点击一键生成按钮."""
        # 校验
        if not self._pallets:
            messagebox.showwarning("无商品数据", "请至少添加一个托盘和商品后再生成。")
            return

        # 检查是否有空商品
        empty_products: list[str] = []
        for p in self._pallets:
            for c in p.get("cartons", []):
                for pr in c.get("products", []):
                    if not pr.get("product_name", "").strip() or not pr.get("hs_code", "").strip():
                        empty_products.append(f"托盘#{p.get('pallet_no')} 纸箱{c.get('carton_label')} 商品#{pr.get('seq_no')}")

        if empty_products:
            if not messagebox.askyesno(
                "商品信息不完整",
                f"以下 {len(empty_products)} 个商品缺少名称或 HS 编码：\n\n"
                f"  • {'\n  • '.join(empty_products[:5])}"
                f"{'  ...还有 ' + str(len(empty_products) - 5) + ' 个' if len(empty_products) > 5 else ''}"
                f"\n\n是否仍要继续生成？",
            ):
                return

        # 构建 OrderData
        order = self.build_order_data()
        if order is None:
            return

        self.app.current_order = order
        self.app.switch_page("generate")

    def _on_import_excel(self) -> None:
        """从 Excel 导入商品明细."""
        from tkinter import filedialog

        file_path: str = filedialog.askopenfilename(
            title="选择订单 Excel 文件",
            filetypes=[("Excel 文件", "*.xlsx *.xls"), ("所有文件", "*.*")],
        )

        if not file_path:
            return

        try:
            from src.importer.excel_importer import import_order_from_excel
            order, _ = import_order_from_excel(file_path)

            if order is None:
                messagebox.showerror("导入失败", "Excel 文件解析失败。")
                return

            # 将 OrderData 的 pallets 转换到树编辑器的数据结构
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

            # 填充表单
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

    def _on_clear_all(self) -> None:
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

    def on_enter(self) -> None:
        """进入页面时初始化."""
        # 如果已有 OrderData，恢复数据
        if self.app.current_order is not None and not self._pallets:
            try:
                order = self.app.current_order
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
                            c_data["products"].append({
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
                            })
                            self._product_seq += 1
                        p_data["cartons"].append(c_data)
                    self._pallets.append(p_data)
                self._refresh_tree()
                self._update_stats()
            except Exception as e:
                logger.warning("[警告]: 恢复订单数据失败: %s", e)

    def on_leave(self) -> None:
        """离开页面时保存数据."""
        if self._pallets:
            self.app.current_order_data["pallets"] = copy.deepcopy(self._pallets)


# ========== 运行说明 ==========
# 依赖安装: pip install ttkbootstrap
# 此页面由 GuiApp 自动加载，无需单独运行
# =============================
