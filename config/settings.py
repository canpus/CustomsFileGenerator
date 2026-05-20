# -*- coding: utf-8 -*-
"""报关资料自动生成系统 — 配置管理模块.

从 .env 文件和环境变量读取敏感配置（API Key 等），
从 settings.json 读取业务配置（公司抬头、模板坐标等）。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from config.constants import CONFIG_DIR

logger = logging.getLogger(__name__)

# ==================== .env 加载 ====================

# 在项目根目录查找 .env 文件
_env_path: Path = CONFIG_DIR.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)
    logger.info("已加载环境配置文件: %s", _env_path)
else:
    logger.info(".env 文件不存在，使用 .env.example 作为参考模板")


# ==================== settings.json 加载 ====================

_settings: dict[str, Any] = {}
_settings_path: Path = CONFIG_DIR / "settings.json"

try:
    with open(_settings_path, "r", encoding="utf-8") as f:
        _settings = json.load(f)
    logger.info("已加载业务配置文件: %s", _settings_path)
except FileNotFoundError:
    logger.warning(
        "[错误]: 业务配置文件 %s 不存在\n"
        "[原因]: 项目可能未正确初始化，或文件被误删\n"
        "[排查]: 请检查 config/settings.json 是否存在，或从备份恢复",
        _settings_path,
    )
except json.JSONDecodeError as e:
    logger.error(
        "[错误]: 业务配置文件 %s JSON 格式错误\n"
        "[原因]: 文件中存在语法错误，位于第 %s 行第 %s 列\n"
        "[排查]: 请使用 JSON 验证工具检查文件格式",
        _settings_path,
        e.lineno,
        e.colno,
    )


def get_env(key: str, default: str = "") -> str:
    """从环境变量读取配置值.

    Args:
        key: 环境变量键名.
        default: 默认值，当环境变量不存在时返回.

    Returns:
        环境变量的值，或默认值.
    """
    return os.getenv(key, default)


def get_setting(key: str, default: Any = None) -> Any:
    """从 settings.json 读取配置值.

    支持点号分隔的多级键，如 "company.name" 会访问 _settings["company"]["name"].

    Args:
        key: 配置键，支持点号分隔的多级路径.
        default: 默认值，当键不存在时返回.

    Returns:
        配置值，或默认值.
    """
    keys = key.split(".")
    value: Any = _settings
    for k in keys:
        if isinstance(value, dict) and k in value:
            value = value[k]
        else:
            return default
    return value


def get_all_settings() -> dict[str, Any]:
    """获取全部业务配置（只读）.

    Returns:
        业务配置字典的浅拷贝.
    """
    return dict(_settings)


# ==================== 便捷访问方法 ====================

def get_company_name() -> str:
    """获取公司名称."""
    return get_setting("company.name", "CYG CHANGTONG NEW MATERIAL CO., LTD")


def get_company_name_cn() -> str:
    """获取公司中文名称."""
    return get_setting("company.name_cn", "长园长通新材料股份有限公司")


def get_company_address() -> str:
    """获取公司地址."""
    return get_setting(
        "company.address",
        "No. 707, Block A, Building 1, Yunzhi Technology Park, "
        "South Side of Shuangming Avenue, Dongzhou Community, "
        "Guangming Street, Guangming District, Shenzhen",
    )


def get_output_dir() -> Path:
    """获取输出目录路径."""
    from config.constants import OUTPUT_DIR

    custom = get_setting("output_dir", "")
    if custom:
        return Path(custom)
    return OUTPUT_DIR
