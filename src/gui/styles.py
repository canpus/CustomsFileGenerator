"""GUI 统一样式定义.

提供全局颜色、字体、间距常量，以及 ttkbootstrap 主题自定义配置。
所有页面应引用此模块中的常量，确保视觉风格一致。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import ttkbootstrap as ttk

# ==================== 字体 ====================

FONT_FAMILY: str = "Microsoft YaHei"
FONT_SIZE_NORMAL: int = 10
FONT_SIZE_TITLE: int = 14
FONT_SIZE_SMALL: int = 9
FONT_SIZE_NAV: int = 11

# ==================== 间距 ====================

PADDING_X: int = 10
PADDING_Y: int = 8
MARGIN: int = 5

# ==================== 颜色 ====================

# 背景与表面
COLOR_BG: str = "#F5F5F5"
COLOR_SURFACE: str = "#FFFFFF"

# 主色与文字
COLOR_PRIMARY: str = "#1565C0"
COLOR_TEXT: str = "#212121"
COLOR_TEXT_SECONDARY: str = "#757575"

# 边框与分隔
COLOR_BORDER: str = "#E0E0E0"

# 语义色
COLOR_ERROR: str = "#D32F2F"
COLOR_SUCCESS: str = "#388E3C"
COLOR_WARNING: str = "#F57C00"

# ==================== 组件尺寸 ====================

BUTTON_WIDTH: int = 100
BUTTON_HEIGHT: int = 32
NAV_PANEL_WIDTH: int = 200


def apply_theme(root: ttk.Window) -> None:
    """应用全局主题样式配置.

    在 ttkbootstrap 主题基础上，注册自定义样式变体。
    所有 ttk 组件通过 bootstyle 参数使用 ttkbootstrap 内建样式；
    此函数仅用于注册需要自定义外观的组件。

    Args:
        root: ttkbootstrap.Window 实例.
    """
    style = root.style

    # 自定义 Header 区域样式
    style.configure("Header.TFrame", background=COLOR_SURFACE, relief="flat")
    style.configure("Header.TLabel", background=COLOR_SURFACE, foreground=COLOR_TEXT)
    style.configure(
        "Header.Title.TLabel",
        background=COLOR_SURFACE,
        foreground=COLOR_PRIMARY,
        font=(FONT_FAMILY, FONT_SIZE_TITLE, "bold"),
    )
    style.configure(
        "Header.Subtitle.TLabel",
        background=COLOR_SURFACE,
        foreground=COLOR_TEXT_SECONDARY,
        font=(FONT_FAMILY, FONT_SIZE_SMALL),
    )

    # 自定义状态栏样式
    style.configure("StatusBar.TFrame", background=COLOR_BG, relief="flat")
    style.configure(
        "StatusBar.TLabel",
        background=COLOR_BG,
        foreground=COLOR_TEXT_SECONDARY,
        font=(FONT_FAMILY, FONT_SIZE_SMALL),
        padding=(10, 3),
    )

    # 自定义导航按钮组样式（覆盖默认按钮内边距）
    style.configure("Nav.TButton", font=(FONT_FAMILY, FONT_SIZE_NAV), padding=(15, 8))
