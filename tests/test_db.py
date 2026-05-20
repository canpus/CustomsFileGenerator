# -*- coding: utf-8 -*-
"""阶段 2 里程碑测试：数据库层（schema + connection + repository）.

运行方式：
    python -m pytest tests/test_db.py -v

覆盖：
    1. 数据库文件自动创建（首次运行时生成 customs.db）
    2. 客户 CRUD：新增 → 查询 → 更新 → 删除
    3. 客户模糊搜索：搜索 "LG" 能匹配 "LG CHEM. LTD."
    4. 产品 CRUD：新增 → 按 HS Code 查询 → 更新 → 删除
    5. 模板保存/加载：存一个 OrderData → 读出来 → 数据一致
    6. 历史记录：生成后自动记录时间戳和摘要
    7. 并发写入测试：两个线程同时写不同表，不报错
    8. 参数化查询防注入测试：输入 "'; DROP TABLE customers;--" 不会删表
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

import pytest

# ==================== 测试配置：使用临时数据库 ====================
# 测试时替换 constants.py 中的 DATABASE_PATH 为临时文件

_TEST_DB_DIR: Path = Path(tempfile.mkdtemp(prefix="test_db_"))
_TEST_DB_PATH: Path = _TEST_DB_DIR / "customs.db"


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    """每个测试前：切换到临时数据库，测试后自动清理."""
    # 确保临时数据库目录存在
    _TEST_DB_DIR.mkdir(parents=True, exist_ok=True)

    # 替换 constants.py 中的 DATABASE_PATH
    import config.constants as consts
    monkeypatch.setattr(consts, "DATABASE_PATH", _TEST_DB_PATH)

    # 如果已有临时数据库文件，先删除（确保每次测试独立）
    if _TEST_DB_PATH.exists():
        _TEST_DB_PATH.unlink()

    # 重置 db.connection 中的线程局部变量
    import src.db.connection as conn_module
    monkeypatch.setattr(conn_module, "_thread_local", threading.local())

    yield

    # 清理：关闭连接 + 删除临时文件
    from src.db.connection import close_all_connections
    close_all_connections()
    if _TEST_DB_PATH.exists():
        _TEST_DB_PATH.unlink()
    if _TEST_DB_DIR.exists():
        try:
            _TEST_DB_DIR.rmdir()
        except OSError:
            pass


# ==================== 测试辅助 ====================


def _make_valid_order() -> "OrderData":
    """构建一个最小合法订单."""
    from src.models.order_data import (
        Carton, Customer, OrderData, OrderMeta, Origin, Pallet, Product, Totals,
    )
    return OrderData(
        order_meta=OrderMeta(
            invoice_no="INV-001",
            contract_no="CT-001",
            date="2025-12-26",
            trade_term="FOB",
            payment_term="100% T/T IN ADVANCE",
            country_of_origin="China",
        ),
        customer=Customer(
            company_name_en="LG CHEM. LTD.",
            country="Korea",
        ),
        pallets=[
            Pallet(
                pallet_no=1,
                length_m=1.2,
                width_m=1.0,
                height_m=1.5,
                cartons=[
                    Carton(
                        carton_label="C1",
                        is_batch=False,
                        batch_count=1,
                        length_cm=30.0,
                        width_cm=30.0,
                        height_cm=30.0,
                        gross_weight_kg=100.0,
                        products=[
                            Product(
                                seq_no=1,
                                product_name="Heat Shrink Sleeve",
                                hs_code="3926909090",
                                unit="Roll",
                                qty_per_carton=1,
                                unit_price=85.0,
                                net_weight_per_unit_kg=22.3,
                                destination_country="Korea",
                            ),
                        ],
                    ),
                ],
            ),
        ],
        totals=Totals(
            total_pallets=1,
            total_cartons=1,
            total_gross_weight_kg=100.0,
            total_net_weight_kg=22.3,
            total_volume_cbm=1.8,
            total_amount=85.0,
        ),
        origin=Origin(),
    )


# ==================== 测试 1：数据库文件自动创建 ====================


class TestDatabaseAutoCreation:
    """验证首次连接时自动创建数据库和表."""

    def test_database_file_created(self) -> None:
        """首次连接后 customs.db 文件应存在."""
        from src.db.connection import get_connection, close_connection
        conn = get_connection()
        assert _TEST_DB_PATH.exists(), "数据库文件未自动创建"
        close_connection()

    def test_tables_created(self) -> None:
        """四张表全部创建成功."""
        from src.db.connection import get_connection, close_connection
        conn = get_connection()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        expected = {"customers", "products", "order_templates", "history"}
        assert expected.issubset(set(tables)), f"缺少表: {expected - set(tables)}"
        close_connection()

    def test_wal_mode_enabled(self) -> None:
        """WAL 模式应已启用."""
        from src.db.connection import get_connection, close_connection
        conn = get_connection()
        cursor = conn.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        assert mode.lower() == "wal", f"journal_mode 应为 wal，实际: {mode}"
        close_connection()


# ==================== 测试 2：客户 CRUD ====================


class TestCustomerCRUD:
    """客户增删改查操作."""

    def test_insert_and_get(self) -> None:
        """新增客户后可按 ID 查询."""
        from src.db.repository import CustomerRepository
        cid = CustomerRepository.insert(
            company_name_en="LG CHEM. LTD.",
            country="Korea",
            address="Seoul, Korea",
        )
        assert cid > 0

        customer = CustomerRepository.get_by_id(cid)
        assert customer is not None
        assert customer["company_name_en"] == "LG CHEM. LTD."
        assert customer["country"] == "Korea"

    def test_update(self) -> None:
        """更新客户信息后查询反映变更."""
        from src.db.repository import CustomerRepository
        cid = CustomerRepository.insert(
            company_name_en="SAMSUNG",
            country="Korea",
        )
        updated = CustomerRepository.update(cid, phone="+82-12345678")
        assert updated is True

        customer = CustomerRepository.get_by_id(cid)
        assert customer is not None
        assert customer["phone"] == "+82-12345678"

    def test_delete_soft(self) -> None:
        """软删除后 get_by_id 返回 None."""
        from src.db.repository import CustomerRepository
        cid = CustomerRepository.insert(
            company_name_en="TO_DELETE",
            country="CN",
        )
        assert CustomerRepository.delete(cid) is True
        assert CustomerRepository.get_by_id(cid) is None

    def test_list_all(self) -> None:
        """分页列出客户."""
        from src.db.repository import CustomerRepository
        CustomerRepository.insert(company_name_en="AAA Corp", country="US")
        CustomerRepository.insert(company_name_en="BBB Corp", country="UK")
        CustomerRepository.insert(company_name_en="CCC Corp", country="JP")

        results = CustomerRepository.list_all(limit=10)
        assert len(results) == 3


# ==================== 测试 3：客户模糊搜索 ====================


class TestCustomerSearch:
    """客户模糊搜索测试."""

    def test_search_by_partial_name(self) -> None:
        """搜索 "LG" 能匹配 "LG CHEM. LTD."."""
        from src.db.repository import CustomerRepository
        CustomerRepository.insert(
            company_name_en="LG CHEM. LTD.",
            country="Korea",
        )
        CustomerRepository.insert(
            company_name_en="SAMSUNG",
            country="Korea",
        )

        results = CustomerRepository.search("LG")
        assert len(results) == 1
        assert "LG" in results[0]["company_name_en"]

    def test_search_by_country(self) -> None:
        """按国家名搜索."""
        from src.db.repository import CustomerRepository
        CustomerRepository.insert(company_name_en="AAA", country="Turkey")
        CustomerRepository.insert(company_name_en="BBB", country="Japan")

        results = CustomerRepository.search("Turkey")
        assert len(results) == 1
        assert results[0]["country"] == "Turkey"

    def test_search_no_match(self) -> None:
        """无匹配时返回空列表."""
        from src.db.repository import CustomerRepository
        results = CustomerRepository.search("ZZZZZ_NOT_EXIST")
        assert results == []


# ==================== 测试 4：产品 CRUD ====================


class TestProductCRUD:
    """产品增删改查操作."""

    def test_insert_and_get(self) -> None:
        """新增产品后可按 ID 查询."""
        from src.db.repository import ProductRepository
        pid = ProductRepository.insert(
            product_name="Heat Shrink Sleeve",
            hs_code="3926909090",
            unit="Roll",
            unit_price=85.0,
            net_weight_per_unit_kg=22.3,
        )
        assert pid > 0

        product = ProductRepository.get_by_id(pid)
        assert product is not None
        assert product["product_name"] == "Heat Shrink Sleeve"

    def test_search_by_hs_code(self) -> None:
        """按 HS 编码搜索."""
        from src.db.repository import ProductRepository
        ProductRepository.insert(
            product_name="Product A",
            hs_code="3926909090",
            unit="Roll",
        )
        ProductRepository.insert(
            product_name="Product B",
            hs_code="8544492000",
            unit="Meter",
        )

        results = ProductRepository.search_by_hs_code("3926")
        assert len(results) == 1
        assert results[0]["hs_code"] == "3926909090"

    def test_update_and_delete(self) -> None:
        """更新和删除产品."""
        from src.db.repository import ProductRepository
        pid = ProductRepository.insert(
            product_name="Old Name",
            hs_code="0000000000",
            unit="Pcs",
        )
        assert ProductRepository.update(pid, product_name="New Name") is True
        product = ProductRepository.get_by_id(pid)
        assert product["product_name"] == "New Name"

        assert ProductRepository.delete(pid) is True
        assert ProductRepository.get_by_id(pid) is None

    def test_list_all(self) -> None:
        """分页列出产品."""
        from src.db.repository import ProductRepository
        ProductRepository.insert(product_name="P1", hs_code="1111", unit="pcs")
        ProductRepository.insert(product_name="P2", hs_code="2222", unit="pcs")

        results = ProductRepository.list_all()
        assert len(results) == 2


# ==================== 测试 5：模板保存/加载 ====================


class TestTemplateCRUD:
    """模板保存和加载测试."""

    def test_save_and_load_roundtrip(self) -> None:
        """保存 OrderData → 加载 → 数据一致."""
        from src.db.repository import TemplateRepository
        order = _make_valid_order()

        tid = TemplateRepository.save(order, "测试模板", "测试用")
        assert tid > 0

        loaded = TemplateRepository.load(tid)
        assert loaded is not None
        assert loaded.order_meta.invoice_no == order.order_meta.invoice_no
        assert loaded.customer.company_name_en == order.customer.company_name_en
        assert loaded.totals.total_pallets == order.totals.total_pallets

    def test_list_templates(self) -> None:
        """列出模板列表（不含 order_json）."""
        from src.db.repository import TemplateRepository
        order = _make_valid_order()
        TemplateRepository.save(order, "模板 A")
        TemplateRepository.save(order, "模板 B")

        results = TemplateRepository.list_all()
        assert len(results) == 2
        # 列表中不应包含 order_json
        assert "order_json" not in results[0]

    def test_delete_template(self) -> None:
        """删除模板后加载返回 None."""
        from src.db.repository import TemplateRepository
        order = _make_valid_order()
        tid = TemplateRepository.save(order, "待删除模板")
        assert TemplateRepository.delete(tid) is True
        assert TemplateRepository.load(tid) is None

    def test_search_template(self) -> None:
        """按模板名搜索."""
        from src.db.repository import TemplateRepository
        order = _make_valid_order()
        TemplateRepository.save(order, "韩国客户模板 A")
        TemplateRepository.save(order, "日本客户模板 B")

        results = TemplateRepository.search("韩国")
        assert len(results) == 1
        assert results[0]["template_name"] == "韩国客户模板 A"


# ==================== 测试 6：历史记录 ====================


class TestHistory:
    """生成历史记录测试."""

    def test_record_history(self) -> None:
        """记录生成历史."""
        from src.db.repository import HistoryRepository
        hid = HistoryRepository.record(
            invoice_no="INV-001",
            contract_no="CT-001",
            customer_name="LG CHEM. LTD.",
            total_amount=85000.0,
            total_pallets=10,
            total_cartons=45,
            generated_files=["packing.xlsx", "invoice.xlsx"],
            status="success",
        )
        assert hid > 0

        record = HistoryRepository.get_by_id(hid)
        assert record is not None
        assert record["invoice_no"] == "INV-001"
        assert record["total_pallets"] == 10
        assert record["status"] == "success"

    def test_list_recent(self) -> None:
        """列出最近记录."""
        from src.db.repository import HistoryRepository
        HistoryRepository.record(
            invoice_no="INV-A", contract_no="CT-A", customer_name="AAA",
            total_amount=100.0, total_pallets=1, total_cartons=1,
        )
        HistoryRepository.record(
            invoice_no="INV-B", contract_no="CT-B", customer_name="BBB",
            total_amount=200.0, total_pallets=2, total_cartons=2,
        )

        results = HistoryRepository.list_recent(limit=10)
        assert len(results) == 2
        # 按时间倒序，最新的在前
        assert results[0]["invoice_no"] == "INV-B"

    def test_record_with_order_snapshot(self) -> None:
        """记录历史时附带订单快照."""
        from src.db.repository import HistoryRepository
        order = _make_valid_order()
        hid = HistoryRepository.record(
            invoice_no="INV-SNAP",
            contract_no="CT-SNAP",
            customer_name="Test",
            total_amount=85.0,
            total_pallets=1,
            total_cartons=1,
            order=order,
        )
        record = HistoryRepository.get_by_id(hid)
        assert record is not None
        # order_json 应不为空
        assert record["order_json"]

    def test_record_failed(self) -> None:
        """记录失败状态."""
        from src.db.repository import HistoryRepository
        hid = HistoryRepository.record(
            invoice_no="INV-FAIL",
            contract_no="CT-FAIL",
            customer_name="FAIL Corp",
            total_amount=0.0,
            total_pallets=0,
            total_cartons=0,
            status="failed",
            error_message="模板损坏，生成失败",
        )
        record = HistoryRepository.get_by_id(hid)
        assert record is not None
        assert record["status"] == "failed"
        assert "模板损坏" in record["error_message"]

    def test_clear_old(self) -> None:
        """清理旧记录."""
        from src.db.repository import HistoryRepository
        HistoryRepository.record(
            invoice_no="INV-OLD", contract_no="CT-OLD", customer_name="OLD",
            total_amount=1.0, total_pallets=1, total_cartons=1,
        )
        # 清理超过 0 天的记录（即全部清理）
        deleted = HistoryRepository.clear_old(days=0)
        assert deleted >= 1
        results = HistoryRepository.list_recent()
        assert len(results) == 0


# ==================== 测试 7：并发写入 ====================


class TestConcurrency:
    """并发写入测试."""

    def test_concurrent_write_different_tables(self) -> None:
        """两个线程同时写入不同表，不报错."""
        from src.db.repository import CustomerRepository, ProductRepository

        errors: list[Exception] = []

        def insert_customers() -> None:
            try:
                for i in range(5):
                    CustomerRepository.insert(
                        company_name_en=f"Thread1_Customer_{i}",
                        country="CN",
                    )
            except Exception as e:
                errors.append(e)

        def insert_products() -> None:
            try:
                for i in range(5):
                    ProductRepository.insert(
                        product_name=f"Thread2_Product_{i}",
                        hs_code=f"99999999{i}",
                        unit="Pcs",
                    )
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=insert_customers, name="CustomerThread")
        t2 = threading.Thread(target=insert_products, name="ProductThread")

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(errors) == 0, f"并发写入出错: {errors}"

        # 验证数据完整性
        customers = CustomerRepository.list_all()
        products = ProductRepository.list_all()
        assert len(customers) == 5
        assert len(products) == 5


# ==================== 测试 8：参数化查询防注入 ====================


class TestSQLInjection:
    """参数化查询防注入测试."""

    def test_injection_in_search(self) -> None:
        """输入 '; DROP TABLE customers;-- 不会删表."""
        from src.db.repository import CustomerRepository
        from src.db.connection import get_connection, close_connection

        # 先插入一条正常数据
        CustomerRepository.insert(
            company_name_en="NORMAL_CUSTOMER",
            country="CN",
        )

        # 尝试注入
        malicious = "'; DROP TABLE customers;--"
        results = CustomerRepository.search(malicious)
        # 不应匹配到任何结果
        assert results == []

        # 验证表仍然存在且数据完好
        conn = get_connection()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='customers'"
        )
        assert cursor.fetchone() is not None, "customers 表被删除了！"

        cursor = conn.execute("SELECT COUNT(*) FROM customers")
        count = cursor.fetchone()[0]
        assert count >= 1, "customers 表中数据丢失了！"
        close_connection()

    def test_injection_in_product_search(self) -> None:
        """产品表同样不被注入."""
        from src.db.repository import ProductRepository
        from src.db.connection import get_connection, close_connection

        ProductRepository.insert(
            product_name="SAFE_PRODUCT",
            hs_code="0000000000",
            unit="Pcs",
        )

        malicious = "'; DROP TABLE products;--"
        results = ProductRepository.search_by_hs_code(malicious)
        assert results == []

        conn = get_connection()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='products'"
        )
        assert cursor.fetchone() is not None, "products 表被删除了！"
        close_connection()


# ==================== 测试 9：repository 列表空结果 ====================


class TestEmptyResults:
    """空结果场景测试."""

    def test_get_by_id_not_exist(self) -> None:
        """查询不存在的 ID 返回 None."""
        from src.db.repository import CustomerRepository, ProductRepository
        assert CustomerRepository.get_by_id(99999) is None
        assert ProductRepository.get_by_id(99999) is None

    def test_update_not_exist(self) -> None:
        """更新不存在的 ID 返回 False."""
        from src.db.repository import CustomerRepository
        assert CustomerRepository.update(99999, company_name_en="GHOST") is False

    def test_delete_not_exist(self) -> None:
        """删除不存在的 ID 返回 False."""
        from src.db.repository import CustomerRepository
        assert CustomerRepository.delete(99999) is False

    def test_load_nonexistent_template(self) -> None:
        """加载不存在的模板返回 None."""
        from src.db.repository import TemplateRepository
        assert TemplateRepository.load(99999) is None
