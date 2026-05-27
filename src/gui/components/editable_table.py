# -*- coding: utf-8 -*-
"""可编辑表格组件 — 基于 ttk.Treeview + Entry 叠加编辑.

提供：
- 双击单元格进入编辑模式
- Tab/Enter 移动编辑焦点
- 右键菜单（插入行、删除行、复制行、粘贴行）
- 列头排序
- 多选 + 批量填充列
- 数据变更回调
"""

from __future__ import annotations

import copy
import logging
from tkinter import (
    END,
    HORIZONTAL,
    LEFT,
    RIGHT,
    VERTICAL,
    Menu,
    StringVar,
    messagebox,
)
from typing import Any, Callable

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

logger = logging.getLogger(__name__)

# ==================== 列定义类型 ====================

ColumnDef = tuple[str, str, int, bool]  # (key, display_name, width_px, editable)


class EditableTable(ttk.Frame):
    """可编辑表格组件.

    基于 ttk.Treeview，叠加 Entry 实现单元格编辑。
    支持右键菜单、批量操作、列排序、剪贴板操作。

    Attributes:
        columns_def: 列定义列表.
        _data: 行数据列表（list[dict]）.
        _tree: 内部 Treeview 控件.
        _change_callback: 数据变更回调函数.
    """

    def __init__(
        self,
        parent: ttk.Frame,
        columns_def: list[ColumnDef],
        height: int = 15,
        on_change: Callable[[], None] | None = None,
    ):
        """初始化可编辑表格.

        Args:
            parent: 父级容器.
            columns_def: 列定义列表，每项为 (key, display_name, width, editable).
            height: 可见行数.
            on_change: 数据变更时回调.
        """
        super().__init__(parent)
        self.columns_def: list[ColumnDef] = columns_def
        self._data: list[dict[str, Any]] = []
        self._change_callback: Callable[[], None] | None = on_change
        self._selected_rows: list[int] = []

        # 编辑状态
        self._edit_entry: ttk.Entry | None = None
        self._edit_row: int = -1
        self._edit_col: int = -1

        # 剪贴板
        self._clipboard: list[dict[str, Any]] = []

        # 排序状态
        self._sort_col: str = ""
        self._sort_reverse: bool = False

        # 构建 UI
        self._build_ui()

    # ==================== UI 构建 ====================

    def _build_ui(self) -> None:
        """构建表格 + 滚动条."""
        # 列 key 列表（Treeview 用）
        col_keys: list[str] = [col[0] for col in self.columns_def]

        # Treeview
        self._tree = ttk.Treeview(
            self,
            columns=col_keys,
            show="headings",
            height=15,
            selectmode="extended",
        )

        # 配置列
        for key, display_name, width, _editable in self.columns_def:
            self._tree.heading(
                key,
                text=display_name,
                command=lambda c=key: self._on_sort_column(c),
            )
            self._tree.column(key, width=width, minwidth=40, stretch=True)

        # 滚动条
        vsb = ttk.Scrollbar(self, orient=VERTICAL, command=self._tree.yview)
        hsb = ttk.Scrollbar(self, orient=HORIZONTAL, command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        # 布局
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        # 事件绑定
        self._tree.bind("<Double-1>", self._on_double_click)
        self._tree.bind("<Button-3>", self._on_right_click)
        self._tree.bind("<ButtonRelease-1>", self._on_selection_change)
        self._tree.bind("<Delete>", lambda e: self.delete_selected_rows())
        self._tree.bind("<Control-c>", lambda e: self.copy_selected_rows())
        self._tree.bind("<Control-v>", lambda e: self.paste_rows())

        logger.info("EditableTable 初始化完成，%d 列", len(self.columns_def))

    # ==================== 数据读写 ====================

    def get_all_rows(self) -> list[dict[str, Any]]:
        """获取所有行数据（深拷贝）."""
        return copy.deepcopy(self._data)

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        """设置所有行数据并刷新显示.

        Args:
            rows: 行数据列表.
        """
        self._data = copy.deepcopy(rows)
        self._refresh_display()
        self._notify_change()

    def get_selected_row_indices(self) -> list[int]:
        """获取选中行的索引列表（按 tree 选中顺序）."""
        selection = self._tree.selection()
        indices: list[int] = []
        for iid in selection:
            idx = self._iid_to_index(iid)
            if idx >= 0:
                indices.append(idx)
        return indices

    def get_selected_rows(self) -> list[dict[str, Any]]:
        """获取选中行的数据（深拷贝）."""
        return [copy.deepcopy(self._data[i]) for i in self.get_selected_row_indices()]

    def add_row(self, data: dict[str, Any] | None = None, index: int = -1) -> None:
        """添加一行.

        Args:
            data: 行数据，None 则使用空字典.
            index: 插入位置，-1 表示末尾.
        """
        row: dict[str, Any] = copy.deepcopy(data) if data else self._empty_row()
        if index < 0 or index >= len(self._data):
            self._data.append(row)
        else:
            self._data.insert(index, row)
        self._refresh_display()
        self._notify_change()
        logger.info("已添加行，当前共 %d 行", len(self._data))

    def delete_rows(self, indices: list[int]) -> None:
        """删除指定索引的行.

        Args:
            indices: 行索引列表（从大到小排序后删除，避免索引偏移）.
        """
        for idx in sorted(indices, reverse=True):
            if 0 <= idx < len(self._data):
                del self._data[idx]
        self._refresh_display()
        self._notify_change()
        logger.info("已删除 %d 行，当前共 %d 行", len(indices), len(self._data))

    def delete_selected_rows(self) -> None:
        """删除当前选中的行."""
        indices = self.get_selected_row_indices()
        if not indices:
            return
        self.delete_rows(indices)

    def update_cell(self, row_idx: int, col_key: str, value: Any) -> None:
        """更新指定单元格.

        Args:
            row_idx: 行索引.
            col_key: 列 key.
            value: 新值.
        """
        if 0 <= row_idx < len(self._data):
            self._data[row_idx][col_key] = value
            self._refresh_display()
            self._notify_change()

    def update_cells_batch(
        self, row_indices: list[int], col_key: str, value: Any
    ) -> None:
        """批量更新多行同一列的值.

        Args:
            row_indices: 行索引列表.
            col_key: 列 key.
            value: 新值.
        """
        for idx in row_indices:
            if 0 <= idx < len(self._data):
                self._data[idx][col_key] = value
        self._refresh_display()
        self._notify_change()

    def clear_all(self) -> None:
        """清空所有数据."""
        self._data.clear()
        self._clipboard.clear()
        self._refresh_display()
        self._notify_change()

    # ==================== 剪贴板操作 ====================

    def copy_selected_rows(self) -> None:
        """复制选中的行到内部剪贴板."""
        selected = self.get_selected_rows()
        if selected:
            self._clipboard = selected
            logger.info("已复制 %d 行到剪贴板", len(selected))

    def paste_rows(self) -> None:
        """从剪贴板粘贴行到末尾."""
        if not self._clipboard:
            return
        for row in self._clipboard:
            self._data.append(copy.deepcopy(row))
        self._refresh_display()
        self._notify_change()
        logger.info("已粘贴 %d 行", len(self._clipboard))

    # ==================== 右键菜单 ====================

    def _on_right_click(self, event: object) -> None:
        """右键菜单."""
        # 先选中右键所在行
        row_iid = self._tree.identify_row(event.y)
        if row_iid:
            if row_iid not in self._tree.selection():
                self._tree.selection_set(row_iid)

        menu = Menu(self, tearoff=0)
        menu.add_command(label="插入行 (Insert)", command=lambda: self._on_insert_row())
        menu.add_command(
            label="删除选中行 (Delete)", command=self.delete_selected_rows
        )
        menu.add_separator()
        menu.add_command(label="复制行 (Ctrl+C)", command=self.copy_selected_rows)
        menu.add_command(label="粘贴行 (Ctrl+V)", command=self.paste_rows)
        menu.add_separator()

        # 批量填充子菜单
        selected = self.get_selected_row_indices()
        if len(selected) >= 2:
            fill_menu = Menu(menu, tearoff=0)
            col_key = self._tree.identify_column(event.x)
            col_idx = int(col_key.replace("#", "")) - 1
            if 0 <= col_idx < len(self.columns_def):
                target_key = self.columns_def[col_idx][0]
                fill_menu.add_command(
                    label=f"用首行值填充此列",
                    command=lambda: self._bulk_fill_column(selected, target_key),
                )
            menu.add_cascade(label="批量填充", menu=fill_menu)

        menu.add_separator()
        menu.add_command(label="清空表格", command=self._on_clear_all)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _on_insert_row(self) -> None:
        """在当前选中行之后插入新行."""
        selected = self.get_selected_row_indices()
        if selected:
            insert_idx = max(selected) + 1
        else:
            insert_idx = len(self._data)
        self.add_row(index=insert_idx)

    def _on_clear_all(self) -> None:
        """清空表格确认."""
        if not self._data:
            return
        if messagebox.askyesno("确认清空", f"确定要清空全部 {len(self._data)} 行数据吗？"):
            self.clear_all()

    def _bulk_fill_column(self, row_indices: list[int], col_key: str) -> None:
        """批量填充：用首行的值填充所有选中行."""
        if not row_indices:
            return
        value = self._data[row_indices[0]].get(col_key, "")
        self.update_cells_batch(row_indices, col_key, value)

    # ==================== 单元格编辑 ====================

    def _on_double_click(self, event: object) -> None:
        """双击开始编辑."""
        row_iid = self._tree.identify_row(event.y)
        col_id = self._tree.identify_column(event.x)
        if not row_iid:
            return

        col_idx = int(col_id.replace("#", "")) - 1
        if col_idx < 0 or col_idx >= len(self.columns_def):
            return

        _key, _name, _width, editable = self.columns_def[col_idx]
        if not editable:
            return

        row_idx = self._iid_to_index(row_iid)
        if row_idx < 0:
            return

        self._start_edit(row_idx, col_idx, row_iid)

    def _start_edit(self, row_idx: int, col_idx: int, row_iid: str) -> None:
        """开始编辑指定单元格."""
        self._cancel_edit()

        col_key = self.columns_def[col_idx][0]
        bbox = self._tree.bbox(row_iid, column=f"#{col_idx + 1}")
        if not bbox:
            return

        x, y, w, h = bbox
        current_value = self._data[row_idx].get(col_key, "")

        self._edit_entry = ttk.Entry(self)
        self._edit_entry.place(x=x, y=y, width=w, height=h)
        self._edit_entry.insert(0, str(current_value))
        self._edit_entry.select_range(0, END)
        self._edit_entry.focus_set()

        self._edit_row = row_idx
        self._edit_col = col_idx

        # 编辑完成事件
        self._edit_entry.bind("<Return>", lambda e: self._commit_edit_and_next())
        self._edit_entry.bind("<Tab>", lambda e: self._commit_edit_and_next())
        self._edit_entry.bind("<Shift-Tab>", lambda e: self._commit_edit_and_prev())
        self._edit_entry.bind("<Escape>", lambda e: self._cancel_edit())
        self._edit_entry.bind("<FocusOut>", lambda e: self._commit_edit())

    def _commit_edit(self) -> None:
        """提交编辑内容."""
        if self._edit_entry is None:
            return
        new_value = self._edit_entry.get()
        if 0 <= self._edit_row < len(self._data) and 0 <= self._edit_col < len(
            self.columns_def
        ):
            col_key = self.columns_def[self._edit_col][0]
            old_value = self._data[self._edit_row].get(col_key, "")
            if str(old_value) != new_value:
                self._data[self._edit_row][col_key] = self._try_convert_value(
                    col_key, new_value
                )
                self._refresh_display()
                self._notify_change()
        self._cancel_edit()

    def _commit_edit_and_next(self) -> None:
        """提交编辑并移动到下一个单元格."""
        self._commit_edit()
        self._move_edit_focus(1)

    def _commit_edit_and_prev(self) -> None:
        """提交编辑并移动到上一个单元格."""
        self._commit_edit()
        self._move_edit_focus(-1)

    def _cancel_edit(self) -> None:
        """取消编辑."""
        if self._edit_entry is not None:
            self._edit_entry.destroy()
            self._edit_entry = None
        self._edit_row = -1
        self._edit_col = -1

    def _move_edit_focus(self, direction: int) -> None:
        """移动编辑焦点.

        Args:
            direction: 1=下一个, -1=上一个.
        """
        if self._edit_row < 0:
            return

        num_rows = len(self._data)
        num_cols = len(self.columns_def)

        # 计算下一个可编辑单元格
        flat_idx = self._edit_row * num_cols + self._edit_col
        max_flat = num_rows * num_cols

        for _ in range(max_flat):
            flat_idx += direction
            if flat_idx < 0:
                flat_idx = max_flat - 1
            if flat_idx >= max_flat:
                flat_idx = 0

            new_row = flat_idx // num_cols
            new_col = flat_idx % num_cols
            _key, _name, _width, editable = self.columns_def[new_col]

            if editable and 0 <= new_row < num_rows:
                # 定位到新单元格
                children = self._tree.get_children()
                if new_row < len(children):
                    self._tree.selection_set(children[new_row])
                    self._tree.see(children[new_row])
                    self._start_edit(new_row, new_col, children[new_row])
                return

    # ==================== 排序 ====================

    def _on_sort_column(self, col_key: str) -> None:
        """点击列头排序."""
        if self._sort_col == col_key:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_col = col_key
            self._sort_reverse = False

        try:
            self._data.sort(
                key=lambda r: self._sort_key(r.get(col_key, "")),
                reverse=self._sort_reverse,
            )
        except TypeError:
            # 混合类型时不排序
            return

        self._refresh_display()
        logger.info("按列 %s 排序, reverse=%s", col_key, self._sort_reverse)

    @staticmethod
    def _sort_key(value: Any) -> Any:
        """排序键：尝试数字比较."""
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return value.lower()
        return str(value).lower()

    # ==================== 事件处理 ====================

    def _on_selection_change(self, event: object) -> None:
        """选择变更事件."""
        self._selected_rows = self.get_selected_row_indices()

    # ==================== 显示刷新 ====================

    def _refresh_display(self) -> None:
        """根据 _data 重建 Treeview 显示."""
        children = self._tree.get_children()
        # 删除多余行
        if len(children) > len(self._data):
            for iid in children[len(self._data):]:
                self._tree.delete(iid)

        col_keys = [col[0] for col in self.columns_def]

        for i, row in enumerate(self._data):
            values = [str(row.get(key, "")) for key in col_keys]
            if i < len(children):
                self._tree.item(children[i], values=values)
            else:
                self._tree.insert("", END, iid=f"row_{i}", values=values)

    # ==================== 辅助方法 ====================

    def _empty_row(self) -> dict[str, Any]:
        """创建空行数据."""
        return {col[0]: "" for col in self.columns_def}

    @staticmethod
    def _iid_to_index(iid: str) -> int:
        """将 Treeview item ID 转为行索引."""
        try:
            return int(iid.replace("row_", ""))
        except (ValueError, AttributeError):
            return -1

    def _try_convert_value(self, col_key: str, value: str) -> Any:
        """尝试将字符串值转为数字类型."""
        # 根据列名判断是否需要数字
        numeric_keys = {
            "batch_count", "length_cm", "width_cm", "height_cm",
            "gross_weight_kg", "qty_per_carton", "unit_price",
            "net_weight_per_unit_kg", "pallet_no",
        }
        if col_key in numeric_keys:
            try:
                return float(value) if "." in value else int(value)
            except ValueError:
                return value
        return value

    def _notify_change(self) -> None:
        """触发数据变更回调."""
        if self._change_callback:
            self._change_callback()

    # ==================== 公开属性 ====================

    @property
    def tree(self) -> ttk.Treeview:
        """获取内部 Treeview 控件."""
        return self._tree

    @property
    def row_count(self) -> int:
        """获取行数."""
        return len(self._data)
