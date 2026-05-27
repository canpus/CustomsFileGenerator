# -*- coding: utf-8 -*-
"""树状编辑器 — 数据导出 mixin.

包含 collect_tree_data 与 build_order_data 方法。
"""

from __future__ import annotations

import copy
import logging
from tkinter import messagebox
from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
    from src.gui.pages.tree_editor_page import TreeEditorPage

logger = logging.getLogger(__name__)


class TreeExportMixin:
    """数据导出方法 mixin.

    假设 self 提供：
    - self._pallets
    - self.app（来自 PageBase）
    """

    _pallets: list[dict[str, Any]]
    app: object

    def collect_tree_data(self: TreeEditorPage) -> list[dict[str, Any]]:
        """收集所有托盘/纸箱/商品数据."""
        return copy.deepcopy(self._pallets)

    def build_order_data(self: TreeEditorPage) -> OrderData | None:
        """从表单数据 + 树数据构建 OrderData 对象."""
        meta_data = self.app.current_order_data.get("order_meta", {})
        customer_data = self.app.current_order_data.get("customer", {})
        origin_data = self.app.current_order_data.get("origin", {})

        try:
            order_meta = OrderMeta(
                invoice_no=meta_data.get("invoice_no", "UNKNOWN"),
                contract_no=meta_data.get("contract_no", "UNKNOWN"),
                date=meta_data.get("date", "2025-01-01"),
                trade_term=meta_data.get("trade_term", "FOB"),
                payment_term=meta_data.get("payment_term", "100% T/T IN ADVANCE"),
                country_of_origin=meta_data.get("country_of_origin", "China"),
                order_no=meta_data.get("order_no", ""),
                transport_mode=meta_data.get("transport_mode", "海运"),
                vessel_flight=meta_data.get("vessel_flight", ""),
                bill_of_lading_no=meta_data.get("bill_of_lading_no", ""),
                currency=meta_data.get("currency", "USD"),
                package_type=meta_data.get("package_type", "pallet"),
                goods_summary=meta_data.get("goods_summary", ""),
                declaration_elements_template=meta_data.get("declaration_elements_template", ""),
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

            pallets: list[Pallet] = []
            for p_data in self._pallets:
                cartons: list[Carton] = []
                for c_data in p_data.get("cartons", []):
                    products: list[Product] = []
                    for pr_data in c_data.get("products", []):
                        product = Product(
                            seq_no=pr_data.get("seq_no", 0),
                            product_name=pr_data.get("product_name", ""),
                            hs_code=pr_data.get("hs_code", ""),
                            unit=pr_data.get("unit", "Roll"),
                            qty_per_carton=float(pr_data.get("qty_per_carton", 0)),
                            unit_price=float(pr_data.get("unit_price", 0)),
                            net_weight_per_unit_kg=float(pr_data.get("net_weight_per_unit_kg", 0)),
                            destination_country=pr_data.get("destination_country", ""),
                            specification=pr_data.get("specification", ""),
                            declaration_elements=pr_data.get("declaration_elements", ""),
                            currency=pr_data.get("currency", "USD"),
                        )
                        products.append(product)

                    carton = Carton(
                        carton_label=c_data.get("carton_label", ""),
                        is_batch=bool(c_data.get("is_batch", False)),
                        batch_count=int(c_data.get("batch_count", 1)),
                        length_cm=float(c_data.get("length_cm", 0)),
                        width_cm=float(c_data.get("width_cm", 0)),
                        height_cm=float(c_data.get("height_cm", 0)),
                        gross_weight_kg=float(c_data.get("gross_weight_kg", 0)),
                        products=products,
                    )
                    cartons.append(carton)

                pallet = Pallet(
                    pallet_no=p_data.get("pallet_no", 0),
                    length_m=float(p_data.get("length_m", 0)),
                    width_m=float(p_data.get("width_m", 0)),
                    height_m=float(p_data.get("height_m", 0)),
                    pallet_weight_kg=float(p_data.get("pallet_weight_kg", 0)),
                    cartons=cartons,
                )
                pallets.append(pallet)

            total_pallets = len(pallets)
            total_cartons = sum(
                c.batch_count if c.is_batch else 1
                for p in pallets for c in p.cartons
            )
            total_gross = sum(
                (c.gross_weight_kg * c.batch_count) if c.is_batch else c.gross_weight_kg
                for p in pallets for c in p.cartons
            )
            total_net = sum(
                pr.net_weight_per_unit_kg * pr.qty_per_carton
                * (c.batch_count if c.is_batch else 1)
                for p in pallets for c in p.cartons for pr in c.products
            )
            total_volume = sum(
                p.length_m * p.width_m * p.height_m
                for p in pallets
            )
            total_amount = sum(
                pr.unit_price * pr.qty_per_carton
                * (c.batch_count if c.is_batch else 1)
                for p in pallets for c in p.cartons for pr in c.products
            )

            totals = Totals(
                total_pallets=total_pallets,
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
                messagebox.showwarning(
                    "数据校验警告",
                    f"订单数据校验发现以下问题：\n\n  • {error_msgs}\n\n建议修正后再生成。\n是否仍要继续生成？",
                )

            return order

        except Exception as e:
            logger.exception("[错误]: 构建 OrderData 失败")
            messagebox.showerror(
                "数据构建失败",
                f"[错误]: 无法构建订单数据\n[原因]: {e}\n[排查]: 请检查商品明细是否填写完整",
            )
            return None
