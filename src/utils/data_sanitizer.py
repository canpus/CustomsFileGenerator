# -*- coding: utf-8 -*-
"""数据脱敏工具 — 阶段 8.4.

对订单数据中的敏感字段进行脱敏处理，用于诊断包导出。
脱敏矩阵（严格按 plan_v6.md 阶段 8 实现）：
    - customer.company_name_en → 截取首两字 + "***"
    - customer.phone → "[REDACTED]"
    - customer.mobile → "[REDACTED]"
    - customer.address → 截取前 10 字符 + "..."
    - products[*].unit_price → 强制覆写为 0.00
    - 异常堆栈中的文件路径 → 替换为相对路径
    - order_meta.invoice_no → 保留原样
    - 产品名称、HS Code、规格 → 保留原样
"""

from __future__ import annotations

import copy
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

import msgspec

from src.models.order_data import (
    Carton,
    Customer,
    OrderData,
    OrderMeta,
    Origin,
    Pallet,
    Product,
    Totals,
    TemplateMeta,
    PackageType,
    encode_order,
)

logger = logging.getLogger(__name__)

# ==================== 脱敏核心函数 ====================


def _truncate_first_two(text: str) -> str:
    """截取前两个非空白字符 + '***'.

    Args:
        text: 原始文本.

    Returns:
        脱敏后的文本，如 "LG***".
    """
    if not text:
        return "***"
    stripped = text.strip()
    if len(stripped) <= 2:
        return stripped + "***"
    return stripped[:2] + "***"


def _truncate_first_10(text: str) -> str:
    """截取前 10 字符 + '...'.

    Args:
        text: 原始文本.

    Returns:
        脱敏后的文本.
    """
    if not text:
        return "..."
    stripped = text.strip()
    if len(stripped) <= 10:
        return stripped + "..."
    return stripped[:10] + "..."


def sanitize_order_data(order: OrderData) -> OrderData:
    """对完整订单数据进行深度脱敏，返回全新的 OrderData 对象.

    脱敏规则：
        - customer.company_name_en → 截取首两字 + "***"
        - customer.phone → "[REDACTED]"
        - customer.mobile → "[REDACTED]"
        - customer.address → 截取前 10 字符 + "..."
        - products[*].unit_price → 强制覆写为 0.00
        - order_meta.invoice_no → 保留原样（便于对账）
        - 产品名称、HS Code、规格 → 保留原样
        - customer.company_name_cn、contact_person → 脱敏

    Args:
        order: 原始 OrderData 对象（不会被修改）.

    Returns:
        脱敏后的新 OrderData 对象.
    """
    # 脱敏 Customer
    sanitized_customer = Customer(
        company_name_en=_truncate_first_two(order.customer.company_name_en),
        country=order.customer.country,
        company_name_cn=_truncate_first_two(order.customer.company_name_cn) if order.customer.company_name_cn else "",
        address=_truncate_first_10(order.customer.address),
        contact_person=_truncate_first_two(order.customer.contact_person) if order.customer.contact_person else "",
        phone="[REDACTED]" if order.customer.phone else "",
        mobile="[REDACTED]" if order.customer.mobile else "",
        destination=order.customer.destination,
    )

    # 脱敏 Pallets（递归脱敏 Product.unit_price）
    sanitized_pallets: list[Pallet] = []
    for pallet in order.pallets:
        sanitized_cartons: list[Carton] = []
        for carton in pallet.cartons:
            sanitized_products: list[Product] = [
                Product(
                    seq_no=p.seq_no,
                    product_name=p.product_name,
                    hs_code=p.hs_code,
                    unit=p.unit,
                    qty_per_carton=p.qty_per_carton,
                    unit_price=0.0,  # 强制覆写为 0.00
                    net_weight_per_unit_kg=p.net_weight_per_unit_kg,
                    destination_country=p.destination_country,
                    specification=p.specification,
                    declaration_elements=p.declaration_elements,
                    currency=p.currency,
                )
                for p in carton.products
            ]
            sanitized_cartons.append(
                Carton(
                    carton_label=carton.carton_label,
                    is_batch=carton.is_batch,
                    batch_count=carton.batch_count,
                    length_cm=carton.length_cm,
                    width_cm=carton.width_cm,
                    height_cm=carton.height_cm,
                    gross_weight_kg=carton.gross_weight_kg,
                    products=sanitized_products,
                )
            )
        sanitized_pallets.append(
            Pallet(
                pallet_no=pallet.pallet_no,
                length_m=pallet.length_m,
                width_m=pallet.width_m,
                height_m=pallet.height_m,
                pallet_weight_kg=pallet.pallet_weight_kg,
                cartons=sanitized_cartons,
            )
        )

    # OrderMeta 保留 invoice_no、contract_no 原样
    sanitized_meta = copy.deepcopy(order.order_meta)

    # Totals 保留原样（汇总金额本身不敏感，细节已脱敏）
    sanitized_totals = copy.deepcopy(order.totals)

    # Origin 保留原样
    sanitized_origin = copy.deepcopy(order.origin)

    return OrderData(
        order_meta=sanitized_meta,
        customer=sanitized_customer,
        pallets=sanitized_pallets,
        totals=sanitized_totals,
        origin=sanitized_origin,
        template_meta=copy.deepcopy(order.template_meta),
    )


def sanitize_file_paths(text: str, project_root: Path | None = None) -> str:
    """将异常堆栈中的绝对路径替换为相对路径.

    匹配模式：磁盘符开头的路径（如 D:\\Coding_Programs\\...）或 Unix 绝对路径。

    Args:
        text: 包含文件路径的文本（如异常堆栈）.
        project_root: 项目根目录，默认从 config.constants 读取.

    Returns:
        路径脱敏后的文本.
    """
    if project_root is None:
        try:
            from config.constants import PROJECT_ROOT
            project_root = PROJECT_ROOT
        except Exception:
            project_root = None

    # 替换 Windows 绝对路径中属于项目根的部分
    if project_root is not None:
        root_str = str(project_root.resolve())
        text = text.replace(root_str, "<PROJECT_ROOT>")

    # 替换通用 Windows 盘符路径（d:\... 格式）→ 只替换非项目路径
    text = re.sub(r"[A-Za-z]:\\[^\s,;:]*", "<ABSOLUTE_PATH>", text)

    # 替换 Unix 绝对路径 /home/... 或 /Users/...
    text = re.sub(r"/(?:home|Users)/[^\s,;:]+/[^\s,;:]*", "<ABSOLUTE_PATH>", text)

    return text


def sanitize_error_info(error_info: str, project_root: Path | None = None) -> str:
    """对错误信息进行脱敏（路径替换）.

    Args:
        error_info: 原始错误信息.
        project_root: 项目根目录.

    Returns:
        脱敏后的错误信息.
    """
    return sanitize_file_paths(error_info, project_root)


# ==================== 便捷函数 ====================


def sanitize_order_to_json(order: OrderData) -> str:
    """将订单数据脱敏后序列化为 JSON 字符串.

    Args:
        order: 原始订单.

    Returns:
        脱敏后的 JSON 字符串（compact 格式）.
    """
    sanitized = sanitize_order_data(order)
    try:
        return encode_order(sanitized).decode("utf-8")
    except Exception:
        logger.exception("[错误]: 脱敏后序列化失败")
        return '{"error": "脱敏序列化失败"}'


# ==================== 独立运行测试 ====================

if __name__ == "__main__":
    """独立测试：验证脱敏规则是否正确应用."""
    print("=" * 50)
    print("数据脱敏工具 — 自检")
    print("=" * 50)

    # 构造测试订单
    test_order = OrderData(
        order_meta=OrderMeta(
            invoice_no="20251202-01",
            contract_no="PO25-018",
            date="2025-12-26",
            trade_term="FOB",
            payment_term="100% T/T IN ADVANCE",
            country_of_origin="China",
            order_no="",
            transport_mode="海运",
        ),
        customer=Customer(
            company_name_en="LG CHEM. LTD.",
            country="South Korea",
            company_name_cn="LG化学有限公司",
            address="Mutlukent Mahallesi, Ankara 85 Sitesi, 2020. Sokak No.21",
            contact_person="MR. Z.AYHAN ACAR",
            phone="+82 123456789",
            mobile="+82 987654321",
            destination="Busan",
        ),
        pallets=[
            Pallet(
                pallet_no=1,
                length_m=1.16,
                width_m=1.01,
                height_m=1.97,
                pallet_weight_kg=15.0,
                cartons=[
                    Carton(
                        carton_label="1",
                        is_batch=False,
                        batch_count=1,
                        length_cm=32.0,
                        width_cm=32.0,
                        height_cm=34.0,
                        gross_weight_kg=23.3,
                        products=[
                            Product(
                                seq_no=1,
                                product_name="50℃ Type 2A-1 Heat Shrink Sleeve",
                                hs_code="3926909090",
                                unit="Roll",
                                qty_per_carton=1.0,
                                unit_price=85.0,
                                net_weight_per_unit_kg=22.3,
                                destination_country="Turkey",
                                specification="330mm*2.0mm*30M",
                                declaration_elements="民用管道防腐用/聚乙烯制/无牌/无型号/330mm",
                            )
                        ],
                    )
                ],
            )
        ],
        totals=Totals(
            total_pallets=1,
            total_cartons=1,
            total_gross_weight_kg=23.3,
            total_net_weight_kg=22.3,
            total_volume_cbm=2.308,
            total_amount=85.0,
        ),
        origin=Origin(),
    )

    # 执行脱敏
    sanitized = sanitize_order_data(test_order)

    print("\n[脱敏结果]:")
    print(f"  company_name_en: \"{sanitized.customer.company_name_en}\"")
    print(f"  company_name_cn: \"{sanitized.customer.company_name_cn}\"")
    print(f"  phone: \"{sanitized.customer.phone}\"")
    print(f"  mobile: \"{sanitized.customer.mobile}\"")
    print(f"  address: \"{sanitized.customer.address}\"")
    print(f"  contact_person: \"{sanitized.customer.contact_person}\"")

    for pallet in sanitized.pallets:
        for carton in pallet.cartons:
            for p in carton.products:
                print(f"  product.seq_no={p.seq_no}: unit_price={p.unit_price}, product_name=\"{p.product_name}\", hs_code=\"{p.hs_code}\"")

    print(f"  invoice_no: \"{sanitized.order_meta.invoice_no}\"")

    # 验证关键规则
    print("\n[验证]:")
    assert sanitized.customer.company_name_en == "LG***", f"company_name_en 脱敏失败: {sanitized.customer.company_name_en}"
    assert sanitized.customer.phone == "[REDACTED]", f"phone 脱敏失败"
    assert sanitized.customer.mobile == "[REDACTED]", f"mobile 脱敏失败"
    assert sanitized.customer.address.startswith("Mutlukent "), f"address 脱敏失败"
    assert sanitized.order_meta.invoice_no == "20251202-01", "invoice_no 不应脱敏"

    # 验证 product unit_price
    for pallet in sanitized.pallets:
        for carton in pallet.cartons:
            for p in carton.products:
                assert p.unit_price == 0.0, f"unit_price 应为 0.00: {p.unit_price}"
                assert p.product_name == "50℃ Type 2A-1 Heat Shrink Sleeve", "product_name 不应脱敏"
                assert p.hs_code == "3926909090", "hs_code 不应脱敏"

    print("  ✅ 所有脱敏规则验证通过")

    # 测试路径脱敏
    test_error = (
        "File \"D:\\Coding_Programs\\CustomsFileGenerator\\src\\generators\\packing_generator.py\", line 42\n"
        "File \"C:\\Users\\admin\\.pyenv\\pyenv-win\\versions\\3.12.0\\lib\\os.py\", line 123"
    )
    sanitized_err = sanitize_file_paths(test_error)
    print(f"\n[路径脱敏测试]:")
    print(f"  原始: {test_error[:80]}...")
    print(f"  脱敏: {sanitized_err[:80]}...")

    print("\n🚀 数据脱敏工具自检通过")
