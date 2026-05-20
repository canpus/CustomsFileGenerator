# -*- coding: utf-8 -*-
"""报关资料自动生成系统 — 错误映射器.

将 msgspec 的 ValidationError 映射为用户可读的中文修复建议，
严格遵循三要素格式：[错误] / [原因] / [排查]。
"""

from __future__ import annotations

import re
import textwrap
from typing import Any


# ==================== 枚举值映射 ====================

# 运输方式合法值
VALID_TRANSPORT_MODES: frozenset[str] = frozenset({"海运", "空运", "陆运"})

# 贸易条款合法值
VALID_TRADE_TERMS: frozenset[str] = frozenset({"FOB", "CIF", "DAP", "DDP", "EXW", "CFR"})

# 包装类型合法值
VALID_PACKAGE_TYPES: frozenset[str] = frozenset({"pallet", "carton", "package"})

# 字段中文名映射
FIELD_CN_MAP: dict[str, str] = {
    "invoice_no": "发票号",
    "contract_no": "合同号",
    "order_no": "订单号",
    "date": "日期",
    "transport_mode": "运输方式",
    "vessel_flight": "船名/航班号",
    "bill_of_lading_no": "提单号",
    "trade_term": "贸易条款",
    "payment_term": "付款方式",
    "currency": "币种",
    "package_type": "包装类型",
    "country_of_origin": "原产国",
    "goods_summary": "货品名称摘要",
    "declaration_elements_template": "申报要素模板",
    "company_name_en": "客户公司英文名",
    "company_name_cn": "客户公司中文名",
    "address": "地址",
    "contact_person": "联系人",
    "phone": "电话",
    "mobile": "手机号",
    "country": "国家",
    "destination": "目的地",
    "export_port": "装运港",
    "domestic_source": "境内货源地",
    "manufacturer": "生产厂家",
    "business_entity": "经营单位",
    "trade_mode": "贸易方式",
    "tax_nature": "征免性质",
    "settlement_method": "结汇方式",
    "tax_rebate": "退税情况",
    "pallet_no": "托盘编号",
    "length_m": "托盘长度(m)",
    "width_m": "托盘宽度(m)",
    "height_m": "托盘高度(m)",
    "pallet_weight_kg": "托盘自重(kg)",
    "carton_label": "纸箱标签",
    "is_batch": "是否批量",
    "batch_count": "批量数量",
    "length_cm": "纸箱长度(cm)",
    "width_cm": "纸箱宽度(cm)",
    "height_cm": "纸箱高度(cm)",
    "gross_weight_kg": "纸箱毛重(kg)",
    "seq_no": "商品序号",
    "product_name": "商品名称",
    "specification": "规格型号",
    "hs_code": "HS编码",
    "declaration_elements": "申报要素",
    "unit": "单位",
    "qty_per_carton": "每箱数量",
    "unit_price": "单价",
    "net_weight_per_unit_kg": "单件净重(kg)",
    "destination_country": "目的国",
    "total_pallets": "托盘总数",
    "total_cartons": "纸箱总数",
    "total_gross_weight_kg": "总毛重(kg)",
    "total_net_weight_kg": "总净重(kg)",
    "total_volume_cbm": "总体积(m³)",
    "total_amount": "总金额",
    "total_amount_upper": "大写金额",
    "template_name": "模板名称",
    "created_at": "创建时间",
    "description": "模板描述",
}


def _field_cn(field_path: str) -> str:
    """将字段路径转为中文名.

    Args:
        field_path: 毫秒 spec 错误中的字段路径，如 "$.order_meta.invoice_no".

    Returns:
        中文字段名，如 "发票号".
    """
    # 提取最后一节路径
    parts = field_path.replace("$.", "").replace("$[", "[").split(".")
    last = parts[-1].split("[")[0] if "[" in parts[-1] else parts[-1]
    return FIELD_CN_MAP.get(last, last)


_TYPE_ERROR_PATTERN = re.compile(r"Expected `(\w+)`, got `(\w+)`")
_ENUM_ERROR_PATTERN = re.compile(r"Invalid enum value '([^']+)'")
_PATH_PATTERN = re.compile(r"at `(\$[\w\[\]\.]+)`")


def _extract_path(msg: str) -> str:
    """从 msgspec 错误消息中提取字段路径.

    如 "Expected `int`, got `str` - at `$.age`" → "$.age".
    """
    m = _PATH_PATTERN.search(msg)
    if m:
        return m.group(1)
    return "$"


def map_validation_error(error: Any) -> str:
    """将 msgspec 校验错误信息映射为中文错误信息.

    Args:
        error: str（错误消息）或 msgspec.ValidationError 对象.

    Returns:
        格式化后的中文错误信息，包含三要素标牌.
    """
    msg: str = str(error)
    field_path: str = _extract_path(msg)
    field_cn: str = _field_cn(field_path)

    # ---- 类型错误 ----
    type_match = _TYPE_ERROR_PATTERN.search(msg)
    if type_match:
        expected_type = type_match.group(1)
        got_type = type_match.group(2)
        return textwrap.dedent(f"""\
        [错误]: 字段"{field_cn}"类型不正确
        [原因]: 期望类型为 {expected_type}, 实际传入 {got_type}
        [排查]: 请将该字段的值改为 {expected_type} 类型，例如：如果期望 int, 请确保 JSON 中不含引号""")

    # ---- 枚举值错误 ----
    enum_match = _ENUM_ERROR_PATTERN.search(msg)
    if enum_match:
        invalid_value = enum_match.group(1)
        field_key = field_path.replace("$.", "").replace("$[", "").split(".")[-1]

        if field_key == "trade_term":
            valid_values = VALID_TRADE_TERMS
        elif field_key == "transport_mode":
            valid_values = VALID_TRANSPORT_MODES
        elif field_key == "package_type":
            valid_values = VALID_PACKAGE_TYPES
        else:
            valid_values = frozenset()

        valid_str = ", ".join(sorted(valid_values)) if valid_values else "（未配置）"
        return textwrap.dedent(f"""\
        [错误]: 字段"{field_cn}"的值"{invalid_value}"不在允许的枚举值中
        [原因]: {field_cn}仅允许以下值: {valid_str}
        [排查]: 请将"{field_cn}"修改为上述允许的值之一""")

    # ---- 缺少必填字段 ----
    if "missing required field" in msg.lower():
        return textwrap.dedent(f"""\
        [错误]: 缺少必填字段"{field_cn}"
        [原因]: 该字段为必填，但 JSON 中未提供
        [排查]: 请在 JSON 中补充"{field_cn}"字段""")

    # ---- 数组类型期望 ----
    if "Expected `array`" in msg:
        return textwrap.dedent(f"""\
        [错误]: 字段"{field_cn}"应为数组/列表
        [原因]: {msg}
        [排查]: 请将"{field_cn}"的值改为 JSON 数组格式，例如: []""")

    # ---- 最小值约束 ----
    if "minimum" in msg.lower() or ">=" in msg:
        return textwrap.dedent(f"""\
        [错误]: 字段"{field_cn}"的值不满足最小值约束
        [原因]: {msg}
        [排查]: 请增大"{field_cn}"的值以满足最小值要求""")

    # ---- 非正值约束 ----
    if "exclusive" in msg.lower() and "0" in msg:
        return textwrap.dedent(f"""\
        [错误]: 字段"{field_cn}"的值必须大于 0
        [原因]: {msg}
        [排查]: 请将"{field_cn}"改为正数（>0）""")

    # ---- 兜底 ----
    return textwrap.dedent(f"""\
    [错误]: 字段"{field_cn}"校验失败
    [原因]: {msg}
    [排查]: 请根据上述错误信息检查"{field_cn}"的值是否正确""")


def map_validation_errors(errors: str | list[Any]) -> list[str]:
    """将 msgspec 校验错误映射为中文错误信息列表.

    msgspec 的 ValidationError 对象是单一异常（不可迭代），
    每次抛出一个错误。本函数接受：
    - 单个 str（直接解析）
    - 一个包含 str 的列表（批量解析）

    Args:
        errors: str 或 str 列表，校验错误信息.

    Returns:
        中文错误信息字符串列表.
    """
    if isinstance(errors, str):
        error_list: list[str] = [errors]
    else:
        error_list = [str(e) for e in errors]

    results: list[str] = []
    for err_str in error_list:
        try:
            results.append(map_validation_error(err_str))
        except Exception:
            # 兜底：直接输出原始错误信息
            results.append(
                f"[错误]: 数据校验失败\n"
                f"[原因]: {err_str}\n"
                f"[排查]: 请检查输入数据格式"
            )
    return results


def format_validation_report(errors: list[str]) -> str:
    """将错误信息列表格式化为完整报告.

    Args:
        errors: map_validation_errors 的输出.

    Returns:
        格式化的验证报告字符串.
    """
    if not errors:
        return "✅ 数据校验通过"

    lines: list[str] = ["=" * 60, f"❌ 数据校验失败，共 {len(errors)} 个错误", "=" * 60, ""]
    for i, err in enumerate(errors, 1):
        lines.append(f"--- 错误 {i} ---")
        lines.append(err)
        lines.append("")
    return "\n".join(lines)


# ========== 运行说明 ==========
# 依赖安装：pip install msgspec
# 使用示例：
#   from src.models.order_data import decode_order
#   from src.models.error_mapper import map_validation_errors, format_validation_report
#   try:
#       order = decode_order(json_str)
#   except msgspec.ValidationError as e:
#       errors = map_validation_errors(e.errors())
#       print(format_validation_report(errors))
# =============================
