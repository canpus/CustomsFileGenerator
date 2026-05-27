# -*- coding: utf-8 -*-
"""偏好设置服务 — 窗口状态记忆与持久化.

将窗口大小/位置/最大化状态、最近使用的目录等持久化到 JSON 文件。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from config.constants import PROJECT_ROOT

logger = logging.getLogger(__name__)

# ==================== 默认偏好设置 ====================

DEFAULT_PREFERENCES: dict[str, Any] = {
    "window_width": 1280,
    "window_height": 800,
    "window_x": -1,
    "window_y": -1,
    "is_maximized": False,
    "last_output_dir": "",
    "last_import_dir": "",
}


class PreferencesService:
    """偏好设置读写服务.

    使用项目 data/ 目录下的 preferences.json 文件持久化用户偏好。
    线程不安全，仅限主线程使用。

    Usage:
        prefs = PreferencesService()
        width = prefs.get("window_width", 1280)
        prefs.set("window_width", 1400)
        prefs.save()
    """

    def __init__(self) -> None:
        """初始化偏好设置服务."""
        self._file: Path = PROJECT_ROOT / "data" / "preferences.json"
        self._data: dict[str, Any] = self._load()

    # ==================== 文件 I/O ====================

    def _load(self) -> dict[str, Any]:
        """从文件加载偏好设置.

        Returns:
            偏好设置字典，若文件不存在或损坏则返回默认值.
        """
        if not self._file.exists():
            logger.info("偏好设置文件不存在，使用默认值: %s", self._file)
            return dict(DEFAULT_PREFERENCES)

        try:
            with open(self._file, "r", encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)
            # 合并默认值：补充缺失的键
            merged: dict[str, Any] = dict(DEFAULT_PREFERENCES)
            merged.update(data)
            logger.info("偏好设置已加载: %s", self._file)
            return merged
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(
                "[警告]: 偏好设置文件读取失败\n"
                "[原因]: %s\n"
                "[排查]: 文件可能损坏，将使用默认值并覆盖保存",
                e,
            )
            return dict(DEFAULT_PREFERENCES)

    def save(self) -> None:
        """将当前偏好设置写入文件."""
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            logger.info("偏好设置已保存: %s", self._file)
        except OSError as e:
            logger.warning(
                "[警告]: 偏好设置保存失败\n"
                "[原因]: %s\n"
                "[排查]: 请检查磁盘权限和目录是否存在",
                e,
            )

    # ==================== 存取接口 ====================

    def get(self, key: str, default: Any = None) -> Any:
        """读取偏好设置值.

        Args:
            key: 配置键名.
            default: 默认值.

        Returns:
            配置值或默认值.
        """
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """设置偏好设置值（不自动保存）.

        Args:
            key: 配置键名.
            value: 配置值.
        """
        self._data[key] = value

    def get_all(self) -> dict[str, Any]:
        """获取全部偏好设置（只读副本）."""
        return dict(self._data)
