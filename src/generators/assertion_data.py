# -*- coding: utf-8 -*-
"""断言引擎 — 数据结构与规则加载."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import List, Literal

from config.constants import ASSERTION_RULES_PATH

logger = logging.getLogger(__name__)


# ==================== 数据结构 ====================

AssertionLevel = Literal["error", "warning", "info"]


@dataclass
class AssertionMessage:
    """单条断言消息."""

    level: AssertionLevel
    template_name: str
    category: str
    message: str
    detail: str = ""


@dataclass
class AssertionReport:
    """断言报告."""

    template_name: str
    passed: bool = True
    messages: List[AssertionMessage] = field(default_factory=list)

    @property
    def errors(self) -> List[AssertionMessage]:
        return [m for m in self.messages if m.level == "error"]

    @property
    def warnings(self) -> List[AssertionMessage]:
        return [m for m in self.messages if m.level == "warning"]

    @property
    def infos(self) -> List[AssertionMessage]:
        return [m for m in self.messages if m.level == "info"]

    def add(
        self,
        level: AssertionLevel,
        category: str,
        message: str,
        detail: str = "",
    ) -> None:
        """添加一条断言消息."""
        if level == "error":
            self.passed = False
        self.messages.append(
            AssertionMessage(
                level=level,
                template_name=self.template_name,
                category=category,
                message=message,
                detail=detail,
            )
        )


@dataclass
class BatchAssertionReport:
    """批量断言报告（多模板汇总）."""

    passed: bool = True
    total: int = 0
    passed_count: int = 0
    failed_count: int = 0
    reports: List[AssertionReport] = field(default_factory=list)


# ==================== 规则加载 ====================


def _load_assertion_rules() -> dict:
    """从 config/assertion_rules.json 加载断言规则."""
    if not ASSERTION_RULES_PATH.exists():
        logger.warning(
            "[警告]: 断言规则文件不存在: %s，将使用内置默认规则",
            ASSERTION_RULES_PATH,
        )
        return {}

    try:
        with open(ASSERTION_RULES_PATH, "r", encoding="utf-8") as f:
            rules = json.load(f)
        logger.info("已加载断言规则: %s", ASSERTION_RULES_PATH)
        return rules
    except json.JSONDecodeError as e:
        logger.error(
            "[错误]: 断言规则文件 JSON 解析失败: %s\n[原因]: %s\n[排查]: 请检查 JSON 格式",
            ASSERTION_RULES_PATH, e,
        )
        return {}
    except Exception as e:
        logger.error(
            "[错误]: 读取断言规则文件失败: %s\n[原因]: %s\n[排查]: 请确认文件存在且有读取权限",
            ASSERTION_RULES_PATH, e,
        )
        return {}
