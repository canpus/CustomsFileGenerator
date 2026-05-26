# -*- coding: utf-8 -*-
"""一键生成协调器（Orchestrator）— 阶段 7.1.

根据 OrderData 依次调用 3 个生成器（Packing + Invoice + Contract），
输出 3 份报关资料文件。支持实时进度回调、错误隔离、诊断包导出。

[待迁移] 阶段 6 完成后，接入第 4 个生成器（CustomsGenerator），输出 4 文件。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from config.constants import (
    FILE_PREFIX_MAP,
    OUTPUT_DIR,
    TEMPLATE_CONTRACT_PATH,
    TEMPLATE_INVOICE_PATH,
    TEMPLATE_PACKING_PATH,
)
from src.generators.contract_generator import ContractGenerator
from src.generators.invoice_generator import InvoiceGenerator
from src.generators.packing_generator import PackingGenerator
from src.generators.template_guard import TemplateGuard
from src.models.order_data import OrderData
from src.models.validators import ValidationReport, validate_order_consistency

logger = logging.getLogger(__name__)


# ==================== 数据结构 ====================


@dataclass
class GeneratorResult:
    """单个生成器的执行结果.

    Attributes:
        generator_name: 生成器名称（如 "装箱单"）.
        file_type: 文件类型标识（如 "packing"）.
        status: 执行状态（"success" / "failed" / "skipped"）.
        output_path: 输出文件路径（成功时）.
        error_message: 错误信息（失败时）.
        skipped_reason: 跳过原因（跳过时）.
    """

    generator_name: str
    file_type: str
    status: str  # "success" | "failed" | "skipped"
    output_path: Optional[Path] = None
    error_message: str = ""
    skipped_reason: str = ""


@dataclass
class OrchestratorReport:
    """一键生成汇总报告.

    Attributes:
        success: 是否全部成功（无失败项）.
        total: 生成器总数.
        succeeded: 成功数量.
        failed: 失败数量.
        skipped: 跳过数量.
        results: 所有生成器的结果列表.
        output_files: 成功生成的文件路径列表.
        validation_report: 数据校验报告.
    """

    success: bool = True
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    results: List[GeneratorResult] = field(default_factory=list)
    output_files: List[Path] = field(default_factory=list)
    validation_report: Optional[ValidationReport] = None


# ==================== 协调器类 ====================


class Orchestrator:
    """一键生成协调器.

    负责：
    1. 订单数据校验
    2. 模板完整性检查
    3. 依次调用所有生成器
    4. 错误隔离（某个生成器失败不影响其他）
    5. 进度回调汇总
    6. 诊断包导出

    使用方式：
        orchestrator = Orchestrator()
        report = orchestrator.generate_all(order, output_dir, progress_callback)
        print(f"生成完成: {report.succeeded}/{report.total} 成功")
    """

    def __init__(self):
        """初始化协调器.

        注册所有生成器（当前 3 个，阶段 6 完成后增至 4 个）。
        """
        self._guard: TemplateGuard = TemplateGuard()
        self._generators: List[tuple[str, str, object]] = self._build_generator_list()

    def _build_generator_list(self) -> List[tuple[str, str, object]]:
        """构建生成器列表.

        每个元素为 (文件类型标识, 显示名称, 生成器实例)。

        Returns:
            生成器注册列表.
        """
        generators: List[tuple[str, str, object]] = [
            ("packing", "装箱单", PackingGenerator(template_path=TEMPLATE_PACKING_PATH)),
            ("invoice", "形式发票", InvoiceGenerator(template_path=TEMPLATE_INVOICE_PATH)),
            ("contract", "形式合同", ContractGenerator(template_path=TEMPLATE_CONTRACT_PATH)),
        ]

        # [待迁移] 阶段 6 完成后，取消下面的注释，接入 CustomsGenerator：
        # from src.generators.customs_generator import CustomsGenerator
        # from config.constants import TEMPLATE_CUSTOMS_PATH
        # generators.append(("customs", "报关单", CustomsGenerator(template_path=TEMPLATE_CUSTOMS_PATH)))

        return generators

    # ==================== 公开 API ====================

    def generate_all(
        self,
        order: OrderData,
        output_dir: str | Path | None = None,
        progress_callback: Callable[[str, float], None] | None = None,
        skip_validation: bool = False,
    ) -> OrchestratorReport:
        """一键生成所有报关资料文件.

        完整流程：
        1. 入口断言（order 非空）
        2. 订单数据校验
        3. 模板完整性检查
        4. 依次调用各生成器（错误隔离）
        5. 汇总报告

        Args:
            order: 订单数据对象.
            output_dir: 输出目录，默认为 OUTPUT_DIR.
            progress_callback: 进度回调，签名为 (description: str, progress_0_1: float).
            skip_validation: 是否跳过数据校验（仅用于测试）.

        Returns:
            OrchestratorReport 生成报告.

        Raises:
            ValueError: order 为 None 时抛出.
        """
        # 步骤 0：入口断言
        if order is None:
            raise ValueError("[错误]: 订单数据为 None, 无法生成报关资料")

        report: OrchestratorReport = OrchestratorReport()
        out_dir: Path = Path(output_dir) if output_dir else OUTPUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)

        # 步骤 1：订单数据校验
        self._report_progress(progress_callback, "正在校验订单数据...", 0.02)
        if not skip_validation:
            validation: ValidationReport = validate_order_consistency(order)
            report.validation_report = validation
            if validation.errors:
                error_msgs: str = "; ".join(m.code for m in validation.errors)
                logger.warning(
                    "订单数据校验发现 %d 个错误: %s", len(validation.errors), error_msgs
                )
            if validation.warnings:
                logger.warning(
                    "订单数据校验发现 %d 个警告: %s",
                    len(validation.warnings),
                    "; ".join(m.code for m in validation.warnings),
                )
        else:
            logger.info("已跳过订单数据校验（skip_validation=True）")

        # 步骤 2：模板完整性检查
        self._report_progress(progress_callback, "正在检查模板文件...", 0.05)
        templates_ok, template_errors = self._guard.validate_all()
        if not templates_ok:
            logger.error("模板完整性检查失败: %s", "; ".join(template_errors))
            # 模板问题不是致命错误——生成器各自检查模板，这里仅记录

        # 步骤 3：依次调用生成器
        total_generators: int = len(self._generators)
        report.total = total_generators

        for idx, (file_type, display_name, generator) in enumerate(self._generators):
            base_progress: float = 0.10 + (idx / total_generators) * 0.85
            step_description: str = f"正在生成{display_name}..."

            # 内部进度回调：将生成器进度映射到整体进度范围
            def gen_callback(desc: str, pct: float) -> None:
                overall: float = base_progress + (pct / total_generators) * 0.85
                overall = min(overall, 0.99)
                self._report_progress(
                    progress_callback,
                    f"[{idx + 1}/{total_generators}] {desc}",
                    overall,
                )

            self._report_progress(
                progress_callback,
                f"[{idx + 1}/{total_generators}] {step_description}",
                base_progress,
            )

            try:
                output_path: Path = generator.generate(
                    order,
                    output_dir=out_dir,
                    progress_callback=gen_callback,
                )
                result: GeneratorResult = GeneratorResult(
                    generator_name=display_name,
                    file_type=file_type,
                    status="success",
                    output_path=output_path,
                )
                report.succeeded += 1
                report.output_files.append(output_path)
                logger.info("%s 生成成功: %s", display_name, output_path)

            except Exception as e:
                result = GeneratorResult(
                    generator_name=display_name,
                    file_type=file_type,
                    status="failed",
                    error_message=str(e),
                )
                report.failed += 1
                logger.error(
                    "[错误]: %s 生成失败\n[原因]: %s\n[排查]: 请检查模板文件和数据格式",
                    display_name,
                    e,
                )

            report.results.append(result)

        # [待迁移] 阶段 6 完成后，第 4 个生成器在 _build_generator_list 中注册，
        # 此循环自动处理，无需修改此处代码。

        # 步骤 4：汇总
        report.success = (report.failed == 0)
        self._report_progress(progress_callback, "生成完成", 1.0)

        logger.info(
            "一键生成完成: 成功 %d/%d, 失败 %d/%d, 跳过 %d/%d",
            report.succeeded, report.total,
            report.failed, report.total,
            report.skipped, report.total,
        )

        return report

    def print_report(self, report: OrchestratorReport) -> None:
        """在控制台打印生成报告.

        Args:
            report: 生成报告.
        """
        print("\n" + "=" * 60)
        print("  报关资料生成报告")
        print("=" * 60)

        # 校验结果
        if report.validation_report:
            vr = report.validation_report
            if vr.errors:
                print(f"\n  ❌ 数据校验错误 ({len(vr.errors)} 项):")
                for m in vr.errors:
                    print(f"     [{m.code}] {m.message}")
            if vr.warnings:
                print(f"\n  ⚠️ 数据校验警告 ({len(vr.warnings)} 项):")
                for m in vr.warnings:
                    print(f"     [{m.code}] {m.message}")

        # 生成结果
        print(f"\n  生成结果: {report.succeeded}/{report.total} 成功")
        print("  " + "-" * 56)

        for result in report.results:
            if result.status == "success":
                print(f"  ✅ {result.generator_name}: {result.output_path}")
            elif result.status == "failed":
                print(f"  ❌ {result.generator_name}: {result.error_message[:80]}")
            elif result.status == "skipped":
                print(f"  ⏳ {result.generator_name}: {result.skipped_reason}")

        print("=" * 60)

        if report.output_files:
            print(f"\n📁 输出目录: {report.output_files[0].parent}")
            print(f"📄 共生成 {len(report.output_files)} 个文件")
            for f in report.output_files:
                print(f"   - {f.name}")

    # ==================== 工具方法 ====================

    @staticmethod
    def _report_progress(
        callback: Callable[[str, float], None] | None,
        description: str,
        progress: float,
    ) -> None:
        """安全的进度回调."""
        if callback:
            try:
                callback(description, progress)
            except Exception as e:
                logger.warning("[警告]: 进度回调执行失败: %s", e)


# ==================== 模块级便捷函数 ====================

_DEFAULT_ORCHESTRATOR: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    """获取默认协调器单例.

    Returns:
        全局唯一的 Orchestrator 实例.
    """
    global _DEFAULT_ORCHESTRATOR
    if _DEFAULT_ORCHESTRATOR is None:
        _DEFAULT_ORCHESTRATOR = Orchestrator()
    return _DEFAULT_ORCHESTRATOR


def generate_all(
    order: OrderData,
    output_dir: str | Path | None = None,
    progress_callback: Callable[[str, float], None] | None = None,
) -> OrchestratorReport:
    """一键生成所有报关资料（便捷函数）.

    Args:
        order: 订单数据.
        output_dir: 输出目录.
        progress_callback: 进度回调.

    Returns:
        OrchestratorReport 报告.
    """
    return get_orchestrator().generate_all(order, output_dir, progress_callback)


# ========== 运行说明 ==========
# 依赖安装: pip install openpyxl msgspec
# 运行命令: 由 main.py --gui 或测试脚本调用，不直接运行此模块
# 预期输出: 3 个文件（装箱单 + 发票 + 合同），阶段 6 完成后 4 个文件
# =============================
