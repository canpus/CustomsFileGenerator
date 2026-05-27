# -*- coding: utf-8 -*-
"""GUI 主应用窗口 — 阶段 9.1.

基于 ttkbootstrap（Flatly 主题），提供：
- DPI 感知激活
- 字体回退池（Microsoft YaHei → Segoe UI → TkDefaultFont）
- 左侧导航栏（新建单据 / 历史模板 / 客户管理 / 产品库）
- 右侧工作区（根据导航切换页面）
"""

from __future__ import annotations

import ctypes
import logging
import sys
from pathlib import Path
from tkinter import font as tkfont
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.models.order_data import OrderData

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from config.constants import APP_NAME, APP_VERSION

logger = logging.getLogger(__name__)

# ==================== 字体回退池 ====================

_FONT_CANDIDATES: list[str] = [
    "Microsoft YaHei",
    "Segoe UI",
    "TkDefaultFont",
]


def _get_available_font(font_size: int = 11) -> tuple[str, int]:
    """查找第一个可用的字体.

    注意：此函数需要 tk 根窗口已创建才能调用 font.families()。
    在 GuiApp.__init__ 中 ttk.Window 创建之后调用是安全的。

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
        # 无显示器环境（如 CI/测试），使用默认字体
        pass
    return "TkDefaultFont", font_size


# ==================== 页面基类 ====================


class PageBase:
    """所有页面的基类.

    每个页面负责构建自己的 UI，处理数据输入/展示。
    页面之间通过 App 控制器（GuiApp）通信。

    Attributes:
        parent: 父级 Widget（右侧工作区 Frame）.
        app: GuiApp 主控制器实例.
    """

    def __init__(self, parent: ttk.Frame, app: GuiApp):
        """初始化页面.

        Args:
            parent: 父级容器.
            app: 主应用控制器.
        """
        self.parent: ttk.Frame = parent
        self.app: GuiApp = app
        self.frame: ttk.Frame | None = None

    def build(self) -> None:
        """构建页面 UI（子类必须实现）."""
        raise NotImplementedError("子类必须实现 build() 方法")

    def destroy(self) -> None:
        """销毁页面 UI."""
        if self.frame is not None:
            self.frame.destroy()
            self.frame = None

    def on_enter(self) -> None:
        """页面被切换到时调用（可选覆盖）."""
        pass

    def on_leave(self) -> None:
        """页面被切换走时调用（可选覆盖）."""
        pass


# ==================== GuiApp 主应用 ====================


class GuiApp:
    """GUI 主应用控制器.

    管理主窗口、导航栏、页面切换、共享订单数据。

    使用方式：
        app = GuiApp()
        app.run()
    """

    def __init__(self):
        """初始化主窗口."""
        # 1. DPI 感知（Windows）
        self._activate_dpi_awareness()

        # 2. 字体
        self._font_name, self._font_size = _get_available_font(11)
        self._font_name_bold = self._font_name
        self._heading_font = (self._font_name, 14)
        self._subheading_font = (self._font_name, 11)
        self._nav_font = (self._font_name, 12)

        # 3. 创建主窗口
        self.root: ttk.Window = ttk.Window(
            themename="flatly",
            title=f"{APP_NAME} v{APP_VERSION}",
            size=(1280, 800),
            minsize=(1024, 680),
            resizable=(True, True),
        )

        # 居中窗口
        self._center_window()

        # 4. 共享数据（当前编辑的订单）
        self._current_order_data: dict[str, Any] = {}
        self._current_order: OrderData | None = None  # OrderData 对象

        # 5. 页面缓存
        self._pages: dict[str, PageBase] = {}
        self._current_page_name: str = ""

        # 6. 构建 UI
        self._setup_ui()

        logger.info("GUI 主窗口初始化完成")

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

    # ==================== UI 构建 ====================

    def _setup_ui(self) -> None:
        """构建主窗口 UI：左侧导航 + 右侧工作区."""
        # ---- 主容器（水平布局） ----
        self._main_paned = ttk.PanedWindow(self.root, orient=HORIZONTAL)
        self._main_paned.pack(fill=BOTH, expand=YES, padx=0, pady=0)

        # ---- 左侧导航栏 ----
        self._nav_frame = ttk.Frame(self._main_paned, width=200, bootstyle="secondary")
        self._main_paned.add(self._nav_frame, weight=0)

        self._setup_navigation()

        # ---- 右侧工作区 ----
        self._workspace_frame = ttk.Frame(self._main_paned)
        self._main_paned.add(self._workspace_frame, weight=1)

        # ---- 状态栏 ----
        self._status_var = ttk.StringVar(value="就绪")
        self._status_bar = ttk.Label(
            self.root,
            textvariable=self._status_var,
            relief=SUNKEN,
            anchor=W,
            padding=(10, 2),
            bootstyle="secondary",
        )
        self._status_bar.pack(side=BOTTOM, fill=X)

    def _setup_navigation(self) -> None:
        """构建左侧导航栏."""
        # 应用标题
        title_frame = ttk.Frame(self._nav_frame)
        title_frame.pack(fill=X, padx=15, pady=(20, 10))

        ttk.Label(
            title_frame,
            text=APP_NAME,
            font=(self._font_name, 13, "bold"),
            bootstyle="inverse-secondary",
            wraplength=170,
        ).pack(anchor=W)

        ttk.Label(
            title_frame,
            text=f"v{APP_VERSION}",
            font=(self._font_name, 9),
            bootstyle="inverse-secondary",
        ).pack(anchor=W)

        ttk.Separator(self._nav_frame, orient=HORIZONTAL).pack(fill=X, padx=10, pady=10)

        # 导航按钮
        nav_items: list[tuple[str, str, str]] = [
            ("新建单据", "📋", "order_info"),
            ("历史模板", "📁", "template"),
            ("客户管理", "👤", "customer"),
            ("产品库", "📦", "product"),
        ]

        self._nav_buttons: dict[str, ttk.Button] = {}

        for label, icon, page_name in nav_items:
            btn = ttk.Button(
                self._nav_frame,
                text=f"  {icon}  {label}",
                bootstyle="secondary-outline",
                command=lambda pn=page_name: self.switch_page(pn),
            )
            btn.pack(fill=X, padx=12, pady=3, ipady=6)
            self._nav_buttons[page_name] = btn

        ttk.Separator(self._nav_frame, orient=HORIZONTAL).pack(fill=X, padx=10, pady=10)

        # 退出按钮
        ttk.Button(
            self._nav_frame,
            text="  🚪  退出",
            bootstyle="danger-outline",
            command=self.root.destroy,
        ).pack(fill=X, padx=12, pady=3, ipady=6, side=BOTTOM)

    # ==================== 页面切换 ====================

    def switch_page(self, page_name: str) -> None:
        """切换到指定页面.

        Args:
            page_name: 页面标识符（order_info / tree_editor / template / customer / product）.
        """
        if page_name == self._current_page_name:
            return

        logger.info("切换页面: %s", page_name)

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
        # 延迟导入，避免循环依赖
        if page_name == "order_info":
            from src.gui.pages.order_info_page import OrderInfoPage
            return OrderInfoPage(self._workspace_frame, self)

        elif page_name == "tree_editor":
            from src.gui.pages.tree_editor_page import TreeEditorPage
            return TreeEditorPage(self._workspace_frame, self)

        elif page_name == "generate":
            from src.gui.pages.generate_page import GeneratePage
            return GeneratePage(self._workspace_frame, self)

        elif page_name == "template":
            from src.gui.pages.template_page import TemplatePage
            return TemplatePage(self._workspace_frame, self)

        elif page_name == "customer":
            # 客户管理页面（简化实现：复用订单录入页面的客户部分）
            from src.gui.pages.order_info_page import OrderInfoPage
            return OrderInfoPage(self._workspace_frame, self)

        elif page_name == "product":
            # 产品库页面（简化实现：显示为树状编辑器只读模式）
            from src.gui.pages.tree_editor_page import TreeEditorPage
            return TreeEditorPage(self._workspace_frame, self)

        elif page_name == "import":
            from src.gui.pages.import_page import ImportPage
            return ImportPage(self._workspace_frame, self)

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

    def get_font(self, bold: bool = False, size: int | None = None) -> tuple[str, int, str]:
        """获取应用标准字体.

        Args:
            bold: 是否加粗.
            size: 字号，默认使用全局字号.

        Returns:
            (字体名, 字号, 样式) 元组.
        """
        sz: int = size if size is not None else self._font_size
        style: str = "bold" if bold else ""
        if style:
            return self._font_name, sz, style
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

    def run(self) -> None:
        """启动主事件循环."""
        # 默认打开新建单据页面
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
# 预期输出: 启动 GUI 窗口，显示左侧导航 + 右侧工作区
# =============================
