"""商品明细表格录入页 — P6 单表格商品录入.

提供：
- 18 列可编辑表格（基于 EditableTable 组件）
- 底部实时汇总栏（总毛重/净重/体积/金额）
- 操作按钮：添加行、删除行、复制行、从产品库插入、批量填充
- OrderData 双向转换器（表格 ↔ 托盘/纸箱/商品层级）
"""

from __future__ import annotations

import logging
from tkinter import messagebox
from typing import Any

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from src.gui.components.editable_table import ColumnDef, EditableTable
from src.gui.page_base import PageBase
from src.models.order_data import (
    Carton,
    Customer,
    OrderData,
    OrderMeta,
    Origin,
    Pallet,
    Product,
    Totals,
)
from src.models.validators import validate_order_consistency

logger = logging.getLogger(__name__)

# ==================== 列定义 ====================

_FIELD_COLUMNS: list[ColumnDef] = [
    ("pallet_no", "托盘号", 60, True),
    ("carton_no", "纸箱号", 60, True),
    ("is_batch_box", "是否批量箱", 80, True),
    ("batch_count", "批量箱数", 70, True),
    ("length_cm", "长(cm)", 65, True),
    ("width_cm", "宽(cm)", 65, True),
    ("height_cm", "高(cm)", 65, True),
    ("gross_weight_kg", "毛重(kg)", 70, True),
    ("product_name", "商品名称", 150, True),
    ("specification", "规格型号", 120, True),
    ("hs_code", "HS Code", 100, True),
    ("declaration_elements", "申报要素", 150, True),
    ("unit", "单位", 60, True),
    ("qty_per_carton", "每箱数量", 70, True),
    ("unit_price", "单价", 70, True),
    ("currency", "币种", 60, True),
    ("net_weight_per_unit_kg", "单件净重(kg)", 80, True),
    ("destination_country", "目的国", 80, True),
]

# 数字列（用于汇总计算和类型转换）
_NUMERIC_KEYS: set[str] = {
    "batch_count",
    "length_cm",
    "width_cm",
    "height_cm",
    "gross_weight_kg",
    "qty_per_carton",
    "unit_price",
    "net_weight_per_unit_kg",
    "pallet_no",
}


class LineItemTablePage(PageBase):
    """商品明细表格录入页.

    用单表格替代树状编辑器的商品录入方式。
    每行 = 一个纸箱 + 一个商品组合。
    """

    def __init__(self, parent: ttk.Frame, app: object):
        super().__init__(parent, app)
        self._table: EditableTable | None = None
        self._summary_vars: dict[str, ttk.StringVar] = {}

    # ==================== 构建 UI ====================

    def build(self) -> None:
        """构建表格录入页 UI."""
        self.frame = ttk.Frame(self.parent)
        self.frame.pack(fill=BOTH, expand=YES, padx=10, pady=10)

        # 标题栏
        title_frame = ttk.Frame(self.frame)
        title_frame.pack(fill=X, pady=(0, 10))

        ttk.Label(
            title_frame,
            text="商品明细（表格录入）",
            font=self.app.get_heading_font(),
            bootstyle="primary",
        ).pack(side=LEFT)

        ttk.Label(
            title_frame,
            text="每行 = 一个纸箱 + 一个商品",
            font=self.app.get_font(size=9),
            bootstyle="secondary",
        ).pack(side=LEFT, padx=(15, 0))

        # 工具栏
        self._build_toolbar()

        # 可编辑表格
        table_frame = ttk.Frame(self.frame)
        table_frame.pack(fill=BOTH, expand=YES)

        self._table = EditableTable(
            table_frame,
            columns_def=_FIELD_COLUMNS,
            height=12,
            on_change=self._on_table_change,
        )
        self._table.pack(fill=BOTH, expand=YES)

        # 汇总栏
        self._build_summary_bar()

        # 底部按钮
        self._build_bottom_bar()

    def _build_toolbar(self) -> None:
        """构建工具栏."""
        toolbar = ttk.Frame(self.frame)
        toolbar.pack(fill=X, pady=(0, 5))

        ttk.Button(
            toolbar,
            text="+ 添加行",
            bootstyle="success-outline",
            command=self._on_add_row,
        ).pack(side=LEFT, padx=(0, 5))

        ttk.Button(
            toolbar,
            text="- 删除选中行",
            bootstyle="danger-outline",
            command=self._on_delete_rows,
        ).pack(side=LEFT, padx=(0, 5))

        ttk.Button(
            toolbar,
            text="复制选中行",
            bootstyle="secondary-outline",
            command=self._on_copy_rows,
        ).pack(side=LEFT, padx=(0, 5))

        ttk.Button(
            toolbar,
            text="粘贴行",
            bootstyle="secondary-outline",
            command=self._on_paste_rows,
        ).pack(side=LEFT, padx=(0, 5))

        ttk.Separator(toolbar, orient=VERTICAL).pack(side=LEFT, fill=Y, padx=10)

        ttk.Button(
            toolbar,
            text="从产品库插入...",
            bootstyle="info-outline",
            command=self._on_insert_from_product_lib,
        ).pack(side=LEFT, padx=(0, 5))

        ttk.Separator(toolbar, orient=VERTICAL).pack(side=LEFT, fill=Y, padx=10)

        ttk.Button(
            toolbar,
            text="自动分配托盘号",
            bootstyle="warning-outline",
            command=self._on_auto_assign_pallets,
        ).pack(side=LEFT, padx=(0, 5))

        ttk.Button(
            toolbar,
            text="清空表格",
            bootstyle="danger-outline",
            command=self._on_clear_table,
        ).pack(side=RIGHT)

    def _build_summary_bar(self) -> None:
        """构建底部汇总栏."""
        summary_frame = ttk.Labelframe(self.frame, text="实时汇总", padding=8, bootstyle="info")
        summary_frame.pack(fill=X, pady=(5, 0))

        summary_items: list[tuple[str, str]] = [
            ("total_rows", "总行数: 0"),
            ("total_cartons", "纸箱数: 0"),
            ("total_gross", "总毛重: 0 kg"),
            ("total_net", "总净重: 0 kg"),
            ("total_volume", "总体积: 0 m³"),
            ("total_amount", "总金额: 0"),
        ]

        for key, default_text in summary_items:
            var = ttk.StringVar(value=default_text)
            self._summary_vars[key] = var
            ttk.Label(
                summary_frame,
                textvariable=var,
                font=self.app.get_font(size=10),
                bootstyle="secondary",
            ).pack(side=LEFT, padx=(0, 20))

    def _build_bottom_bar(self) -> None:
        """构建底部操作按钮."""
        bottom = ttk.Frame(self.frame)
        bottom.pack(fill=X, pady=(10, 0))

        ttk.Button(
            bottom,
            text="← 返回新建单据",
            bootstyle="secondary-outline",
            command=lambda: self.app.switch_page("order_info"),
        ).pack(side=LEFT)

        ttk.Button(
            bottom,
            text="层级视图（旧版）",
            bootstyle="secondary-outline",
            command=lambda: self.app.switch_page("tree_editor"),
        ).pack(side=LEFT, padx=(10, 0))

        ttk.Button(
            bottom,
            text="下一步 → 生成报关资料",
            bootstyle="success",
            command=self._on_next_step,
        ).pack(side=RIGHT)

    # ==================== 工具栏操作 ====================

    def _on_add_row(self) -> None:
        """添加空白行."""
        if self._table is None:
            return
        # 默认托盘号取最后一行或有数据的行
        default_pallet = 1
        data = self._table.get_all_rows()
        if data:
            try:
                default_pallet = max(int(r.get("pallet_no", 0) or 0) for r in data)
            except ValueError:
                default_pallet = 1

        self._table.add_row(
            {
                "pallet_no": str(default_pallet),
                "carton_no": str(self._table.row_count + 1),
                "is_batch_box": "",
                "batch_count": "1",
                "length_cm": "32",
                "width_cm": "32",
                "height_cm": "34",
                "gross_weight_kg": "23.3",
                "product_name": "",
                "specification": "",
                "hs_code": "",
                "declaration_elements": "",
                "unit": "Roll",
                "qty_per_carton": "1",
                "unit_price": "0",
                "currency": "USD",
                "net_weight_per_unit_kg": "0",
                "destination_country": "",
            }
        )

    def _on_delete_rows(self) -> None:
        """删除选中行."""
        if self._table is not None:
            self._table.delete_selected_rows()

    def _on_copy_rows(self) -> None:
        """复制选中行."""
        if self._table is not None:
            self._table.copy_selected_rows()

    def _on_paste_rows(self) -> None:
        """粘贴行."""
        if self._table is not None:
            self._table.paste_rows()

    def _on_insert_from_product_lib(self) -> None:
        """从产品库选择产品插入."""
        if self._table is None:
            return

        from src.gui.pages.product_page import ProductSelectDialog

        dialog = ProductSelectDialog(self.frame)
        selected = dialog.show()

        if selected:
            self._insert_product_rows(selected)

    def _insert_product_rows(self, products: list[dict[str, Any]]) -> None:
        """将选中的产品插入为表格行.

        Args:
            products: 选中的产品记录列表.
        """
        if self._table is None:
            return

        existing = self._table.get_all_rows()
        default_pallet = 1
        if existing:
            try:
                default_pallet = max(int(r.get("pallet_no", 0) or 0) for r in existing)
            except ValueError:
                default_pallet = 1

        next_carton = self._table.row_count + 1

        for product in products:
            row = {
                "pallet_no": str(default_pallet),
                "carton_no": str(next_carton),
                "is_batch_box": "",
                "batch_count": "1",
                "length_cm": "32",
                "width_cm": "32",
                "height_cm": "34",
                "gross_weight_kg": "23.3",
                "product_name": str(product.get("product_name", "")),
                "specification": str(product.get("specification", "")),
                "hs_code": str(product.get("hs_code", "")),
                "declaration_elements": str(product.get("declaration_elements", "")),
                "unit": str(product.get("unit", "Roll")),
                "qty_per_carton": "1",
                "unit_price": str(product.get("unit_price", "0")),
                "currency": str(product.get("currency", "USD")),
                "net_weight_per_unit_kg": str(product.get("net_weight_per_unit_kg", "0")),
                "destination_country": str(product.get("destination_country", "")),
            }
            self._table.add_row(row)
            next_carton += 1

        logger.info("已从产品库插入 %d 个产品", len(products))

    def _on_auto_assign_pallets(self) -> None:
        """自动分配托盘号（基于数据量简单分配）."""
        if self._table is None:
            return

        data = self._table.get_all_rows()
        if not data:
            return

        # 简单策略：按 pallet_no 分组
        pallet_groups: dict[str, list[int]] = {}
        for i, row in enumerate(data):
            pn = str(row.get("pallet_no", "1"))
            pallet_groups.setdefault(pn, []).append(i)

        # 不改变现有分组，只重新编号
        sorted_groups = sorted(pallet_groups.keys())
        for new_pn, old_key in enumerate(sorted_groups, 1):
            for idx in pallet_groups[old_key]:
                data[idx]["pallet_no"] = str(new_pn)

        self._table.set_rows(data)
        messagebox.showinfo("完成", f"已重新分配托盘号，共 {len(sorted_groups)} 个托盘。")

    def _on_clear_table(self) -> None:
        """清空表格."""
        if self._table is None or self._table.row_count == 0:
            return
        if messagebox.askyesno("确认清空", "确定要清空全部商品明细吗？此操作不可撤销。"):
            self._table.clear_all()

    # ==================== 步骤导航 ====================

    def _on_next_step(self) -> None:
        """下一步：构建 OrderData → 校验 → 切换到生成页."""
        order = self._table_to_order_data()
        if order is None:
            return

        self.app.current_order = order
        self.app.set_dirty(True)
        self.app.switch_page("generate")

    # ==================== 数据变更回调 ====================

    def _on_table_change(self) -> None:
        """表格数据变更时更新汇总."""
        self._update_summary()

    # ==================== 汇总计算 ====================

    def _update_summary(self) -> None:
        """更新汇总栏."""
        if self._table is None:
            return

        data = self._table.get_all_rows()
        total_rows = len(data)

        total_cartons = 0
        total_gross = 0.0
        total_net = 0.0
        total_volume = 0.0
        total_amount = 0.0

        for row in data:
            is_batch = str(row.get("is_batch_box", "")).strip().lower() in (
                "true",
                "1",
                "yes",
                "是",
            )
            batch_count = _to_float(row.get("batch_count", "1"), 1.0)
            multiplier = batch_count if is_batch else 1.0
            total_cartons += int(multiplier)

            gross = _to_float(row.get("gross_weight_kg", "0"), 0.0)
            total_gross += gross * multiplier

            net_per_unit = _to_float(row.get("net_weight_per_unit_kg", "0"), 0.0)
            qty = _to_float(row.get("qty_per_carton", "0"), 0.0)
            total_net += net_per_unit * qty * multiplier

            l_cm = _to_float(row.get("length_cm", "0"), 0.0)
            w_cm = _to_float(row.get("width_cm", "0"), 0.0)
            h_cm = _to_float(row.get("height_cm", "0"), 0.0)
            total_volume += (l_cm * w_cm * h_cm) / 1_000_000 * multiplier

            unit_price = _to_float(row.get("unit_price", "0"), 0.0)
            total_amount += unit_price * qty * multiplier

        self._summary_vars["total_rows"].set(f"总行数: {total_rows}")
        self._summary_vars["total_cartons"].set(f"纸箱数: {total_cartons}")
        self._summary_vars["total_gross"].set(f"总毛重: {total_gross:.2f} kg")
        self._summary_vars["total_net"].set(f"总净重: {total_net:.3f} kg")
        self._summary_vars["total_volume"].set(f"总体积: {total_volume:.4f} m³")
        self._summary_vars["total_amount"].set(f"总金额: {total_amount:,.2f}")

    # ==================== 数据转换 ====================

    def _table_to_order_data(self) -> OrderData | None:
        """将表格数据转换为 OrderData 对象.

        转换逻辑：
        1. 按 pallet_no 分组 → Pallets
        2. 每组内按 carton_no 分组 → Cartons
        3. 每个 Carton 含一个 Product
        4. 批量箱处理：is_batch_box=True → Carton.is_batch=True, batch_count 关联

        Returns:
            OrderData 实例，失败返回 None.
        """
        data = self._table.get_all_rows() if self._table else []
        if not data:
            messagebox.showwarning("提示", "请至少添加一行商品明细。")
            return None

        # 按托盘号分组
        pallet_groups: dict[str, list[dict[str, Any]]] = {}
        for row in data:
            pn = str(row.get("pallet_no", "1"))
            pallet_groups.setdefault(pn, []).append(row)

        pallets: list[Pallet] = []
        product_seq = 1

        for pn_str, rows in sorted(pallet_groups.items()):
            # 按纸箱号分组
            carton_groups: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                cn = str(row.get("carton_no", "1"))
                carton_groups.setdefault(cn, []).append(row)

            cartons: list[Carton] = []
            pallet_no = int(pn_str) if pn_str.isdigit() else 0

            for _cn, c_rows in carton_groups.items():
                first = c_rows[0]
                is_batch = str(first.get("is_batch_box", "")).strip().lower() in (
                    "true",
                    "1",
                    "yes",
                    "是",
                )
                batch_count = int(_to_float(first.get("batch_count", "1"), 1.0))

                products: list[Product] = []
                for pr_data in c_rows:
                    product = Product(
                        seq_no=product_seq,
                        product_name=str(pr_data.get("product_name", "")),
                        specification=str(pr_data.get("specification", "")),
                        hs_code=str(pr_data.get("hs_code", "")),
                        declaration_elements=str(pr_data.get("declaration_elements", "")),
                        unit=str(pr_data.get("unit", "Roll")),
                        qty_per_carton=_to_float(pr_data.get("qty_per_carton", "1"), 1.0),
                        unit_price=_to_float(pr_data.get("unit_price", "0"), 0.0),
                        currency=str(pr_data.get("currency", "USD")),
                        net_weight_per_unit_kg=_to_float(
                            pr_data.get("net_weight_per_unit_kg", "0"), 0.0
                        ),
                        destination_country=str(pr_data.get("destination_country", "")),
                    )
                    products.append(product)
                    product_seq += 1

                carton = Carton(
                    carton_label=str(first.get("carton_no", "")),
                    is_batch=is_batch,
                    batch_count=max(batch_count, 1),
                    length_cm=_to_float(first.get("length_cm", "0"), 0.0),
                    width_cm=_to_float(first.get("width_cm", "0"), 0.0),
                    height_cm=_to_float(first.get("height_cm", "0"), 0.0),
                    gross_weight_kg=_to_float(first.get("gross_weight_kg", "0"), 0.0),
                    products=products,
                )
                cartons.append(carton)

            pallet = Pallet(
                pallet_no=pallet_no,
                length_m=1.16,
                width_m=1.01,
                height_m=1.97,
                pallet_weight_kg=0.0,
                cartons=cartons,
            )
            pallets.append(pallet)

        try:
            order_meta_data = self.app.current_order_data.get("order_meta", {})
            customer_data = self.app.current_order_data.get("customer", {})
            origin_data = self.app.current_order_data.get("origin", {})

            order_meta = OrderMeta(
                invoice_no=order_meta_data.get("invoice_no", "UNKNOWN"),
                contract_no=order_meta_data.get("contract_no", "UNKNOWN"),
                date=order_meta_data.get("date", "2025-01-01"),
                trade_term=order_meta_data.get("trade_term", "FOB"),
                payment_term=order_meta_data.get("payment_term", "100% T/T IN ADVANCE"),
                country_of_origin=order_meta_data.get("country_of_origin", "China"),
                order_no=order_meta_data.get("order_no", ""),
                transport_mode=order_meta_data.get("transport_mode", "海运"),
                vessel_flight=order_meta_data.get("vessel_flight", ""),
                bill_of_lading_no=order_meta_data.get("bill_of_lading_no", ""),
                currency=order_meta_data.get("currency", "USD"),
                package_type=order_meta_data.get("package_type", "pallet"),
                goods_summary=order_meta_data.get("goods_summary", ""),
                declaration_elements_template=order_meta_data.get(
                    "declaration_elements_template", ""
                ),
            )

            customer = Customer(
                company_name_en=customer_data.get("company_name_en", "UNKNOWN"),
                country=customer_data.get("country", "Unknown"),
                company_name_cn=customer_data.get("company_name_cn", ""),
                address=customer_data.get("address", ""),
                contact_person=customer_data.get("contact_person", ""),
                phone=customer_data.get("phone", ""),
                mobile=customer_data.get("mobile", ""),
                destination=customer_data.get("destination", ""),
            )

            origin = Origin(
                export_port=origin_data.get("export_port", ""),
                domestic_source=origin_data.get("domestic_source", "深圳特区"),
                manufacturer=origin_data.get("manufacturer", "长园长通新材料股份有限公司"),
                business_entity=origin_data.get("business_entity", "长园长通新材料股份有限公司"),
                trade_mode=origin_data.get("trade_mode", "一般贸易"),
                tax_nature=origin_data.get("tax_nature", "一般征税"),
                settlement_method=origin_data.get("settlement_method", "电汇"),
                tax_rebate=origin_data.get("tax_rebate", "申请退税"),
            )

            total_cartons = sum(
                c.batch_count if c.is_batch else 1 for p in pallets for c in p.cartons
            )
            total_gross = sum(
                (c.gross_weight_kg * c.batch_count) if c.is_batch else c.gross_weight_kg
                for p in pallets
                for c in p.cartons
            )
            total_net = sum(
                pr.net_weight_per_unit_kg * pr.qty_per_carton * (c.batch_count if c.is_batch else 1)
                for p in pallets
                for c in p.cartons
                for pr in c.products
            )
            total_volume = sum(p.length_m * p.width_m * p.height_m for p in pallets)
            total_amount = sum(
                pr.unit_price * pr.qty_per_carton * (c.batch_count if c.is_batch else 1)
                for p in pallets
                for c in p.cartons
                for pr in c.products
            )

            totals = Totals(
                total_pallets=len(pallets),
                total_cartons=total_cartons,
                total_gross_weight_kg=round(total_gross, 3),
                total_net_weight_kg=round(total_net, 3),
                total_volume_cbm=round(total_volume, 3),
                total_amount=round(total_amount, 2),
            )

            order = OrderData(
                order_meta=order_meta,
                customer=customer,
                pallets=pallets,
                totals=totals,
                origin=origin,
            )

            report = validate_order_consistency(order)
            if report.errors:
                error_msgs = "\n  • ".join(f"[{m.code}] {m.message}" for m in report.errors)
                if not messagebox.askyesno(
                    "数据校验警告",
                    f"订单数据校验发现以下问题：\n\n  • {error_msgs}\n\n"
                    "建议修正后再生成。\n是否仍要继续？",
                ):
                    return None

            return order

        except Exception as e:
            logger.exception("[错误]: 构建 OrderData 失败")
            messagebox.showerror(
                "数据构建失败",
                f"[错误]: 无法构建订单数据\n[原因]: {e}\n[排查]: 请检查商品明细是否填写完整",
            )
            return None

    def _order_data_to_table(self, order: OrderData) -> None:
        """从 OrderData 对象反向填充表格.

        Args:
            order: OrderData 实例.
        """
        rows: list[dict[str, Any]] = []
        for pallet in order.pallets:
            for carton in pallet.cartons:
                for product in carton.products:
                    row = {
                        "pallet_no": str(pallet.pallet_no),
                        "carton_no": str(carton.carton_label),
                        "is_batch_box": "是" if carton.is_batch else "",
                        "batch_count": str(carton.batch_count),
                        "length_cm": str(carton.length_cm),
                        "width_cm": str(carton.width_cm),
                        "height_cm": str(carton.height_cm),
                        "gross_weight_kg": str(carton.gross_weight_kg),
                        "product_name": str(product.product_name),
                        "specification": str(product.specification),
                        "hs_code": str(product.hs_code),
                        "declaration_elements": str(product.declaration_elements),
                        "unit": str(product.unit),
                        "qty_per_carton": str(product.qty_per_carton),
                        "unit_price": str(product.unit_price),
                        "currency": str(product.currency),
                        "net_weight_per_unit_kg": str(product.net_weight_per_unit_kg),
                        "destination_country": str(product.destination_country),
                    }
                    rows.append(row)

        if self._table is not None:
            self._table.set_rows(rows)

    # ==================== 生命周期 ====================

    def on_enter(self) -> None:
        """页面进入时：如果有 current_order 则反向填充表格."""
        order = self.app.current_order
        if (
            order is not None
            and order.pallets
            and self._table is not None
            and self._table.row_count == 0
        ):
            self._order_data_to_table(order)
            logger.info("已从现有订单填充表格，共 %d 行", self._table.row_count)

    def on_leave(self) -> None:
        """页面离开时：不自动保存（由 _on_next_step 显式构建）."""
        pass


# ==================== 产品选择对话框 ====================


# ==================== 辅助函数 ====================


def _to_float(value: Any, default: float = 0.0) -> float:
    """安全转换为 float."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except (ValueError, AttributeError):
            return default
    return default
