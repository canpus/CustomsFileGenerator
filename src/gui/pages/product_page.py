# -*- coding: utf-8 -*-
"""产品管理页 — P7 产品库功能.

提供：
- 产品列表浏览与搜索
- 新增/编辑/删除产品
- 插入到商品明细表格
- 可复用的产品选择对话框
"""

from __future__ import annotations

import logging
from tkinter import messagebox
from typing import Any

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from src.db.repository import ProductRepository
from src.gui.page_base import PageBase

logger = logging.getLogger(__name__)


# ==================== 产品编辑对话框 ====================


class ProductEditDialog:
    """产品新增/编辑对话框."""

    FIELD_DEFS: list[tuple[str, str, int, str]] = [
        ("product_name", "商品名称 *", 45, ""),
        ("specification", "规格型号", 45, ""),
        ("hs_code", "HS 编码 *", 30, ""),
        ("declaration_elements", "申报要素", 45, ""),
        ("unit", "计量单位 *", 20, "Roll"),
        ("unit_price", "单价 (USD)", 20, "0.00"),
        ("net_weight_per_unit_kg", "单件净重 (kg)", 20, "0.00"),
        ("destination_country", "目的国", 25, ""),
        ("currency", "币种", 15, "USD"),
    ]

    def __init__(
        self,
        parent: ttk.Frame,
        title: str,
        product: dict[str, Any] | None = None,
    ):
        """初始化对话框.

        Args:
            parent: 父级容器.
            title: 对话框标题.
            product: 编辑模式下的现有产品数据，None 为新增模式.
        """
        self._product = product
        self._result: dict[str, Any] | None = None

        self._dialog = ttk.Toplevel(parent, title=title)
        self._dialog.geometry("520x500")
        self._dialog.transient(parent)
        self._dialog.grab_set()

        self._vars: dict[str, ttk.StringVar] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        """构建对话框 UI."""
        ttk.Label(
            self._dialog,
            text="产品信息",
            font=("Microsoft YaHei", 12, "bold"),
            bootstyle="primary",
        ).pack(padx=20, pady=(15, 10))

        for field, label, width, fallback in self.FIELD_DEFS:
            row = ttk.Frame(self._dialog)
            row.pack(fill=X, padx=20, pady=2)

            ttk.Label(
                row, text=label, font=("Microsoft YaHei", 10), width=18, anchor=W
            ).pack(side=LEFT)

            default = fallback
            if self._product:
                val = self._product.get(field)
                if val is not None:
                    default = str(val)

            var = ttk.StringVar(value=default)
            self._vars[field] = var
            ttk.Entry(row, textvariable=var, width=width).pack(
                side=LEFT, fill=X, expand=YES
            )

        # 按钮
        btn_frame = ttk.Frame(self._dialog)
        btn_frame.pack(fill=X, padx=20, pady=(15, 10))

        ttk.Button(
            btn_frame,
            text="保存",
            bootstyle="success",
            command=self._on_save,
        ).pack(side=LEFT, padx=(0, 10))

        ttk.Button(
            btn_frame,
            text="取消",
            bootstyle="secondary-outline",
            command=self._dialog.destroy,
        ).pack(side=LEFT)

    def _on_save(self) -> None:
        """保存按钮回调 — 校验并返回数据."""
        product_name = self._vars["product_name"].get().strip()
        hs_code = self._vars["hs_code"].get().strip()
        unit = self._vars["unit"].get().strip()

        if not product_name:
            messagebox.showwarning("必填字段缺失", "商品名称不能为空。")
            return
        if not hs_code:
            messagebox.showwarning("必填字段缺失", "HS 编码不能为空。")
            return
        if not unit:
            messagebox.showwarning("必填字段缺失", "计量单位不能为空。")
            return

        self._result = {
            field: var.get().strip()
            for field, var in self._vars.items()
        }
        self._dialog.destroy()

    def show(self) -> dict[str, Any] | None:
        """显示对话框并等待用户操作.

        Returns:
            用户输入的数据，取消则返回 None.
        """
        self._dialog.wait_window()
        return self._result


# ==================== 产品选择对话框（可复用） ====================


class ProductSelectDialog:
    """产品选择对话框 — 供商品明细页等外部页面使用.

    支持搜索过滤和多选，按产品 ID 精确匹配选中项.
    """

    def __init__(self, parent: ttk.Frame):
        """初始化.

        Args:
            parent: 父级容器.
        """
        self._result: list[dict[str, Any]] = []
        self._products: list[dict[str, Any]] = []

        self._dialog = ttk.Toplevel(parent, title="从产品库选择")
        self._dialog.geometry("780x520")
        self._dialog.transient(parent)
        self._dialog.grab_set()

        self._build_ui()
        self._load_products()

    def _build_ui(self) -> None:
        """构建对话框 UI."""
        # 搜索栏
        search_frame = ttk.Frame(self._dialog)
        search_frame.pack(fill=X, padx=15, pady=(15, 5))

        ttk.Label(
            search_frame,
            text="搜索产品:",
            font=("Microsoft YaHei", 10),
        ).pack(side=LEFT, padx=(0, 10))

        self._search_var = ttk.StringVar()
        search_entry = ttk.Entry(
            search_frame, textvariable=self._search_var, width=30
        )
        search_entry.pack(side=LEFT, padx=(0, 10))
        search_entry.bind("<KeyRelease>", lambda e: self._filter())

        ttk.Label(
            search_frame,
            text="共 0 个产品",
            font=("Microsoft YaHei", 10),
            bootstyle="secondary",
        ).pack(side=LEFT)

        self._count_label = search_frame.winfo_children()[-1]

        # 表格
        table_frame = ttk.Labelframe(
            self._dialog, text="产品列表（可多选）", padding=10, bootstyle="info"
        )
        table_frame.pack(fill=BOTH, expand=YES, padx=15, pady=(0, 10))

        columns = [
            ("product_name", "商品名称", 180),
            ("specification", "规格型号", 120),
            ("hs_code", "HS Code", 100),
            ("unit", "单位", 50),
            ("unit_price", "单价", 60),
            ("currency", "币种", 50),
        ]

        self._tree = ttk.Treeview(
            table_frame,
            columns=[c[0] for c in columns],
            show="headings",
            height=14,
            selectmode="extended",
        )
        for key, name, width in columns:
            self._tree.heading(key, text=name)
            self._tree.column(key, width=width, minwidth=30, stretch=True)

        vsb = ttk.Scrollbar(table_frame, orient=VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side=LEFT, fill=BOTH, expand=YES)
        vsb.pack(side=RIGHT, fill=Y)

        # 按钮
        btn_frame = ttk.Frame(self._dialog)
        btn_frame.pack(fill=X, padx=15, pady=(0, 15))

        ttk.Button(
            btn_frame,
            text="确定（插入选中产品）",
            bootstyle="success",
            command=self._on_confirm,
        ).pack(side=RIGHT, padx=(5, 0))

        ttk.Button(
            btn_frame,
            text="取消",
            bootstyle="secondary-outline",
            command=self._dialog.destroy,
        ).pack(side=RIGHT)

    def _load_products(self) -> None:
        """加载产品列表."""
        try:
            self._products = ProductRepository.list_all(limit=200)
            self._populate(self._products)
            self._count_label.configure(text=f"共 {len(self._products)} 个产品")
        except Exception as e:
            logger.exception("[错误]: 加载产品列表失败")
            messagebox.showerror(
                "加载失败",
                f"[错误]: 加载产品列表失败\n[原因]: {e}\n[排查]: 请检查数据库连接是否正常",
            )

    def _populate(self, products: list[dict[str, Any]]) -> None:
        """填充表格."""
        for item in self._tree.get_children():
            self._tree.delete(item)
        for p in products:
            product_id = p.get("id", "")
            values = [
                str(p.get("product_name", "")),
                str(p.get("specification", "")),
                str(p.get("hs_code", "")),
                str(p.get("unit", "")),
                str(p.get("unit_price", "")),
                str(p.get("currency", "USD")),
            ]
            self._tree.insert("", END, values=values, tags=(str(product_id),))

    def _filter(self) -> None:
        """搜索过滤."""
        keyword = self._search_var.get().strip().lower()
        if not keyword:
            self._populate(self._products)
            self._count_label.configure(text=f"共 {len(self._products)} 个产品")
            return
        filtered = [
            p for p in self._products
            if keyword in str(p.get("product_name", "")).lower()
            or keyword in str(p.get("hs_code", "")).lower()
            or keyword in str(p.get("specification", "")).lower()
        ]
        self._populate(filtered)
        self._count_label.configure(text=f"筛选 {len(filtered)} / {len(self._products)} 个产品")

    def _on_confirm(self) -> None:
        """确认选择 — 按 ID 精确匹配."""
        selection = self._tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请至少选择一个产品。")
            return

        selected_ids: set[int] = set()
        for iid in selection:
            tags = self._tree.item(iid)["tags"]
            if tags and tags[0]:
                try:
                    selected_ids.add(int(tags[0]))
                except ValueError:
                    pass

        self._result = [
            p for p in self._products
            if p.get("id") in selected_ids
        ]
        self._dialog.destroy()

    @property
    def result(self) -> list[dict[str, Any]]:
        """获取选中的产品列表."""
        return self._result

    def show(self) -> list[dict[str, Any]]:
        """显示对话框并等待用户操作.

        Returns:
            选中的产品记录列表.
        """
        self._dialog.wait_window()
        return self._result


# ==================== 产品管理页 ====================


class ProductPage(PageBase):
    """产品管理页.

    显示所有产品列表，支持搜索、新增、编辑、删除及插入到商品表格。
    """

    def __init__(self, parent: ttk.Frame, app: object):
        """初始化.

        Args:
            parent: 父级容器.
            app: 主应用控制器.
        """
        super().__init__(parent, app)
        self._product_tree: ttk.Treeview | None = None
        self._products: list[dict[str, Any]] = []

    def build(self) -> None:
        """构建产品管理页 UI."""
        self.frame = ttk.Frame(self.parent)
        self.frame.pack(fill=BOTH, expand=YES, padx=10, pady=10)

        # ---- 标题 ----
        title_frame = ttk.Frame(self.frame)
        title_frame.pack(fill=X, padx=5, pady=(5, 10))

        ttk.Label(
            title_frame,
            text="产品库",
            font=self.app.get_heading_font(),
            bootstyle="primary",
        ).pack(side=LEFT)

        # ---- 工具栏 ----
        toolbar = ttk.Frame(self.frame)
        toolbar.pack(fill=X, pady=(0, 5))

        ttk.Button(
            toolbar,
            text="新增产品",
            bootstyle="success-outline",
            command=self._on_add_product,
        ).pack(side=LEFT, padx=(0, 10))

        ttk.Button(
            toolbar,
            text="编辑产品",
            bootstyle="primary-outline",
            command=self._on_edit_product,
        ).pack(side=LEFT, padx=(0, 10))

        ttk.Button(
            toolbar,
            text="删除产品",
            bootstyle="danger-outline",
            command=self._on_delete_product,
        ).pack(side=LEFT, padx=(0, 10))

        ttk.Button(
            toolbar,
            text="插入到商品表格",
            bootstyle="warning-outline",
            command=self._on_insert_to_table,
        ).pack(side=LEFT, padx=(0, 10))

        ttk.Button(
            toolbar,
            text="刷新列表",
            bootstyle="secondary-outline",
            command=self._refresh_list,
        ).pack(side=LEFT)

        # 搜索框
        search_frame = ttk.Frame(toolbar)
        search_frame.pack(side=RIGHT)

        self._search_var = ttk.StringVar()
        ttk.Entry(
            search_frame,
            textvariable=self._search_var,
            width=25,
        ).pack(side=LEFT, padx=(0, 5))
        self._search_var.trace_add("write", lambda *args: self._on_search())

        ttk.Button(
            search_frame,
            text="搜索",
            bootstyle="info-outline",
            command=self._on_search,
        ).pack(side=LEFT)

        # ---- 产品列表 ----
        list_frame = ttk.Labelframe(
            self.frame, text="产品列表", padding=10, bootstyle="info"
        )
        list_frame.pack(fill=BOTH, expand=YES)

        columns = (
            "id", "product_name", "specification", "hs_code",
            "unit", "unit_price", "currency", "destination_country",
        )
        self._product_tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            height=18,
        )
        self._product_tree.heading("id", text="ID")
        self._product_tree.heading("product_name", text="商品名称")
        self._product_tree.heading("specification", text="规格型号")
        self._product_tree.heading("hs_code", text="HS Code")
        self._product_tree.heading("unit", text="单位")
        self._product_tree.heading("unit_price", text="单价")
        self._product_tree.heading("currency", text="币种")
        self._product_tree.heading("destination_country", text="目的国")
        self._product_tree.column("id", width=50, anchor=CENTER)
        self._product_tree.column("product_name", width=160)
        self._product_tree.column("specification", width=120)
        self._product_tree.column("hs_code", width=100, anchor=CENTER)
        self._product_tree.column("unit", width=50, anchor=CENTER)
        self._product_tree.column("unit_price", width=60, anchor=CENTER)
        self._product_tree.column("currency", width=50, anchor=CENTER)
        self._product_tree.column("destination_country", width=70, anchor=CENTER)

        scrollbar = ttk.Scrollbar(
            list_frame, orient=VERTICAL, command=self._product_tree.yview
        )
        self._product_tree.configure(yscrollcommand=scrollbar.set)

        self._product_tree.pack(side=LEFT, fill=BOTH, expand=YES)
        scrollbar.pack(side=RIGHT, fill=Y)

        self._product_tree.bind("<Double-1>", lambda e: self._on_edit_product())

        # ---- 底部状态 ----
        self._status_var = ttk.StringVar(value="共 0 个产品")
        ttk.Label(
            self.frame,
            textvariable=self._status_var,
            font=self.app.get_font(size=10),
            bootstyle="secondary",
        ).pack(anchor=W, padx=5, pady=(5, 0))

    # ==================== 产品操作 ====================

    def _on_add_product(self) -> None:
        """新增产品."""
        dialog = ProductEditDialog(self.frame, "新增产品")
        data = dialog.show()

        if data is None:
            return

        try:
            product_name = data.pop("product_name")
            hs_code = data.pop("hs_code")
            unit = data.pop("unit")

            unit_price = _parse_float(data.pop("unit_price", "0"))
            net_weight = _parse_float(data.pop("net_weight_per_unit_kg", "0"))

            CustomerRepository_like_kwargs: dict[str, Any] = {
                k: v for k, v in data.items() if v
            }

            ProductRepository.insert(
                product_name=product_name,
                hs_code=hs_code,
                unit=unit,
                unit_price=unit_price,
                net_weight_per_unit_kg=net_weight,
                **CustomerRepository_like_kwargs,
            )
            messagebox.showinfo("新增成功", f"产品「{product_name}」已添加。")
            self._refresh_list()
            self.app.set_status(f"已新增产品: {product_name}")
        except Exception as e:
            logger.exception("[错误]: 新增产品失败")
            messagebox.showerror(
                "新增失败",
                f"[错误]: 新增产品失败\n[原因]: {e}\n[排查]: 请检查数据库连接是否正常",
            )

    def _on_edit_product(self) -> None:
        """编辑选中产品."""
        if self._product_tree is None:
            return

        selection = self._product_tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请先在列表中选择一个产品。")
            return

        item = self._product_tree.item(selection[0])
        product_id = item["values"][0]

        try:
            product = ProductRepository.get_by_id(int(product_id))
            if product is None:
                messagebox.showerror("错误", "产品不存在或已被删除。")
                return
        except Exception as e:
            logger.exception("[错误]: 获取产品详情失败")
            messagebox.showerror("错误", f"[错误]: {e}")
            return

        dialog = ProductEditDialog(self.frame, "编辑产品", product=product)
        data = dialog.show()

        if data is None:
            return

        try:
            product_name = data.pop("product_name")
            hs_code = data.pop("hs_code")
            unit = data.pop("unit")
            unit_price = _parse_float(data.pop("unit_price", "0"))
            net_weight = _parse_float(data.pop("net_weight_per_unit_kg", "0"))

            data["product_name"] = product_name
            data["hs_code"] = hs_code
            data["unit"] = unit
            data["unit_price"] = unit_price
            data["net_weight_per_unit_kg"] = net_weight

            ProductRepository.update(product_id=int(product_id), **data)
            messagebox.showinfo("更新成功", f"产品「{product_name}」已更新。")
            self._refresh_list()
            self.app.set_status(f"已更新产品: {product_name}")
        except Exception as e:
            logger.exception("[错误]: 更新产品失败")
            messagebox.showerror(
                "更新失败",
                f"[错误]: 更新产品失败\n[原因]: {e}\n[排查]: 请检查数据库连接是否正常",
            )

    def _on_delete_product(self) -> None:
        """删除选中产品."""
        if self._product_tree is None:
            return

        selection = self._product_tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请先在列表中选择一个产品。")
            return

        item = self._product_tree.item(selection[0])
        product_id = item["values"][0]
        product_name = item["values"][1]

        if not messagebox.askyesno(
            "确认删除",
            f"确定要删除产品「{product_name}」吗？\n此操作将软删除该产品记录。",
        ):
            return

        try:
            success = ProductRepository.delete(product_id=int(product_id))
            if success:
                messagebox.showinfo("删除成功", f"产品「{product_name}」已删除。")
                self._refresh_list()
                self.app.set_status(f"已删除产品: {product_name}")
            else:
                messagebox.showerror("删除失败", "产品不存在或已被删除。")
        except Exception as e:
            logger.exception("[错误]: 删除产品失败")
            messagebox.showerror(
                "删除失败",
                f"[错误]: 删除产品失败\n[原因]: {e}\n[排查]: 请检查数据库连接是否正常",
            )

    def _on_insert_to_table(self) -> None:
        """将选中产品插入到商品明细表格."""
        if self._product_tree is None:
            return

        selection = self._product_tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请先在列表中选择一个或多个产品。")
            return

        selected_products: list[dict[str, Any]] = []
        for iid in selection:
            item = self._product_tree.item(iid)
            product_id = item["values"][0]
            try:
                product = ProductRepository.get_by_id(int(product_id))
                if product:
                    selected_products.append(product)
            except Exception as e:
                logger.warning("[警告]: 获取产品 ID=%s 失败: %s", product_id, e)

        if not selected_products:
            messagebox.showerror("错误", "无法获取选中产品的详细信息。")
            return

        # 切换到商品明细页并插入
        self.app.switch_page("line_items")

        # 延迟插入（等待页面构建完成）
        def _do_insert() -> None:
            line_items_page = self.app._pages.get("line_items")
            if line_items_page is not None and hasattr(line_items_page, "_insert_product_rows"):
                line_items_page._insert_product_rows(selected_products)
                self.app.set_status(f"已从产品库插入 {len(selected_products)} 个产品")

        self.frame.after(200, _do_insert)

    # ==================== 列表操作 ====================

    def _on_search(self) -> None:
        """搜索产品."""
        keyword = self._search_var.get().strip()
        try:
            if keyword:
                # 同时按名称和 HS Code 搜索并合并去重
                by_name = ProductRepository.search_by_name(keyword, limit=100)
                by_hs = ProductRepository.search_by_hs_code(keyword, limit=100)
                seen_ids: set[int] = set()
                merged: list[dict[str, Any]] = []
                for p in by_name + by_hs:
                    pid = p.get("id")
                    if pid not in seen_ids:
                        seen_ids.add(pid)
                        merged.append(p)
                self._products = merged
            else:
                self._products = ProductRepository.list_all(limit=100)
            self._populate_tree(self._products)
        except Exception as e:
            logger.exception("[错误]: 搜索产品失败")
            self._status_var.set(f"搜索失败: {e}")

    def _refresh_list(self) -> None:
        """刷新产品列表."""
        self._search_var.set("")
        try:
            self._products = ProductRepository.list_all(limit=100)
            self._populate_tree(self._products)
            self.app.set_status("产品列表已刷新")
        except Exception as e:
            logger.exception("[错误]: 刷新产品列表失败")
            self._status_var.set(f"刷新失败: {e}")

    def _populate_tree(self, products: list[dict[str, Any]]) -> None:
        """填充产品列表."""
        if self._product_tree is None:
            return

        for item in self._product_tree.get_children():
            self._product_tree.delete(item)

        for p in products:
            self._product_tree.insert(
                "",
                END,
                values=(
                    p.get("id", ""),
                    p.get("product_name", ""),
                    p.get("specification", ""),
                    p.get("hs_code", ""),
                    p.get("unit", ""),
                    p.get("unit_price", ""),
                    p.get("currency", "USD"),
                    p.get("destination_country", ""),
                ),
            )

        self._status_var.set(f"共 {len(products)} 个产品")

    def on_enter(self) -> None:
        """进入页面时刷新列表."""
        self._refresh_list()
        self.app.set_status("产品库 — 浏览和管理产品信息")


def _parse_float(value: str, default: float = 0.0) -> float:
    """安全转换为 float."""
    try:
        return float(value.strip())
    except (ValueError, AttributeError):
        return default


# ========== 运行说明 ==========
# 依赖安装: pip install ttkbootstrap
# 此页面由 GuiApp 自动加载，无需单独运行
# =============================
