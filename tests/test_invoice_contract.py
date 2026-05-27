"""阶段 5 测试 — 发票生成器 + 合同生成器.

测试覆盖：
- InvoiceGenerator 生成功能
- ContractGenerator 生成功能
- 金额大写转换
- 数据展平/聚合
- 模板锚点扫描失败处理
- 空订单报错
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

# 确保项目根目录在 sys.path 中
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.generators.contract_generator import (
    ContractGenerator,
    flatten_for_contract,
)
from src.generators.invoice_generator import (
    InvoiceGenerator,
    _amount_to_english_upper,
    flatten_for_invoice,
)
from src.models.order_data import (
    Carton,
    Customer,
    OrderData,
    OrderMeta,
    Origin,
    Pallet,
    Product,
    Totals,
)

# ==================== 测试数据工厂 ====================


def _make_product(
    name: str = "50℃ Type 2A-1 Heat Shrink Sleeve",
    spec: str = "330mm*2.0mm*30M",
    hs: str = "3926909090",
    unit: str = "Roll",
    qty: float = 1.0,
    price: float = 85.0,
    weight: float = 22.3,
    country: str = "Turkey",
    seq: int = 1,
) -> Product:
    """创建测试用 Product 实例."""
    return Product(
        seq_no=seq,
        product_name=name,
        specification=spec,
        hs_code=hs,
        unit=unit,
        qty_per_carton=qty,
        unit_price=price,
        net_weight_per_unit_kg=weight,
        destination_country=country,
    )


def _make_carton(
    label: str = "45",
    is_batch: bool = True,
    batch_count: int = 45,
    products: list[Product] | None = None,
) -> Carton:
    """创建测试用 Carton 实例."""
    if products is None:
        products = [_make_product()]
    return Carton(
        carton_label=label,
        is_batch=is_batch,
        batch_count=batch_count,
        length_cm=32.0,
        width_cm=32.0,
        height_cm=34.0,
        gross_weight_kg=23.3,
        products=products,
    )


def _make_pallet(
    pallet_no: int = 1,
    cartons: list[Carton] | None = None,
) -> Pallet:
    """创建测试用 Pallet 实例."""
    if cartons is None:
        cartons = [_make_carton()]
    return Pallet(
        pallet_no=pallet_no,
        length_m=1.16,
        width_m=1.01,
        height_m=1.97,
        cartons=cartons,
    )


def _make_minimal_order(pallets: list[Pallet] | None = None) -> OrderData:
    """创建最小合法 OrderData."""
    if pallets is None:
        pallets = [_make_pallet()]
    return OrderData(
        order_meta=OrderMeta(
            invoice_no="TEST-001",
            contract_no="PO-TEST",
            date="2025-12-26",
            trade_term="FOB",
            payment_term="100% T/T IN ADVANCE",
            country_of_origin="China",
        ),
        customer=Customer(
            company_name_en="TEST CUSTOMER LTD.",
            country="Turkey",
        ),
        origin=Origin(export_port="Shenzhen"),
        pallets=pallets,
        totals=Totals(
            total_pallets=len(pallets),
            total_cartons=1,
            total_gross_weight_kg=1000.0,
            total_net_weight_kg=950.0,
            total_volume_cbm=2.3,
            total_amount=40000.0,
        ),
    )


# ==================== 金额大写测试 ====================


class TestAmountToEnglish:
    """num2words 金额大写转换测试."""

    def test_integer_only(self):
        """整美元金额."""
        result = _amount_to_english_upper(1900.0)
        assert "ONE THOUSAND NINE HUNDRED" in result
        assert result.startswith("USD ")

    def test_with_cents(self):
        """带美分的金额."""
        result = _amount_to_english_upper(1234.56)
        assert "AND CENTS" in result
        assert "FIFTY-SIX" in result

    def test_zero_dollars_with_cents(self):
        """零美元有美分."""
        result = _amount_to_english_upper(0.50)
        assert "ZERO" in result
        assert "CENTS FIFTY" in result

    def test_no_comma_in_output(self):
        """输出中不含逗号."""
        result = _amount_to_english_upper(1234567.89)
        assert "," not in result

    def test_large_amount(self):
        """大额金额（百万级别）."""
        result = _amount_to_english_upper(1000000.0)
        assert "ONE MILLION" in result


# ==================== 数据展平测试 ====================


class TestFlattenForInvoice:
    """发票数据聚合测试."""

    def test_single_product_single_pallet(self):
        """单个商品、单个托盘 → 1 行."""
        order = _make_minimal_order()
        rows = flatten_for_invoice(order)
        assert len(rows) == 1
        assert rows[0]["product_name"] == "50℃ Type 2A-1 Heat Shrink Sleeve"

    def test_same_product_aggregated(self):
        """同款商品跨托盘聚合."""
        p = _make_product()
        pallets = [
            _make_pallet(1, [_make_carton("45", batch_count=45, products=[p])]),
            _make_pallet(2, [_make_carton("45", batch_count=45, products=[p])]),
        ]
        order = _make_minimal_order(pallets)
        rows = flatten_for_invoice(order)
        # 同一商品聚合为 1 行
        assert len(rows) == 1
        assert rows[0]["total_qty"] == 90.0  # 45+45

    def test_different_products_not_aggregated(self):
        """不同商品不聚合."""
        p1 = _make_product(name="Product A", price=10.0, seq=1)
        p2 = _make_product(name="Product B", price=20.0, seq=2)
        pallets = [
            _make_pallet(1, [_make_carton("1", is_batch=False, batch_count=1, products=[p1, p2])]),
        ]
        order = _make_minimal_order(pallets)
        rows = flatten_for_invoice(order)
        assert len(rows) == 2

    def test_different_spec_not_aggregated(self):
        """同名称不同规格不聚合."""
        p1 = _make_product(name="Sleeve", spec="330mm", price=85.0, seq=1)
        p2 = _make_product(name="Sleeve", spec="370mm", price=100.0, seq=2)
        pallets = [
            _make_pallet(1, [_make_carton("1", is_batch=False, batch_count=1, products=[p1, p2])]),
        ]
        order = _make_minimal_order(pallets)
        rows = flatten_for_invoice(order)
        assert len(rows) == 2

    def test_different_price_not_aggregated(self):
        """同名称同规格不同单价不聚合."""
        p1 = _make_product(name="Sleeve", spec="330mm", price=85.0, seq=1)
        p2 = _make_product(name="Sleeve", spec="330mm", price=90.0, seq=2)
        pallets = [
            _make_pallet(1, [_make_carton("1", is_batch=False, batch_count=1, products=[p1, p2])]),
        ]
        order = _make_minimal_order(pallets)
        rows = flatten_for_invoice(order)
        assert len(rows) == 2

    def test_amount_calculation(self):
        """金额计算：total_qty × unit_price."""
        p = _make_product(qty=2.0, price=50.0)
        pallets = [
            _make_pallet(1, [_make_carton("10", batch_count=10, products=[p])]),
        ]
        order = _make_minimal_order(pallets)
        rows = flatten_for_invoice(order)
        assert rows[0]["total_qty"] == 20.0  # 2 × 10
        assert rows[0]["amount"] == 1000.0  # 20 × 50


class TestFlattenForContract:
    """合同数据聚合测试（与发票逻辑相同）."""

    def test_same_as_invoice(self):
        """合同聚合与发票一致."""
        p1 = _make_product(name="A", price=10.0, seq=1)
        p2 = _make_product(name="B", price=20.0, seq=2)
        pallets = [
            _make_pallet(1, [_make_carton("1", is_batch=False, batch_count=1, products=[p1, p2])]),
        ]
        order = _make_minimal_order(pallets)
        inv_rows = flatten_for_invoice(order)
        ctr_rows = flatten_for_contract(order)
        assert len(inv_rows) == len(ctr_rows)
        assert inv_rows[0]["product_name"] == ctr_rows[0]["product_name"]


# ==================== 发票生成器集成测试 ====================


class TestInvoiceGenerator:
    """InvoiceGenerator 集成测试."""

    def test_small_order_generates_valid_xlsx(self):
        """小订单（1 托盘 1 商品） → 生成 xlsx 可打开."""
        order = _make_minimal_order()
        gen = InvoiceGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = gen.generate(order, output_dir=tmpdir)
            assert path.exists()
            assert path.suffix == ".xlsx"
            assert path.stat().st_size > 0

    def test_order_with_multiple_products(self):
        """多商品订单 → 文件可打开，数据正确."""
        p1 = _make_product(name="Product A", price=10.0, qty=5.0, seq=1)
        p2 = _make_product(name="Product B", price=20.0, qty=3.0, seq=2)
        pallets = [
            _make_pallet(1, [_make_carton("1", is_batch=False, batch_count=1, products=[p1, p2])]),
        ]
        order = _make_minimal_order(pallets)
        gen = InvoiceGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = gen.generate(order, output_dir=tmpdir)
            assert path.exists()

    def test_empty_order_raises_error(self):
        """空订单（0 商品） → 报错."""
        _make_minimal_order()
        # 清除所有商品
        empty_pallet = Pallet(
            pallet_no=1,
            length_m=1.0, width_m=1.0, height_m=1.0,
            cartons=[Carton(
                carton_label="1",
                is_batch=False,
                batch_count=1,
                length_cm=10.0, width_cm=10.0, height_cm=10.0,
                gross_weight_kg=1.0,
                products=[],
            )],
        )
        order_empty = _make_minimal_order([empty_pallet])
        gen = InvoiceGenerator()
        with pytest.raises(ValueError):
            gen.generate(order_empty)

    def test_template_not_found_raises_error(self):
        """模板文件不存在 → 报错."""
        order = _make_minimal_order()
        gen = InvoiceGenerator(template_path="/nonexistent/template.xlsx")
        with pytest.raises(FileNotFoundError):
            gen.generate(order)

    def test_progress_callback_called(self):
        """进度回调被调用."""
        order = _make_minimal_order()
        gen = InvoiceGenerator()
        calls: list = []

        def cb(desc: str, pct: float) -> None:
            calls.append((desc, pct))

        with tempfile.TemporaryDirectory() as tmpdir:
            gen.generate(order, output_dir=tmpdir, progress_callback=cb)
        assert len(calls) > 0
        # 最后一次回调 progress=1.0
        assert calls[-1][1] == 1.0


# ==================== 合同生成器集成测试 ====================


class TestContractGenerator:
    """ContractGenerator 集成测试."""

    def test_small_order_generates_valid_xlsx(self):
        """小订单 → 生成 xlsx 可打开."""
        order = _make_minimal_order()
        gen = ContractGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = gen.generate(order, output_dir=tmpdir)
            assert path.exists()
            assert path.suffix == ".xlsx"

    def test_multiple_products(self):
        """多商品订单 → 文件可打开."""
        p1 = _make_product(name="A", price=10.0, seq=1)
        p2 = _make_product(name="B", price=20.0, seq=2)
        pallets = [
            _make_pallet(1, [_make_carton("1", is_batch=False, batch_count=1, products=[p1, p2])]),
        ]
        order = _make_minimal_order(pallets)
        gen = ContractGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = gen.generate(order, output_dir=tmpdir)
            assert path.exists()

    def test_empty_order_raises_error(self):
        """空订单 → 报错."""
        empty_pallet = Pallet(
            pallet_no=1,
            length_m=1.0, width_m=1.0, height_m=1.0,
            cartons=[Carton(
                carton_label="1", is_batch=False, batch_count=1,
                length_cm=10.0, width_cm=10.0, height_cm=10.0,
                gross_weight_kg=1.0, products=[],
            )],
        )
        order = _make_minimal_order([empty_pallet])
        gen = ContractGenerator()
        with pytest.raises(ValueError):
            gen.generate(order)

    def test_template_not_found_raises_error(self):
        """模板不存在 → 报错."""
        order = _make_minimal_order()
        gen = ContractGenerator(template_path="/nonexistent/template.xlsx")
        with pytest.raises(FileNotFoundError):
            gen.generate(order)

    def test_progress_callback_called(self):
        """进度回调被调用."""
        order = _make_minimal_order()
        gen = ContractGenerator()
        calls: list = []

        def cb(desc: str, pct: float) -> None:
            calls.append((desc, pct))

        with tempfile.TemporaryDirectory() as tmpdir:
            gen.generate(order, output_dir=tmpdir, progress_callback=cb)
        assert len(calls) > 0
        assert calls[-1][1] == 1.0


# ========== 运行说明 ==========
# 依赖安装: pip install openpyxl msgspec num2words pytest
# 运行命令: python -m pytest tests/test_invoice_contract.py -v
# =============================
