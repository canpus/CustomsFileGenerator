# -*- coding: utf-8 -*-
"""生成与预览页 — 阶段 9.6（3 文件模式）.

提供：
- 一键生成按钮 → 进度条 → 完成提示
- 生成清单显示 3 项（装箱单 ✅ / 发票 ✅ / 合同 ✅ / 报关单 ⏳ 暂未就绪）
- 诊断包导出按钮（仅出错时显示）
- 打开输出文件夹按钮
- 完整性校验提示

[待迁移] 阶段 6 完成后，报关单行改为可交互生成。
"""

from __future__ import annotations


import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import messagebox
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.models.order_data import OrderData

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from config.constants import OUTPUT_DIR

logger = logging.getLogger(__name__)


def _open_directory(path: str) -> None:
    """跨平台打开文件夹.

    Args:
        path: 文件夹路径.
    """
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        logger.warning("[警告]: 打开文件夹失败: %s — %s", path, e)

try:
    from src.gui.app import PageBase, GuiApp
except ImportError:
    PageBase = object
    GuiApp = object


class GeneratePage(PageBase):
    """生成与预览页.

    负责：
    1. 展示生成前的数据摘要
    2. 一键生成 3 个报关资料文件
    3. 显示进度和结果
    4. 支持诊断包导出
    """

    def __init__(self, parent: ttk.Frame, app: GuiApp):
        """初始化.

        Args:
            parent: 父级容器.
            app: 主应用控制器.
        """
        super().__init__(parent, app)
        self._progress_bar: ttk.Progressbar | None = None
        self._progress_label: ttk.Label | None = None
        self._result_frame: ttk.Frame | None = None
        self._result_vars: dict[str, ttk.StringVar] = {}
        self._result_icons: dict[str, ttk.Label] = {}
        self._diagnostic_btn: ttk.Button | None = None
        self._open_folder_btn: ttk.Button | None = None
        self._generate_btn: ttk.Button | None = None
        self._report: Any = None
        self._is_generating: bool = False

    def build(self) -> None:
        """构建生成页 UI."""
        self.frame = ttk.Frame(self.parent)
        self.frame.pack(fill=BOTH, expand=YES, padx=10, pady=10)

        # ---- 标题 ----
        title_frame = ttk.Frame(self.frame)
        title_frame.pack(fill=X, padx=5, pady=(5, 10))

        ttk.Label(
            title_frame,
            text="🚀 生成报关资料",
            font=self.app.get_heading_font(),
            bootstyle="primary",
        ).pack(side=LEFT)

        ttk.Label(
            title_frame,
            text="3 文件模式（报关单暂未就绪）",
            font=self.app.get_font(size=9),
            bootstyle="warning",
        ).pack(side=RIGHT)

        # ---- 订单摘要 ----
        self._build_summary_section()

        # ---- 生成结果 ----
        self._build_result_section()

        # ---- 进度区 ----
        progress_frame = ttk.Labelframe(self.frame, text="生成进度", padding=10, bootstyle="info")
        progress_frame.pack(fill=X, pady=(0, 10))

        self._progress_label = ttk.Label(
            progress_frame,
            text="准备就绪，点击下方按钮开始生成。",
            font=self.app.get_font(size=10),
        )
        self._progress_label.pack(anchor=W, pady=(0, 5))

        self._progress_bar = ttk.Progressbar(
            progress_frame,
            mode="determinate",
            length=400,
            bootstyle="success-striped",
        )
        self._progress_bar.pack(fill=X)
        self._progress_bar["value"] = 0

        # ---- 底部按钮 ----
        bottom = ttk.Frame(self.frame)
        bottom.pack(fill=X, padx=5, pady=(10, 5))

        ttk.Button(
            bottom,
            text="← 返回编辑商品明细",
            bootstyle="secondary-outline",
            command=lambda: self.app.switch_page("tree_editor"),
        ).pack(side=LEFT)

        self._open_folder_btn = ttk.Button(
            bottom,
            text="📂 打开输出文件夹",
            bootstyle="info-outline",
            command=self._on_open_folder,
        )
        self._open_folder_btn.pack(side=LEFT, padx=(10, 0))

        self._diagnostic_btn = ttk.Button(
            bottom,
            text="🩺 导出诊断包",
            bootstyle="warning-outline",
            command=self._on_export_diagnostic,
        )
        # 初始隐藏，出错时显示
        # self._diagnostic_btn.pack(side=LEFT, padx=(10, 0))

        self._generate_btn = ttk.Button(
            bottom,
            text="🚀 一键生成报关资料",
            bootstyle="success",
            command=self._on_generate,
        )
        self._generate_btn.pack(side=RIGHT)

    def _build_summary_section(self) -> None:
        """构建订单摘要区域."""
        summary_frame = ttk.Labelframe(self.frame, text="📋 订单摘要", padding=10, bootstyle="primary")
        summary_frame.pack(fill=X, pady=(0, 10))

        self._summary_text = ttk.Text(
            summary_frame,
            height=6,
            wrap="word",
            font=self.app.get_font(size=10),
            state="disabled",
        )
        self._summary_text.pack(fill=X)

    def _build_result_section(self) -> None:
        """构建生成结果区域."""
        self._result_frame = ttk.Labelframe(
            self.frame,
            text="📄 生成结果",
            padding=10,
            bootstyle="success",
        )
        self._result_frame.pack(fill=X, pady=(0, 10))

        # 4 个文件的状态行（第 4 个报关单为暂缓状态）
        items: list[tuple[str, str, str]] = [
            ("packing", "📦 装箱单", "等待生成..."),
            ("invoice", "🧾 形式发票", "等待生成..."),
            ("contract", "📝 形式合同", "等待生成..."),
            ("customs", "📋 报关单", "⏳ 暂未就绪（阶段 6 开发中）"),
        ]

        for file_type, label, default_status in items:
            row = ttk.Frame(self._result_frame)
            row.pack(fill=X, pady=3)

            icon_var = ttk.StringVar(value="⏳")
            icon_label = ttk.Label(row, textvariable=icon_var, font=("Segoe UI Symbol", 16))
            icon_label.pack(side=LEFT, padx=(0, 5))
            self._result_icons[file_type] = icon_label

            ttk.Label(row, text=label, font=self.app.get_font(bold=True, size=10), width=15, anchor=W).pack(side=LEFT)

            status_var = ttk.StringVar(value=default_status)
            status_label = ttk.Label(row, textvariable=status_var, font=self.app.get_font(size=9))
            status_label.pack(side=LEFT, padx=(5, 0))
            self._result_vars[file_type] = status_var

    # ==================== 生成操作 ====================

    def _on_generate(self) -> None:
        """点击一键生成按钮."""
        if self._is_generating:
            messagebox.showinfo("提示", "正在生成中，请等待完成。")
            return

        order = self.app.current_order
        if order is None:
            messagebox.showwarning("无订单数据", "请先在「新建单据」中录入订单信息和商品明细。")
            return

        # 确认生成
        if not messagebox.askyesno(
            "确认生成",
            f"即将生成以下 3 个报关资料文件：\n\n"
            f"  📦 装箱单\n"
            f"  🧾 形式发票\n"
            f"  📝 形式合同\n\n"
            f"发票号: {order.order_meta.invoice_no}\n"
            f"客户: {order.customer.company_name_en}\n"
            f"托盘: {order.totals.total_pallets} | "
            f"纸箱: {order.totals.total_cartons}\n\n"
            f"输出目录: {OUTPUT_DIR}\n\n"
            f"确认生成？",
        ):
            return

        self._is_generating = True
        self._generate_btn.configure(state="disabled", text="⏳ 正在生成...")
        self._reset_results()
        self._update_progress(0, "正在初始化...")

        # 在后台线程中执行生成
        thread = threading.Thread(target=self._do_generate, args=(order,), daemon=True)
        thread.start()

    def _do_generate(self, order: OrderData) -> None:
        """在后台线程中执行生成.

        Args:
            order: OrderData 对象.
        """
        try:
            from src.generators.orchestrator import Orchestrator

            orchestrator = Orchestrator()

            def progress_callback(description: str, progress: float) -> None:
                self.frame.after(0, lambda: self._update_progress(
                    int(progress * 100), description
                ))

            self.frame.after(0, lambda: self._update_progress(5, "正在校验订单数据..."))
            report = orchestrator.generate_all(
                order,
                output_dir=OUTPUT_DIR,
                progress_callback=progress_callback,
            )

            self._report = report

            # 在主线程更新 UI
            self.frame.after(0, lambda: self._on_generation_complete(report))

        except Exception as e:
            logger.exception("[错误]: 生成过程中发生异常")
            self.frame.after(0, lambda: self._on_generation_error(str(e)))

    def _on_generation_complete(self, report: Any) -> None:
        """生成完成回调（主线程）.

        Args:
            report: OrchestratorReport 对象.
        """
        self._is_generating = False
        self._generate_btn.configure(state="normal", text="🚀 一键生成报关资料")

        if report.success:
            self._update_progress(100, "✅ 全部生成完成！")
            self._generate_btn.configure(bootstyle="success")

            # 更新结果状态
            for result in report.results:
                if result.file_type in self._result_vars:
                    if result.status == "success":
                        self._result_icons[result.file_type].configure(
                            textvariable=ttk.StringVar(value="✅")
                        )
                        self._result_vars[result.file_type].set(
                            f"✅ 已生成 — {Path(str(result.output_path)).name if result.output_path else '完成'}"
                        )
                    elif result.status == "failed":
                        self._result_icons[result.file_type].configure(
                            textvariable=ttk.StringVar(value="❌")
                        )
                        self._result_vars[result.file_type].set(
                            f"❌ 失败 — {result.error_message[:60]}"
                        )

            # 显示打开文件夹按钮
            self._open_folder_btn.pack(side=LEFT, padx=(10, 0))

            self.app.set_status(f"生成完成: {report.succeeded}/{report.total} 成功")

            messagebox.showinfo(
                "生成完成",
                f"报关资料已生成！\n\n"
                f"成功: {report.succeeded}/{report.total}\n"
                f"输出目录: {OUTPUT_DIR}\n\n"
                f"生成的文件：\n" +
                "\n".join(f"  • {Path(str(r.output_path)).name}"
                          for r in report.results if r.status == "success"),
            )
        else:
            self._update_progress(100, "⚠️ 生成完成（有错误）")
            self._generate_btn.configure(bootstyle="warning")

            # 显示诊断包按钮
            if self._diagnostic_btn is not None:
                self._diagnostic_btn.pack(side=LEFT, padx=(10, 0))

            # 更新结果
            for result in report.results:
                if result.file_type in self._result_vars:
                    if result.status == "success":
                        self._result_icons[result.file_type].configure(
                            textvariable=ttk.StringVar(value="✅")
                        )
                        self._result_vars[result.file_type].set(
                            f"✅ 已生成"
                        )
                    elif result.status == "failed":
                        self._result_icons[result.file_type].configure(
                            textvariable=ttk.StringVar(value="❌")
                        )
                        self._result_vars[result.file_type].set(
                            f"❌ 失败 — {result.error_message[:60]}"
                        )

            self._open_folder_btn.pack(side=LEFT, padx=(10, 0))
            self.app.set_status(f"生成完成: {report.succeeded}/{report.total} 成功, {report.failed} 失败")

            messagebox.showwarning(
                "生成完成（有错误）",
                f"部分文件生成失败。\n\n"
                f"成功: {report.succeeded}/{report.total}\n"
                f"失败: {report.failed}/{report.total}\n\n"
                f"可点击「导出诊断包」按钮获取详细信息。",
            )

    def _on_generation_error(self, error_msg: str) -> None:
        """生成异常回调（主线程）.

        Args:
            error_msg: 错误信息.
        """
        self._is_generating = False
        self._generate_btn.configure(state="normal", text="🚀 重试生成", bootstyle="danger")
        self._update_progress(0, f"❌ 生成失败: {error_msg[:60]}")

        if self._diagnostic_btn is not None:
            self._diagnostic_btn.pack(side=LEFT, padx=(10, 0))

        self.app.set_status(f"生成失败: {error_msg[:50]}")

        messagebox.showerror(
            "生成失败",
            f"[错误]: 资料生成过程中发生异常\n\n"
            f"[原因]: {error_msg}\n\n"
            f"[排查]: 请检查模板文件是否完整、订单数据是否有效。\n"
            f"可点击「导出诊断包」获取详细信息。",
        )

    def _reset_results(self) -> None:
        """重置结果状态."""
        defaults = {
            "packing": "等待生成...",
            "invoice": "等待生成...",
            "contract": "等待生成...",
            "customs": "⏳ 暂未就绪（阶段 6 开发中）",
        }
        icons = {
            "packing": "⏳",
            "invoice": "⏳",
            "contract": "⏳",
            "customs": "⏳",
        }
        for ft in defaults:
            if ft in self._result_vars:
                self._result_vars[ft].set(defaults[ft])
            if ft in self._result_icons:
                self._result_icons[ft].configure(textvariable=ttk.StringVar(value=icons[ft]))

        self._update_progress(0, "准备就绪...")

    def _update_progress(self, value: int, description: str) -> None:
        """更新进度条和进度文字.

        Args:
            value: 进度值 (0-100).
            description: 进度描述.
        """
        if self._progress_bar is not None:
            self._progress_bar["value"] = value
        if self._progress_label is not None:
            self._progress_label.configure(text=description)

    # ==================== 诊断包导出 ====================

    def _on_export_diagnostic(self) -> None:
        """导出诊断包."""
        order = self.app.current_order
        if order is None:
            messagebox.showinfo("提示", "没有订单数据可供诊断。")
            return

        try:
            from src.utils.diagnostic_exporter import DiagnosticExporter

            error_info = ""
            if self._report is not None:
                error_results = [r for r in self._report.results if r.status == "failed"]
                if error_results:
                    error_info = "\n".join(
                        f"{r.generator_name}: {r.error_message}"
                        for r in error_results
                    )

            zip_path = DiagnosticExporter.export(
                order=order,
                error_info=error_info,
            )

            messagebox.showinfo(
                "诊断包导出成功",
                f"诊断包已保存到：\n\n{zip_path}\n\n"
                f"包含：脱敏后的订单数据、错误信息、系统环境信息。\n"
                f"请将此文件发送给开发者以便排查问题。",
            )

            # 打开文件所在目录
            _open_directory(str(zip_path.parent))

        except Exception as e:
            logger.exception("[错误]: 导出诊断包失败")
            messagebox.showerror("导出失败", f"[错误]: {e}")

    def _on_open_folder(self) -> None:
        """打开输出文件夹."""
        try:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            _open_directory(str(OUTPUT_DIR))
        except Exception as e:
            logger.exception("[错误]: 打开输出文件夹失败")
            messagebox.showerror("打开失败", f"[错误]: 无法打开输出文件夹\n[原因]: {e}")

    def on_enter(self) -> None:
        """进入页面时更新摘要."""
        order = self.app.current_order
        if order is None:
            self._update_summary("⚠️ 无订单数据，请先在「新建单据」中录入。")
            if self._generate_btn is not None:
                self._generate_btn.configure(state="disabled")
            return

        if self._generate_btn is not None:
            self._generate_btn.configure(state="normal")

        # 构建摘要
        meta = order.order_meta
        cust = order.customer
        totals = order.totals

        summary_lines = [
            f"发票号: {meta.invoice_no}",
            f"合同号: {meta.contract_no}",
            f"日期: {meta.date}",
            f"客户: {cust.company_name_en}",
            f"国家: {cust.country}",
            f"贸易条款: {meta.trade_term}    运输方式: {meta.transport_mode}",
            f"托盘: {totals.total_pallets} | 纸箱: {totals.total_cartons} | "
            f"总毛重: {totals.total_gross_weight_kg} kg | "
            f"总净重: {totals.total_net_weight_kg} kg",
            f"总体积: {totals.total_volume_cbm} m³ | "
            f"总金额: ${totals.total_amount:,.2f}",
            f"输出目录: {OUTPUT_DIR}",
        ]

        self._update_summary("\n".join(summary_lines))

        # 重置结果
        self._reset_results()

    def _update_summary(self, text: str) -> None:
        """更新摘要文本.

        Args:
            text: 摘要内容.
        """
        if self._summary_text is None:
            return
        self._summary_text.configure(state="normal")
        self._summary_text.delete("1.0", END)
        self._summary_text.insert(END, text)
        self._summary_text.configure(state="disabled")


# ========== 运行说明 ==========
# 依赖安装: pip install ttkbootstrap
# 此页面由 GuiApp 自动加载，无需单独运行
# =============================
