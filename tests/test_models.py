# -*- coding: utf-8 -*-
"""阶段 1 里程碑测试：数据模型 + 校验器 + 错误映射.

运行方式：
    python -m pytest tests/test_models.py -v

覆盖：
    1. 合法 JSON → 成功反序列化
    2. 缺少必填字段 → error_mapper 返回中文错误
    3. 类型错误 → error_mapper 返回中文错误
    4. 枚举值非法 → error_mapper 返回中文错误
    5. 总毛重 < 总净重 → validate_order_consistency 返回警告
    6. 纸箱毛重 < 商品净重之和 → validate_order_consistency 返回警告
    7. 空订单（pallets 为空数组）→ reject
    8. 超大订单（100+ 托盘）→ 通过但打印 info
"""

from __future__ import annotations

import json

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
    TemplateMeta,
    Totals,
    decode_order,
    encode_order,
    encode_order_pretty,
)
from src.models.validators import (
    ValidationReport,
    validate_order_consistency,
)
from src.models.error_mapper import (
    map_validation_errors,
    format_validation_report,
)


# ==================== 测试辅助：构造合法订单 ====================


def _make_valid_order_json() -> dict:
    """返回一个最小合法订单的 JSON 字典，供各测试使用."""
    return {
        "order_meta": {
            "invoice_no": "20251202-01",
            "contract_no": "PO25-018",
            "date": "2025-12-26",
            "trade_term": "FOB",
            "payment_term": "100% T/T IN ADVANCE",
            "country_of_origin": "China",
            "transport_mode": "海运",
        },
        "customer": {
            "company_name_en": "YARIMKURE INSAAT LTD. STI.",
            "country": "Turkey",
            "address": "Ankara, Turkey",
        },
        "pallets": [
            {
                "pallet_no": 1,
                "length_m": 1.16,
                "width_m": 1.01,
                "height_m": 1.97,
                "pallet_weight_kg": 15.0,
                "cartons": [
                    {
                        "carton_label": "45",
                        "is_batch": False,
                        "batch_count": 1,
                        "length_cm": 32.0,
                        "width_cm": 32.0,
                        "height_cm": 34.0,
                        "gross_weight_kg": 1048.5,
                        "products": [
                            {
                                "seq_no": 1,
                                "product_name": "50℃ Type 2A-1 Heat Shrink Sleeve",
                                "specification": "330mm*2.0mm*30M",
                                "hs_code": "3926909090",
                                "declaration_elements": "民用管道防腐用/聚乙烯制/无牌/无型号/330mm",
                                "unit": "Roll",
                                "qty_per_carton": 1,
                                "unit_price": 85.0,
                                "currency": "USD",
                                "net_weight_per_unit_kg": 22.3,
                                "destination_country": "Turkey",
                            }
                        ],
                    }
                ],
            }
        ],
        "totals": {
            "total_pallets": 1,
            "total_cartons": 1,
            "total_gross_weight_kg": 1048.5,
            "total_net_weight_kg": 1003.5,
            "total_volume_cbm": 2.308,
            "total_amount": 28050.0,
        },
        "origin": {
            "export_port": "Shenzhen",
            "domestic_source": "深圳特区",
            "manufacturer": "长园长通新材料股份有限公司",
            "business_entity": "长园长通新材料股份有限公司",
            "trade_mode": "一般贸易",
            "tax_nature": "一般征税",
            "settlement_method": "电汇",
            "tax_rebate": "申请退税",
        },
        "template_meta": {
            "template_name": "测试模板",
            "created_at": "2025-12-26T10:00:00",
            "description": "单元测试用",
        },
    }


def _make_valid_order_json_str() -> str:
    return json.dumps(_make_valid_order_json(), ensure_ascii=False)


# ==================== 测试 1：合法 JSON → 成功反序列化 ====================


class TestDecodeValidOrder:
    """合法 JSON 反序列化测试."""

    def test_decode_minimal_order(self) -> None:
        """最简合法订单可成功解码."""
        json_str = _make_valid_order_json_str()
        order = decode_order(json_str)
        assert isinstance(order, OrderData)
        assert order.order_meta.invoice_no == "20251202-01"
        assert order.order_meta.contract_no == "PO25-018"
        assert order.customer.company_name_en == "YARIMKURE INSAAT LTD. STI."
        assert len(order.pallets) == 1
        assert order.pallets[0].pallet_no == 1
        assert len(order.pallets[0].cartons) == 1
        assert order.totals.total_pallets == 1

    def test_decode_with_defaults(self) -> None:
        """缺少可选字段时自动填充默认值."""
        data = _make_valid_order_json()
        # 删除 origin 和 template_meta（均为可选）
        del data["origin"]
        del data["template_meta"]
        json_str = json.dumps(data, ensure_ascii=False)
        order = decode_order(json_str)
        assert order.origin.export_port == ""
        assert order.origin.domestic_source == "深圳特区"
        assert order.template_meta.template_name == ""

    def test_roundtrip_encode_decode(self) -> None:
        """编码再解码保持数据一致."""
        json_str = _make_valid_order_json_str()
        order1 = decode_order(json_str)
        encoded = encode_order(order1)
        order2 = decode_order(encoded)
        assert order1 == order2

    def test_encode_pretty(self) -> None:
        """美化输出包含换行和缩进."""
        json_str = _make_valid_order_json_str()
        order = decode_order(json_str)
        pretty = encode_order_pretty(order).decode("utf-8")
        assert "\n" in pretty
        assert "  " in pretty


# ==================== 测试 2：缺少必填字段 → error_mapper ====================


class TestMissingRequiredFields:
    """缺少必填字段时的错误处理."""

    def test_missing_invoice_no(self) -> None:
        """缺少 invoice_no 应报告中文错误."""
        data = _make_valid_order_json()
        del data["order_meta"]["invoice_no"]
        json_str = json.dumps(data, ensure_ascii=False)
        with pytest.raises(msgspec.ValidationError) as exc_info:
            decode_order(json_str)
        errors = map_validation_errors(str(exc_info.value))
        assert len(errors) >= 1
        assert any("发票号" in e or "invoice_no" in e.lower() or "缺少" in e for e in errors)

    def test_missing_customer(self) -> None:
        """缺少整个 customer 应报告多字段错误."""
        data = _make_valid_order_json()
        del data["customer"]
        json_str = json.dumps(data, ensure_ascii=False)
        with pytest.raises(msgspec.ValidationError) as exc_info:
            decode_order(json_str)
        errors = map_validation_errors(str(exc_info.value))
        assert len(errors) >= 1

    def test_missing_totals(self) -> None:
        """缺少 totals 应报告错误."""
        data = _make_valid_order_json()
        del data["totals"]
        json_str = json.dumps(data, ensure_ascii=False)
        with pytest.raises(msgspec.ValidationError) as exc_info:
            decode_order(json_str)
        errors = map_validation_errors(str(exc_info.value))
        assert len(errors) >= 1


# ==================== 测试 3：类型错误 → error_mapper ====================


class TestTypeErrors:
    """类型错误时的中文提示."""

    def test_string_in_int_field(self) -> None:
        """字符串填在整数字段应报告中文类型错误."""
        data = _make_valid_order_json()
        data["pallets"][0]["pallet_no"] = "第一号"
        json_str = json.dumps(data, ensure_ascii=False)
        with pytest.raises(msgspec.ValidationError) as exc_info:
            decode_order(json_str)
        errors = map_validation_errors(str(exc_info.value))
        assert len(errors) >= 1
        # 应包含中文
        has_chinese = any("\u4e00" <= c <= "\u9fff" for c in errors[0])
        assert has_chinese, f"错误信息应包含中文，实际: {errors[0]}"

    def test_float_in_int_field(self) -> None:
        """浮点数填在整数字段."""
        data = _make_valid_order_json()
        data["totals"]["total_pallets"] = 1.5
        json_str = json.dumps(data, ensure_ascii=False)
        with pytest.raises(msgspec.ValidationError) as exc_info:
            decode_order(json_str)
        errors = map_validation_errors(str(exc_info.value))
        assert len(errors) >= 1

    def test_string_in_number_field(self) -> None:
        """字符串填在数字字段."""
        data = _make_valid_order_json()
        data["totals"]["total_gross_weight_kg"] = "一千公斤"
        json_str = json.dumps(data, ensure_ascii=False)
        with pytest.raises(msgspec.ValidationError) as exc_info:
            decode_order(json_str)
        errors = map_validation_errors(str(exc_info.value))
        assert len(errors) >= 1


# ==================== 测试 4：枚举值非法 → error_mapper ====================


class TestInvalidEnum:
    """非法枚举值时的中文提示."""

    def test_invalid_transport_mode(self) -> None:
        """运输方式填"高铁"应报告中文枚举错误."""
        data = _make_valid_order_json()
        data["order_meta"]["transport_mode"] = "高铁"
        json_str = json.dumps(data, ensure_ascii=False)
        with pytest.raises(msgspec.ValidationError) as exc_info:
            decode_order(json_str)
        errors = map_validation_errors(str(exc_info.value))
        assert len(errors) >= 1
        combined = " ".join(errors)
        assert "高铁" in combined
        assert any("运输方式" in e or "transport_mode" in e.lower() for e in errors)

    def test_invalid_trade_term(self) -> None:
        """贸易条款填非法值."""
        data = _make_valid_order_json()
        data["order_meta"]["trade_term"] = "快递"
        json_str = json.dumps(data, ensure_ascii=False)
        with pytest.raises(msgspec.ValidationError) as exc_info:
            decode_order(json_str)
        errors = map_validation_errors(str(exc_info.value))
        assert len(errors) >= 1

    def test_invalid_package_type(self) -> None:
        """包装类型填非法值."""
        data = _make_valid_order_json()
        data["order_meta"]["package_type"] = "木箱"
        json_str = json.dumps(data, ensure_ascii=False)
        with pytest.raises(msgspec.ValidationError) as exc_info:
            decode_order(json_str)
        errors = map_validation_errors(str(exc_info.value))
        assert len(errors) >= 1


# ==================== 测试 5：总毛重 < 总净重 → 警告 ====================


class TestGrossLessThanNet:
    """总毛重 < 总净重时的警告."""

    def test_gross_less_than_net(self) -> None:
        """总毛重小于总净重时产生 W001 警告."""
        json_str = _make_valid_order_json_str()
        order = decode_order(json_str)
        # 用 msgspec 的 replace 创建一个修改后的副本
        bad_totals = Totals(
            total_pallets=1,
            total_cartons=1,
            total_gross_weight_kg=500.0,  # 小于净重 1003.5
            total_net_weight_kg=1003.5,
            total_volume_cbm=2.308,
            total_amount=28050.0,
        )
        order = OrderData(
            order_meta=order.order_meta,
            customer=order.customer,
            pallets=order.pallets,
            totals=bad_totals,
            origin=order.origin,
            template_meta=order.template_meta,
        )
        report = validate_order_consistency(order)
        # WARNING 级别消息不应导致 passed=False，只有 ERROR 才设为 False
        assert report.passed
        assert any("W001" in m.code for m in report.warnings)

    def test_gross_equal_to_net(self) -> None:
        """总毛重等于总净重时不产生 W001 警告."""
        json_str = _make_valid_order_json_str()
        order = decode_order(json_str)
        equal_totals = Totals(
            total_pallets=1,
            total_cartons=1,
            total_gross_weight_kg=1048.5,
            total_net_weight_kg=1048.5,
            total_volume_cbm=2.308,
            total_amount=28050.0,
        )
        order = OrderData(
            order_meta=order.order_meta,
            customer=order.customer,
            pallets=order.pallets,
            totals=equal_totals,
            origin=order.origin,
            template_meta=order.template_meta,
        )
        report = validate_order_consistency(order)
        # 毛重 = 净重，W001 不应触发
        assert "W001" not in [m.code for m in report.warnings]


# ==================== 测试 6：纸箱毛重 < 商品净重之和 → 警告 ====================


class TestCartonGrossLessThanProducts:
    """纸箱毛重 < 商品净重之和时的警告."""

    def test_carton_gross_too_low(self) -> None:
        """纸箱毛重低于商品净重之和时应产生 W002."""
        data = _make_valid_order_json()
        # 商品净重 22.3 kg，设置纸箱毛重仅 10 kg
        data["pallets"][0]["cartons"][0]["gross_weight_kg"] = 10.0
        json_str = json.dumps(data, ensure_ascii=False)
        order = decode_order(json_str)
        report = validate_order_consistency(order)
        assert any("W002" in m.code for m in report.warnings)

    def test_carton_with_multiple_products(self) -> None:
        """纸箱含多个商品时，净重之和 > 毛重应报警."""
        data = _make_valid_order_json()
        carton = data["pallets"][0]["cartons"][0]
        carton["products"].append(
            {
                "seq_no": 2,
                "product_name": "Filler",
                "specification": "1.5mm*50mm*5m",
                "hs_code": "3926909090",
                "declaration_elements": "民用管道防腐用",
                "unit": "Roll",
                "qty_per_carton": 1,
                "unit_price": 3.15,
                "currency": "USD",
                "net_weight_per_unit_kg": 5.0,
                "destination_country": "Turkey",
            }
        )
        # 两个商品净重共 27.3 kg，毛重仅 10 kg
        carton["gross_weight_kg"] = 10.0
        json_str = json.dumps(data, ensure_ascii=False)
        order = decode_order(json_str)
        report = validate_order_consistency(order)
        assert any("W002" in m.code for m in report.warnings)


# ==================== 测试 7：空订单（pallets 为空）→ reject ====================


class TestEmptyOrder:
    """空订单拒绝测试."""

    def test_empty_pallets_array(self) -> None:
        """pallets 为空数组时应 reject."""
        data = _make_valid_order_json()
        data["pallets"] = []
        json_str = json.dumps(data, ensure_ascii=False)
        order = decode_order(json_str)
        report = validate_order_consistency(order)
        assert not report.passed
        assert any("E001" in e.code for e in report.errors)

    def test_format_validation_report_for_empty(self) -> None:
        """空订单的格式化报告应包含错误详情."""
        data = _make_valid_order_json()
        data["pallets"] = []
        json_str = json.dumps(data, ensure_ascii=False)
        order = decode_order(json_str)
        report = validate_order_consistency(order)
        assert not report.passed
        # 格式化后应包含中文
        formatted = "\n".join(
            [f"[错误]: {e.message}" for e in report.errors]
        )
        assert "托盘" in formatted or "pallets" in formatted.lower()


# ==================== 测试 8：超大订单（100+ 托盘）→ info ====================


class TestLargeOrder:
    """超大订单性能提示测试."""

    def test_large_order_info(self) -> None:
        """100+ 托盘时产生 I001 信息."""
        data = _make_valid_order_json()
        # 构造 100 个托盘
        pallet_template = data["pallets"][0]
        data["pallets"] = []
        for i in range(1, 101):
            p = json.loads(json.dumps(pallet_template))
            p["pallet_no"] = i
            data["pallets"].append(p)
        # 更新 totals 与明细一致
        data["totals"]["total_pallets"] = 100
        data["totals"]["total_cartons"] = 100
        data["totals"]["total_gross_weight_kg"] = 100 * 1048.5
        data["totals"]["total_net_weight_kg"] = 100 * 22.3  # 1 carton × 1 product × 22.3 kg
        data["totals"]["total_volume_cbm"] = 100 * 1.16 * 1.01 * 1.97
        data["totals"]["total_amount"] = 100 * 85.0  # 1 product × 1 qty × 85 USD

        json_str = json.dumps(data, ensure_ascii=False)
        order = decode_order(json_str)
        report = validate_order_consistency(order, large_order_threshold=100)
        # 应包含 I001 信息
        assert any("I001" in m.code for m in report.infos)
        # 不应包含 error 级别消息
        assert not report.errors


# ==================== 跨校验规则测试 ====================


class TestCrossValidation:
    """交叉校验（规则 4）测试."""

    def test_totals_mismatch_cartons(self) -> None:
        """纸箱总数不匹配应报警."""
        data = _make_valid_order_json()
        data["totals"]["total_cartons"] = 999
        json_str = json.dumps(data, ensure_ascii=False)
        order = decode_order(json_str)
        report = validate_order_consistency(order)
        assert any("W005" in m.code for m in report.warnings)

    def test_totals_mismatch_amount(self) -> None:
        """总金额不匹配应报警."""
        data = _make_valid_order_json()
        data["totals"]["total_amount"] = 1.0
        json_str = json.dumps(data, ensure_ascii=False)
        order = decode_order(json_str)
        report = validate_order_consistency(order)
        assert any("W009" in m.code for m in report.warnings)

    def test_validation_report_bool(self) -> None:
        """ValidationReport.__bool__ 正确反映通过状态."""
        report = ValidationReport()
        assert bool(report) is True
        report.add_error("E999", "测试错误", "原因", "解决")
        assert bool(report) is False


# ==================== 格式化报告测试 ====================


class TestFormatReport:
    """format_validation_report 输出测试."""

    def test_empty_errors_shows_pass(self) -> None:
        """无错误时显示通过."""
        result = format_validation_report([])
        assert "通过" in result

    def test_with_errors_shows_count(self) -> None:
        """有错误时显示计数和详情."""
        errors = ["[错误]: 测试\n[原因]: 测试\n[排查]: 测试"]
        result = format_validation_report(errors)
        assert "1 个错误" in result
        assert "--- 错误 1 ---" in result


# ========== 运行说明 ==========
# 运行命令：python -m pytest tests/test_models.py -v
# 预期输出：所有测试 PASSED
# =============================
