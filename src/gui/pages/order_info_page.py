# -*- coding: utf-8 -*-
"""订单信息录入页 — 阶段 9.2.

提供：
- 订单元信息录入（发票号、合同号、日期等）
- 客户信息录入（公司名、地址、国家等）
- 运输与贸易信息录入（运输方式、贸易术语、币种）
- 境内信息录入（默认值预填）
- 校验与下一步跳转

子模块拆分：
- order_info_ui.py   : 四个区块 UI 构建 + 表单工具方法（OrderInfoUIMixin）
- order_info_data.py : 数据收集、表单填充、校验、导入/清空（OrderInfoDataMixin）
- 本模块             : 主类定义 + build 画布 + 生命周期方法
"""

from __future__ import annotations

import logging
from typing import Any

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from config.settings import get_all_settings
from src.gui.page_base import PageBase
from src.gui.pages.order_info_data import OrderInfoDataMixin
from src.gui.pages.order_info_ui import OrderInfoUIMixin

logger = logging.getLogger(__name__)


class OrderInfoPage(PageBase, OrderInfoUIMixin, OrderInfoDataMixin):
    """订单信息录入页."""

    def __init__(self, parent: ttk.Frame, app: object):
        super().__init__(parent, app)
        self._settings: dict[str, Any] = get_all_settings()
        self._variables: dict[str, ttk.StringVar | ttk.IntVar] = {}
        self._entry_widgets: dict[str, ttk.Entry] = {}

    # ==================== 构建 UI ====================

    def build(self) -> None:
        """构建订单录入页 UI."""
        self.frame = ttk.Frame(self.parent)
        self.frame.pack(fill=BOTH, expand=YES, padx=10, pady=10)

        canvas = ttk.Canvas(self.frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.frame, orient=VERTICAL, command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=LEFT, fill=BOTH, expand=YES)
        scrollbar.pack(side=RIGHT, fill=Y)

        def _on_mousewheel(event: Any) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        self.frame.bind("<Destroy>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # 标题
        title_frame = ttk.Frame(scrollable_frame)
        title_frame.pack(fill=X, padx=15, pady=(10, 5))

        ttk.Label(
            title_frame, text="新建报关单据",
            font=self.app.get_heading_font(),
            bootstyle="primary",
        ).pack(side=LEFT)

        inner = ttk.Frame(scrollable_frame)
        inner.pack(fill=BOTH, expand=YES, padx=15, pady=5)

        self._build_order_meta_section(inner)
        self._build_customer_section(inner)
        self._build_shipping_section(inner)
        self._build_origin_section(inner)

        # 底部按钮
        bottom = ttk.Frame(scrollable_frame)
        bottom.pack(fill=X, padx=15, pady=(10, 20))

        ttk.Button(
            bottom, text="从 Excel 导入订单数据...",
            bootstyle="info-outline",
            command=self._on_import_excel,
        ).pack(side=LEFT, padx=(0, 10))

        ttk.Button(
            bottom, text="下一步 → 编辑商品明细",
            bootstyle="success",
            command=self._on_next_step,
        ).pack(side=RIGHT)

        ttk.Button(
            bottom, text="清空表单",
            bootstyle="secondary-outline",
            command=self._on_clear,
        ).pack(side=RIGHT, padx=(0, 10))

        # 设置实时校验
        self._setup_validation()

    # ==================== 生命周期 ====================

    def on_enter(self) -> None:
        """页面进入时恢复数据."""
        data = self.app.current_order_data
        if data and "order_meta" in data:
            for k, v in data.get("order_meta", {}).items():
                if k in self._variables:
                    self._variables[k].set(str(v))
            for k, v in data.get("customer", {}).items():
                if k in self._variables:
                    self._variables[k].set(str(v))
            for k, v in data.get("origin", {}).items():
                if k in self._variables:
                    self._variables[k].set(str(v))
