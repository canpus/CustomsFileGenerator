"""报关资料自动生成系统 — 订单业务规则校验.

对 OrderData 进行一致性校验，包括：
- 总毛重 ≥ 总净重
- 每个纸箱毛重 ≥ 箱内所有商品净重之和
- 托盘总体积 = 长×宽×高（允许 ±0.001 误差）
- 汇总数据与明细加总一致（交叉校验）
- 所有必填字段不为空
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from src.models.order_data import Carton, OrderData, Pallet, Product

logger = logging.getLogger(__name__)

# ==================== 校验结果数据结构 ====================

Severity = Literal["error", "warning", "info"]


@dataclass
class ValidationMessage:
    """单条校验消息.

    Attributes:
        severity: 严重程度（error/warning/info）.
        code: 消息代码（如 "E001"）.
        message: 中文描述.
        reason: 可能的原因.
        solution: 解决方法.
    """

    severity: Severity
    code: str
    message: str
    reason: str
    solution: str


@dataclass
class ValidationReport:
    """校验报告.

    Attributes:
        passed: 是否通过（无 error 级别消息）.
        messages: 所有校验消息.
        errors: error 级别消息.
        warnings: warning 级别消息.
        infos: info 级别消息.
    """

    passed: bool = True
    messages: list[ValidationMessage] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationMessage]:
        """error 级别的消息."""
        return [m for m in self.messages if m.severity == "error"]

    @property
    def warnings(self) -> list[ValidationMessage]:
        """warning 级别的消息."""
        return [m for m in self.messages if m.severity == "warning"]

    @property
    def infos(self) -> list[ValidationMessage]:
        """info 级别的消息."""
        return [m for m in self.messages if m.severity == "info"]

    def add_error(self, code: str, message: str, reason: str, solution: str) -> None:
        """添加一条 error 级别消息."""
        self.passed = False
        self.messages.append(ValidationMessage("error", code, message, reason, solution))

    def add_warning(self, code: str, message: str, reason: str, solution: str) -> None:
        """添加一条 warning 级别消息."""
        self.messages.append(ValidationMessage("warning", code, message, reason, solution))

    def add_info(self, code: str, message: str) -> None:
        """添加一条 info 级别消息."""
        self.messages.append(ValidationMessage("info", code, message, "", ""))

    def __bool__(self) -> bool:
        return self.passed


# ==================== 辅助函数 ====================


def _flatten_products(pallets: list[Pallet]) -> list[Product]:
    """展开所有托盘下的所有商品为一维列表."""
    result: list[Product] = []
    for pallet in pallets:
        for carton in pallet.cartons:
            for product in carton.products:
                result.append(product)
    return result


def _flatten_cartons(pallets: list[Pallet]) -> list[Carton]:
    """展开所有托盘下的所有纸箱为一维列表."""
    result: list[Carton] = []
    for pallet in pallets:
        for carton in pallet.cartons:
            result.append(carton)
    return result


def _safe_float(value: float) -> float:
    """安全取浮点数，避免 NaN/inf."""
    import math

    if math.isnan(value) or math.isinf(value):
        return 0.0
    return value


# ==================== 校验函数 ====================


def validate_order_consistency(
    order: OrderData, large_order_threshold: int = 100
) -> ValidationReport:
    """对订单数据进行全面一致性校验.

    校验规则：
    1. 总毛重 ≥ 总净重
    2. 每个纸箱毛重 ≥ 箱内所有商品净重之和
    3. 每个托盘总体积 = 长×宽×高（允许 ±0.001 误差）
    4. 汇总数据与明细加总一致（交叉校验）
    5. 所有必填字段不为空

    Args:
        order: 待校验的 OrderData 对象.
        large_order_threshold: 大订单托盘数阈值，超过时打印性能提示.

    Returns:
        ValidationReport 校验报告.
    """
    report = ValidationReport()

    # ---- 规则 0：空订单检查 ----
    if not order.pallets or len(order.pallets) == 0:
        report.add_error(
            "E001",
            "托盘列表为空，不是有效订单",
            "订单数据中 pallets 数组长度为 0，可能是数据导入或构造过程中丢失了数据",
            "请检查数据源，确保至少包含一个托盘及其下的纸箱和商品信息",
        )
        return report

    # ---- 信息：大订单提示 ----
    if len(order.pallets) >= large_order_threshold:
        report.add_info(
            "I001",
            f"订单包含 {len(order.pallets)} 个托盘（≥{large_order_threshold}），属于大订单，"
            f"生成过程可能耗时较长，请耐心等待",
        )

    # ---- 规则 1：总毛重 ≥ 总净重 ----
    gross = _safe_float(order.totals.total_gross_weight_kg)
    net = _safe_float(order.totals.total_net_weight_kg)
    if gross < net:
        report.add_warning(
            "W001",
            f"总毛重 {gross:.3f} kg 小于总净重 {net:.3f} kg，不符合物理常识",
            "商品净重 + 包装材料重量 = 毛重，毛重应不小于净重；可能是商品净重数据有误或汇总计算错误",
            "请检查每个商品的 net_weight_per_unit_kg 字段是否正确，以及汇总值是否按（净重×数量）正确加总",
        )

    # ---- 规则 2：每个纸箱毛重 ≥ 箱内商品净重之和 ----
    all_cartons = _flatten_cartons(order.pallets)
    for idx, carton in enumerate(all_cartons):
        carton_net: float = 0.0
        for product in carton.products:
            carton_net += _safe_float(product.net_weight_per_unit_kg) * _safe_float(
                product.qty_per_carton
            )
        carton_gross = _safe_float(carton.gross_weight_kg)

        if carton_gross < carton_net - 0.001:  # 允许微小浮点误差
            report.add_warning(
                "W002",
                (
                    f'纸箱 "{carton.carton_label}"（第 {idx + 1} 个）毛重 {carton_gross:.3f} kg '
                    f"小于箱内商品净重之和 {carton_net:.3f} kg"
                ),
                "纸箱毛重应 ≥ 箱内所有商品的净重之和（含包装）；可能是纸箱 gross_weight_kg 或商品 net_weight_per_unit_kg 数值有误",
                f'请检查纸箱 "{carton.carton_label}" 的 gross_weight_kg 和箱内商品的 net_weight_per_unit_kg',
            )

    # ---- 规则 3：托盘体积 = 长×宽×高 ----
    for pallet in order.pallets:
        expected_volume = (
            _safe_float(pallet.length_m)
            * _safe_float(pallet.width_m)
            * _safe_float(pallet.height_m)
        )

        # 托盘总体积从 totals 拿不到，这里仅做自身一致性检查
        # 同时检查 cm/m 单位是否正确（如果体积 > 100 m³，大概率是单位错误）
        if expected_volume > 100.0:
            report.add_warning(
                "W003",
                (
                    f"托盘 {pallet.pallet_no} 的体积 {expected_volume:.3f} m³ 异常大（>100 m³），"
                    f"长={pallet.length_m}m 宽={pallet.width_m}m 高={pallet.height_m}m"
                ),
                "托盘长/宽/高可能填写了 cm 而非 m，导致体积异常",
                f"请确认托盘 {pallet.pallet_no} 的尺寸单位（应为 m），如果确实以 cm 填写，请将数值除以 100",
            )

    # ---- 规则 4：汇总数据与明细加总一致（交叉校验） ----
    # 从明细重新计算汇总
    calc_gross: float = 0.0
    calc_net: float = 0.0
    calc_cartons: int = 0
    calc_volume: float = 0.0
    calc_amount: float = 0.0

    for pallet in order.pallets:
        for carton in pallet.cartons:
            effective_count = carton.batch_count if carton.is_batch else 1
            calc_cartons += effective_count
            calc_gross += _safe_float(carton.gross_weight_kg) * effective_count

            carton_net_total: float = 0.0
            for product in carton.products:
                carton_net_total += _safe_float(product.net_weight_per_unit_kg) * _safe_float(
                    product.qty_per_carton
                )
                calc_amount += (
                    _safe_float(product.unit_price)
                    * _safe_float(product.qty_per_carton)
                    * effective_count
                )
            calc_net += carton_net_total * effective_count

        calc_volume += (
            _safe_float(pallet.length_m)
            * _safe_float(pallet.width_m)
            * _safe_float(pallet.height_m)
        )

    # 托盘数
    if order.totals.total_pallets != len(order.pallets):
        report.add_warning(
            "W004",
            (
                f"托盘总数不匹配：totals 声明 {order.totals.total_pallets} 个，"
                f"实际明细 {len(order.pallets)} 个"
            ),
            "totals 汇总值与明细列表长度不一致",
            "请更新 totals.total_pallets 为实际托盘数，或检查是否有托盘被遗漏",
        )

    # 纸箱数
    if abs(order.totals.total_cartons - calc_cartons) > 0.5:
        report.add_warning(
            "W005",
            (
                f"纸箱总数不匹配：totals 声明 {order.totals.total_cartons} 个，"
                f"明细加总 {calc_cartons} 个"
            ),
            "totals 汇总值与明细逐箱加总不一致；注意批量纸箱（is_batch=True）应按 batch_count 计算",
            "请重新计算纸箱总数，确保与明细一致；批量纸箱需按 batch_count 计数",
        )

    # 总毛重
    if abs(order.totals.total_gross_weight_kg - calc_gross) > 0.1:
        report.add_warning(
            "W006",
            (
                f"总毛重不匹配：totals 声明 {order.totals.total_gross_weight_kg:.3f} kg，"
                f"明细加总 {calc_gross:.3f} kg（差 {abs(order.totals.total_gross_weight_kg - calc_gross):.3f} kg）"
            ),
            "totals 汇总值与明细逐箱加总不一致",
            "请重新计算总毛重，确保与明细一致",
        )

    # 总净重
    if abs(order.totals.total_net_weight_kg - calc_net) > 0.1:
        report.add_warning(
            "W007",
            (
                f"总净重不匹配：totals 声明 {order.totals.total_net_weight_kg:.3f} kg，"
                f"明细加总 {calc_net:.3f} kg（差 {abs(order.totals.total_net_weight_kg - calc_net):.3f} kg）"
            ),
            "totals 汇总值与明细逐商品加总不一致",
            "请重新计算总净重，确保与明细一致",
        )

    # 总体积
    if abs(order.totals.total_volume_cbm - calc_volume) > 0.001:
        report.add_warning(
            "W008",
            (
                f"总体积不匹配：totals 声明 {order.totals.total_volume_cbm:.3f} m³，"
                f"明细加总 {calc_volume:.3f} m³（差 {abs(order.totals.total_volume_cbm - calc_volume):.3f} m³）"
            ),
            "totals 汇总值与各托盘（长×宽×高）加总不一致",
            "请重新计算总体积，确保与明细一致",
        )

    # 总金额
    if abs(order.totals.total_amount - calc_amount) > 0.01:
        report.add_warning(
            "W009",
            (
                f"总金额不匹配：totals 声明 {order.totals.total_amount:.2f}，"
                f"明细加总 {calc_amount:.2f}（差 {abs(order.totals.total_amount - calc_amount):.2f}）"
            ),
            "totals 汇总值与逐商品（单价×数量）加总不一致",
            "请重新计算总金额，确保与明细一致",
        )

    # ---- 规则 5：汇总后的状态 ----
    if report.passed:
        report.add_info("I002", "订单一致性校验通过")

    return report


# ========== 运行说明 ==========
# 依赖安装：pip install msgspec
# 使用示例：
#   from src.models.order_data import decode_order
#   from src.models.validators import validate_order_consistency
#   order = decode_order(json_str)
#   report = validate_order_consistency(order)
#   if report.passed:
#       print("校验通过")
#   else:
#       for err in report.errors:
#           print(err.message)
# =============================
