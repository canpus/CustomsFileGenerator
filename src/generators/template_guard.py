# -*- coding: utf-8 -*-
"""模板保护机制 — 阶段 7.2.

提供模板存在性校验、完整性检查、沙箱操作和出厂默认模板自动恢复功能。
所有生成器在操作模板前必须经过此守卫的验证。
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from config.constants import (
    ALL_TEMPLATE_FILES,
    BACKUP_TEMPLATES_DIR,
    TEMPLATES_DIR,
)

logger = logging.getLogger(__name__)


class TemplateGuard:
    """模板保护守卫.

    职责：
    1. 生成前校验模板存在性和完整性
    2. 沙箱操作（复制到临时目录）
    3. 出厂默认模板自动恢复（当模板损坏时从备份恢复）

    使用方式：
        guard = TemplateGuard()
        is_valid, errors = guard.validate_all()
        sandbox_path = guard.create_sandbox("template_packing.xlsx")
    """

    def __init__(
        self,
        templates_dir: str | Path | None = None,
        backup_dir: str | Path | None = None,
    ):
        """初始化模板守卫.

        Args:
            templates_dir: 模板目录路径，默认为 TEMPLATES_DIR.
            backup_dir: 备份模板目录路径，默认为 BACKUP_TEMPLATES_DIR.
        """
        self._templates_dir: Path = Path(templates_dir) if templates_dir else TEMPLATES_DIR
        self._backup_dir: Path = Path(backup_dir) if backup_dir else BACKUP_TEMPLATES_DIR

    # ==================== 公开 API ====================

    def validate_all(self) -> Tuple[bool, List[str]]:
        """校验所有模板文件的存在性和可读性.

        Returns:
            (is_valid, errors): 是否全部通过，以及错误信息列表.

        注意：不检查模板内容完整性（由 template_assertion 负责），
        仅检查文件存在且大小 > 0。
        """
        errors: List[str] = []

        for filename in ALL_TEMPLATE_FILES:
            template_path: Path = self._templates_dir / filename
            if not template_path.exists():
                errors.append(
                    f"[错误]: 模板文件缺失: templates/{filename}\n"
                    f"[原因]: 模板文件可能被误删或移动\n"
                    f"[排查]: 请将 {filename} 放入 templates/ 目录，"
                    f"或从 src/assets/backup_templates/ 恢复"
                )
            elif template_path.stat().st_size == 0:
                errors.append(
                    f"[错误]: 模板文件为空: templates/{filename}\n"
                    f"[原因]: 模板文件内容被清空\n"
                    f"[排查]: 请从 src/assets/backup_templates/ 恢复出厂模板"
                )

        is_valid: bool = len(errors) == 0
        if is_valid:
            logger.info("模板文件校验通过: %d/%d 存在", len(ALL_TEMPLATE_FILES), len(ALL_TEMPLATE_FILES))
        else:
            logger.warning("模板文件校验失败: %d 个错误", len(errors))

        return is_valid, errors

    def validate_single(self, template_name: str) -> Tuple[bool, Optional[str]]:
        """校验单个模板文件.

        Args:
            template_name: 模板文件名（如 "template_packing.xlsx"）.

        Returns:
            (is_valid, error_message): 是否通过，以及错误信息（通过时为 None）.
        """
        if not template_name:
            return False, "[错误]: 模板文件名为空"

        template_path: Path = self._templates_dir / template_name

        if not template_path.exists():
            return False, (
                f"[错误]: 模板文件缺失: templates/{template_name}\n"
                f"[原因]: 模板文件可能被误删或移动\n"
                f"[排查]: 请将 {template_name} 放入 templates/ 目录，"
                f"或从 src/assets/backup_templates/ 恢复"
            )

        if template_path.stat().st_size == 0:
            return False, (
                f"[错误]: 模板文件为空: templates/{template_name}\n"
                f"[原因]: 模板文件内容被清空\n"
                f"[排查]: 请从 src/assets/backup_templates/ 恢复出厂模板"
            )

        return True, None

    def create_sandbox(self, template_name: str) -> Path:
        """在临时目录创建模板的沙箱副本.

        所有生成操作必须在沙箱副本上进行，原模板只读不写。

        Args:
            template_name: 模板文件名（如 "template_packing.xlsx"）.

        Returns:
            沙箱副本的路径.

        Raises:
            FileNotFoundError: 模板文件不存在时抛出.
        """
        if not template_name:
            raise ValueError("[错误]: 模板文件名为空，无法创建沙箱副本")

        template_path: Path = self._templates_dir / template_name

        if not template_path.exists():
            raise FileNotFoundError(
                f"[错误]: 模板文件不存在: {template_path}\n"
                f"[原因]: 模板文件可能被删除、移动或改名\n"
                f"[排查]: 请将 {template_name} 放入 templates/ 目录"
            )

        temp_dir: str = tempfile.gettempdir()
        sandbox_name: str = f"sandbox_{template_name}"
        sandbox_path: Path = Path(temp_dir) / sandbox_name
        shutil.copy2(template_path, sandbox_path)
        logger.debug("沙箱副本已创建: %s", sandbox_path)
        return sandbox_path

    def restore_from_backup(self, template_name: str) -> Tuple[bool, str]:
        """从备份目录恢复出厂默认模板.

        当模板损坏或丢失时，从 src/assets/backup_templates/ 复制恢复。

        Args:
            template_name: 模板文件名（如 "template_packing.xlsx"）.

        Returns:
            (success, message): 是否成功，以及描述信息.
        """
        if not template_name:
            return False, "[错误]: 模板文件名为空，无法恢复"

        backup_path: Path = self._backup_dir / template_name
        target_path: Path = self._templates_dir / template_name

        if not backup_path.exists():
            return False, (
                f"[错误]: 备份模板不存在: {backup_path}\n"
                f"[原因]: 备份目录可能未正确初始化，或 {template_name} 的备份缺失\n"
                f"[排查]: 请确认 src/assets/backup_templates/ 目录包含所有模板文件"
            )

        try:
            self._templates_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_path, target_path)
            logger.info("模板已从备份恢复: %s → %s", backup_path, target_path)
            return True, f"模板 {template_name} 已从备份恢复"
        except PermissionError as e:
            return False, (
                f"[错误]: 无法写入模板文件: {target_path}\n"
                f"[原因]: 文件可能被其他程序占用（如 Excel 正在打开此文件）\n"
                f"[排查]: 请关闭所有使用该模板的程序后重试: {e}"
            )
        except Exception as e:
            return False, (
                f"[错误]: 恢复模板失败: {e}\n"
                f"[原因]: 磁盘空间不足或文件系统权限问题\n"
                f"[排查]: 请检查磁盘空间和 templates/ 目录的写入权限"
            )

    def restore_all_from_backup(self) -> Tuple[int, List[str]]:
        """批量从备份恢复所有模板.

        Returns:
            (success_count, messages): 成功恢复的数量，以及每条操作的消息列表.
        """
        messages: List[str] = []
        success_count: int = 0

        for filename in ALL_TEMPLATE_FILES:
            success, msg = self.restore_from_backup(filename)
            messages.append(msg)
            if success:
                success_count += 1

        logger.info(
            "批量恢复完成: 成功 %d/%d", success_count, len(ALL_TEMPLATE_FILES)
        )
        return success_count, messages

    @staticmethod
    def cleanup_sandbox(sandbox_path: Path) -> None:
        """清理沙箱临时文件.

        Args:
            sandbox_path: 沙箱文件路径.
        """
        try:
            if sandbox_path.exists():
                sandbox_path.unlink(missing_ok=True)
                logger.debug("沙箱副本已清理: %s", sandbox_path)
        except Exception as e:
            logger.warning("[警告]: 清理沙箱文件失败: %s — %s", sandbox_path, e)

    # ==================== 属性 ====================

    @property
    def templates_dir(self) -> Path:
        """模板目录路径."""
        return self._templates_dir

    @property
    def backup_dir(self) -> Path:
        """备份目录路径."""
        return self._backup_dir


# ==================== 模块级便捷函数 ====================

_DEFAULT_GUARD: TemplateGuard | None = None


def get_guard() -> TemplateGuard:
    """获取默认模板守卫单例.

    Returns:
        全局唯一的 TemplateGuard 实例.
    """
    global _DEFAULT_GUARD
    if _DEFAULT_GUARD is None:
        _DEFAULT_GUARD = TemplateGuard()
    return _DEFAULT_GUARD


def validate_all_templates() -> Tuple[bool, List[str]]:
    """校验所有模板文件（便捷函数）."""
    return get_guard().validate_all()


# ========== 运行说明 ==========
# 依赖安装: pip install openpyxl（已在 requirements.txt 中锁定版本）
# 运行命令: 由 orchestrator 统一调用，不直接运行此模块
# =============================
