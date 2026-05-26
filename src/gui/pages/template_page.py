# -*- coding: utf-8 -*-
"""模板管理页 — 阶段 9.5.

提供：
- 保存当前订单为模板
- 加载已有模板
- 删除模板
- 模板列表浏览与搜索
"""

from __future__ import annotations

import logging
from datetime import datetime
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


class TemplatePage(PageBase):
    """模板管理页.

    显示已保存的模板列表，支持加载、删除和保存操作。
    """

    def __init__(self, parent: ttk.Frame, app: GuiApp):
        """初始化.

        Args:
            parent: 父级容器.
            app: 主应用控制器.
        """
        super().__init__(parent, app)
        self._template_tree: ttk.Treeview | None = None
        self._templates: list[dict[str, Any]] = []

    def build(self) -> None:
        """构建模板管理页 UI."""
        self.frame = ttk.Frame(self.parent)
        self.frame.pack(fill=BOTH, expand=YES, padx=10, pady=10)

        # ---- 标题 ----
        title_frame = ttk.Frame(self.frame)
        title_frame.pack(fill=X, padx=5, pady=(5, 10))

        ttk.Label(
            title_frame,
            text="📁 历史模板",
            font=self.app.get_heading_font(),
            bootstyle="primary",
        ).pack(side=LEFT)

        # ---- 工具栏 ----
        toolbar = ttk.Frame(self.frame)
        toolbar.pack(fill=X, pady=(0, 5))

        ttk.Button(
            toolbar,
            text="💾 保存当前订单为模板",
            bootstyle="success-outline",
            command=self._on_save_template,
        ).pack(side=LEFT, padx=(0, 10))

        ttk.Button(
            toolbar,
            text="📥 加载选中模板",
            bootstyle="primary-outline",
            command=self._on_load_template,
        ).pack(side=LEFT, padx=(0, 10))

        ttk.Button(
            toolbar,
            text="🗑 删除选中模板",
            bootstyle="danger-outline",
            command=self._on_delete_template,
        ).pack(side=LEFT, padx=(0, 10))

        ttk.Button(
            toolbar,
            text="🔄 刷新列表",
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
            text="🔍 搜索",
            bootstyle="info-outline",
            command=self._on_search,
        ).pack(side=LEFT)

        # ---- 模板列表 ----
        list_frame = ttk.Labelframe(self.frame, text="模板列表", padding=10, bootstyle="info")
        list_frame.pack(fill=BOTH, expand=YES)

        columns = ("id", "name", "customer", "products", "date")
        self._template_tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            height=18,
        )
        self._template_tree.heading("id", text="ID")
        self._template_tree.heading("name", text="模板名称 / 发票号")
        self._template_tree.heading("customer", text="客户")
        self._template_tree.heading("products", text="商品数")
        self._template_tree.heading("date", text="创建日期")
        self._template_tree.column("id", width=50, anchor=CENTER)
        self._template_tree.column("name", width=220)
        self._template_tree.column("customer", width=220)
        self._template_tree.column("products", width=80, anchor=CENTER)
        self._template_tree.column("date", width=120, anchor=CENTER)

        scrollbar = ttk.Scrollbar(list_frame, orient=VERTICAL, command=self._template_tree.yview)
        self._template_tree.configure(yscrollcommand=scrollbar.set)

        self._template_tree.pack(side=LEFT, fill=BOTH, expand=YES)
        scrollbar.pack(side=RIGHT, fill=Y)

        # 双击加载模板
        self._template_tree.bind("<Double-1>", lambda e: self._on_load_template())

        # ---- 底部状态 ----
        self._status_var = ttk.StringVar(value="共 0 个模板")
        ttk.Label(
            self.frame,
            textvariable=self._status_var,
            font=self.app.get_font(size=10),
            bootstyle="secondary",
        ).pack(anchor=W, padx=5, pady=(5, 0))

    # ==================== 模板操作 ====================

    def _on_save_template(self) -> None:
        """保存当前订单为模板."""
        order = self.app.current_order
        if order is None:
            # 检查是否有树编辑器的数据
            order_data = self.app.current_order_data
            if not order_data or not order_data.get("order_meta"):
                messagebox.showinfo("提示", "没有可保存的订单数据。\n\n请先在「新建单据」中录入订单信息和商品明细。")
                return

            # 构建 OrderData
            try:
                from src.gui.pages.tree_editor_page import TreeEditorPage
                # 尝试从树编辑器页面获取
                pass
            except Exception:
                pass

            messagebox.showinfo("提示", "当前没有完整的订单数据。\n\n请先在「新建单据」中完成订单录入和商品编辑。")
            return

        # 获取模板名称
        dialog = ttk.Toplevel(self.frame, title="保存模板")
        dialog.geometry("400x250")
        dialog.transient(self.frame)
        dialog.grab_set()

        ttk.Label(
            dialog,
            text="💾 保存订单为模板",
            font=self.app.get_font(bold=True, size=12),
            bootstyle="primary",
        ).pack(padx=20, pady=(20, 10))

        ttk.Label(dialog, text="模板名称:", font=self.app.get_font(size=10)).pack(anchor=W, padx=20)
        name_var = ttk.StringVar(
            value=f"{order.order_meta.invoice_no} - {order.customer.company_name_en[:30]}"
        )
        ttk.Entry(dialog, textvariable=name_var, width=45).pack(padx=20, pady=(0, 5))

        ttk.Label(dialog, text="备注（可选）:", font=self.app.get_font(size=10)).pack(anchor=W, padx=20)
        desc_var = ttk.StringVar()
        ttk.Entry(dialog, textvariable=desc_var, width=45).pack(padx=20, pady=(0, 15))

        def _do_save() -> None:
            template_name = name_var.get().strip()
            if not template_name:
                messagebox.showwarning("提示", "请输入模板名称。")
                return

            try:
                from src.db.repository import TemplateRepository
                TemplateRepository.save(
                    template_name=template_name,
                    description=desc_var.get().strip(),
                    order=order,
                )
                messagebox.showinfo("保存成功", f"模板「{template_name}」已保存。")
                dialog.destroy()
                self._refresh_list()
                self.app.set_status(f"模板已保存: {template_name}")
            except Exception as e:
                logger.exception("[错误]: 保存模板失败")
                messagebox.showerror("保存失败", f"[错误]: {e}")

        ttk.Button(dialog, text="💾 保存", bootstyle="success", command=_do_save).pack(side=LEFT, padx=(20, 10))
        ttk.Button(dialog, text="取消", bootstyle="secondary-outline", command=dialog.destroy).pack(side=LEFT)

    def _on_load_template(self) -> None:
        """加载选中的模板."""
        if self._template_tree is None:
            return

        selection = self._template_tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请先在列表中选择一个模板。")
            return

        item = self._template_tree.item(selection[0])
        template_id = item["values"][0]

        try:
            from src.importer.template_loader import TemplateLoader
            order = TemplateLoader.load_template(template_id=int(template_id))

            if order is None:
                messagebox.showerror("加载失败", f"模板 ID={template_id} 不存在或已损坏。")
                return

            self.app.current_order = order
            self.app.set_status(f"已加载模板: ID={template_id}")

            messagebox.showinfo(
                "加载成功",
                f"模板已加载。\n\n发票号: {order.order_meta.invoice_no}\n"
                f"客户: {order.customer.company_name_en}\n"
                f"商品数: {sum(len(c.products) for p in order.pallets for c in p.cartons)}\n\n"
                f"现在将跳转到「新建单据」页面。",
            )
            self.app.switch_page("order_info")

        except Exception as e:
            logger.exception("[错误]: 加载模板失败")
            messagebox.showerror("加载失败", f"[错误]: {e}")

    def _on_delete_template(self) -> None:
        """删除选中的模板."""
        if self._template_tree is None:
            return

        selection = self._template_tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请先在列表中选择一个模板。")
            return

        item = self._template_tree.item(selection[0])
        template_id = item["values"][0]
        template_name = item["values"][1]

        if not messagebox.askyesno("确认删除", f"确定要删除模板「{template_name}」吗？\n此操作不可撤销。"):
            return

        try:
            from src.db.repository import TemplateRepository
            success = TemplateRepository.delete(template_id=int(template_id))
            if success:
                messagebox.showinfo("删除成功", f"模板「{template_name}」已删除。")
                self._refresh_list()
                self.app.set_status(f"已删除模板: {template_name}")
            else:
                messagebox.showerror("删除失败", "模板不存在或已删除。")
        except Exception as e:
            logger.exception("[错误]: 删除模板失败")
            messagebox.showerror("删除失败", f"[错误]: {e}")

    def _on_search(self) -> None:
        """搜索模板."""
        keyword = self._search_var.get().strip()
        try:
            from src.importer.template_loader import TemplateLoader
            if keyword:
                templates = TemplateLoader.search_templates(keyword, limit=50)
            else:
                templates = TemplateLoader.list_templates(limit=50)
            self._templates = templates
            self._populate_tree(templates)
        except Exception as e:
            logger.exception("[错误]: 搜索模板失败")
            self._show_error(f"搜索失败: {e}")

    def _refresh_list(self) -> None:
        """刷新模板列表."""
        self._search_var.set("")
        try:
            from src.importer.template_loader import TemplateLoader
            self._templates = TemplateLoader.list_templates(limit=50)
            self._populate_tree(self._templates)
            self.app.set_status("模板列表已刷新")
        except Exception as e:
            logger.exception("[错误]: 刷新模板列表失败")
            self._show_error(f"刷新失败: {e}")

    def _populate_tree(self, templates: list[dict[str, Any]]) -> None:
        """填充模板列表.

        Args:
            templates: 模板列表.
        """
        if self._template_tree is None:
            return

        for item in self._template_tree.get_children():
            self._template_tree.delete(item)

        for tpl in templates:
            self._template_tree.insert(
                "",
                END,
                values=(
                    tpl.get("id", ""),
                    tpl.get("template_name", tpl.get("invoice_no", "未命名")),
                    tpl.get("customer_name", "未知客户"),
                    tpl.get("product_count", "0"),
                    (tpl.get("created_at", "") or "")[:10],
                ),
            )

        self._status_var.set(f"共 {len(templates)} 个模板")

    def _show_error(self, message: str) -> None:
        """显示错误信息.

        Args:
            message: 错误信息.
        """
        self._status_var.set(f"⚠️ {message}")

    def on_enter(self) -> None:
        """进入页面时刷新列表."""
        self._refresh_list()
        self.app.set_status("模板管理 — 浏览和加载已保存的订单模板")


# ========== 运行说明 ==========
# 依赖安装: pip install ttkbootstrap
# 此页面由 GuiApp 自动加载，无需单独运行
# =============================
