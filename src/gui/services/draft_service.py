# -*- coding: utf-8 -*-
"""草稿服务 — 订单编辑状态的自动保存与恢复.

将当前订单数据和页面位置持久化为 JSON 文件，支持：
- 自动保存（页面切换/关闭时触发）
- 启动时检测并恢复未完成草稿
- 草稿的生命周期管理（保存/加载/删除）
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from config.constants import PROJECT_ROOT

logger = logging.getLogger(__name__)

# 草稿文件路径
DRAFT_DIR: Path = PROJECT_ROOT / "data" / "drafts"
DRAFT_FILE: Path = DRAFT_DIR / "autosave.json"

# 自动保存最小间隔（秒）
MIN_AUTOSAVE_INTERVAL: float = 5.0


class DraftService:
    """草稿自动保存与恢复服务.

    线程不安全，仅限主线程使用。

    Usage:
        service = DraftService()
        service.save_draft(order_data, "line_items")
        if service.has_draft():
            draft = service.load_draft()
        service.delete_draft()
    """

    def __init__(self) -> None:
        """初始化草稿服务."""
        self._last_save_time: float = 0.0

    # ==================== 文件 I/O ====================

    def _ensure_dir(self) -> None:
        """确保草稿目录存在."""
        try:
            DRAFT_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning(
                "[警告]: 无法创建草稿目录 %s\n[原因]: %s\n[排查]: 检查磁盘权限",
                DRAFT_DIR, e,
            )

    def save_draft(self, order_data: dict[str, Any], current_page: str) -> bool:
        """保存草稿.

        Args:
            order_data: 当前订单数据字典.
            current_page: 当前页面标识符.

        Returns:
            是否保存成功.
        """
        # 频率控制
        now: float = time.time()
        if now - self._last_save_time < MIN_AUTOSAVE_INTERVAL:
            return False
        self._last_save_time = now

        self._ensure_dir()

        draft: dict[str, Any] = {
            "order_data": order_data,
            "current_page": current_page,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
        }

        try:
            with open(DRAFT_FILE, "w", encoding="utf-8") as f:
                json.dump(draft, f, ensure_ascii=False, indent=2)
            logger.info("草稿已保存: 页面=%s, 时间=%s", current_page, draft["updated_at"])
            return True
        except OSError as e:
            logger.warning(
                "[警告]: 草稿保存失败\n[原因]: %s\n[排查]: 检查磁盘空间和目录权限", e
            )
            return False

    def load_draft(self) -> dict[str, Any] | None:
        """加载最新草稿.

        Returns:
            草稿字典，不存在或损坏时返回 None.
        """
        if not DRAFT_FILE.exists():
            return None

        try:
            with open(DRAFT_FILE, "r", encoding="utf-8") as f:
                draft: dict[str, Any] = json.load(f)

            required_keys = {"order_data", "current_page", "updated_at"}
            if not required_keys.issubset(draft.keys()):
                logger.warning("[警告]: 草稿文件格式不完整，忽略")
                return None

            logger.info("草稿已加载: 页面=%s, 时间=%s",
                        draft.get("current_page"), draft.get("updated_at"))
            return draft
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(
                "[警告]: 草稿文件读取失败\n[原因]: %s\n[排查]: 文件可能损坏", e
            )
            return None

    def delete_draft(self) -> bool:
        """删除草稿文件.

        Returns:
            是否删除成功.
        """
        if not DRAFT_FILE.exists():
            return True

        try:
            DRAFT_FILE.unlink()
            logger.info("草稿已删除")
            return True
        except OSError as e:
            logger.warning(
                "[警告]: 草稿文件删除失败\n[原因]: %s\n[排查]: 请手动删除 %s", e, DRAFT_FILE
            )
            return False

    def has_draft(self) -> bool:
        """检查是否存在未完成的草稿.

        Returns:
            True 表示存在草稿文件.
        """
        return DRAFT_FILE.exists()
