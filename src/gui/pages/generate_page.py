"""生成与预览页 — 阶段 9.6（3 文件模式）.

提供：
- 一键生成按钮 → 进度条 → 完成提示
- 生成清单显示 3 项（装箱单 / 发票 / 合同 / 报关单暂未就绪）
- 诊断包导出按钮（仅出错时显示）
- 打开输出文件夹按钮

子模块拆分：
- generate_events.py: 生成启动/线程/回调、诊断包导出、打开文件夹（GenerateEventsMixin）
- 本模块            : UI 构建 + 生命周期方法
"""

from __future__ import annotations

import logging
from tkinter import END
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.gui.app import GuiApp

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from config.constants import OUTPUT_DIR
from src.gui.page_base import PageBase
from src.gui.pages.generate_events import GenerateEventsMixin

logger = logging.getLogger(__name__)


class GeneratePage(PageBase, GenerateEventsMixin):
    """生成与预览页."""

    def __init__(self, parent: ttk.Frame, app: GuiApp):
        super().__init__(parent, app)
        self._progress_bar: ttk.Progressbar | None = None
        self._progress_label: ttk.Label | None = None
        self._result_frame: ttk.Frame | None = None
        self._result_vars: dict[str, ttk.StringVar] = {}
        self._result_icons: dict[str, ttk.Label] = {}
        self._diagnostic_btn: ttk.Button | None = None
        self._open_folder_btn: ttk.Button | None = None
        self._generate_btn: ttk.Button | None = None
        self._report: Any = None
        self._is_generating: bool = False
        self._summary_text: ttk.Text | None = None

    # ==================== 构建 UI ====================

    def build(self) -> None:
        """构建生成页 UI."""
        self.frame = ttk.Frame(self.parent)
        self.frame.pack(fill=BOTH, expand=YES, padx=10, pady=10)

        # 标题
        title_frame = ttk.Frame(self.frame)
        title_frame.pack(fill=X, padx=5, pady=(5, 10))

        ttk.Label(
            title_frame,
            text="生成报关资料",
            font=self.app.get_heading_font(),
            bootstyle="primary",
        ).pack(side=LEFT)

        ttk.Label(
            title_frame,
            text="3 文件模式（报关单暂未就绪）",
            font=self.app.get_font(size=9),
            bootstyle="warning",
        ).pack(side=RIGHT)

        self._build_summary_section()
        self._build_result_section()

        # 进度区
        progress_frame = ttk.Labelframe(self.frame, text="生成进度", padding=10, bootstyle="info")
        progress_frame.pack(fill=X, pady=(0, 10))

        self._progress_label = ttk.Label(
            progress_frame,
            text="准备就绪，点击下方按钮开始生成。",
            font=self.app.get_font(size=10),
        )
        self._progress_label.pack(anchor=W, pady=(0, 5))

        self._progress_bar = ttk.Progressbar(
            progress_frame,
            mode="determinate",
            length=400,
            bootstyle="success-striped",
        )
        self._progress_bar.pack(fill=X)
        self._progress_bar["value"] = 0

        # 底部按钮
        bottom = ttk.Frame(self.frame)
        bottom.pack(fill=X, padx=5, pady=(10, 5))

        ttk.Button(
            bottom,
            text="← 返回编辑商品明细",
            bootstyle="secondary-outline",
            command=lambda: self.app.switch_page("line_items"),
        ).pack(side=LEFT)

        self._open_folder_btn = ttk.Button(
            bottom,
            text="打开输出文件夹",
            bootstyle="info-outline",
            command=self._on_open_folder,
        )
        self._open_folder_btn.pack(side=LEFT, padx=(10, 0))

        self._diagnostic_btn = ttk.Button(
            bottom,
            text="导出诊断包",
            bootstyle="warning-outline",
            command=self._on_export_diagnostic,
        )

        self._generate_btn = ttk.Button(
            bottom,
            text="一键生成报关资料",
            bootstyle="success",
            command=self._on_generate,
        )
        self._generate_btn.pack(side=RIGHT)

    def _build_summary_section(self) -> None:
        """构建订单摘要区域."""
        summary_frame = ttk.Labelframe(self.frame, text="订单摘要", padding=10, bootstyle="primary")
        summary_frame.pack(fill=X, pady=(0, 10))

        self._summary_text = ttk.Text(
            summary_frame,
            height=6,
            wrap="word",
            font=self.app.get_font(size=10),
            state="disabled",
        )
        self._summary_text.pack(fill=X)

    def _build_result_section(self) -> None:
        """构建生成结果区域."""
        self._result_frame = ttk.Labelframe(
            self.frame,
            text="生成结果",
            padding=10,
            bootstyle="success",
        )
        self._result_frame.pack(fill=X, pady=(0, 10))

        items: list[tuple[str, str, str]] = [
            ("packing", "装箱单", "等待生成..."),
            ("invoice", "形式发票", "等待生成..."),
            ("contract", "形式合同", "等待生成..."),
            ("customs", "报关单", "暂未就绪（阶段 6 开发中）"),
        ]

        for file_type, label, default_status in items:
            row = ttk.Frame(self._result_frame)
            row.pack(fill=X, pady=3)

            icon_var = ttk.StringVar(value="⏳")
            icon_label = ttk.Label(row, textvariable=icon_var, font=("Segoe UI Symbol", 16))
            icon_label.pack(side=LEFT, padx=(0, 5))
            self._result_icons[file_type] = icon_label

            ttk.Label(
                row, text=label, font=self.app.get_font(bold=True, size=10), width=15, anchor=W
            ).pack(side=LEFT)

            status_var = ttk.StringVar(value=default_status)
            status_label = ttk.Label(row, textvariable=status_var, font=self.app.get_font(size=9))
            status_label.pack(side=LEFT, padx=(5, 0))
            self._result_vars[file_type] = status_var

    # ==================== 状态方法 ====================

    def _reset_results(self) -> None:
        """重置结果状态."""
        defaults = {
            "packing": "等待生成...",
            "invoice": "等待生成...",
            "contract": "等待生成...",
            "customs": "⏳ 暂未就绪（阶段 6 开发中）",
        }
        icons = {"packing": "⏳", "invoice": "⏳", "contract": "⏳", "customs": "⏳"}
        for ft in defaults:
            if ft in self._result_vars:
                self._result_vars[ft].set(defaults[ft])
            if ft in self._result_icons:
                self._result_icons[ft].configure(textvariable=ttk.StringVar(value=icons[ft]))

        self._update_progress(0, "准备就绪...")

    def _update_progress(self, value: int, description: str) -> None:
        """更新进度条和进度文字."""
        if self._progress_bar is not None:
            self._progress_bar["value"] = value
        if self._progress_label is not None:
            self._progress_label.configure(text=description)

    def _update_summary(self, text: str) -> None:
        """更新摘要文本."""
        if self._summary_text is None:
            return
        self._summary_text.configure(state="normal")
        self._summary_text.delete("1.0", END)
        self._summary_text.insert(END, text)
        self._summary_text.configure(state="disabled")

    # ==================== 生命周期 ====================

    def on_enter(self) -> None:
        """进入页面时更新摘要."""
        order = self.app.current_order
        if order is None:
            self._update_summary("⚠️ 无订单数据，请先在「新建单据」中录入。")
            if self._generate_btn is not None:
                self._generate_btn.configure(state="disabled")
            return

        if self._generate_btn is not None:
            self._generate_btn.configure(state="normal")

        meta = order.order_meta
        cust = order.customer
        totals = order.totals

        summary_lines = [
            f"发票号: {meta.invoice_no}",
            f"合同号: {meta.contract_no}",
            f"日期: {meta.date}",
            f"客户: {cust.company_name_en}",
            f"国家: {cust.country}",
            f"贸易条款: {meta.trade_term}    运输方式: {meta.transport_mode}",
            f"托盘: {totals.total_pallets} | 纸箱: {totals.total_cartons} | "
            f"总毛重: {totals.total_gross_weight_kg} kg | "
            f"总净重: {totals.total_net_weight_kg} kg",
            f"总体积: {totals.total_volume_cbm} m³ | 总金额: ${totals.total_amount:,.2f}",
            f"输出目录: {OUTPUT_DIR}",
        ]

        self._update_summary("\n".join(summary_lines))
        self._reset_results()
