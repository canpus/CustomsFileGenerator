# -*- coding: utf-8 -*-
"""表格导入页 — 阶段 9.4.

提供：
- 选择 Excel 文件
- 预览映射结果（字段对应关系）
- 确认导入（填充到树状编辑器）
- 从数据库加载模板
"""

from __future__ import annotations

import logging
from tkinter import filedialog, messagebox
from typing import Any

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

logger = logging.getLogger(__name__)

from src.gui.page_base import PageBase


class ImportPage(PageBase):
    """表格导入页.

    支持：
    1. 从 Excel 文件导入完整订单数据
    2. 从 SQLite 数据库加载已保存的订单模板
    3. 预览导入结果
    """

    def __init__(self, parent: ttk.Frame, app: object):
        """初始化.

        Args:
            parent: 父级容器.
            app: 主应用控制器.
        """
        super().__init__(parent, app)
        self._preview_text: ttk.Text | None = None
        self._imported_order: Any = None

    def build(self) -> None:
        """构建导入页 UI."""
        self.frame = ttk.Frame(self.parent)
        self.frame.pack(fill=BOTH, expand=YES, padx=10, pady=10)

        # ---- 标题 ----
        title_frame = ttk.Frame(self.frame)
        title_frame.pack(fill=X, padx=5, pady=(5, 10))

        ttk.Label(
            title_frame,
            text="数据导入",
            font=self.app.get_heading_font(),
            bootstyle="primary",
        ).pack(side=LEFT)

        # ---- 导入选项 ----
        options_frame = ttk.Labelframe(self.frame, text="导入方式", padding=15, bootstyle="primary")
        options_frame.pack(fill=X, pady=(0, 10))

        row1 = ttk.Frame(options_frame)
        row1.pack(fill=X, pady=5)

        ttk.Button(
            row1,
            text="从 Excel 文件导入订单数据...",
            bootstyle="primary-outline",
            command=self._on_import_from_excel,
        ).pack(side=LEFT, padx=(0, 20))

        ttk.Button(
            row1,
            text="从数据库加载模板...",
            bootstyle="info-outline",
            command=self._on_load_template,
        ).pack(side=LEFT)

        ttk.Label(
            row1,
            text="支持 .xlsx / .xls 格式的订单表格",
            font=self.app.get_font(size=9),
            bootstyle="secondary",
        ).pack(side=RIGHT)

        # ---- 预览区域 ----
        preview_label = ttk.Labelframe(self.frame, text="导入预览", padding=10, bootstyle="info")
        preview_label.pack(fill=BOTH, expand=YES, pady=(0, 10))

        self._preview_text = ttk.Text(
            preview_label,
            height=20,
            wrap="word",
            font=self.app.get_font(size=10),
        )
        self._preview_text.pack(fill=BOTH, expand=YES, padx=5, pady=5)

        # 滚动条
        scrollbar = ttk.Scrollbar(self._preview_text, orient=VERTICAL, command=self._preview_text.yview)
        self._preview_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=RIGHT, fill=Y)

        self._preview_text.insert(END, "选择导入方式后，数据预览将在此显示。\n\n")
        self._preview_text.insert(END, "支持的列名包括：\n")
        self._preview_text.insert(END, "  • 订单元信息：发票号、合同号、日期、运输方式、贸易条款等\n")
        self._preview_text.insert(END, "  • 客户信息：客户名称、客户地址、联系人、电话、国家等\n")
        self._preview_text.insert(END, "  • 商品明细：商品名称、规格、HS编码、单位、数量、单价、净重等\n")
        self._preview_text.insert(END, "  • 托盘/纸箱：托盘号、纸箱尺寸、毛重、箱数等\n")
        self._preview_text.configure(state="disabled")

        # ---- 底部按钮 ----
        bottom = ttk.Frame(self.frame)
        bottom.pack(fill=X, padx=5, pady=(5, 10))

        ttk.Button(
            bottom,
            text="← 返回订单信息",
            bootstyle="secondary-outline",
            command=lambda: self.app.switch_page("order_info"),
        ).pack(side=LEFT)

        self._confirm_btn = ttk.Button(
            bottom,
            text="确认导入 → 编辑商品明细",
            bootstyle="success",
            command=self._on_confirm_import,
            state="disabled",
        )
        self._confirm_btn.pack(side=RIGHT)

    # ==================== 导入操作 ====================

    def _on_import_from_excel(self) -> None:
        """从 Excel 文件导入."""
        file_path: str = filedialog.askopenfilename(
            title="选择订单 Excel 文件",
            filetypes=[("Excel 文件", "*.xlsx *.xls"), ("所有文件", "*.*")],
        )

        if not file_path:
            return

        self.app.set_status(f"正在导入: {file_path}...")

        try:
            from src.importer.excel_importer import import_order_from_excel
            order, _ = import_order_from_excel(file_path)

            if order is None:
                self._show_preview("❌ Excel 文件解析失败。\n\n请检查文件格式是否正确。")
                return

            self._imported_order = order
            self._display_order_preview(order)
            self._confirm_btn.configure(state="normal")
            self.app.set_status(f"导入完成: {file_path}")

        except Exception as e:
            logger.exception("[错误]: Excel 导入失败")
            self._show_preview(f"❌ 导入失败\n\n[错误]: {e}\n[原因]: 文件格式可能不匹配\n[排查]: 请确认文件为标准订单 Excel 格式")
            self.app.set_status("导入失败")

    def _on_load_template(self) -> None:
        """从数据库加载模板."""
        try:
            from src.importer.template_loader import TemplateLoader
            templates = TemplateLoader.list_templates(limit=50)

            if not templates:
                self._show_preview("ℹ️ 数据库中暂无保存的模板。\n\n请先在「新建单据」中创建并保存订单模板。")
                return

            # 显示模板选择对话框
            self._show_template_selection(templates)

        except Exception as e:
            logger.exception("[错误]: 加载模板列表失败")
            self._show_preview(f"❌ 加载模板列表失败\n\n[错误]: {e}")

    def _show_template_selection(self, templates: list[dict[str, Any]]) -> None:
        """显示模板选择对话框.

        Args:
            templates: 模板列表.
        """
        dialog = ttk.Toplevel(self.frame, title="选择导入模板")
        dialog.geometry("600x400")
        dialog.transient(self.frame)
        dialog.grab_set()

        ttk.Label(
            dialog,
            text="选择要导入的订单模板",
            font=self.app.get_font(bold=True, size=12),
            bootstyle="primary",
        ).pack(padx=15, pady=(15, 10))

        # 列表
        list_frame = ttk.Frame(dialog)
        list_frame.pack(fill=BOTH, expand=YES, padx=15, pady=5)

        columns = ("id", "name", "customer", "date")
        tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=12)
        tree.heading("id", text="ID")
        tree.heading("name", text="模板名称")
        tree.heading("customer", text="客户")
        tree.heading("date", text="创建日期")
        tree.column("id", width=50, anchor=CENTER)
        tree.column("name", width=180)
        tree.column("customer", width=200)
        tree.column("date", width=120, anchor=CENTER)

        for tpl in templates:
            tree.insert(
                "",
                END,
                values=(
                    tpl.get("id", ""),
                    tpl.get("template_name", tpl.get("invoice_no", "")),
                    tpl.get("customer_name", ""),
                    tpl.get("created_at", "")[:10],
                ),
            )

        scrollbar = ttk.Scrollbar(list_frame, orient=VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=LEFT, fill=BOTH, expand=YES)
        scrollbar.pack(side=RIGHT, fill=Y)

        # 按钮
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=X, padx=15, pady=(10, 15))

        def _on_select() -> None:
            selection = tree.selection()
            if not selection:
                messagebox.showinfo("提示", "请先选择一个模板。")
                return

            item = tree.item(selection[0])
            template_id = item["values"][0]

            try:
                from src.importer.template_loader import TemplateLoader
                order = TemplateLoader.load_template(template_id=int(template_id))

                if order is None:
                    messagebox.showerror("加载失败", f"模板 ID={template_id} 不存在或已损坏。")
                    return

                self._imported_order = order
                self._display_order_preview(order)
                self._confirm_btn.configure(state="normal")
                self.app.set_status(f"已加载模板 ID={template_id}")
                dialog.destroy()

            except Exception as e:
                logger.exception("[错误]: 加载模板失败")
                messagebox.showerror("加载失败", f"[错误]: {e}")

        ttk.Button(btn_frame, text="加载选中模板", bootstyle="success", command=_on_select).pack(side=RIGHT)
        ttk.Button(btn_frame, text="取消", bootstyle="secondary-outline", command=dialog.destroy).pack(side=RIGHT, padx=(0, 10))

    # ==================== 预览显示 ====================

    def _display_order_preview(self, order: Any) -> None:
        """在预览区显示订单数据摘要.

        Args:
            order: OrderData 对象.
        """
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append("📋 订单数据预览")
        lines.append("=" * 60)
        lines.append("")

        meta = order.order_meta
        lines.append("--- 订单元信息 ---")
        lines.append(f"  发票号: {meta.invoice_no}")
        lines.append(f"  合同号: {meta.contract_no}")
        lines.append(f"  日期: {meta.date}")
        lines.append(f"  运输方式: {meta.transport_mode}")
        lines.append(f"  贸易条款: {meta.trade_term}")
        lines.append(f"  付款方式: {meta.payment_term}")
        lines.append(f"  币种: {meta.currency}")
        lines.append("")

        cust = order.customer
        lines.append("--- 客户信息 ---")
        lines.append(f"  公司: {cust.company_name_en}")
        lines.append(f"  国家: {cust.country}")
        lines.append(f"  地址: {cust.address[:60]}..." if len(cust.address) > 60 else f"  地址: {cust.address}")
        lines.append("")

        lines.append("--- 商品明细 ---")
        total_products = 0
        for pallet in order.pallets:
            for carton in pallet.cartons:
                for product in carton.products:
                    total_products += 1
                    lines.append(
                        f"  托盘#{pallet.pallet_no} 箱{carton.carton_label} "
                        f"#{product.seq_no}: {product.product_name[:30]} "
                        f"HS:{product.hs_code} "
                        f"Qty:{product.qty_per_carton}{product.unit} "
                        f"${product.unit_price:.2f}"
                    )

        lines.append("")
        lines.append("--- 汇总 ---")
        lines.append(f"  托盘数: {order.totals.total_pallets}")
        lines.append(f"  纸箱数: {order.totals.total_cartons}")
        lines.append(f"  总毛重: {order.totals.total_gross_weight_kg} kg")
        lines.append(f"  总净重: {order.totals.total_net_weight_kg} kg")
        lines.append(f"  总体积: {order.totals.total_volume_cbm} m³")
        lines.append(f"  总金额: ${order.totals.total_amount:,.2f}")
        lines.append("")
        lines.append("=" * 60)

        self._show_preview("\n".join(lines))

    def _show_preview(self, text: str) -> None:
        """在预览区显示文本.

        Args:
            text: 显示的文本.
        """
        if self._preview_text is None:
            return
        self._preview_text.configure(state="normal")
        self._preview_text.delete("1.0", END)
        self._preview_text.insert(END, text)
        self._preview_text.configure(state="disabled")

    def _on_confirm_import(self) -> None:
        """确认导入，跳转到树状编辑器."""
        if self._imported_order is None:
            messagebox.showwarning("无数据", "请先导入数据后再确认。")
            return

        self.app.current_order = self._imported_order
        self.app.set_status("数据已导入，跳转到商品明细编辑")

        # 切换到树状编辑器页面
        self.app.switch_page("tree_editor")

    def on_enter(self) -> None:
        """进入页面时更新状态."""
        self.app.set_status("数据导入页 — 选择 Excel 文件或数据库模板")


# ========== 运行说明 ==========
# 依赖安装: pip install ttkbootstrap
# 此页面由 GuiApp 自动加载，无需单独运行
# =============================
