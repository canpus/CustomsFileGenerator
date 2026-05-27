"""诊断包导出器 — 阶段 8.3.

在生成出错时，将脱敏后的订单数据、运行日志、系统环境信息打包为 ZIP 文件，
便于开发者排查问题。
"""

from __future__ import annotations

import logging
import os
import platform
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from config.constants import APP_NAME, APP_VERSION, LOGS_DIR, PROJECT_ROOT, TradeTerm
from src.models.order_data import OrderData, OrderMeta
from src.utils.data_sanitizer import sanitize_error_info, sanitize_order_to_json

logger = logging.getLogger(__name__)

# ==================== 诊断包导出器 ====================


class DiagnosticExporter:
    """诊断包导出器.

    使用方式：
        exporter = DiagnosticExporter()
        zip_path = exporter.export(order, error_info)
        print(f"诊断包已导出到: {zip_path}")
    """

    @staticmethod
    def export(
        order: OrderData | None = None,
        error_info: str = "",
        output_dir: str | Path | None = None,
    ) -> Path:
        """导出诊断包 ZIP 文件.

        包含：
            - 脱敏后的订单 JSON（sanitized_order.json）
            - 运行日志（errors.log，若存在）
            - 系统环境信息（system_info.txt）

        Args:
            order: 原始订单数据，为 None 时跳过.
            error_info: 错误描述信息.
            output_dir: 输出目录，默认为 LOGS_DIR.

        Returns:
            生成的 ZIP 文件路径.

        Raises:
            OSError: ZIP 文件写入失败时抛出.
        """
        # 入口断言
        if output_dir is None:
            output_dir = LOGS_DIR
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"diagnostic_{timestamp}.zip"
        zip_path = output_dir / zip_filename

        print(f"正在导出诊断包: {zip_path}")

        try:
            with tempfile.TemporaryDirectory(prefix="diagnostic_") as tmp_dir:
                tmp_path = Path(tmp_dir)

                # 1. 脱敏后的订单 JSON
                if order is not None:
                    print("  → 脱敏订单数据...")
                    try:
                        sanitized_json = sanitize_order_to_json(order)
                        (tmp_path / "sanitized_order.json").write_text(
                            sanitized_json, encoding="utf-8"
                        )
                    except Exception:
                        logger.exception("[错误]: 订单数据脱敏失败")
                        (tmp_path / "sanitized_order.json").write_text(
                            '{"error": "脱敏失败，请查看原始 error_info"}',
                            encoding="utf-8",
                        )

                # 2. 错误信息
                print("  → 写入错误信息...")
                sanitized_error = sanitize_error_info(error_info, PROJECT_ROOT)
                (tmp_path / "error_info.txt").write_text(
                    f"诊断时间: {datetime.now().isoformat()}\n"
                    f"程序版本: {APP_NAME} v{APP_VERSION}\n"
                    f"{'=' * 60}\n"
                    f"{sanitized_error}\n",
                    encoding="utf-8",
                )

                # 3. 系统环境信息
                print("  → 收集系统环境信息...")
                system_info = _collect_system_info()
                (tmp_path / "system_info.txt").write_text(system_info, encoding="utf-8")

                # 4. 运行日志（errors.log）
                errors_log_path = LOGS_DIR / "errors.log"
                if errors_log_path.exists():
                    print("  → 复制错误日志...")
                    log_content = errors_log_path.read_text(encoding="utf-8")
                    # 脱敏日志中的路径
                    log_content = sanitize_error_info(log_content, PROJECT_ROOT)
                    (tmp_path / "errors.log").write_text(log_content, encoding="utf-8")
                else:
                    (tmp_path / "errors.log").write_text("(无错误日志)\n", encoding="utf-8")

                # 5. operations.log（可选）
                ops_log_path = LOGS_DIR / "operations.log"
                if ops_log_path.exists():
                    ops_content = ops_log_path.read_text(encoding="utf-8")[
                        -50000:
                    ]  # 最多取最后 50KB
                    (tmp_path / "operations.log").write_text(ops_content, encoding="utf-8")

                # 打包 ZIP
                print("  → 打包为 ZIP...")
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for file_path in tmp_path.iterdir():
                        if file_path.is_file():
                            zf.write(file_path, file_path.name)

            print(f"✅ 诊断包导出完成: {zip_path}")
            logger.info("诊断包已导出: %s", zip_path)
            return zip_path

        except Exception:
            logger.exception("[错误]: 诊断包导出失败")
            raise


def _collect_system_info() -> str:
    """收集系统环境信息.

    Returns:
        格式化的系统信息文本.
    """
    try:
        info_lines = [
            f"程序: {APP_NAME} v{APP_VERSION}",
            f"时间: {datetime.now().isoformat()}",
            f"Python: {sys.version}",
            f"平台: {platform.platform()}",
            f"系统: {platform.system()} {platform.release()}",
            f"架构: {platform.machine()}",
            f"处理器: {platform.processor()}",
            f"工作目录: {Path.cwd()}",
            f"项目根目录: {PROJECT_ROOT}",
        ]

        # 已安装的关键包版本
        key_packages = [
            "openpyxl",
            "msgspec",
            "python-docx",
            "ttkbootstrap",
            "python-dotenv",
            "num2words",
        ]
        for pkg in key_packages:
            try:
                mod = __import__(pkg)
                version = getattr(mod, "__version__", "unknown")
                info_lines.append(f"  {pkg}: {version}")
            except ImportError:
                info_lines.append(f"  {pkg}: NOT INSTALLED")

        # 环境变量（脱敏 — 仅列出 KEY，不列 VALUE）
        env_keys = [
            k
            for k in os.environ
            if "KEY" in k.upper() or "TOKEN" in k.upper() or "SECRET" in k.upper()
        ]
        if env_keys:
            info_lines.append(f"环境变量 (含 'KEY/TOKEN/SECRET' 的键): {', '.join(env_keys)}")

        return "\n".join(info_lines) + "\n"

    except Exception as e:
        return f"系统信息收集失败: {e}\n"


# ==================== 独立运行测试 ====================

if __name__ == "__main__":
    """独立测试：导出诊断包."""
    print("=" * 50)
    print("诊断包导出器 — 自检")
    print("=" * 50)

    # 创建一个简单的测试订单
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

    test_order = OrderData(
        order_meta=OrderMeta(
            invoice_no="TEST-001",
            contract_no="TEST-CT-001",
            date="2026-05-26",
            trade_term=TradeTerm("FOB"),
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

    # 模拟错误信息
    error_info = (
        "生成装箱单失败\n"
        'File "D:\\Coding_Programs\\CustomsFileGenerator\\src\\generators\\packing_generator.py", line 42, in generate\n'
        '    raise ValueError("模板单元格 D3 为空")\n'
        "ValueError: 模板单元格 D3 为空"
    )

    # 导出诊断包
    try:
        zip_path = DiagnosticExporter.export(order=test_order, error_info=error_info)

        # 验证 ZIP 文件
        import zipfile

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            print(f"\nZIP 内容: {names}")
            # 应包含 sanitized_order.json, error_info.txt, system_info.txt
            expected_files = ["sanitized_order.json", "error_info.txt", "system_info.txt"]
            for ef in expected_files:
                assert ef in names, f"诊断包缺少文件: {ef}"
            print("✅ 诊断包内容完整")

        print("\n🚀 诊断包导出器自检通过")
        print(f"诊断包位于: {zip_path}")

    except Exception as e:
        print(f"[错误]: 诊断包导出失败: {e}")
        import traceback

        traceback.print_exc()
