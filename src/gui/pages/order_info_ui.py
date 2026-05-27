"""订单信息页 — UI 构建 mixin.

包含四个区块的构建及表单工具方法。
"""

from __future__ import annotations

# pyright: reportAttributeAccessIssue=false
from typing import TYPE_CHECKING

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

if TYPE_CHECKING:
    from src.gui.app import GuiApp


class OrderInfoUIMixin:
    """订单信息页 UI 构建方法.

    假设 self 提供：
    - self._variables, self._settings
    - self.app（来自 PageBase）
    """

    _variables: dict[str, ttk.StringVar | ttk.IntVar]
    _entry_widgets: dict[str, ttk.Entry]
    _settings: dict
    app: GuiApp

    # ==================== 订单元信息区块 ====================

    def _build_order_meta_section(self, parent: ttk.Frame) -> None:
        """构建订单元信息区块."""
        section = self._add_section(parent, "订单元信息")

        row1 = ttk.Frame(section)
        row1.pack(fill=X, pady=2)
        self._add_field(row1, "发票号 *:", "invoice_no", 0)
        self._add_field(row1, "合同号 *:", "contract_no", 1)

        row2 = ttk.Frame(section)
        row2.pack(fill=X, pady=2)
        self._add_date_field(row2, "日期 *:", "date", 0)
        self._add_field(row2, "订单号:", "order_no", 1)

        row3 = ttk.Frame(section)
        row3.pack(fill=X, pady=2)
        self._add_combobox(row3, "运输方式:", "transport_mode", ["海运", "空运", "陆运"], "海运", 0)
        self._add_field(row3, "船名/航班号:", "vessel_flight", 1)

        row4 = ttk.Frame(section)
        row4.pack(fill=X, pady=2)
        self._add_field(row4, "提单号:", "bill_of_lading_no", 0)
        self._add_combobox(
            row4, "贸易条款:", "trade_term", ["FOB", "CIF", "DAP", "DDP", "EXW", "CFR"], "FOB", 1
        )

        row5 = ttk.Frame(section)
        row5.pack(fill=X, pady=2)
        self._add_field(row5, "付款方式:", "payment_term", 0)
        self._add_combobox(row5, "币种:", "currency", ["USD", "EUR", "CNY", "GBP", "JPY"], "USD", 1)

        row6 = ttk.Frame(section)
        row6.pack(fill=X, pady=2)
        self._add_field(row6, "原产国:", "country_of_origin", 0)
        self._add_field(row6, "货品名称:", "goods_summary", 1)

    # ==================== 客户信息区块 ====================

    def _build_customer_section(self, parent: ttk.Frame) -> None:
        """构建客户信息区块."""
        section = self._add_section(parent, "客户信息")

        row1 = ttk.Frame(section)
        row1.pack(fill=X, pady=2)
        self._add_field(row1, "客户公司名 *:", "company_name_en", 0, width=45)

        row2 = ttk.Frame(section)
        row2.pack(fill=X, pady=2)
        self._add_field(row2, "客户中文名:", "company_name_cn", 0)
        self._add_field(row2, "国家 *:", "country", 1)

        row3 = ttk.Frame(section)
        row3.pack(fill=X, pady=2)
        self._add_field(row3, "客户地址:", "address", 0, width=45)

        row4 = ttk.Frame(section)
        row4.pack(fill=X, pady=2)
        self._add_field(row4, "联系人:", "contact_person", 0)
        self._add_field(row4, "电话:", "phone", 1)

        row5 = ttk.Frame(section)
        row5.pack(fill=X, pady=2)
        self._add_field(row5, "手机号:", "mobile", 0)
        self._add_field(row5, "目的地/卸货港:", "destination", 1)

        # "从客户库选择"按钮
        btn_row = ttk.Frame(section)
        btn_row.pack(fill=X, pady=(5, 0))
        ttk.Button(
            btn_row,
            text="从客户库选择...",
            bootstyle="info-outline",
            command=self._on_select_from_customer_lib,
        ).pack(side=LEFT)

    # ==================== 运输信息区块 ====================

    def _build_shipping_section(self, parent: ttk.Frame) -> None:
        """构建运输贸易信息区块."""
        section = self._add_section(parent, "运输与发货信息")

        row1 = ttk.Frame(section)
        row1.pack(fill=X, pady=2)
        self._add_field(row1, "装运港:", "export_port", 0)
        self._add_combobox(
            row1, "包装类型:", "package_type", ["pallet", "carton", "package"], "pallet", 1
        )

        row2 = ttk.Frame(section)
        row2.pack(fill=X, pady=2)
        self._add_field(row2, "申报要素模板:", "declaration_elements_template", 0, width=45)

    # ==================== 境内信息区块 ====================

    def _build_origin_section(self, parent: ttk.Frame) -> None:
        """构建境内信息区块（默认值预填）."""
        section = self._add_section(parent, "境内信息（默认值可修改）")

        company_defaults = self._settings.get("company", {})

        row1 = ttk.Frame(section)
        row1.pack(fill=X, pady=2)
        self._add_field(
            row1,
            "经营单位:",
            "business_entity",
            0,
            default=company_defaults.get("name_cn", "长园长通新材料股份有限公司"),
        )
        self._add_field(
            row1,
            "生产厂家:",
            "manufacturer",
            1,
            default=company_defaults.get("name_cn", "长园长通新材料股份有限公司"),
        )

        row2 = ttk.Frame(section)
        row2.pack(fill=X, pady=2)
        self._add_field(row2, "境内货源地:", "domestic_source", 0, default="深圳特区")
        self._add_field(row2, "贸易方式:", "trade_mode", 1, default="一般贸易")

        row3 = ttk.Frame(section)
        row3.pack(fill=X, pady=2)
        self._add_field(row3, "征免性质:", "tax_nature", 0, default="一般征税")
        self._add_field(row3, "结汇方式:", "settlement_method", 1, default="电汇")

        row4 = ttk.Frame(section)
        row4.pack(fill=X, pady=2)
        self._add_field(row4, "退税:", "tax_rebate", 0, default="申请退税")

    # ==================== UI 工具方法 ====================

    def _add_section(self, parent: ttk.Frame, title: str) -> ttk.Labelframe:
        """添加一个区块."""
        section = ttk.Labelframe(parent, text=title, padding=10, bootstyle="primary")
        section.pack(fill=X, pady=(5, 10))
        return section

    def _add_field(
        self,
        parent: ttk.Frame,
        label: str,
        field_name: str,
        col: int,
        default: str = "",
        width: int = 30,
    ) -> ttk.Frame:
        """添加一个标签 + 输入框."""
        f = ttk.Frame(parent)
        f.pack(side=LEFT, fill=X, expand=YES, padx=(0 if col == 0 else 20, 5))

        ttk.Label(f, text=label, font=self.app.get_font(size=10)).pack(anchor=W)

        var = ttk.StringVar(value=default)
        entry = ttk.Entry(f, textvariable=var, width=width)
        entry.pack(fill=X, expand=YES)
        self._variables[field_name] = var
        if hasattr(self, "_entry_widgets"):
            self._entry_widgets[field_name] = entry
        return f

    def _add_date_field(
        self,
        parent: ttk.Frame,
        label: str,
        field_name: str,
        col: int,
        default: str = "",
    ) -> None:
        """添加日期输入字段，默认填入今天日期."""
        if not default:
            from datetime import datetime

            default = datetime.now().strftime("%Y-%m-%d")
        self._add_field(parent, label, field_name, col, default=default, width=18)

    def _add_combobox(
        self,
        parent: ttk.Frame,
        label: str,
        field_name: str,
        values: list[str],
        default: str,
        col: int,
    ) -> None:
        """添加下拉选择框."""
        f = ttk.Frame(parent)
        f.pack(side=LEFT, fill=X, expand=YES, padx=(0 if col == 0 else 20, 5))

        ttk.Label(f, text=label, font=self.app.get_font(size=10)).pack(anchor=W)

        var = ttk.StringVar(value=default)
        cb = ttk.Combobox(f, textvariable=var, values=values, state="readonly", width=18)
        cb.pack(fill=X, expand=YES)
        self._variables[field_name] = var
