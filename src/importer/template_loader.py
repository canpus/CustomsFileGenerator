# -*- coding: utf-8 -*-
"""订单模板加载器 — 阶段 8.2.

从 SQLite 数据库加载已保存的订单模板，反序列化为 OrderData 对象。
"""

from __future__ import annotations

import logging
from typing import Any

from src.db.repository import TemplateRepository
from src.models.order_data import OrderData

logger = logging.getLogger(__name__)


class TemplateLoader:
    """订单模板加载器.

    封装 TemplateRepository，提供面向业务的模板加载接口。

    使用方式：
        loader = TemplateLoader()
        templates = loader.list_templates()           # 列出所有模板
        order = loader.load_template(template_id=1)   # 加载指定模板
        order = loader.load_latest()                  # 加载最新模板
    """

    @staticmethod
    def list_templates(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """列出所有可用模板（元信息，不含 order_json）.

        Args:
            limit: 每页数量.
            offset: 偏移量.

        Returns:
            模板元信息列表，每个包含 id、template_name、description、
            invoice_no、customer_name、product_count、created_at、updated_at.
        """
        try:
            templates = TemplateRepository.list_all(limit=limit, offset=offset)
            logger.info("列出模板: %d 条", len(templates))
            return templates
        except Exception:
            logger.exception("[错误]: 列出模板失败")
            raise

    @staticmethod
    def search_templates(keyword: str, limit: int = 20) -> list[dict[str, Any]]:
        """按模板名称或客户名模糊搜索模板.

        Args:
            keyword: 搜索关键词.
            limit: 返回数量上限.

        Returns:
            匹配的模板列表.
        """
        try:
            templates = TemplateRepository.search(keyword=keyword, limit=limit)
            logger.info("搜索模板 \"%s\": %d 条结果", keyword, len(templates))
            return templates
        except Exception:
            logger.exception("[错误]: 搜索模板失败")
            raise

    @staticmethod
    def load_template(template_id: int) -> OrderData | None:
        """加载指定 ID 的订单模板.

        Args:
            template_id: 模板 ID.

        Returns:
            OrderData 对象，不存在或已删除则返回 None.

        Raises:
            ValueError: 模板数据已损坏无法反序列化时抛出.
        """
        if template_id <= 0:
            raise ValueError(
                f"[错误]: template_id 必须为正整数，当前值: {template_id}\n"
                f"[原因]: 模板 ID 由数据库自动生成，最小值为 1\n"
                f"[排查]: 请传入有效的模板 ID"
            )

        try:
            order = TemplateRepository.load(template_id)
            if order is None:
                logger.warning("模板 ID=%d 不存在或已删除", template_id)
                return None
            logger.info("加载模板 ID=%d: 发票号=%s", template_id, order.order_meta.invoice_no)
            return order
        except ValueError:
            raise
        except Exception:
            logger.exception("[错误]: 加载模板 ID=%d 失败", template_id)
            raise

    @staticmethod
    def load_latest() -> OrderData | None:
        """加载最近更新的一条模板.

        Returns:
            OrderData 对象，无模板时返回 None.
        """
        try:
            templates = TemplateRepository.list_all(limit=1, offset=0)
            if not templates:
                logger.info("无可用模板")
                return None
            latest_id: int = templates[0]["id"]
            return TemplateLoader.load_template(latest_id)
        except Exception:
            logger.exception("[错误]: 加载最新模板失败")
            raise

    @staticmethod
    def delete_template(template_id: int) -> bool:
        """软删除指定模板.

        Args:
            template_id: 模板 ID.

        Returns:
            True 表示删除成功.
        """
        if template_id <= 0:
            raise ValueError(
                f"[错误]: template_id 必须为正整数，当前值: {template_id}"
            )

        try:
            result = TemplateRepository.delete(template_id)
            logger.info("删除模板 ID=%d: %s", template_id, "成功" if result else "失败（不存在）")
            return result
        except Exception:
            logger.exception("[错误]: 删除模板 ID=%d 失败", template_id)
            raise


# ==================== 独立运行测试 ====================

if __name__ == "__main__":
    """独立测试：列出所有模板（需要已初始化的数据库）."""
    print("=" * 50)
    print("订单模板加载器 — 自检")
    print("=" * 50)

    try:
        templates = TemplateLoader.list_templates(limit=10)
        print(f"\n当前模板数量: {len(templates)}")
        if templates:
            for t in templates:
                print(
                    f"  ID={t['id']} | {t['template_name']} | "
                    f"客户={t['customer_name']} | "
                    f"发票={t['invoice_no']} | "
                    f"{t['product_count']} 种商品"
                )
        else:
            print("  (暂无模板)")

        # 尝试加载最新模板
        latest = TemplateLoader.load_latest()
        if latest:
            print(f"\n最新模板: 发票号={latest.order_meta.invoice_no}, 客户={latest.customer.company_name_en}")
        else:
            print("\n无可用模板（首次运行，需要先保存模板）")

        print("\n🚀 模板加载器自检通过")
    except Exception as e:
        print(f"\n[错误]: 模板加载器自检失败: {e}")
        import traceback
        traceback.print_exc()
