"""套用模板对话框 — 选择并套用已保存的分块模板.

提供：
- 按类型筛选已保存的模板块
- 选择套用范围（仅对 order_full 类型）
- 预览并确认套用
"""

from __future__ import annotations

import logging
from tkinter import messagebox
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.gui.app import GuiApp

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

logger = logging.getLogger(__name__)

# 块类型选项（商品信息暂不在此处支持，由商品录入页单独处理）
BLOCK_TYPE_OPTIONS: list[tuple[str, str]] = [
    ("customer", "客户信息"),
    ("shipping", "运输与发货信息"),
    ("order_full", "整单模板"),
]

# order_full 套用范围选项
ORDER_FULL_FIELD_GROUPS: list[tuple[str, str, list[str]]] = [
    (
        "订单元信息",
        "order_meta",
        [
            "invoice_no",
            "contract_no",
            "date",
            "order_no",
            "transport_mode",
            "vessel_flight",
            "bill_of_lading_no",
            "trade_term",
            "payment_term",
            "currency",
            "country_of_origin",
            "goods_summary",
            "declaration_elements_template",
            "package_type",
        ],
    ),
    (
        "客户信息",
        "customer",
        [
            "company_name_en",
            "company_name_cn",
            "country",
            "address",
            "contact_person",
            "phone",
            "mobile",
            "destination",
        ],
    ),
    (
        "境内信息",
        "origin",
        [
            "export_port",
            "domestic_source",
            "manufacturer",
            "business_entity",
            "trade_mode",
            "tax_nature",
            "settlement_method",
            "tax_rebate",
        ],
    ),
]


class TemplateBlockDialog:
    """套用模板对话框.

    Usage:
        dialog = TemplateBlockDialog(parent, app)
        dialog.show()
    """

    def __init__(self, parent: ttk.Frame, app: GuiApp) -> None:
        """初始化对话框.

        Args:
            parent: 父级组件.
            app: GuiApp 主控制器.
        """
        self._parent = parent
        self._app = app
        self._blocks: list[dict[str, Any]] = []
        self._block_list_tree: ttk.Treeview | None = None
        self._dialog: ttk.Toplevel | None = None

    def show(self) -> None:
        """显示对话框."""
        self._dialog = ttk.Toplevel(self._parent, title="套用分块模板")
        self._dialog.geometry("620x520")
        self._dialog.transient(self._parent)
        self._dialog.grab_set()

        # ---- 标题 ----
        ttk.Label(
            self._dialog,
            text="从已保存的模板中套用数据",
            font=self._app.get_font(bold=True, size=12),
            bootstyle="primary",
        ).pack(padx=20, pady=(15, 10))

        # ---- 类型筛选 ----
        filter_frame = ttk.Frame(self._dialog)
        filter_frame.pack(fill=X, padx=20, pady=(0, 10))

        ttk.Label(filter_frame, text="模板类型:", font=self._app.get_font(size=10)).pack(
            side=LEFT, padx=(0, 8)
        )

        self._type_var = ttk.StringVar(value="customer")
        type_combo = ttk.Combobox(
            filter_frame,
            textvariable=self._type_var,
            values=[opt[1] for opt in BLOCK_TYPE_OPTIONS],
            state="readonly",
            width=18,
        )
        type_combo.pack(side=LEFT, padx=(0, 15))
        type_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_list())

        ttk.Button(
            filter_frame,
            text="刷新",
            bootstyle="secondary-outline",
            command=self._refresh_list,
        ).pack(side=LEFT)

        # ---- 模板列表 ----
        list_frame = ttk.Labelframe(self._dialog, text="已保存的模板", padding=8, bootstyle="info")
        list_frame.pack(fill=BOTH, expand=YES, padx=20, pady=(0, 10))

        columns = ("id", "name", "desc", "date")
        self._block_list_tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            height=8,
        )
        self._block_list_tree.heading("id", text="ID")
        self._block_list_tree.heading("name", text="模板名称")
        self._block_list_tree.heading("desc", text="备注")
        self._block_list_tree.heading("date", text="保存日期")
        self._block_list_tree.column("id", width=40, anchor=CENTER)
        self._block_list_tree.column("name", width=180)
        self._block_list_tree.column("desc", width=180)
        self._block_list_tree.column("date", width=100, anchor=CENTER)

        tree_scrollbar = ttk.Scrollbar(
            list_frame, orient=VERTICAL, command=self._block_list_tree.yview
        )
        self._block_list_tree.configure(yscrollcommand=tree_scrollbar.set)
        self._block_list_tree.pack(side=LEFT, fill=BOTH, expand=YES)
        tree_scrollbar.pack(side=RIGHT, fill=Y)

        # ---- 套用范围（仅 order_full 显示） ----
        self._scope_frame = ttk.Labelframe(
            self._dialog, text="套用范围（勾选需要覆盖的字段组）", padding=8, bootstyle="warning"
        )
        self._scope_vars: dict[str, ttk.BooleanVar] = {}
        for _label, key, _ in ORDER_FULL_FIELD_GROUPS:
            var = ttk.BooleanVar(value=True)
            self._scope_vars[key] = var

        self._scope_checkbuttons: list[ttk.Checkbutton] = []
        for _label, key, _ in ORDER_FULL_FIELD_GROUPS:
            cb = ttk.Checkbutton(
                self._scope_frame,
                text=_label,
                variable=self._scope_vars[key],
                bootstyle="info-round-toggle",
            )
            cb.pack(side=LEFT, padx=(5, 15), pady=5)
            self._scope_checkbuttons.append(cb)

        # 默认隐藏 scope_frame（非 order_full 时）
        self._scope_frame.pack_forget()

        # ---- 底部操作按钮 ----
        btn_frame = ttk.Frame(self._dialog)
        btn_frame.pack(fill=X, padx=20, pady=(5, 15))

        ttk.Button(
            btn_frame,
            text="取消",
            bootstyle="secondary-outline",
            command=self._dialog.destroy,
        ).pack(side=RIGHT, padx=(10, 0))

        ttk.Button(
            btn_frame,
            text="套用到当前订单",
            bootstyle="success",
            command=self._on_apply,
        ).pack(side=RIGHT)

        # 初始加载
        self._refresh_list()

    # ==================== 内部方法 ====================

    def _get_selected_type(self) -> str:
        """获取当前选中的块类型键."""
        label = self._type_var.get()
        for key, lbl in BLOCK_TYPE_OPTIONS:
            if lbl == label:
                return key
        return "customer"

    def _refresh_list(self) -> None:
        """刷新模板列表."""
        if self._block_list_tree is None:
            return

        for item in self._block_list_tree.get_children():
            self._block_list_tree.delete(item)

        block_type = self._get_selected_type()

        try:
            from src.gui.services.template_block_service import TemplateBlockService

            self._blocks = TemplateBlockService.load_blocks(block_type)
        except Exception as e:
            logger.exception("[错误]: 加载分块模板列表失败")
            messagebox.showerror("加载失败", f"[错误]: 无法加载模板列表\n[原因]: {e}")
            return

        for blk in self._blocks:
            self._block_list_tree.insert(
                "",
                END,
                values=(
                    blk.get("id", ""),
                    blk.get("block_name", "未命名"),
                    blk.get("description", ""),
                    (blk.get("created_at", "") or "")[:10],
                ),
            )

        # 根据类型显示/隐藏套用范围面板
        if block_type == "order_full":
            self._scope_frame.pack(
                fill=X, padx=20, pady=(0, 10), before=self._dialog.winfo_children()[-1]
            )
        else:
            self._scope_frame.pack_forget()

    def _on_apply(self) -> None:
        """点击套用按钮."""
        if self._block_list_tree is None:
            return

        selection = self._block_list_tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请先在列表中选择一个模板。")
            return

        item = self._block_list_tree.item(selection[0])
        block_id = item["values"][0]

        try:
            from src.gui.services.template_block_service import TemplateBlockService

            block = TemplateBlockService.get_block(int(block_id))
            if block is None:
                messagebox.showerror("加载失败", f"分块模板 ID={block_id} 不存在或已删除。")
                return

            current_data = self._app.current_order_data
            if not current_data:
                current_data = {}

            block_type = self._get_selected_type()

            if block_type == "order_full":
                # 收集勾选的字段
                selected_fields: set[str] = set()
                for _label, key, fields in ORDER_FULL_FIELD_GROUPS:
                    if self._scope_vars.get(key, ttk.BooleanVar(value=True)).get():
                        selected_fields.update(fields)
                new_data = TemplateBlockService.apply_block(block, current_data, selected_fields)
            else:
                new_data = TemplateBlockService.apply_block(block, current_data)

            # 更新订单数据
            self._app.current_order_data = new_data
            self._app.set_dirty(True)

            # 如果当前在订单信息页，重新填充表单
            current_page = getattr(self._app, "_current_page_name", "")
            if current_page == "order_info" and hasattr(self._app, "_pages"):
                page = self._app._pages.get("order_info")
                if page is not None and hasattr(page, "_fill_from_order_data_dict"):
                    page._fill_from_order_data_dict(new_data)

            block_name = block.get("block_name", "未命名")
            messagebox.showinfo(
                "套用成功",
                f"模板「{block_name}」已套用到当前订单。\n\n请检查套用后的数据是否正确。",
            )
            self._app.set_status(f"已套用模板: {block_name}")

            if self._dialog is not None:
                self._dialog.destroy()

        except Exception as e:
            logger.exception("[错误]: 套用模板失败")
            messagebox.showerror("套用失败", f"[错误]: {e}")
