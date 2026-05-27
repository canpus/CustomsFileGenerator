# -*- coding: utf-8 -*-
"""阶段 8 里程碑测试：诊断包导出 + 数据脱敏.

运行方式：
    python -m pytest tests/test_diagnostic.py -v

覆盖：
    6. 诊断包导出：生成 zip 文件 → 解压后包含 3+ 个文件
    7. 脱敏：公司名 "LG CHEM. LTD." → "LG***"
    8. 脱敏：电话号码 "+82 123456789" → "[REDACTED]"
    9. 脱敏：单价 0.63 → 0.00
"""

from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

import msgspec
import pytest

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


# ==================== 辅助函数 ====================


def _make_test_order() -> OrderData:
    """构造用于脱敏测试的订单."""
    return OrderData(
        order_meta=OrderMeta(
            invoice_no="20251202-01",
            contract_no="PO25-018",
            date="2025-12-26",
            trade_term="FOB",
            payment_term="100% T/T IN ADVANCE",
            country_of_origin="China",
        ),
        customer=Customer(
            company_name_en="LG CHEM. LTD.",
            country="South Korea",
            company_name_cn="LG化学有限公司",
            address="Mutlukent Mahallesi, Ankara 85 Sitesi, 2020. Sokak No.21, Beysukent, Cankaya, Ankara,Turkey",
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
                        carton_label="A-1",
                        is_batch=False,
                        batch_count=1,
                        length_cm=32.0,
                        width_cm=32.0,
                        height_cm=34.0,
                        gross_weight_kg=23.3,
                        products=[
                            Product(
                                seq_no=1,
                                product_name="50°C Type 2A-1 Heat Shrink Sleeve",
                                hs_code="3926909090",
                                unit="Roll",
                                qty_per_carton=1.0,
                                unit_price=0.63,
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
            total_amount=0.63,
        ),
        origin=Origin(export_port="Shenzhen"),
    )


# ==================== 测试 6：诊断包导出 ====================


def test_diagnostic_export():
    """测试 6: 诊断包导出 → 生成 zip 文件 → 解压后包含必要文件."""
    from src.utils.diagnostic_exporter import DiagnosticExporter

    order = _make_test_order()
    error_info = (
        "生成装箱单失败\n"
        "File \"src/generators/packing_generator.py\", line 42\n"
        "ValueError: 模板单元格 D3 为空"
    )

    # 导出到临时目录
    with tempfile.TemporaryDirectory(prefix="test_diag_") as tmp_dir:
        zip_path = DiagnosticExporter.export(
            order=order,
            error_info=error_info,
            output_dir=tmp_dir,
        )

        assert zip_path.exists(), f"诊断包未生成: {zip_path}"
        assert zip_path.suffix == ".zip", f"输出不是 ZIP 文件: {zip_path}"

        # 解压检查内容
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            print(f"ZIP 内容: {names}")

            # 必须包含的文件
            assert "sanitized_order.json" in names, "诊断包缺少 sanitized_order.json"
            assert "error_info.txt" in names, "诊断包缺少 error_info.txt"
            assert "system_info.txt" in names, "诊断包缺少 system_info.txt"

            # 验证 sanitized_order.json 内容
            with zf.open("sanitized_order.json") as f:
                content = f.read().decode("utf-8")
                # 应包含脱敏后的数据
                assert "LG***" in content, f"脱敏不完整: {content[:200]}"

            # 验证 error_info.txt 路径已脱敏
            with zf.open("error_info.txt") as f:
                err_content = f.read().decode("utf-8")
                # 路径应被替换为 <PROJECT_ROOT> 或 <ABSOLUTE_PATH>
                assert "ValueError" in err_content, f"错误信息不完整: {err_content[:200]}"

    print("✅ 测试 6 通过: 诊断包导出完整 (3+ 个文件)")


# ==================== 测试 7：脱敏 — 公司名 ====================


def test_sanitize_company_name():
    """测试 7: 公司名 "LG CHEM. LTD." → "LG***"."""
    from src.utils.data_sanitizer import sanitize_order_data

    order = _make_test_order()
    sanitized = sanitize_order_data(order)

    # 验证公司名
    expected = "LG***"
    actual = sanitized.customer.company_name_en
    assert actual == expected, f"公司名脱敏失败: 期望 \"{expected}\", 实际 \"{actual}\""

    # 验证中文名也脱敏
    assert sanitized.customer.company_name_cn == "LG***", (
        f"中文公司名脱敏失败: \"{sanitized.customer.company_name_cn}\""
    )

    # 验证 invoice_no 不被脱敏
    assert sanitized.order_meta.invoice_no == "20251202-01", "invoice_no 不应被脱敏"

    # 验证 产品名/HS Code 不被脱敏
    product = sanitized.pallets[0].cartons[0].products[0]
    assert "50°C" in product.product_name, f"产品名不应被脱敏: {product.product_name}"
    assert product.hs_code == "3926909090", f"HS Code 不应被脱敏: {product.hs_code}"
    assert product.specification == "330mm*2.0mm*30M", f"规格不应被脱敏: {product.specification}"

    print(f"✅ 测试 7 通过: 公司名 \"{actual}\" (原始: \"{order.customer.company_name_en}\")")


# ==================== 测试 8：脱敏 — 电话号码 ====================


def test_sanitize_phone():
    """测试 8: 电话号码 "+82 123456789" → "[REDACTED]"."""
    from src.utils.data_sanitizer import sanitize_order_data

    order = _make_test_order()
    sanitized = sanitize_order_data(order)

    # 验证 phone
    assert sanitized.customer.phone == "[REDACTED]", (
        f"phone 脱敏失败: 期望 \"[REDACTED]\", 实际 \"{sanitized.customer.phone}\""
    )

    # 验证 mobile
    assert sanitized.customer.mobile == "[REDACTED]", (
        f"mobile 脱敏失败: 期望 \"[REDACTED]\", 实际 \"{sanitized.customer.mobile}\""
    )

    # 原始对象不应被修改
    assert order.customer.phone == "+82 123456789", "原始订单 phone 被意外修改"
    assert order.customer.mobile == "+82 987654321", "原始订单 mobile 被意外修改"

    print(f"✅ 测试 8 通过: phone={sanitized.customer.phone}, mobile={sanitized.customer.mobile}")


# ==================== 测试 9：脱敏 — 单价 ====================


def test_sanitize_unit_price():
    """测试 9: 单价 0.63 → 0.00."""
    from src.utils.data_sanitizer import sanitize_order_data

    order = _make_test_order()
    sanitized = sanitize_order_data(order)

    # 验证所有 product 的 unit_price 都被置为 0.0
    for pallet in sanitized.pallets:
        for carton in pallet.cartons:
            for product in carton.products:
                assert product.unit_price == 0.0, (
                    f"单价应被覆写为 0.00: {product.product_name} unit_price={product.unit_price}"
                )
                # 验证产品名等不被覆写
                assert product.product_name, "产品名不应为空"

    # 原始对象不应被修改
    original_price = order.pallets[0].cartons[0].products[0].unit_price
    assert original_price == 0.63, f"原始订单单价被意外修改: {original_price}"

    # 验证 address 脱敏
    assert sanitized.customer.address.startswith("Mutlukent "), (
        f"address 脱敏失败: \"{sanitized.customer.address}\""
    )
    assert sanitized.customer.address.endswith("..."), (
        f"address 应以 ... 结尾: \"{sanitized.customer.address}\""
    )

    print(f"✅ 测试 9 通过: 单价 {original_price} → {sanitized.pallets[0].cartons[0].products[0].unit_price}")


# ==================== 测试：空字段脱敏 ====================


def test_sanitize_empty_fields():
    """附加测试: 空字段脱敏不崩溃."""
    from src.utils.data_sanitizer import sanitize_order_data

    # 构造一个字段为空的订单
    order = OrderData(
        order_meta=OrderMeta(
            invoice_no="",
            contract_no="",
            date="",
            trade_term="FOB",
            payment_term="",
            country_of_origin="",
        ),
        customer=Customer(
            company_name_en="",
            country="",
            phone="",
            mobile="",
            address="",
        ),
        pallets=[],
        totals=Totals(
            total_pallets=0,
            total_cartons=0,
            total_gross_weight_kg=0.0,
            total_net_weight_kg=0.0,
            total_volume_cbm=0.0,
            total_amount=0.0,
        ),
        origin=Origin(),
    )

    # 不应抛出异常
    try:
        sanitized = sanitize_order_data(order)
        assert sanitized.customer.company_name_en == "***", f"空公司名脱敏: {sanitized.customer.company_name_en}"
        assert sanitized.customer.phone == "", "空 phone 应保持空"
        assert sanitized.customer.address == "...", f"空地址脱敏: {sanitized.customer.address}"
    except Exception as e:
        pytest.fail(f"空字段脱敏抛出异常: {e}")

    print("✅ 附加测试通过: 空字段脱敏不崩溃")


# ==================== 测试：路径脱敏 ====================


def test_sanitize_file_paths():
    """附加测试: 异常堆栈中的绝对路径替换为相对路径."""
    from src.utils.data_sanitizer import sanitize_file_paths

    test_error = (
        'File "D:\\Coding_Programs\\CustomsFileGenerator\\src\\generators\\packing_generator.py", line 42\n'
        'File "C:\\Users\\admin\\.pyenv\\pyenv-win\\versions\\3.12.0\\lib\\os.py", line 123\n'
        'File "/home/user/projects/utils.py", line 10'
    )

    sanitized = sanitize_file_paths(test_error)

    # 项目根路径应替换为 <PROJECT_ROOT>
    assert "<PROJECT_ROOT>" in sanitized, f"项目路径应被替换: {sanitized[:200]}"

    # 非项目的绝对路径应被替换
    assert "ABSOLUTE_PATH" in sanitized, f"非项目绝对路径应被替换: {sanitized[:200]}"

    # 相对路径 / src/xx.py 不被替换
    # （在 sanitized 中找不到原始盘符路径）
    assert "D:\\Coding_Programs" not in sanitized
    assert "C:\\Users" not in sanitized

    print(f"✅ 路径脱敏测试通过")
