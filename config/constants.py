# -*- coding: utf-8 -*-
"""报关资料自动生成系统 — 配置常量模块.

定义所有默认值、枚举值、模板路径常量。
"""

from __future__ import annotations

from pathlib import Path
from enum import Enum


# ==================== 路径常量 ====================

# 项目根目录（main.py 所在目录）
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# 模板目录
TEMPLATES_DIR: Path = PROJECT_ROOT / "templates"

# 输出目录
OUTPUT_DIR: Path = PROJECT_ROOT / "output"

# 日志目录
LOGS_DIR: Path = PROJECT_ROOT / "logs"

# 配置目录
CONFIG_DIR: Path = PROJECT_ROOT / "config"

# 数据库文件路径
DATABASE_PATH: Path = PROJECT_ROOT / "data" / "customs.db"

# 备份模板目录（阶段 7 使用，预留）
BACKUP_TEMPLATES_DIR: Path = PROJECT_ROOT / "src" / "assets" / "backup_templates"

# 锚点扫描规则文件路径（阶段 3）
TEMPLATE_RULES_PATH: Path = CONFIG_DIR / "template_rules.json"

# 模板断言规则文件路径（阶段 7 预留）
ASSERTION_RULES_PATH: Path = CONFIG_DIR / "assertion_rules.json"


# ==================== 模板文件名常量 ====================

TEMPLATE_PACKING: str = "template_packing.xlsx"
TEMPLATE_INVOICE: str = "template_invoice.xlsx"
TEMPLATE_CONTRACT: str = "template_contract.xlsx"
TEMPLATE_CUSTOMS: str = "template_customs.docx"

# 四个模板文件的完整路径
TEMPLATE_PACKING_PATH: Path = TEMPLATES_DIR / TEMPLATE_PACKING
TEMPLATE_INVOICE_PATH: Path = TEMPLATES_DIR / TEMPLATE_INVOICE
TEMPLATE_CONTRACT_PATH: Path = TEMPLATES_DIR / TEMPLATE_CONTRACT
TEMPLATE_CUSTOMS_PATH: Path = TEMPLATES_DIR / TEMPLATE_CUSTOMS

# 所有模板文件列表（用于环境自检）
ALL_TEMPLATE_FILES: list[str] = [
    TEMPLATE_PACKING,
    TEMPLATE_INVOICE,
    TEMPLATE_CONTRACT,
    TEMPLATE_CUSTOMS,
]


# ==================== 枚举值 ====================

class TradeTerm(str, Enum):
    """贸易条款."""
    FOB = "FOB"
    CIF = "CIF"
    CFR = "CFR"
    EXW = "EXW"
    DDP = "DDP"
    DAP = "DAP"


class PaymentMethod(str, Enum):
    """付款方式."""
    TT_ADVANCE = "100% T/T IN ADVANCE"
    TT_30 = "T/T 30% DEPOSIT"
    LC_AT_SIGHT = "L/C AT SIGHT"
    LC_90 = "L/C 90 DAYS"
    DP = "D/P"


class TransportMode(str, Enum):
    """运输方式."""
    SEA = "SEA"
    AIR = "AIR"
    RAIL = "RAIL"
    TRUCK = "TRUCK"


class Currency(str, Enum):
    """币种."""
    USD = "USD"
    EUR = "EUR"
    CNY = "CNY"
    GBP = "GBP"
    JPY = "JPY"


# ==================== 业务默认值 ====================

# 默认运输方式
DEFAULT_TRANSPORT_MODE: str = "SEA"

# 默认币种
DEFAULT_CURRENCY: str = "USD"

# 默认贸易条款
DEFAULT_TRADE_TERM: str = "FOB"

# 默认付款方式
DEFAULT_PAYMENT_METHOD: str = "100% T/T IN ADVANCE"

# 默认产地
DEFAULT_ORIGIN_COUNTRY: str = "China"

# ==================== 系统配置 ====================

# 最低 Python 版本要求
MIN_PYTHON_VERSION: tuple[int, int] = (3, 10)

# 程序版本
APP_VERSION: str = "6.0.1-a"

# 程序名称
APP_NAME: str = "报关资料自动生成系统"

# 日志配置
LOG_MAX_BYTES: int = 5 * 1024 * 1024  # 5MB
LOG_BACKUP_COUNT: int = 3

# 大订单阈值（托盘数超过此值时打印性能提示）
LARGE_ORDER_THRESHOLD: int = 100

# ==================== 生成器配置 ====================

# 生成的文件名前缀映射
FILE_PREFIX_MAP: dict[str, str] = {
    "packing": "装箱单",
    "invoice": "形式发票",
    "contract": "形式合同",
    "customs": "报关单",  # [待迁移] 阶段 6 完成后启用
}
