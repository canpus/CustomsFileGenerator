# -*- coding: utf-8 -*-
"""报关资料自动生成系统 — 统一数据模型（msgspec.Struct）.

严格遵循 plan_v6.md 附录 A 之 JSON Schema 定义。
所有数据结构均为不可变结构体，通过 msgspec.field 控制默认值。
"""

from __future__ import annotations

from typing import Literal

import msgspec


# ==================== TradeTerm 贸易条款 ====================

TradeTerm = Literal["FOB", "CIF", "DAP", "DDP", "EXW", "CFR"]


# ==================== TransportMode 运输方式 ====================

TransportMode = Literal["海运", "空运", "陆运"]


# ==================== PackageType 包装类型 ====================

PackageType = Literal["pallet", "carton", "package"]


# ==================== Product 商品 ====================

class Product(msgspec.Struct, frozen=True):
    """单个商品.

    Attributes:
        seq_no: 商品序号（≥1）.
        product_name: 商品名称.
        specification: 规格型号（可为空）.
        hs_code: HS 编码.
        declaration_elements: 申报要素（可为空）.
        unit: 计量单位.
        qty_per_carton: 每箱数量.
        unit_price: 单价（USD）.
        currency: 币种，默认 USD.
        net_weight_per_unit_kg: 单件净重（kg）.
        destination_country: 目的国.
    """

    seq_no: int
    product_name: str
    hs_code: str
    unit: str
    qty_per_carton: float
    unit_price: float
    net_weight_per_unit_kg: float
    destination_country: str

    specification: str = msgspec.field(default="")
    declaration_elements: str = msgspec.field(default="")
    currency: str = msgspec.field(default="USD")


# ==================== Carton 纸箱 ====================

class Carton(msgspec.Struct, frozen=True):
    """单个纸箱（含箱内商品列表）.

    Attributes:
        carton_label: 纸箱标签（如 "45"）.
        is_batch: 是否为批量纸箱（同规格多箱）.
        batch_count: 批量数量（is_batch=True 时有效）.
        length_cm: 纸箱长度（cm）.
        width_cm: 纸箱宽度（cm）.
        height_cm: 纸箱高度（cm）.
        gross_weight_kg: 纸箱毛重（kg）.
        products: 箱内商品列表.
    """

    carton_label: str
    is_batch: bool
    batch_count: int
    length_cm: float
    width_cm: float
    height_cm: float
    gross_weight_kg: float
    products: list[Product]


# ==================== Pallet 托盘 ====================

class Pallet(msgspec.Struct, frozen=True):
    """单个托盘（含纸箱列表）.

    Attributes:
        pallet_no: 托盘编号（≥1）.
        length_m: 托盘长度（m）.
        width_m: 托盘宽度（m）.
        height_m: 托盘高度（m）.
        pallet_weight_kg: 托盘自重（kg），默认 0.
        cartons: 托盘上的纸箱列表.
    """

    pallet_no: int
    length_m: float
    width_m: float
    height_m: float
    cartons: list[Carton]

    pallet_weight_kg: float = msgspec.field(default=0.0)


# ==================== OrderMeta 订单元信息 ====================

class OrderMeta(msgspec.Struct, frozen=True):
    """订单元信息.

    Attributes:
        invoice_no: 发票号.
        contract_no: 合同号.
        date: 报关单据日期（ISO 8601: YYYY-MM-DD）.
        order_no: 订单号（可为空）.
        transport_mode: 运输方式.
        vessel_flight: 船名/航班号（可为空）.
        bill_of_lading_no: 提单号（可为空）.
        trade_term: 贸易条款.
        payment_term: 付款方式.
        currency: 币种，默认 USD.
        package_type: 包装类型，默认 pallet.
        country_of_origin: 原产国.
        goods_summary: 货品名称摘要（可为空）.
        declaration_elements_template: 申报要素模板（可为空）.
    """

    invoice_no: str
    contract_no: str
    date: str
    trade_term: TradeTerm
    payment_term: str
    country_of_origin: str

    order_no: str = msgspec.field(default="")
    transport_mode: TransportMode = msgspec.field(default="海运")
    vessel_flight: str = msgspec.field(default="")
    bill_of_lading_no: str = msgspec.field(default="")
    currency: str = msgspec.field(default="USD")
    package_type: PackageType = msgspec.field(default="pallet")
    goods_summary: str = msgspec.field(default="")
    declaration_elements_template: str = msgspec.field(default="")


# ==================== Customer 客户信息 ====================

class Customer(msgspec.Struct, frozen=True):
    """客户信息.

    Attributes:
        company_name_en: 客户公司英文名.
        country: 客户所在国家.
        company_name_cn: 客户公司中文名（可为空）.
        address: 客户地址（可为空）.
        contact_person: 联系人（可为空）.
        phone: 联系电话（可为空）.
        mobile: 手机号（可为空）.
        destination: 目的地/卸货港（可为空）.
    """

    company_name_en: str
    country: str

    company_name_cn: str = msgspec.field(default="")
    address: str = msgspec.field(default="")
    contact_person: str = msgspec.field(default="")
    phone: str = msgspec.field(default="")
    mobile: str = msgspec.field(default="")
    destination: str = msgspec.field(default="")


# ==================== Origin 产地/发货信息 ====================

class Origin(msgspec.Struct, frozen=True):
    """产地与发货人信息.

    Attributes:
        export_port: 装运港.
        domestic_source: 境内货源地.
        manufacturer: 生产厂家.
        business_entity: 经营单位.
        trade_mode: 贸易方式.
        tax_nature: 征免性质.
        settlement_method: 结汇方式.
        tax_rebate: 退税情况.
    """

    export_port: str = msgspec.field(default="")
    domestic_source: str = msgspec.field(default="深圳特区")
    manufacturer: str = msgspec.field(default="长园长通新材料股份有限公司")
    business_entity: str = msgspec.field(default="长园长通新材料股份有限公司")
    trade_mode: str = msgspec.field(default="一般贸易")
    tax_nature: str = msgspec.field(default="一般征税")
    settlement_method: str = msgspec.field(default="电汇")
    tax_rebate: str = msgspec.field(default="申请退税")


# ==================== Totals 汇总数据 ====================

class Totals(msgspec.Struct, frozen=True):
    """订单汇总数据.

    Attributes:
        total_pallets: 托盘总数.
        total_cartons: 纸箱总数.
        total_gross_weight_kg: 总毛重（kg）.
        total_net_weight_kg: 总净重（kg）.
        total_volume_cbm: 总体积（m³）.
        total_amount: 总金额（USD）.
        total_amount_upper: 英文大写金额（生成时填充）.
    """

    total_pallets: int
    total_cartons: int
    total_gross_weight_kg: float
    total_net_weight_kg: float
    total_volume_cbm: float
    total_amount: float

    total_amount_upper: str = msgspec.field(default="")


# ==================== TemplateMeta 模板元信息 ====================

class TemplateMeta(msgspec.Struct, frozen=True):
    """模板元信息（用于模板保存/加载）.

    Attributes:
        template_name: 模板名称.
        created_at: 创建时间（ISO 8601）.
        description: 模板描述.
    """

    template_name: str = msgspec.field(default="")
    created_at: str = msgspec.field(default="")
    description: str = msgspec.field(default="")


# ==================== OrderData 根模型 ====================

class OrderData(msgspec.Struct, frozen=True):
    """报关订单根数据结构.

    严格遵循 plan_v6.md 附录 A JSON Schema。

    Attributes:
        order_meta: 订单元信息.
        customer: 客户信息.
        pallets: 托盘列表（至少 1 个）.
        totals: 汇总数据.
        origin: 产地/发货信息.
        template_meta: 模板元信息（保存时选用）.
    """

    order_meta: OrderMeta
    customer: Customer
    pallets: list[Pallet]
    totals: Totals

    origin: Origin = msgspec.field(default_factory=Origin)
    template_meta: TemplateMeta = msgspec.field(default_factory=TemplateMeta)


# ==================== 序列化/反序列化 ====================

_DECODER = msgspec.json.Decoder(OrderData)
_ENCODER = msgspec.json.Encoder()


def decode_order(json_str: str | bytes) -> OrderData:
    """将 JSON 字符串解码为 OrderData 对象.

    Args:
        json_str: JSON 字符串或字节.

    Returns:
        OrderData 实例.

    Raises:
        msgspec.ValidationError: JSON 数据不符合 Schema 定义时抛出.
    """
    return _DECODER.decode(json_str)


def encode_order(order: OrderData) -> bytes:
    """将 OrderData 对象编码为 JSON 字节.

    Args:
        order: OrderData 实例.

    Returns:
        JSON 字节（紧凑模式，ensure_ascii=False）.
    """
    return _ENCODER.encode(order)


def encode_order_pretty(order: OrderData) -> bytes:
    """将 OrderData 对象编码为格式化 JSON（用于日志/展示）.

    Args:
        order: OrderData 实例.

    Returns:
        格式化 JSON 字节（indent=2）.
    """
    return msgspec.json.format(msgspec.json.encode(order), indent=2)
