-- 报关资料自动生成系统 — 数据库表结构定义
-- 版本：6.0.1-a | 日期：2026-05-20
-- 使用方式：在 SQLite 连接时由 connection.py 自动执行

-- ==================== customers 客户表 ====================
-- 存储常用客户信息，避免每次手动录入
CREATE TABLE IF NOT EXISTS customers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name_en TEXT    NOT NULL,          -- 客户公司英文名（必填）
    company_name_cn TEXT    DEFAULT '',        -- 客户公司中文名
    country         TEXT    NOT NULL,          -- 客户所在国家（必填）
    address         TEXT    DEFAULT '',        -- 客户地址
    contact_person  TEXT    DEFAULT '',        -- 联系人
    phone           TEXT    DEFAULT '',        -- 联系电话
    mobile          TEXT    DEFAULT '',        -- 手机号
    destination     TEXT    DEFAULT '',        -- 目的地/卸货港
    created_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),  -- 创建时间
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),  -- 更新时间
    is_deleted      INTEGER NOT NULL DEFAULT 0 -- 软删除标记：0=正常, 1=已删除
);

CREATE INDEX IF NOT EXISTS idx_customers_company ON customers(company_name_en);
CREATE INDEX IF NOT EXISTS idx_customers_country  ON customers(country);


-- ==================== products 产品表 ====================
-- 存储常用产品信息，减少重复录入
CREATE TABLE IF NOT EXISTS products (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name        TEXT    NOT NULL,          -- 商品名称（必填）
    specification       TEXT    DEFAULT '',        -- 规格型号
    hs_code             TEXT    NOT NULL,          -- HS 编码（必填）
    declaration_elements TEXT   DEFAULT '',        -- 申报要素
    unit                TEXT    NOT NULL,          -- 计量单位（必填）
    unit_price          REAL    NOT NULL DEFAULT 0.0,  -- 单价（USD）
    net_weight_per_unit_kg REAL NOT NULL DEFAULT 0.0,  -- 单件净重（kg）
    destination_country TEXT    DEFAULT '',        -- 目的国
    currency            TEXT    DEFAULT 'USD',     -- 币种
    created_at          TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    is_deleted          INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_products_name   ON products(product_name);
CREATE INDEX IF NOT EXISTS idx_products_hs_code ON products(hs_code);


-- ==================== order_templates 订单模板表 ====================
-- 保存整个订单为模板，供下次复用（存储 JSON 序列化后的 OrderData）
CREATE TABLE IF NOT EXISTS order_templates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    template_name   TEXT    NOT NULL,          -- 模板名称（必填，用于展示和搜索）
    order_json      TEXT    NOT NULL,          -- OrderData 的 JSON 字符串（必填）
    description     TEXT    DEFAULT '',        -- 模板描述
    invoice_no      TEXT    DEFAULT '',        -- 发票号（冗余字段，便于搜索）
    customer_name   TEXT    DEFAULT '',        -- 客户名（冗余字段，便于搜索）
    product_count   INTEGER NOT NULL DEFAULT 0,-- 商品种类数（冗余字段）
    created_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    is_deleted      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_templates_name   ON order_templates(template_name);
CREATE INDEX IF NOT EXISTS idx_templates_customer ON order_templates(customer_name);


-- ==================== history 生成历史表 ====================
-- 记录每次一键生成的订单摘要，便于追溯
CREATE TABLE IF NOT EXISTS history (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_no        TEXT    NOT NULL,          -- 发票号
    contract_no       TEXT    NOT NULL,          -- 合同号
    customer_name     TEXT    NOT NULL,          -- 客户名
    total_amount      REAL    NOT NULL DEFAULT 0.0,  -- 总金额
    total_pallets     INTEGER NOT NULL DEFAULT 0,    -- 托盘总数
    total_cartons     INTEGER NOT NULL DEFAULT 0,    -- 纸箱总数
    generated_files   TEXT    NOT NULL DEFAULT '',   -- 生成的文件名列表（JSON 数组）
    generated_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),  -- 生成时间
    order_json        TEXT    DEFAULT '',        -- 订单 JSON 快照（可选，用于回溯）
    status            TEXT    NOT NULL DEFAULT 'success',  -- 状态：success / partial / failed
    error_message     TEXT    DEFAULT ''         -- 错误信息（失败时记录）
);

CREATE INDEX IF NOT EXISTS idx_history_invoice  ON history(invoice_no);
CREATE INDEX IF NOT EXISTS idx_history_date     ON history(generated_at);
CREATE INDEX IF NOT EXISTS idx_history_customer ON history(customer_name);
