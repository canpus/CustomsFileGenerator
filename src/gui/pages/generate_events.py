"""生成页 — 事件处理 mixin.

包含生成启动、后台线程、完成/异常回调、诊断包导出、打开文件夹。
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

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from config.constants import OUTPUT_DIR
from src.generators.orchestrator import Orchestrator

if TYPE_CHECKING:
    from src.gui.pages.generate_page import GeneratePage
    from src.models.order_data import OrderData

logger = logging.getLogger(__name__)


def _open_directory(path: str) -> None:
    """跨平台打开文件夹."""
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        logger.warning("[警告]: 打开文件夹失败: %s — %s", path, e)


class GenerateEventsMixin:
    """生成页事件处理方法 mixin.

    假设 self 提供：
    - self._generate_btn, self._progress_bar, self._progress_label
    - self._result_vars, self._result_icons
    - self._diagnostic_btn, self._open_folder_btn
    - self._is_generating, self._report
    - self.app（来自 PageBase）
    - self._update_progress, self._reset_results（来自 GeneratePage）
    """

    _generate_btn: ttk.Button | None
    _progress_bar: ttk.Progressbar | None
    _progress_label: ttk.Label | None
    _result_vars: dict[str, ttk.StringVar]
    _result_icons: dict[str, ttk.Label]
    _diagnostic_btn: ttk.Button | None
    _open_folder_btn: ttk.Button | None
    _is_generating: bool
    _report: Any
    app: object
    frame: ttk.Frame

    # ==================== 生成操作 ====================

    def _on_generate(self: GeneratePage) -> None:
        """点击一键生成按钮."""
        if self._is_generating:
            messagebox.showinfo("提示", "正在生成中，请等待完成。")
            return

        order = self.app.current_order
        if order is None:
            messagebox.showwarning("无订单数据", "请先在「新建单据」中录入订单信息和商品明细。")
            return

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
        self._generate_btn.configure(state="disabled", text="正在生成...")
        self._reset_results()
        self._update_progress(0, "正在初始化...")

        thread = threading.Thread(target=self._do_generate, args=(order,), daemon=True)
        thread.start()

    def _do_generate(self: GeneratePage, order: OrderData) -> None:
        """在后台线程中执行生成."""
        try:
            orchestrator = Orchestrator()

            def progress_callback(description: str, progress: float) -> None:
                self.frame.after(0, lambda: self._update_progress(int(progress * 100), description))

            self.frame.after(0, lambda: self._update_progress(5, "正在校验订单数据..."))
            report = orchestrator.generate_all(
                order,
                output_dir=OUTPUT_DIR,
                progress_callback=progress_callback,
            )

            self._report = report
            self.frame.after(0, lambda: self._on_generation_complete(report))

        except Exception as exc:
            logger.exception("[错误]: 生成过程中发生异常")
            err_msg = str(exc)
            self.frame.after(0, lambda msg=err_msg: self._on_generation_error(msg))

    def _on_generation_complete(self: GeneratePage, report: Any) -> None:
        """生成完成回调（主线程）."""
        self._is_generating = False
        self._generate_btn.configure(state="normal", text="一键生成报关资料")

        if report.success:
            self._update_progress(100, "全部生成完成！")
            self._generate_btn.configure(bootstyle="success")

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

            self._open_folder_btn.pack(side=LEFT, padx=(10, 0))
            self.app.set_status(f"生成完成: {report.succeeded}/{report.total} 成功")

            messagebox.showinfo(
                "生成完成",
                f"报关资料已生成！\n\n"
                f"成功: {report.succeeded}/{report.total}\n"
                f"输出目录: {OUTPUT_DIR}\n\n"
                f"生成的文件：\n"
                + "\n".join(
                    f"  • {Path(str(r.output_path)).name}"
                    for r in report.results
                    if r.status == "success"
                ),
            )
        else:
            self._update_progress(100, "生成完成（有错误）")
            self._generate_btn.configure(bootstyle="warning")

            if self._diagnostic_btn is not None:
                self._diagnostic_btn.pack(side=LEFT, padx=(10, 0))

            for result in report.results:
                if result.file_type in self._result_vars:
                    if result.status == "success":
                        self._result_icons[result.file_type].configure(
                            textvariable=ttk.StringVar(value="✅")
                        )
                        self._result_vars[result.file_type].set("✅ 已生成")
                    elif result.status == "failed":
                        self._result_icons[result.file_type].configure(
                            textvariable=ttk.StringVar(value="❌")
                        )
                        self._result_vars[result.file_type].set(
                            f"❌ 失败 — {result.error_message[:60]}"
                        )

            self._open_folder_btn.pack(side=LEFT, padx=(10, 0))
            self.app.set_status(
                f"生成完成: {report.succeeded}/{report.total} 成功, {report.failed} 失败"
            )

            messagebox.showwarning(
                "生成完成（有错误）",
                f"部分文件生成失败。\n\n"
                f"成功: {report.succeeded}/{report.total}\n"
                f"失败: {report.failed}/{report.total}\n\n"
                f"可点击「导出诊断包」按钮获取详细信息。",
            )

    def _on_generation_error(self: GeneratePage, error_msg: str) -> None:
        """生成异常回调（主线程）."""
        self._is_generating = False
        self._generate_btn.configure(state="normal", text="重试生成", bootstyle="danger")
        self._update_progress(0, f"生成失败: {error_msg[:60]}")

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

    # ==================== 诊断包导出 ====================

    def _on_export_diagnostic(self: GeneratePage) -> None:
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
                        f"{r.generator_name}: {r.error_message}" for r in error_results
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

            _open_directory(str(zip_path.parent))

        except Exception as e:
            logger.exception("[错误]: 导出诊断包失败")
            messagebox.showerror("导出失败", f"[错误]: {e}")

    def _on_open_folder(self: GeneratePage) -> None:
        """打开输出文件夹."""
        try:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            _open_directory(str(OUTPUT_DIR))
        except Exception as e:
            logger.exception("[错误]: 打开输出文件夹失败")
            messagebox.showerror("打开失败", f"[错误]: 无法打开输出文件夹\n[原因]: {e}")
