"""树状编辑器 — UI 构建 mixin.

包含 build、Treeview 构建、详情面板框架、右键菜单、节点选择路由。
详情表单的具体字段构建与保存见 tree_detail.py。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

if TYPE_CHECKING:
    from src.gui.pages.tree_editor_page import TreeEditorPage

logger = logging.getLogger(__name__)


class TreeUIMixin:
    """树状编辑器的 UI 构建方法.

    假设 self 提供：
    - self._pallets, self._tree, self._detail_frame, self._detail_vars
    - self._detail_title_var, self._stats_var, self._context_menu
    - self._selected_* 系列属性
    - self.app, self.parent（来自 PageBase）
    - self._add_pallet/carton/product（来自 TreeDataMixin）
    - self._expand/collapse_all（来自 TreeDataMixin）
    - self._show_*_detail（来自 TreeDetailMixin）
    - self._on_generate/import/clear（来自 TreeEventsMixin）
    """

    _pallets: list[dict[str, Any]]
    _tree: ttk.Treeview | None
    _detail_frame: ttk.Frame | None
    _detail_vars: dict[str, Any]
    _detail_title_var: ttk.StringVar
    _stats_var: ttk.StringVar
    _context_menu: ttk.Menu | None
    _selected_pallet_idx: int
    _selected_carton_idx: int
    _selected_product_idx: int
    _selected_level: str
    app: object
    parent: ttk.Frame

    # ==================== 构建 UI ====================

    def build(self: TreeEditorPage) -> None:
        """构建树状编辑器 UI."""
        self.frame = ttk.Frame(self.parent)
        self.frame.pack(fill=BOTH, expand=YES, padx=10, pady=10)

        title_frame = ttk.Frame(self.frame)
        title_frame.pack(fill=X, padx=5, pady=(5, 10))

        ttk.Label(
            title_frame,
            text="商品明细编辑（托盘 → 纸箱 → 商品）",
            font=self.app.get_heading_font(),
            bootstyle="primary",
        ).pack(side=LEFT)

        self._stats_var = ttk.StringVar(value="托盘: 0 | 纸箱: 0 | 商品: 0")
        ttk.Label(
            title_frame,
            textvariable=self._stats_var,
            font=self.app.get_font(size=10),
            bootstyle="secondary",
        ).pack(side=RIGHT)

        content_paned = ttk.PanedWindow(self.frame, orient=HORIZONTAL)
        content_paned.pack(fill=BOTH, expand=YES)

        left_frame = ttk.Frame(content_paned)
        content_paned.add(left_frame, weight=2)
        self._build_tree_view(left_frame)

        right_frame = ttk.Frame(content_paned)
        content_paned.add(right_frame, weight=3)
        self._build_detail_panel(right_frame)

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
            text="清空所有商品",
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

        self._setup_context_menu()

    def _build_tree_view(self: TreeEditorPage, parent: ttk.Frame) -> None:
        """构建左侧树状视图."""
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

        tree_scroll = ttk.Scrollbar(tree_frame, orient=VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=tree_scroll.set)
        self._tree.pack(side=LEFT, fill=BOTH, expand=YES)
        tree_scroll.pack(side=RIGHT, fill=Y)

        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._tree.bind("<Button-3>", self._on_right_click)

    def _build_detail_panel(self: TreeEditorPage, parent: ttk.Frame) -> None:
        """构建右侧详情表单面板."""
        self._detail_title_var = ttk.StringVar(value="选择左侧节点查看详情")
        ttk.Label(
            parent,
            textvariable=self._detail_title_var,
            font=self.app.get_font(bold=True, size=12),
            bootstyle="primary",
        ).pack(anchor=W, padx=10, pady=(10, 5))

        ttk.Separator(parent, orient=HORIZONTAL).pack(fill=X, padx=5)

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

        def _on_wheel(event: Any) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        ttk.Label(
            self._detail_frame,
            text="从左侧树中选择一个节点，\n即可在此处查看和编辑详细信息。\n\n"
            "• 选中托盘 → 编辑托盘尺寸和重量\n"
            "• 选中纸箱 → 编辑纸箱尺寸和毛重\n"
            "• 选中商品 → 编辑商品规格和价格",
            font=self.app.get_font(size=10),
            bootstyle="secondary",
            justify=LEFT,
        ).pack(padx=20, pady=20)

    # ==================== 右键菜单 ====================

    def _setup_context_menu(self: TreeEditorPage) -> None:
        """设置右键菜单."""
        self._context_menu = ttk.Menu(self.frame, tearoff=0)
        self._context_menu.add_command(label="➕ 新增托盘", command=lambda: self._add_pallet())
        self._context_menu.add_command(label="➕ 新增纸箱", command=lambda: self._add_carton())
        self._context_menu.add_command(label="➕ 新增商品", command=lambda: self._add_product())
        self._context_menu.add_separator()
        self._context_menu.add_command(label="🐑 克隆当前节点", command=self._on_clone)
        self._context_menu.add_separator()
        self._context_menu.add_command(label="🗑 删除当前节点", command=self._on_delete_node)

    def _on_right_click(self: TreeEditorPage, event: Any) -> None:
        """右键点击事件."""
        item = self._tree.identify_row(event.y)
        if item:
            self._tree.selection_set(item)
            self._on_tree_select(None)
        try:
            self._context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._context_menu.grab_release()

    # ==================== 节点选择路由 ====================

    def _on_tree_select(self: TreeEditorPage, event: Any) -> None:
        """Treeview 节点选中事件 — 路由到对应的详情展示方法."""
        if self._tree is None:
            return

        selection = self._tree.selection()
        if not selection:
            return

        item_id = selection[0]
        parts = item_id.split("_")

        try:
            if len(parts) == 2 and parts[0] == "p":
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
                    self._selected_product_idx = int(parts[5])
                    self._selected_level = "product"
                    self._show_product_detail()
                else:
                    self._selected_level = "carton"
                    self._show_carton_detail()

        except (IndexError, ValueError) as e:
            logger.warning("[警告]: 解析 Treeview 节点 ID 失败: %s (%s)", item_id, e)
