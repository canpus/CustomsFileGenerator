"""页面基类模块 — 独立于 app.py，消除循环导入.

所有页面类继承此基类，不再需要从 app.py 导入 PageBase。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import ttkbootstrap as ttk

if TYPE_CHECKING:
    from src.gui.app import GuiApp


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
            app: 主应用控制器（GuiApp 实例）.
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
