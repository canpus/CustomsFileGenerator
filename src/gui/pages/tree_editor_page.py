# -*- coding: utf-8 -*-
"""托盘-纸箱-商品树状编辑器 — 阶段 9.3.

提供：
- 左侧 Treeview 显示三级结构（托盘 → 纸箱 → 商品）
- 选中节点时右侧显示对应属性表单
- 右键菜单：新增/克隆/删除 节点
- 支持批量纸箱输入（is_batch + batch_count）
- 底部操作栏：生成报关资料 / 返回上一步

子模块拆分（mixin 模式）：
- tree_ui.py     : UI 构建、Treeview、详情面板框架、右键菜单、节点选择路由
- tree_detail.py : 详情表单字段构建与保存
- tree_data.py   : 节点增删克隆、Treeview 刷新、统计更新、展开/折叠
- tree_export.py : collect_tree_data / build_order_data
- tree_events.py : 生成/导入/清空事件处理
- 本模块         : 主类定义 + 生命周期方法
"""

from __future__ import annotations

import copy
import logging
from typing import Any

import ttkbootstrap as ttk

from src.gui.page_base import PageBase
from src.gui.pages.tree_data import TreeDataMixin
from src.gui.pages.tree_detail import TreeDetailMixin
from src.gui.pages.tree_events import TreeEventsMixin
from src.gui.pages.tree_export import TreeExportMixin
from src.gui.pages.tree_ui import TreeUIMixin

logger = logging.getLogger(__name__)


class TreeEditorPage(TreeUIMixin, TreeDetailMixin, TreeDataMixin, TreeExportMixin, TreeEventsMixin, PageBase):
    """托盘-纸箱-商品树状编辑器."""

    def __init__(self, parent: ttk.Frame, app: object):
        super().__init__(parent, app)
        self._pallets: list[dict[str, Any]] = []
        self._tree: ttk.Treeview | None = None
        self._context_menu: ttk.Menu | None = None
        self._detail_vars: dict[str, Any] = {}
        self._detail_frame: ttk.Frame | None = None
        self._selected_node_id: str = ""
        self._selected_level: str = ""
        self._selected_pallet_idx: int = -1
        self._selected_carton_idx: int = -1
        self._selected_product_idx: int = -1
        self._product_seq: int = 1

    # ==================== 生命周期 ====================

    def on_enter(self) -> None:
        """进入页面时初始化."""
        if self.app.current_order is not None and not self._pallets:
            try:
                order = self.app.current_order
                self._pallets = []
                self._product_seq = 1
                for pallet in order.pallets:
                    p_data = {
                        "pallet_no": pallet.pallet_no,
                        "length_m": pallet.length_m,
                        "width_m": pallet.width_m,
                        "height_m": pallet.height_m,
                        "pallet_weight_kg": pallet.pallet_weight_kg,
                        "cartons": [],
                    }
                    for carton in pallet.cartons:
                        c_data = {
                            "carton_label": carton.carton_label,
                            "is_batch": carton.is_batch,
                            "batch_count": carton.batch_count,
                            "length_cm": carton.length_cm,
                            "width_cm": carton.width_cm,
                            "height_cm": carton.height_cm,
                            "gross_weight_kg": carton.gross_weight_kg,
                            "products": [],
                        }
                        for product in carton.products:
                            c_data["products"].append({
                                "seq_no": self._product_seq,
                                "product_name": product.product_name,
                                "specification": product.specification,
                                "hs_code": product.hs_code,
                                "declaration_elements": product.declaration_elements,
                                "unit": product.unit,
                                "qty_per_carton": product.qty_per_carton,
                                "unit_price": product.unit_price,
                                "currency": product.currency,
                                "net_weight_per_unit_kg": product.net_weight_per_unit_kg,
                                "destination_country": product.destination_country,
                            })
                            self._product_seq += 1
                        p_data["cartons"].append(c_data)
                    self._pallets.append(p_data)
                self._refresh_tree()
                self._update_stats()
            except Exception as e:
                logger.warning("[警告]: 恢复订单数据失败: %s", e)

    def on_leave(self) -> None:
        """离开页面时保存数据."""
        if self._pallets:
            self.app.current_order_data["pallets"] = copy.deepcopy(self._pallets)
