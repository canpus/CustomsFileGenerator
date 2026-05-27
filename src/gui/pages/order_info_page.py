# -*- coding: utf-8 -*-
"""订单信息录入页 — 阶段 9.2.

提供：
- 订单元信息录入（发票号、合同号、日期等）
- 客户信息录入（公司名、地址、国家等）
- 运输与贸易信息录入（运输方式、贸易术语、币种）
- 境内信息录入（默认值预填）
- 校验与下一步跳转
"""

from __future__ import annotations

import logging
from datetime import datetime
from tkinter import messagebox
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.models.order_data import OrderData

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from config.constants import (
    Currency,
    PaymentMethod,
    TradeTerm,
    TransportMode,
    DEFAULT_CURRENCY,
    DEFAULT_ORIGIN_COUNTRY,
    DEFAULT_PAYMENT_METHOD,
    DEFAULT_TRADE_TERM,
)
from config.settings import get_all_settings

logger = logging.getLogger(__name__)

# 导入 PageBase（延迟导入避免循环）
try:
    from src.gui.app import PageBase, GuiApp
except ImportError:
    PageBase = object
    GuiApp = object


class OrderInfoPage(PageBase):
    """订单信息录入页.

    包含订单元信息、客户信息、运输贸易信息、境内信息四个区块。
    填写完成后可点击"下一步 → 编辑商品明细"跳转到树状编辑器。
    """

    def __init__(self, parent: ttk.Frame, app: GuiApp):
        """初始化.

        Args:
            parent: 父级容器.
            app: 主应用控制器.
        """
        super().__init__(parent, app)
        self._settings: dict[str, Any] = get_all_settings()
        self._variables: dict[str, ttk.StringVar | ttk.IntVar] = {}

    def build(self) -> None:
        """构建订单录入页 UI."""
        self.frame = ttk.Frame(self.parent)
        self.frame.pack(fill=BOTH, expand=YES, padx=10, pady=10)

        # 可滚动的画布
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

        # 绑定鼠标滚轮
        def _on_mousewheel(event: Any) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        self.frame.bind("<Destroy>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # ---- 标题 ----
        title_frame = ttk.Frame(scrollable_frame)
        title_frame.pack(fill=X, padx=15, pady=(10, 5))

        ttk.Label(
            title_frame,
            text="📋 新建报关单据",
            font=self.app.get_heading_font(),
            bootstyle="primary",
        ).pack(side=LEFT)

        # 填充剩余内容
        inner = ttk.Frame(scrollable_frame)
        inner.pack(fill=BOTH, expand=YES, padx=15, pady=5)

        self._build_order_meta_section(inner)
        self._build_customer_section(inner)
        self._build_shipping_section(inner)
        self._build_origin_section(inner)

        # ---- 底部按钮 ----
        bottom = ttk.Frame(scrollable_frame)
        bottom.pack(fill=X, padx=15, pady=(10, 20))

        ttk.Button(
            bottom,
            text="从 Excel 导入订单数据...",
            bootstyle="info-outline",
            command=self._on_import_excel,
        ).pack(side=LEFT, padx=(0, 10))

        ttk.Button(
            bottom,
            text="下一步 → 编辑商品明细",
            bootstyle="success",
            command=self._on_next_step,
        ).pack(side=RIGHT)

        ttk.Button(
            bottom,
            text="清空表单",
            bootstyle="secondary-outline",
            command=self._on_clear,
        ).pack(side=RIGHT, padx=(0, 10))

    # ==================== 订单元信息区块 ====================

    def _build_order_meta_section(self, parent: ttk.Frame) -> None:
        """构建订单元信息区块."""
        section = self._add_section(parent, "📄 订单元信息")

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
        self._add_combobox(
            row3,
            "运输方式:",
            "transport_mode",
            ["海运", "空运", "陆运"],
            "海运",
            0,
        )
        self._add_field(row3, "船名/航班号:", "vessel_flight", 1)

        row4 = ttk.Frame(section)
        row4.pack(fill=X, pady=2)
        self._add_field(row4, "提单号:", "bill_of_lading_no", 0)
        self._add_combobox(
            row4,
            "贸易条款:",
            "trade_term",
            ["FOB", "CIF", "DAP", "DDP", "EXW", "CFR"],
            "FOB",
            1,
        )

        row5 = ttk.Frame(section)
        row5.pack(fill=X, pady=2)
        self._add_field(row5, "付款方式:", "payment_term", 0)
        self._add_combobox(
            row5,
            "币种:",
            "currency",
            ["USD", "EUR", "CNY", "GBP", "JPY"],
            "USD",
            1,
        )

        row6 = ttk.Frame(section)
        row6.pack(fill=X, pady=2)
        self._add_field(row6, "原产国:", "country_of_origin", 0)
        self._add_field(row6, "货品名称:", "goods_summary", 1)

    # ==================== 客户信息区块 ====================

    def _build_customer_section(self, parent: ttk.Frame) -> None:
        """构建客户信息区块."""
        section = self._add_section(parent, "👤 客户信息")

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

    # ==================== 运输信息区块 ====================

    def _build_shipping_section(self, parent: ttk.Frame) -> None:
        """构建运输贸易信息区块."""
        section = self._add_section(parent, "🚢 运输与发货信息")

        row1 = ttk.Frame(section)
        row1.pack(fill=X, pady=2)
        self._add_field(row1, "装运港:", "export_port", 0)
        self._add_combobox(
            row1,
            "包装类型:",
            "package_type",
            ["pallet", "carton", "package"],
            "pallet",
            1,
        )

        row2 = ttk.Frame(section)
        row2.pack(fill=X, pady=2)
        self._add_field(
            row2,
            "申报要素模板:",
            "declaration_elements_template",
            0,
            width=45,
        )

    # ==================== 境内信息区块 ====================

    def _build_origin_section(self, parent: ttk.Frame) -> None:
        """构建境内信息区块（默认值预填）."""
        section = self._add_section(parent, "🏭 境内信息（默认值可修改）")

        company_defaults = self._settings.get("company", {})
        defaults_data = self._settings.get("defaults", {})

        row1 = ttk.Frame(section)
        row1.pack(fill=X, pady=2)
        self._add_field(
            row1, "经营单位:", "business_entity",
            0, default=company_defaults.get("name_cn", "长园长通新材料股份有限公司"),
        )
        self._add_field(
            row1, "生产厂家:", "manufacturer",
            1, default=company_defaults.get("name_cn", "长园长通新材料股份有限公司"),
        )

        row2 = ttk.Frame(section)
        row2.pack(fill=X, pady=2)
        self._add_field(
            row2, "境内货源地:", "domestic_source",
            0, default="深圳特区",
        )
        self._add_field(
            row2, "贸易方式:", "trade_mode",
            1, default="一般贸易",
        )

        row3 = ttk.Frame(section)
        row3.pack(fill=X, pady=2)
        self._add_field(
            row3, "征免性质:", "tax_nature",
            0, default="一般征税",
        )
        self._add_field(
            row3, "结汇方式:", "settlement_method",
            1, default="电汇",
        )

        row4 = ttk.Frame(section)
        row4.pack(fill=X, pady=2)
        self._add_field(
            row4, "退税:", "tax_rebate",
            0, default="申请退税",
        )

    # ==================== UI 工具方法 ====================

    def _add_section(self, parent: ttk.Frame, title: str) -> ttk.Labelframe:
        """添加一个区块.

        Args:
            parent: 父容器.
            title: 区块标题.

        Returns:
            Labelframe 容器.
        """
        section = ttk.Labelframe(
            parent,
            text=title,
            padding=10,
            bootstyle="primary",
        )
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
        """添加一个标签 + 输入框.

        Args:
            parent: 父容器（通常是 Frame 行容器）.
            label: 字段标签.
            field_name: 字段标识符.
            col: 列位置 (0 或 1).
            default: 默认值.
            width: 输入框宽度.

        Returns:
            包含标签和输入框的 Frame.
        """
        f = ttk.Frame(parent)
        f.pack(side=LEFT, fill=X, expand=YES, padx=(0 if col == 0 else 20, 5))

        ttk.Label(f, text=label, font=self.app.get_font(size=10)).pack(anchor=W)

        var = ttk.StringVar(value=default)
        entry = ttk.Entry(f, textvariable=var, width=width)
        entry.pack(fill=X, expand=YES)
        self._variables[field_name] = var
        return f

    def _add_date_field(
        self,
        parent: ttk.Frame,
        label: str,
        field_name: str,
        col: int,
        default: str = "",
    ) -> None:
        """添加日期输入字段，默认填入今天日期.

        Args:
            parent: 父容器.
            label: 字段标签.
            field_name: 字段标识符.
            col: 列位置.
            default: 默认值.
        """
        if not default:
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
        """添加下拉选择框.

        Args:
            parent: 父容器.
            label: 字段标签.
            field_name: 字段标识符.
            values: 可选值列表.
            default: 默认值.
            col: 列位置.
        """
        f = ttk.Frame(parent)
        f.pack(side=LEFT, fill=X, expand=YES, padx=(0 if col == 0 else 20, 5))

        ttk.Label(f, text=label, font=self.app.get_font(size=10)).pack(anchor=W)

        var = ttk.StringVar(value=default)
        cb = ttk.Combobox(f, textvariable=var, values=values, state="readonly", width=18)
        cb.pack(fill=X, expand=YES)
        self._variables[field_name] = var

    # ==================== 数据收集 ====================

    def collect_data(self) -> dict[str, Any]:
        """收集所有表单数据，组装为字典.

        Returns:
            订单数据字典.
        """
        data: dict[str, Any] = {
            "order_meta": {},
            "customer": {},
            "origin": {},
            "shipping": {},
        }

        # 订单元信息
        meta_fields = [
            "invoice_no", "contract_no", "date", "order_no",
            "transport_mode", "vessel_flight", "bill_of_lading_no",
            "trade_term", "payment_term", "currency",
            "country_of_origin", "goods_summary",
            "declaration_elements_template", "package_type",
        ]
        for f in meta_fields:
            val = self._get_var(f)
            if val:
                data["order_meta"][f] = val

        # 客户信息
        cust_fields = [
            "company_name_en", "company_name_cn", "country",
            "address", "contact_person", "phone", "mobile", "destination",
        ]
        for f in cust_fields:
            val = self._get_var(f)
            if val:
                data["customer"][f] = val

        # 境内信息
        origin_fields = [
            "export_port", "domestic_source", "manufacturer",
            "business_entity", "trade_mode", "tax_nature",
            "settlement_method", "tax_rebate",
        ]
        for f in origin_fields:
            val = self._get_var(f)
            if val:
                data["origin"][f] = val

        return data

    def _get_var(self, field_name: str) -> str:
        """安全获取字段值.

        Args:
            field_name: 字段标识符.

        Returns:
            字段值（去除首尾空白）.
        """
        var = self._variables.get(field_name)
        if var is None:
            return ""
        return var.get().strip()

    # ==================== 事件处理 ====================

    def _on_next_step(self) -> None:
        """点击"下一步"按钮."""
        # 校验必填字段
        required_fields: dict[str, str] = {
            "invoice_no": "发票号",
            "contract_no": "合同号",
            "date": "日期",
            "company_name_en": "客户公司名",
            "country": "国家",
        }

        missing: list[str] = []
        for field, label in required_fields.items():
            if not self._get_var(field):
                missing.append(label)

        if missing:
            messagebox.showwarning(
                "必填字段缺失",
                f"以下必填字段不能为空：\n\n  • {'\n  • '.join(missing)}\n\n请填写后重试。",
            )
            return

        # 收集数据
        data = self.collect_data()
        self.app.current_order_data = data
        self.app.set_status(f"订单信息已录入: 发票号 {data['order_meta'].get('invoice_no', 'N/A')}")

        # 自动填入的默认值
        if "currency" not in data["order_meta"]:
            data["order_meta"]["currency"] = DEFAULT_CURRENCY
        if "trade_term" not in data["order_meta"]:
            data["order_meta"]["trade_term"] = DEFAULT_TRADE_TERM
        if "payment_term" not in data["order_meta"]:
            data["order_meta"]["payment_term"] = DEFAULT_PAYMENT_METHOD
        if "country_of_origin" not in data["order_meta"]:
            data["order_meta"]["country_of_origin"] = DEFAULT_ORIGIN_COUNTRY

        # 跳转到树状编辑器
        messagebox.showinfo(
            "信息录入完成",
            f"订单基本信息已保存。\n\n发票号: {data['order_meta'].get('invoice_no')}\n"
            f"客户: {data['customer'].get('company_name_en')}\n\n"
            f"现在将进入商品明细编辑页面。",
        )

        # 切换到树状编辑器页面
        self.app.switch_page("tree_editor")

    def _on_import_excel(self) -> None:
        """点击从 Excel 导入按钮."""
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
                messagebox.showerror(
                    "导入失败",
                    "Excel 文件解析失败，请检查文件格式。\n\n"
                    "支持的列名包括：发票号、合同号、客户名称、产品名称等。",
                )
                return

            # 填充表单
            self._fill_from_order(order)

            self.app.current_order = order
            messagebox.showinfo(
                "导入成功",
                f"订单数据已导入。\n\n发票号: {order.order_meta.invoice_no}\n"
                f"客户: {order.customer.company_name_en}\n"
                f"商品数: {sum(len(c.products) for p in order.pallets for c in p.cartons)}",
            )

        except Exception as e:
            logger.exception("[错误]: Excel 导入失败")
            messagebox.showerror(
                "导入失败",
                f"[错误]: Excel 导入失败\n[原因]: {e}\n[排查]: 请检查文件是否为标准订单 Excel 格式",
            )

    def _fill_from_order(self, order: OrderData) -> None:
        """从 OrderData 对象填充表单.

        Args:
            order: OrderData 实例.
        """
        if order is None:
            return

        # 订单元信息
        meta = order.order_meta
        meta_map = {
            "invoice_no": meta.invoice_no,
            "contract_no": meta.contract_no,
            "date": meta.date,
            "order_no": meta.order_no,
            "transport_mode": meta.transport_mode,
            "vessel_flight": meta.vessel_flight,
            "bill_of_lading_no": meta.bill_of_lading_no,
            "trade_term": meta.trade_term,
            "payment_term": meta.payment_term,
            "currency": meta.currency,
            "country_of_origin": meta.country_of_origin,
            "goods_summary": meta.goods_summary,
            "declaration_elements_template": meta.declaration_elements_template,
        }
        for k, v in meta_map.items():
            if k in self._variables and v:
                self._variables[k].set(str(v))

        # 客户信息
        cust = order.customer
        cust_map = {
            "company_name_en": cust.company_name_en,
            "company_name_cn": cust.company_name_cn,
            "country": cust.country,
            "address": cust.address,
            "contact_person": cust.contact_person,
            "phone": cust.phone,
            "mobile": cust.mobile,
            "destination": cust.destination,
        }
        for k, v in cust_map.items():
            if k in self._variables and v:
                self._variables[k].set(str(v))

        # 境内信息
        origin = order.origin
        origin_map = {
            "export_port": origin.export_port,
            "domestic_source": origin.domestic_source,
            "manufacturer": origin.manufacturer,
            "business_entity": origin.business_entity,
            "trade_mode": origin.trade_mode,
            "tax_nature": origin.tax_nature,
            "settlement_method": origin.settlement_method,
            "tax_rebate": origin.tax_rebate,
        }
        for k, v in origin_map.items():
            if k in self._variables and v:
                self._variables[k].set(str(v))

    def _on_clear(self) -> None:
        """清空所有表单."""
        if messagebox.askyesno("确认清空", "确定要清空所有已填写的表单数据吗？"):
            for var in self._variables.values():
                if isinstance(var, ttk.StringVar):
                    var.set("")
            self.app.set_status("表单已清空")

    def on_enter(self) -> None:
        """页面进入时恢复数据."""
        # 如果有之前保存的数据，回填
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


# ========== 运行说明 ==========
# 依赖安装: pip install ttkbootstrap
# 此页面由 GuiApp 自动加载，无需单独运行
# =============================
