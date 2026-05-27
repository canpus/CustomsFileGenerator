"""订单信息页 — 数据操作与事件处理 mixin.

包含数据收集、表单填充、校验、导入导出、清空等。
"""

from __future__ import annotations

# pyright: reportAttributeAccessIssue=false
import logging
import re
from datetime import datetime
from tkinter import messagebox
from typing import TYPE_CHECKING, Any

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from config.constants import (
    DEFAULT_CURRENCY,
    DEFAULT_ORIGIN_COUNTRY,
    DEFAULT_PAYMENT_METHOD,
    DEFAULT_TRADE_TERM,
)
from src.importer.excel_importer import import_order_from_excel

if TYPE_CHECKING:
    from src.gui.app import GuiApp
    from src.models.order_data import OrderData

logger = logging.getLogger(__name__)


class OrderInfoDataMixin:
    """订单信息页数据与事件方法.

    假设 self 提供：
    - self._variables
    - self.app（来自 PageBase）
    """

    _variables: dict[str, ttk.StringVar | ttk.IntVar]
    _entry_widgets: dict[str, ttk.Entry]
    app: GuiApp

    # ==================== 实时校验 ====================

    def _setup_validation(self) -> None:
        """设置字段实时校验.

        1. 日期字段 (date): KeyRelease 时校验 YYYY-MM-DD 格式
        2. 必填字段: FocusOut 时校验非空
        """
        # 日期格式实时校验
        if "date" in self._entry_widgets:
            date_entry = self._entry_widgets["date"]
            date_entry.bind("<KeyRelease>", lambda e: self._validate_date_field())
            date_entry.bind("<FocusOut>", lambda e: self._validate_date_field())

        # 必填字段焦点离开校验
        required_fields = ["invoice_no", "contract_no", "date", "company_name_en", "country"]
        for field in required_fields:
            if field in self._entry_widgets:
                entry = self._entry_widgets[field]
                entry.bind("<FocusOut>", lambda e, f=field: self._validate_required_field(f))

        # 初始校验一次
        for field in required_fields:
            if field in self._entry_widgets:
                self._validate_required_field(field)

    def _validate_date_field(self) -> None:
        """校验日期字段格式 (YYYY-MM-DD)."""
        entry = self._entry_widgets.get("date")
        var = self._variables.get("date")
        if entry is None or var is None:
            return

        val = var.get().strip()
        if not val:
            entry.configure(bootstyle="")
            return

        date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        if not date_pattern.match(val):
            entry.configure(bootstyle="danger")
        else:
            try:
                datetime.strptime(val, "%Y-%m-%d")
                entry.configure(bootstyle="success")
            except ValueError:
                entry.configure(bootstyle="danger")

    def _validate_required_field(self, field_name: str) -> None:
        """校验必填字段非空."""
        entry = self._entry_widgets.get(field_name)
        var = self._variables.get(field_name)
        if entry is None or var is None:
            return

        val = var.get().strip()
        if not val:
            entry.configure(bootstyle="danger")
        else:
            # 日期字段特殊处理：非空时由 _validate_date_field 管理样式
            if field_name == "date":
                self._validate_date_field()
            else:
                entry.configure(bootstyle="")

    # ==================== 数据收集 ====================

    def collect_data(self) -> dict[str, Any]:
        """收集所有表单数据，组装为字典."""
        data: dict[str, Any] = {
            "order_meta": {},
            "customer": {},
            "origin": {},
            "shipping": {},
        }

        meta_fields = [
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
        ]
        for f in meta_fields:
            val = self._get_var(f)
            if val:
                data["order_meta"][f] = val

        cust_fields = [
            "company_name_en",
            "company_name_cn",
            "country",
            "address",
            "contact_person",
            "phone",
            "mobile",
            "destination",
        ]
        for f in cust_fields:
            val = self._get_var(f)
            if val:
                data["customer"][f] = val

        origin_fields = [
            "export_port",
            "domestic_source",
            "manufacturer",
            "business_entity",
            "trade_mode",
            "tax_nature",
            "settlement_method",
            "tax_rebate",
        ]
        for f in origin_fields:
            val = self._get_var(f)
            if val:
                data["origin"][f] = val

        return data

    def _get_var(self, field_name: str) -> str:
        """安全获取字段值."""
        var = self._variables.get(field_name)
        if var is None:
            return ""
        return var.get().strip()

    def _fill_from_order(self, order: OrderData) -> None:
        """从 OrderData 对象填充表单."""
        if order is None:
            return

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

    # ==================== 事件处理 ====================

    def _on_next_step(self) -> None:
        """点击"下一步"按钮."""
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
                "以下必填字段不能为空：\n\n  • " + "\n  • ".join(missing) + "\n\n请填写后重试。",
            )
            return

        data = self.collect_data()
        self.app.current_order_data = data
        self.app.set_status(f"订单信息已录入: 发票号 {data['order_meta'].get('invoice_no', 'N/A')}")

        if "currency" not in data["order_meta"]:
            data["order_meta"]["currency"] = DEFAULT_CURRENCY
        if "trade_term" not in data["order_meta"]:
            data["order_meta"]["trade_term"] = DEFAULT_TRADE_TERM
        if "payment_term" not in data["order_meta"]:
            data["order_meta"]["payment_term"] = DEFAULT_PAYMENT_METHOD
        if "country_of_origin" not in data["order_meta"]:
            data["order_meta"]["country_of_origin"] = DEFAULT_ORIGIN_COUNTRY

        messagebox.showinfo(
            "信息录入完成",
            f"订单基本信息已保存。\n\n发票号: {data['order_meta'].get('invoice_no')}\n"
            f"客户: {data['customer'].get('company_name_en')}\n\n"
            f"现在将进入商品明细编辑页面。",
        )

        self.app.switch_page("line_items")

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
            order, _ = import_order_from_excel(file_path)

            if order is None:
                messagebox.showerror(
                    "导入失败",
                    "Excel 文件解析失败，请检查文件格式。\n\n"
                    "支持的列名包括：发票号、合同号、客户名称、产品名称等。",
                )
                return

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

    def _on_select_from_customer_lib(self) -> None:
        """点击"从客户库选择"按钮."""
        from src.gui.pages.customer_page import CustomerSelectDialog

        dialog = CustomerSelectDialog(self.frame)
        customer = dialog.show()

        if customer is None:
            return

        # 将客户数据填充到表单
        field_map: dict[str, str] = {
            "company_name_en": "company_name_en",
            "company_name_cn": "company_name_cn",
            "country": "country",
            "address": "address",
            "contact_person": "contact_person",
            "phone": "phone",
            "mobile": "mobile",
            "destination": "destination",
        }
        for db_field, form_field in field_map.items():
            val = customer.get(db_field, "")
            if val and form_field in self._variables:
                self._variables[form_field].set(str(val))

        self.app.set_status(f"已从客户库选择: {customer.get('company_name_en', '')}")

    def _on_apply_template(self) -> None:
        """点击"套用模板"按钮 — 打开分块模板对话框."""
        from src.gui.components.template_block_dialog import TemplateBlockDialog

        dialog = TemplateBlockDialog(self.frame, self.app)
        dialog.show()

        # 对话框关闭后 刷新表单（如果数据有变更）
        data = self.app.current_order_data
        if data:
            self._fill_from_order_data_dict(data)

    def _on_save_as_block(self) -> None:
        """保存当前订单为分块模板."""
        data = self.collect_data()

        # 检查是否有数据
        has_data = False
        for section in ("order_meta", "customer", "origin", "shipping"):
            if data.get(section):
                has_data = True
                break

        if not has_data:
            messagebox.showinfo("提示", "当前表单没有可保存的数据。\n\n请先填写表单。")
            return

        # 弹出保存对话框
        dialog = ttk.Toplevel(self.frame, title="保存为模板块")
        dialog.geometry("450x320")
        dialog.transient(self.frame)
        dialog.grab_set()

        ttk.Label(
            dialog,
            text="保存当前表单为模板块",
            font=self.app.get_font(bold=True, size=12),
            bootstyle="primary",
        ).pack(padx=20, pady=(15, 10))

        # 块类型选择
        type_frame = ttk.Frame(dialog)
        type_frame.pack(fill=X, padx=20, pady=(0, 5))
        ttk.Label(type_frame, text="模板类型:", font=self.app.get_font(size=10)).pack(
            side=LEFT, padx=(0, 8)
        )

        from src.gui.components.template_block_dialog import BLOCK_TYPE_OPTIONS

        block_type_var = ttk.StringVar(value="customer")
        type_combo = ttk.Combobox(
            type_frame,
            textvariable=block_type_var,
            values=[opt[1] for opt in BLOCK_TYPE_OPTIONS],
            state="readonly",
            width=18,
        )
        type_combo.pack(side=LEFT)

        # 块名称
        ttk.Label(dialog, text="模板名称:", font=self.app.get_font(size=10)).pack(
            anchor=W, padx=20, pady=(10, 0)
        )
        name_var = ttk.StringVar(value="")
        ttk.Entry(dialog, textvariable=name_var, width=45).pack(padx=20, pady=(0, 5))

        # 备注
        ttk.Label(dialog, text="备注（可选）:", font=self.app.get_font(size=10)).pack(
            anchor=W, padx=20, pady=(5, 0)
        )
        desc_var = ttk.StringVar()
        ttk.Entry(dialog, textvariable=desc_var, width=45).pack(padx=20, pady=(0, 10))

        # 提示信息
        ttk.Label(
            dialog,
            text="将根据所选类型保存对应字段数据。\n"
            "- 客户信息：保存客户公司名、地址、联系人等\n"
            "- 运输信息：保存运输方式、装运港、贸易条款等\n"
            "- 整单模板：保存全部表单数据",
            font=self.app.get_font(size=9),
            bootstyle="secondary",
            wraplength=400,
        ).pack(padx=20, pady=(5, 10))

        def _do_save() -> None:
            block_type_label = block_type_var.get()
            block_type = "customer"
            for key, lbl in BLOCK_TYPE_OPTIONS:
                if lbl == block_type_label:
                    block_type = key
                    break

            block_name = name_var.get().strip()
            if not block_name:
                messagebox.showwarning("提示", "请输入模板名称。")
                return

            # 根据类型提取要保存的数据
            block_data: dict[str, Any]
            if block_type == "customer":
                block_data = data.get("customer", {})
            elif block_type == "shipping":
                block_data = {}
                block_data.update(data.get("order_meta", {}))
                block_data.update(data.get("origin", {}))
            else:
                # order_full: 保存全部
                block_data = data

            if not block_data:
                messagebox.showwarning("提示", "对应类型的表单数据为空，无需保存。")
                return

            try:
                from src.gui.services.template_block_service import TemplateBlockService

                block_id = TemplateBlockService.save_block(
                    block_type, block_name, block_data, desc_var.get().strip()
                )
                messagebox.showinfo("保存成功", f"模板块「{block_name}」已保存（ID={block_id}）。")
                dialog.destroy()
                self.app.set_status(f"模板块已保存: {block_name}")
            except Exception as e:
                logger.exception("[错误]: 保存模板块失败")
                messagebox.showerror("保存失败", f"[错误]: {e}")

        ttk.Button(dialog, text="保存", bootstyle="success", command=_do_save).pack(
            side=LEFT, padx=(20, 10)
        )
        ttk.Button(dialog, text="取消", bootstyle="secondary-outline", command=dialog.destroy).pack(
            side=LEFT
        )

    def _fill_from_order_data_dict(self, data: dict[str, Any]) -> None:
        """从字典数据填充表单（用于套用模板后刷新）.

        Args:
            data: collect_data() 格式的字典.
        """
        if not data:
            return

        for section, fields in [
            (
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
        ]:
            section_data = data.get(section, {})
            for field in fields:
                val = section_data.get(field, "")
                if val and field in self._variables:
                    self._variables[field].set(str(val))

    def _on_clear(self) -> None:
        """清空所有表单."""
        if messagebox.askyesno("确认清空", "确定要清空所有已填写的表单数据吗？"):
            for var in self._variables.values():
                if isinstance(var, ttk.StringVar):
                    var.set("")
            self.app.set_status("表单已清空")
