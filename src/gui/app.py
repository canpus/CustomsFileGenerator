# -*- coding: utf-8 -*-
"""GUI 主应用窗口 — 阶段 9.1 / P5 GUI 现代化.

基于 ttkbootstrap（Flatly 主题），提供：
- DPI 感知激活
- 字体回退池（Microsoft YaHei → Segoe UI → TkDefaultFont）
- 三段式布局：顶部标题栏 + 左侧导航 / 右侧工作区 + 底部状态栏
- 窗口状态记忆（大小/位置/最大化）
- 关闭确认对话框
- 脏标记追踪（未保存数据保护）
"""

from __future__ import annotations

import ctypes
import logging
import sys
from pathlib import Path
from tkinter import font as tkfont
from tkinter import messagebox
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.models.order_data import OrderData

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from config.constants import APP_NAME, APP_VERSION
from src.gui.page_base import PageBase
from src.gui.styles import (
    FONT_FAMILY,
    FONT_SIZE_NORMAL,
    FONT_SIZE_NAV,
    FONT_SIZE_SMALL,
    FONT_SIZE_TITLE,
    NAV_PANEL_WIDTH,
    apply_theme,
)

# 页面导入
from src.gui.pages.order_info_page import OrderInfoPage
from src.gui.pages.tree_editor_page import TreeEditorPage
from src.gui.pages.line_item_table_page import LineItemTablePage
from src.gui.pages.generate_page import GeneratePage
from src.gui.pages.template_page import TemplatePage
from src.gui.pages.import_page import ImportPage
from src.gui.pages.customer_page import CustomerPage
from src.gui.pages.product_page import ProductPage

logger = logging.getLogger(__name__)

# ==================== 字体回退池 ====================

_FONT_CANDIDATES: list[str] = [
    "Microsoft YaHei",
    "Segoe UI",
    "TkDefaultFont",
]


def _get_available_font(font_size: int = FONT_SIZE_NORMAL) -> tuple[str, int]:
    """查找第一个可用的字体.

    Args:
        font_size: 字号.

    Returns:
        (字体名, 字号) 元组.
    """
    try:
        available = set(tkfont.families())
        for name in _FONT_CANDIDATES:
            if name in available:
                return name, font_size
    except RuntimeError:
        pass
    return "TkDefaultFont", font_size


# ==================== GuiApp 主应用 ====================


class GuiApp:
    """GUI 主应用控制器.

    管理主窗口、导航栏、页面切换、共享订单数据、窗口状态记忆。

    使用方式：
        app = GuiApp()
        app.run()
    """

    def __init__(self) -> None:
        """初始化主窗口."""
        # 0. 偏好设置服务
        self._prefs = self._init_preferences()

        # 1. DPI 感知（Windows）
        self._activate_dpi_awareness()

        # 2. 字体
        self._font_name, self._font_size = _get_available_font(FONT_SIZE_NORMAL)
        self._heading_font = (self._font_name, FONT_SIZE_TITLE)
        self._subheading_font = (self._font_name, FONT_SIZE_NORMAL)
        self._nav_font = (self._font_name, FONT_SIZE_NAV)

        # 3. 创建主窗口
        self.root: ttk.Window = ttk.Window(
            themename="flatly",
            title=f"{APP_NAME} v{APP_VERSION}",
            size=(
                self._prefs.get("window_width", 1280),
                self._prefs.get("window_height", 800),
            ),
            minsize=(1024, 680),
            resizable=(True, True),
        )

        # 4. 恢复窗口状态
        self._restore_window_state()

        # 5. 应用自定义主题
        apply_theme(self.root)

        # 6. 共享数据（当前编辑的订单）
        self._current_order_data: dict[str, Any] = {}
        self._current_order: OrderData | None = None

        # 7. 页面缓存
        self._pages: dict[str, PageBase] = {}
        self._current_page_name: str = ""

        # 8. 脏标记（未保存数据保护）
        self._is_dirty: bool = False

        # 9. 窗口状态保存防抖
        self._save_state_timer: str | None = None

        # 10. 草稿服务（自动保存/恢复）
        self._draft_service = self._init_draft_service()

        # 11. 构建 UI
        self._setup_ui()

        # 12. 绑定窗口事件
        self._bind_window_events()

        # 13. 检查未完成的草稿（延迟到主循环启动后执行）
        self.root.after(200, self._check_draft_on_startup)

        logger.info("GUI 主窗口初始化完成")

    # ==================== 偏好设置 ====================

    @staticmethod
    def _init_preferences() -> object:
        """延迟导入偏好设置服务，避免启动时的循环依赖."""
        from src.gui.services.preferences_service import PreferencesService
        return PreferencesService()

    @staticmethod
    def _init_draft_service() -> object:
        """延迟导入草稿服务."""
        from src.gui.services.draft_service import DraftService
        return DraftService()

    # ==================== DPI 感知 ====================

    @staticmethod
    def _activate_dpi_awareness() -> None:
        """激活 Windows DPI 感知，避免高分屏下界面模糊."""
        if sys.platform != "win32":
            return
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            logger.info("DPI 感知已激活")
        except Exception:
            logger.warning(
                "[警告]: DPI 感知激活失败\n"
                "[原因]: 当前 Windows 版本可能不支持 SetProcessDpiAwareness\n"
                "[排查]: 如界面模糊，请在 Windows 显示设置中调整缩放比例"
            )

    # ==================== 窗口状态 ====================

    def _restore_window_state(self) -> None:
        """恢复上次关闭时的窗口状态."""
        x = self._prefs.get("window_x", -1)
        y = self._prefs.get("window_y", -1)
        is_maximized = self._prefs.get("is_maximized", False)

        if x >= 0 and y >= 0:
            try:
                self.root.geometry(f"+{x}+{y}")
            except Exception:
                self._center_window()
        else:
            self._center_window()

        if is_maximized:
            try:
                self.root.state("zoomed")
            except Exception:
                pass

    def _center_window(self) -> None:
        """将窗口居中显示."""
        self.root.update_idletasks()
        w: int = self.root.winfo_width()
        h: int = self.root.winfo_height()
        sw: int = self.root.winfo_screenwidth()
        sh: int = self.root.winfo_screenheight()
        x: int = (sw - w) // 2
        y: int = (sh - h) // 2
        self.root.geometry(f"+{x}+{y}")

    def _bind_window_events(self) -> None:
        """绑定窗口大小/位置变化和关闭事件."""
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.root.bind("<Configure>", self._on_window_configure)
        # 绑定最大化/还原事件（Windows 特有）
        self.root.bind("<Unmap>", lambda e: None)
        self.root.bind("<Map>", lambda e: None)

    def _on_window_configure(self, event: object) -> None:
        """窗口大小/位置变化时延迟保存状态."""
        # 仅响应根窗口事件
        if event.widget != self.root:
            return
        # 防抖：500ms 内多次触发只保存一次
        if self._save_state_timer is not None:
            self.root.after_cancel(self._save_state_timer)
        self._save_state_timer = self.root.after(500, self._save_window_state)

    def _save_window_state(self) -> None:
        """保存当前窗口状态到偏好设置."""
        self._save_state_timer = None
        try:
            # 最大化时不保存尺寸和位置
            if self.root.state() == "zoomed":
                self._prefs.set("is_maximized", True)
            else:
                self._prefs.set("is_maximized", False)
                self._prefs.set("window_width", self.root.winfo_width())
                self._prefs.set("window_height", self.root.winfo_height())
                self._prefs.set("window_x", self.root.winfo_x())
                self._prefs.set("window_y", self.root.winfo_y())
            self._prefs.save()
        except Exception as e:
            logger.warning("[警告]: 窗口状态保存失败: %s", e)

    # ==================== 关闭确认 ====================

    def _on_closing(self) -> None:
        """窗口关闭事件处理 — 检查未保存数据 + 自动保存草稿."""
        # 自动保存当前草稿
        self._autosave()

        if self._is_dirty:
            choice = messagebox.askyesnocancel(
                "确认退出",
                "当前订单尚未保存为模板。\n\n"
                "  [是] - 自动保存草稿后退出\n"
                "  [否] - 返回继续编辑\n"
                "  [取消] - 返回继续编辑",
            )
            if choice is True:
                pass  # 草稿已保存，直接退出
            else:
                # choice is False or None → 取消关闭
                return

        # 正常退出：删除草稿（订单已完成）
        if not self._is_dirty:
            self._draft_service.delete_draft()

        self._save_window_state()
        logger.info("用户退出应用")
        self.root.destroy()

    # ==================== 脏标记 ====================

    def set_dirty(self, value: bool = True) -> None:
        """设置数据脏标记.

        Args:
            value: True 表示有未保存数据.
        """
        self._is_dirty = value
        if value:
            self.set_status("有未保存的更改")

    # ==================== 草稿自动保存/恢复 ====================

    def _autosave(self) -> None:
        """自动保存当前编辑状态为草稿.

        仅在设置了脏标记时才触发保存，且受频率控制（5 秒最小间隔）。
        """
        if not self._is_dirty:
            return
        if not self._current_order_data:
            return

        try:
            saved = self._draft_service.save_draft(
                self._current_order_data, self._current_page_name
            )
            if saved:
                self.set_status("草稿已自动保存")
        except Exception as e:
            logger.warning("[警告]: 自动保存草稿失败: %s", e)

    def _check_draft_on_startup(self) -> None:
        """启动时检查是否存在未完成的草稿，提示用户恢复."""
        try:
            if not self._draft_service.has_draft():
                return

            draft = self._draft_service.load_draft()
            if draft is None:
                return

            updated_at = draft.get("updated_at", "未知时间")
            choice = messagebox.askyesnocancel(
                "恢复草稿",
                f"检测到未完成的订单草稿（最后更新: {updated_at}）。\n\n"
                "是否恢复？\n"
                "  [是] - 恢复草稿，继续编辑\n"
                "  [否] - 忽略并删除草稿\n"
                "  [取消] - 保留草稿，下次再决定",
            )
            if choice is True:
                self._restore_from_draft(draft)
            elif choice is False:
                self._draft_service.delete_draft()
            # choice is None → 取消，保留草稿
        except Exception as e:
            logger.warning("[警告]: 草稿检测失败: %s", e)

    def _restore_from_draft(self, draft: dict[str, Any]) -> None:
        """从草稿恢复订单数据和页面位置.

        Args:
            draft: 草稿字典，含 order_data、current_page、updated_at.
        """
        order_data = draft.get("order_data", {})
        saved_page = draft.get("current_page", "order_info")

        if order_data:
            self._current_order_data = order_data
            self._is_dirty = True
            logger.info("已从草稿恢复订单数据")

        # 导航到保存时的页面
        if saved_page and saved_page != self._current_page_name:
            self.switch_page(saved_page)
        elif saved_page and saved_page == self._current_page_name:
            # 已在目标页面，直接刷新表单
            page = self._pages.get(saved_page)
            if page is not None:
                page.on_enter()

        updated_at = draft.get("updated_at", "")
        self.set_status(f"已恢复草稿（{updated_at}）")
        messagebox.showinfo(
            "恢复成功",
            f"草稿已恢复。\n\n最后编辑: {updated_at}\n当前页面: {saved_page}",
        )

    # ==================== UI 构建 ====================

    def _setup_ui(self) -> None:
        """构建主窗口 UI：顶部标题栏 + 内容区（导航 + 工作区）+ 底部状态栏."""
        # ---- 顶部标题栏 ----
        self._header_frame = ttk.Frame(
            self.root, style="Header.TFrame", padding=(15, 10)
        )
        self._header_frame.pack(fill=X)

        ttk.Label(
            self._header_frame,
            text=APP_NAME,
            style="Header.Title.TLabel",
        ).pack(side=LEFT)

        ttk.Label(
            self._header_frame,
            text=f" v{APP_VERSION}",
            style="Header.Subtitle.TLabel",
        ).pack(side=LEFT, padx=(5, 0))

        ttk.Separator(self.root, orient=HORIZONTAL).pack(fill=X)

        # ---- 内容区（导航 + 工作区） ----
        self._main_paned = ttk.PanedWindow(self.root, orient=HORIZONTAL)
        self._main_paned.pack(fill=BOTH, expand=YES, padx=0, pady=0)

        # 左侧导航栏
        self._nav_frame = ttk.Frame(
            self._main_paned, width=NAV_PANEL_WIDTH, bootstyle="secondary"
        )
        self._main_paned.add(self._nav_frame, weight=0)
        self._setup_navigation()

        # 右侧工作区
        self._workspace_frame = ttk.Frame(self._main_paned)
        self._main_paned.add(self._workspace_frame, weight=1)

        # ---- 底部状态栏 ----
        self._status_var = ttk.StringVar(value="就绪")
        self._status_bar = ttk.Label(
            self.root,
            textvariable=self._status_var,
            style="StatusBar.TLabel",
            anchor=W,
        )
        self._status_bar.pack(side=BOTTOM, fill=X)

    def _setup_navigation(self) -> None:
        """构建左侧导航栏（无 Emoji，简洁文字风格）."""
        # 导航标题
        nav_header = ttk.Frame(self._nav_frame)
        nav_header.pack(fill=X, padx=15, pady=(20, 10))

        ttk.Label(
            nav_header,
            text="导航菜单",
            font=(self._font_name, FONT_SIZE_NAV, "bold"),
            bootstyle="inverse-secondary",
        ).pack(anchor=W)

        ttk.Separator(self._nav_frame, orient=HORIZONTAL).pack(
            fill=X, padx=10, pady=10
        )

        # 导航按钮（纯文字，无 Emoji）
        nav_items: list[tuple[str, str]] = [
            ("新建单据", "order_info"),
            ("商品明细", "line_items"),
            ("层级视图（旧）", "tree_editor"),
            ("历史模板", "template"),
            ("数据导入", "import"),
            ("客户管理", "customer"),
            ("产品库", "product"),
        ]

        self._nav_buttons: dict[str, ttk.Button] = {}

        for label, page_name in nav_items:
            btn = ttk.Button(
                self._nav_frame,
                text=label,
                bootstyle="secondary-outline",
                style="Nav.TButton",
                command=lambda pn=page_name: self.switch_page(pn),
            )
            btn.pack(fill=X, padx=12, pady=3)
            self._nav_buttons[page_name] = btn

        ttk.Separator(self._nav_frame, orient=HORIZONTAL).pack(
            fill=X, padx=10, pady=10
        )

        # 退出按钮
        ttk.Button(
            self._nav_frame,
            text="退出系统",
            bootstyle="danger-outline",
            style="Nav.TButton",
            command=self._on_closing,
        ).pack(fill=X, padx=12, pady=3, side=BOTTOM)

    # ==================== 页面切换 ====================

    def switch_page(self, page_name: str) -> None:
        """切换到指定页面.

        Args:
            page_name: 页面标识符.
        """
        if page_name == self._current_page_name:
            return

        logger.info("切换页面: %s", page_name)

        # 0. 离开前自动保存草稿
        self._autosave()

        # 1. 离开当前页面
        if self._current_page_name and self._current_page_name in self._pages:
            self._pages[self._current_page_name].on_leave()
            self._pages[self._current_page_name].destroy()

        # 2. 清除工作区
        for widget in self._workspace_frame.winfo_children():
            widget.destroy()

        # 3. 构建目标页面
        page = self._build_page(page_name)
        if page is not None:
            self._pages[page_name] = page
            page.build()
            page.on_enter()
            self._current_page_name = page_name

            # 高亮当前导航按钮
            self._highlight_nav_button(page_name)

            self.set_status(f"当前页面: {page_name}")

    def _build_page(self, page_name: str) -> PageBase | None:
        """根据页面名称构建页面实例.

        Args:
            page_name: 页面标识符.

        Returns:
            页面实例，不支持则返回 None.
        """
        if page_name == "order_info":
            return OrderInfoPage(self._workspace_frame, self)

        elif page_name == "line_items":
            return LineItemTablePage(self._workspace_frame, self)

        elif page_name == "tree_editor":
            return TreeEditorPage(self._workspace_frame, self)

        elif page_name == "generate":
            return GeneratePage(self._workspace_frame, self)

        elif page_name == "template":
            return TemplatePage(self._workspace_frame, self)

        elif page_name == "import":
            return ImportPage(self._workspace_frame, self)

        elif page_name == "customer":
            return CustomerPage(self._workspace_frame, self)

        elif page_name == "product":
            return ProductPage(self._workspace_frame, self)

        return None

    def _highlight_nav_button(self, page_name: str) -> None:
        """高亮当前选中的导航按钮.

        Args:
            page_name: 当前页面名称.
        """
        for name, btn in self._nav_buttons.items():
            if name == page_name:
                btn.configure(bootstyle="primary")
            else:
                btn.configure(bootstyle="secondary-outline")

    # ==================== 公开 API ====================

    def set_status(self, message: str) -> None:
        """设置状态栏文字.

        Args:
            message: 状态信息.
        """
        self._status_var.set(message)
        self.root.update_idletasks()

    def get_font(
        self, bold: bool = False, size: int | None = None
    ) -> tuple:
        """获取应用标准字体.

        Args:
            bold: 是否加粗.
            size: 字号.

        Returns:
            (字体名, 字号) 或 (字体名, 字号, 样式) 元组.
        """
        sz: int = size if size is not None else self._font_size
        if bold:
            return self._font_name, sz, "bold"
        return self._font_name, sz

    def get_heading_font(self) -> tuple[str, int]:
        """获取标题字体."""
        return self._heading_font

    @property
    def current_order(self) -> OrderData | None:
        """获取当前编辑的订单数据."""
        return self._current_order

    @current_order.setter
    def current_order(self, order: OrderData) -> None:
        """设置当前订单数据."""
        self._current_order = order

    @property
    def current_order_data(self) -> dict[str, Any]:
        """获取当前订单的字典数据."""
        return self._current_order_data

    @current_order_data.setter
    def current_order_data(self, data: dict[str, Any]) -> None:
        """设置当前订单的字典数据."""
        self._current_order_data = data

    @property
    def preferences(self) -> object:
        """获取偏好设置服务."""
        return self._prefs

    def run(self) -> None:
        """启动主事件循环."""
        self.switch_page("order_info")
        logger.info("GUI 主循环启动")
        self.root.mainloop()


# ==================== 模块入口 ====================

def launch_gui() -> None:
    """启动 GUI 应用（便捷函数）."""
    app = GuiApp()
    app.run()


# ========== 运行说明 ==========
# 依赖安装: pip install ttkbootstrap
# 运行命令: python main.py --gui
# 预期输出: 启动 GUI 窗口，显示顶部标题栏 + 左侧导航 + 右侧工作区 + 底部状态栏
# =============================
