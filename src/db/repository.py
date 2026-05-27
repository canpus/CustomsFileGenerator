"""报关资料自动生成系统 — Repository 数据访问层（聚合入口）.

此模块为子模块的聚合重导出入口：
- customer_repository.py: CustomerRepository
- product_repository.py: ProductRepository
- template_repository.py: TemplateRepository
- history_repository.py: HistoryRepository
"""

from __future__ import annotations

from src.db.customer_repository import CustomerRepository
from src.db.history_repository import HistoryRepository
from src.db.product_repository import ProductRepository
from src.db.template_block_repository import TemplateBlockRepository
from src.db.template_repository import TemplateRepository

__all__ = [
    "CustomerRepository",
    "HistoryRepository",
    "ProductRepository",
    "TemplateBlockRepository",
    "TemplateRepository",
]
