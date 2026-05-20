# 报关资料自动生成系统 — 实施计划 v6.0(Agent 版)

> **目标读者**:AI Agent(每次一个对话窗口,按阶段执行)
> **版本**:6.0.0 | **日期**:2026-05-10
> **技术栈**:tkinter + ttkbootstrap + openpyxl + python-docx + msgspec + sqlite3
> **体积红线**:< 50MB(目标 38-42MB)

---

## ⚠️ AGENT 使用说明(必读)

1. 本计划共 **10 个阶段**,每个阶段在一个独立的对话窗口中完成
2. 每阶段开头会标注 **📥 你需要在对话开始时提供给 Agent 的文件清单**
3. 每阶段结尾会标注 **✅ 里程碑验证方法** — Agent 必须产出能通过该验证的代码
4. **跨阶段依赖**:后续阶段依赖前序阶段产出的文件/数据模型,不可跳过
5. 若某阶段 Agent 产出不通过里程碑验证,在原对话窗口中继续修正,不要开启新窗口

---

## 阶段 0️⃣:项目骨架与环境自检

**📥 你需要提供给 Agent 的文件**:
- 根 `Claude.md`(本文件)
- `Claude.python.md`(Python 规范)
- `docs/pyproject.toml`(Ruff/mypy/pytest 配置)
- 四个真实模板文件(放入 `templates/` 目录):
  - `template_customs.docx`(报关单模板)
  - `template_packing.xlsx`(装箱单模板)
  - `template_invoice.xlsx`(形式发票模板)
  - `template_contract.xlsx`(形式合同模板)

**Agent 任务**:

| 子任务 | 具体内容 |
|--------|---------|
| 0.1 | 创建完整项目目录结构(见下方) |
| 0.2 | 编写 `requirements.txt`(锁定精确版本号) |
| 0.3 | 编写 `main.py` 入口:环境自检(Python 版本 ≥ 3.10,模板文件存在性,依赖安装检查) |
| 0.4 | 编写 `config/settings.py`:从 `.env` + `settings.json` 读取配置 |
| 0.5 | 编写 `config/constants.py`:所有默认值,枚举值,模板路径常量 |
| 0.6 | 创建 `.env.example` 模板文件 |

**目录结构**:

```
CustomsFileGenerator/
├── main.py
├── requirements.txt
├── .env.example
├── .gitignore
├── config/
│   ├── __init__.py
│   ├── settings.py
│   ├── constants.py
│   └── settings.json
├── src/
│   ├── __init__.py
│   ├── models/
│   │   └── __init__.py
│   ├── db/
│   │   └── __init__.py
│   ├── generators/
│   │   └── __init__.py
│   ├── importer/
│   │   └── __init__.py
│   └── gui/
│       ├── __init__.py
│       └── pages/
│           └── __init__.py
├── templates/              ← 你放入 4 个模板文件
│   ├── template_customs.docx
│   ├── template_packing.xlsx
│   ├── template_invoice.xlsx
│   └── template_contract.xlsx
├── output/                 ← 生成的文件输出目录
├── docs/
│   └── schemas/
└── tests/
    └── __init__.py
```

**✅ 里程碑 0 验证方法**:
```bash
# 在项目根目录执行:
python main.py

# 预期输出(模板文件都存在时):
# ✅ Python 版本:3.12.0 — 通过
# ✅ 依赖检查:全部已安装
# ✅ 模板文件:4/4 存在
# 🚀 环境自检通过,程序就绪

# 如果缺少某个模板文件,预期输出:
# ❌ 模板文件缺失:templates/template_customs.docx
# 💡 请将报关单模板文件放入 templates/ 目录
# 🔧 模板文件名必须为:template_customs.docx
```

---

## 阶段 1️⃣:统一数据模型(msgspec 结构体)

**📥 你需要提供给 Agent 的文件**:
- 阶段 0 产出的所有文件
- 你的真实订单数据示例(至少 1 个完整订单的 Excel 或手写数据)
- `RealOrderData.md`(真实订单数据参考文档)

**Agent 任务**:

| 子任务 | 具体内容 |
|--------|---------|
| 1.1 | 编写 `src/models/order_data.py`:定义 `OrderData`,`OrderMeta`,`Customer`,`Origin`,`Shipping`,`Misc`,`Pallet`,`Carton`,`Product`,`Totals` 等 msgspec.Struct 结构体,**严格遵循本计划末尾的完整 JSON Schema** |
| 1.2 | 编写 `src/models/validators.py`:实现 `validate_order_consistency()` 函数,检查以下业务规则:
| | - 总毛重 ≥ 总净重 |
| | - 每个纸箱毛重 ≥ 箱内所有商品净重之和 |
| | - 托盘总体积 = 长×宽×高(允许 ±0.001 误差) |
| | - 汇总数据与明细加总一致(交叉校验) |
| | - 所有必填字段不为空 |
| 1.3 | 编写 `src/models/error_mapper.py`:将 msgspec 的 `ValidationError` 映射为中文修复建议(三要素:❌发生了什么 / 💡原因 / 🔧解决方法) |

**数据流向**:
```
JSON 字符串 → msgspec.decode() → OrderData 对象 → validators.validate_order_consistency() → (通过/警告/拒绝)
```

**✅ 里程碑 1 验证方法**:
```bash
# 在项目根目录执行:
python -m pytest tests/test_models.py -v

# 测试文件必须覆盖:
# 1. 合法 JSON → 成功反序列化
# 2. 缺少必填字段 → error_mapper 返回中文错误
# 3. 类型错误(字符串填数字字段)→ error_mapper 返回中文错误
# 4. 枚举值非法(运输方式填"高铁")→ error_mapper 返回中文错误
# 5. 总毛重 < 总净重 → validate_order_consistency 返回警告
# 6. 纸箱毛重 < 商品净重之和 → validate_order_consistency 返回警告
# 7. 空订单(pallets 为空数组)→ 拒绝
# 8. 超大订单(100+ 托盘)→ 通过但打印性能提示

# 预期:8 个测试全部 PASSED
```

---

## 阶段 2️⃣:SQLite 数据库层

**📥 你需要提供给 Agent 的文件**:
- 阶段 0-1 产出的所有文件

**Agent 任务**:

| 子任务 | 具体内容 |
|--------|---------|
| 2.1 | 编写 `src/db/schema.sql`:定义 `customers`,`products`,`order_templates`,`history` 四张表的结构 |
| 2.2 | 编写 `src/db/connection.py`:SQLite 连接上下文管理器,启用 WAL 模式,自动执行 `schema.sql` 建表 |
| 2.3 | 编写 `src/db/repository.py`:Repository 模式实现客户/产品/模板/历史的 CRUD 操作 |
| | - `CustomerRepository`:增删改查 + 模糊搜索 |
| | - `ProductRepository`:增删改查 + 按 HS Code 搜索 |
| | - `TemplateRepository`:保存订单为模板,加载模板,删除模板 |
| | - `HistoryRepository`:记录每次生成的订单摘要 |
| 2.4 | 所有 SQL 操作必须使用参数化查询,禁止拼接字符串 |

**✅ 里程碑 2 验证方法**:
```bash
python -m pytest tests/test_db.py -v

# 测试文件必须覆盖:
# 1. 数据库文件自动创建(首次运行时生成 customs.db)
# 2. 客户 CRUD:新增 → 查询 → 更新 → 删除
# 3. 客户模糊搜索:搜索 "LG" 能匹配 "LG CHEM. LTD."
# 4. 产品 CRUD:新增 → 按 HS Code 查询 → 更新 → 删除
# 5. 模板保存/加载:存一个 OrderData → 读出来 → 数据一致
# 6. 历史记录:生成后自动记录时间戳和摘要
# 7. 并发写入测试:两个线程同时写不同表,不报错
# 8. 参数化查询防注入测试:输入 "'; DROP TABLE customers;--" 不会删表

# 预期:8 个测试全部 PASSED
```

---

## 阶段 3️⃣:XLSX 工具库(openpyxl 安全操作)

**📥 你需要提供给 Agent 的文件**:
- 阶段 0-2 产出的所有文件
- 你的装箱单,发票,合同模板(已在 `templates/` 中)

**⚠️ 这是最核心的技术难点阶段,Agent 必须特别注意**.

**📌 开始前必读**:查阅 **附录 B:XLSX 模板字段映射表**,了解三个 xlsx 模板(装箱单,发票,合同)的单元格位置,合并区域,字体字号和行结构.锚点扫描规则和后续生成器的数据填充逻辑均依赖此附录.

**Agent 任务**:

| 子任务 | 具体内容 |
|--------|---------|
| 3.1 | 编写 `src/generators/xlsx_utils.py`,实现以下安全操作函数:
| | - `clone_row_style(ws, source_row, target_row)`:深拷贝一行的所有样式(font, border, fill, alignment, number_format) |
| | - `insert_rows_with_style(ws, anchor_row, count)`:在锚点行后插入 N 行并复制样式 |
| | - `delete_rows_safely(ws, start, end)`:逆序删除行,删除前自动 `unmerge_cells` |
| | - `update_sum_formula(ws, col_letter, start_row, end_row)`:修正 SUM 公式的范围 |
| | - `get_merged_ranges_in_row(ws, row)`:获取指定行涉及的所有合并单元格范围 |
| 3.2 | 编写 `src/generators/template_anchor_scanner.py`:动态锚点扫描引擎
| | - 扫描 xlsx 模板前 30 行,通过关键词匹配定位数据起始行和汇总行 |
| | - 不依赖硬编码行号(例如不写死"A8",而是找到含"序号"的行,下一行即数据起始行) |
| | - 支持 `config/template_rules.json` 可配置规则 + 内置默认规则兜底 |
| 3.3 | 编写 `config/template_rules.json`:定义各模板的锚点扫描规则 |

**关键算法(须严格实现)**:

```python
# delete_rows_safely 伪代码
def delete_rows_safely(ws, start_row, end_row):
    """
    逆序安全删除行.

    为什么必须逆序:正序删除会导致行号偏移,后续删除位置错误.
    为什么必须先 unmerge:openpyxl 在删除含合并单元格的行时会崩溃.
    """
    for row in range(end_row, start_row - 1, -1):  # 逆序
        # 1. 检测并解除该行的所有合并单元格
        merged_ranges = get_merged_ranges_in_row(ws, row)
        for merged_range in merged_ranges:
            ws.unmerge_cells(str(merged_range))

        # 2. 删除该行
        ws.delete_rows(row)
```

**✅ 里程碑 3 验证方法**:
```bash
python -m pytest tests/test_xlsx_utils.py -v

# 测试文件必须覆盖:
# 1. clone_row_style:源行 A8 有加粗+边框,目标行 A20 获得完全相同的样式
# 2. insert_rows_with_style:插入 5 行后,每行样式与锚点行一致
# 3. delete_rows_safely 缩水场景(50行→5行):删除 45 行后,汇总行公式自动修正
# 4. delete_rows_safely 含合并单元格:第 8-10 行有合并,安全删除不报错
# 5. update_sum_formula:SUM(G8:G57) 修正为 SUM(G8:G20)
# 6. 锚点扫描 packing 模板:正确找到数据起始行和汇总行
# 7. 锚点扫描 invoice 模板:正确找到数据起始行和汇总行
# 8. 锚点扫描 contract 模板:正确找到数据起始行和汇总行
# 9. 锚点扫描失败时(模板损坏)→ 返回明确错误信息

# 预期:9 个测试全部 PASSED
```

---

## 阶段 4️⃣:装箱单生成器(Packing Generator)

**📥 你需要提供给 Agent 的文件**:
- 阶段 0-3 产出的所有文件
- 一个真实订单的完整数据(托盘数,箱数,商品种类,重量体积)

**Agent 任务**:

**📌 开始前必读**:查阅 **附录 B.1 装箱单**,确认装箱单模板的单元格位置(表头 D3:K6,数据起始行 8,汇总行 58),列映射(A–K)和字体字号(表头 Arial 11pt / 明细 Arial 12pt).

| 子任务 | 具体内容 |
|--------|---------|
| 4.1 | 编写 `src/generators/packing_generator.py`,实现 `PackingGenerator` 类:
| | - 沙箱操作:复制模板到 `tempfile.gettempdir()` 再操作 |
| | - 动态锚点定位起始行和汇总行 |
| | - 根据订单数据行数决定缩容/扩容操作 |
| | - 填充表头信息(公司抬头,客户信息,订单信息) |
| | - 填充商品明细行(逐托盘,逐箱写入) |
| | - 处理 `is_batch` 批量纸箱(一个 `batch_count=10` 的节点展开为 10 行) |
| | - 更新汇总公式(总箱数,总净重,总毛重,总体积) |
| | - 输出到 `output/` 目录 |
| 4.2 | 编写数据展平函数 `flatten_for_packing(order: OrderData) -> list[dict]` |

**✅ 里程碑 4 验证方法**:
```bash
python -m pytest tests/test_packing_generator.py -v

# 测试文件必须覆盖:
# 1. 小订单(1 托盘,1 箱,1 商品)→ 生成 xlsx 可打开,数据正确
# 2. 中等订单(5 托盘,20 箱,3 种商品)→ 行数正确,汇总数据一致
# 3. 大订单(50+ 行数据 → 触发扩容)→ 插入新行带样式,公式修正
# 4. 批量纸箱(is_batch=true, batch_count=10)→ 正确展开为 10 行
# 5. 空订单(0 商品)→ 报错不生成,模板不被破坏
# 6. 模板损坏(锚点扫描失败)→ 报错并提示恢复出厂模板

# 此外:用你提供的真实订单数据生成一份装箱单,用 Excel 打开人工检查:
# - 格式是否与模板一致(字体,边框,合并单元格)
# - 数据是否正确(重量,体积加总一致)
# - 公式是否有效(修改数据后汇总自动更新)

# 预期:6 个自动化测试全部 PASSED + 人工检查通过
```

---

## 阶段 5️⃣:发票 + 合同生成器(Invoice & Contract Generator)

**📥 你需要提供给 Agent 的文件**:
- 阶段 0-4 产出的所有文件

**Agent 任务**:

**📌 开始前必读**:查阅 **附录 B.2 形式发票** 和 **附录 B.3 形式合同**,确认两个模板的单元格位置,合并区域,列映射和字体字号(发票:Times New Roman 14–16pt / 合同:Times New Roman 12–14pt).

| 子任务 | 具体内容 |
|--------|---------|
| 5.1 | 编写 `src/generators/invoice_generator.py`,实现 `InvoiceGenerator` 类:
| | - 沙箱操作 + 动态锚点定位 |
| | - 填充发票表头(发票号,日期,客户信息,贸易条款) |
| | - 填充商品明细行(Product, Specification, Unit, Qty, Unit Price, Amount) |
| | - 集成 `num2words` 将总金额转换为英文大写(SAY: USD ... ONLY) |
| | - 更新汇总行 |
| 5.2 | 编写 `src/generators/contract_generator.py`,实现 `ContractGenerator` 类:
| | - 沙箱操作 + 动态锚点定位 |
| | - 填充合同表头(合同号,日期,买卖双方信息) |
| | - 填充商品明细行 |
| | - 集成 `num2words` 大写金额 |
| 5.3 | 编写 `src/generators/base_generator.py`:抽象基类,定义 `generate(order, output_dir, progress_callback)` 接口 |

**✅ 里程碑 5 验证方法**:
```bash
python -m pytest tests/test_invoice_generator.py tests/test_contract_generator.py -v

# 测试文件必须覆盖(发票和合同各 6 项):
# 1. 小/中/大订单 → 生成文件可打开,数据正确
# 2. 金额大写转换:1900.00 → "USD ONE THOUSAND NINE HUNDRED ONLY"
# 3. 金额大写转换:1234567.89 → 正确转换
# 4. 模板损坏 → 报错不生成
# 5. 空订单 → 报错不生成
# 6. 模板锚点扫描失败 → 报错并提示

# 人工检查:生成的发票和合同中:
# - 大写金额是否正确
# - 商品明细是否完整
# - 格式是否与模板一致

# 预期:12 个自动化测试全部 PASSED + 人工检查通过
```

---

## 阶段 6️⃣:报关单生成器(Customs Generator — docx 引擎)

**📥 你需要提供给 Agent 的文件**:
- 阶段 0-5 产出的所有文件

**🚫 硬约束（优先级高于所有子任务——在获得货代/海关确认前，以下条款不可豁免）**:
- **禁止修改模板的表格结构**（禁止拆分/合并单元格、禁止增减列、禁止修改合并区域、禁止修改列宽行高）
- **仅允许通过 `{{占位符}}` 替换单元格内的 Run 文字内容**
- **所有操作必须在沙箱副本上进行**（原始模板只读，不碰 `templates/` 中的文件）
- **所有输出须经货代验证格式合规后方可投入生产使用**

**📌 前置确认项（开始编写代码前必须完成）**:

| # | 确认项 | 确认人 | 状态 |
|---|--------|--------|------|
| 1 | 单元格内文字内容可以修改？用 `{{占位符}}` 标记是否影响海关系统读取？ | 货代/海关 | ⬜ 待确认 |
| 2 | 商品明细行数可以增加？行克隆是否影响海关系统读取？ | 货代/海关 | ⬜ 待确认 |
| 3 | 表格单元格可以拆分？ | 货代/海关 | ⬜ 待确认 |
| 4 | 对齐技术方案确定（`{{占位符}}` + 空格/独立单元格/人工微调） | 技术负责人 | ⬜ 待确认 |

**⚠️ 这是技术难度最高的阶段:docx 的 XML 操作比 xlsx 复杂得多**.

**Agent 任务**:

| 子任务 | 具体内容 |
|--------|---------|
| 6.1 | 编写 `src/generators/customs_generator.py`,实现 `CustomsGenerator` 类:
| | - 沙箱操作:复制模板 docx 到临时目录 |
| | - 动态锚点定位报关单表格(通过关键词"经营单位","商品编号"定位) |
| | - 填充表头 8 行(经营单位,运输方式,发货单位,境外收货人……) |
| | - **成对行克隆**:每个商品占 2 行(上行:项号/HS/名称/净重/币制;下行:申报要素/数量单位/目的国/单价/总价) |
| | - 使用 `copy.deepcopy()` 克隆 `w:tr` XML 节点对,保留所有样式 |
| | - 填充商品明细数据 |
| 6.2 | 编写 docx 锚点扫描逻辑(扩展 `template_anchor_scanner.py`) |
| 6.3 | 编写数据展平函数 `flatten_for_customs(order: OrderData) -> list[dict]` |

**关键算法(成对行克隆)**:

```python
# 成对行克隆伪代码
def clone_product_row_pair(table, anchor_row_idx, clone_count):
    """
    报关单中每个商品占 2 行.锚点行(上行)和锚点行+1(下行)作为一个单元克隆.

    Args:
        table: python-docx Table 对象
        anchor_row_idx: 锚点行索引(第一个商品的上行)
        clone_count: 需要克隆的单元数(商品数-1)
    """
    from copy import deepcopy

    tr_upper = table.rows[anchor_row_idx]._tr       # 上行 XML 节点
    tr_lower = table.rows[anchor_row_idx + 1]._tr   # 下行 XML 节点

    for i in range(clone_count):
        # 深拷贝一对行
        new_upper = deepcopy(tr_upper)
        new_lower = deepcopy(tr_lower)

        # 插入到表格 XML 树中(在最后一行之后)
        tr_upper.addnext(new_lower)
        new_lower.addprevious(new_upper)
```

**✅ 里程碑 6 验证方法**:
```bash
python -m pytest tests/test_customs_generator.py -v

# 测试文件必须覆盖:
# 1. 1 个商品 → 表头 8 行 + 商品 2 行 = 共 10 行,数据正确
# 2. 5 个商品 → 表头 8 行 + 5×2 = 18 行,项号连续 1-5
# 3. 10 个商品 → 行数正确,每个商品的上下行成对存在
# 4. 表头关键占位符检查("经营单位","境外收货人"等文本存在)
# 5. 样式保留检查(表头加粗,Times New Roman 字体仍在)
# 6. 空订单 → 报错不生成
# 7. 模板损坏(无表格)→ 报错

# 人工检查:生成的报关单 docx 中:
# - 表头信息是否全部填充正确
# - 商品明细行格式是否与模板一致(项号/HS/名称在上行,申报要素在下行)
# - HS Code 字体是否为 Arial 10pt 加粗
# - 中文是否为 Simsun 8.5pt/小五

# 预期:7 个自动化测试全部 PASSED + 人工检查通过
```

---

## 阶段 7️⃣:一键生成 + 模板无损断言

**📥 你需要提供给 Agent 的文件**:
- 阶段 0-6 产出的所有文件

**Agent 任务**:

| 子任务 | 具体内容 |
|--------|---------|
| 7.1 | 编写 `src/generators/orchestrator.py`:一键生成协调器
| | - 接收 `OrderData` + 输出目录 → 依次调用四个生成器 → 输出四份文件 |
| | - 实时进度回调(哪个文件正在生成,百分比) |
| | - 错误隔离:某个生成器失败不影响其他生成器 |
| 7.2 | 编写 `src/generators/template_assertion.py`:模板无损断言引擎
| | - xlsx 断言:检查关键单元格的字体,边框,合并范围,公式是否与模板一致 |
| | - docx 断言:检查表格数量,表头行数,关键占位符存在性 |
| | - 断言分级:error(阻断)/ warning(警告)/ info(日志) |
| | - 可配置规则:从 `config/assertion_rules.json` 读取 |
| 7.3 | 编写 `config/assertion_rules.json`:定义各模板的断言规则 |
| 7.4 | 编写 `src/generators/template_guard.py`:模板保护机制
| | - 生成前校验模板存在性和完整性 |
| | - 沙箱操作(复制到临时目录) |
| | - 出厂默认模板自动恢复(当模板损坏时从 `src/assets/backup_templates/` 恢复) |
| 7.5 | 创建 `src/assets/backup_templates/` 目录,放入 4 个模板的备份副本 |

**✅ 里程碑 7 验证方法**:
```bash
python -m pytest tests/test_orchestrator.py tests/test_template_assertion.py -v

# 测试文件必须覆盖:
# 1. 一键生成:给定一个合法 OrderData → 输出 4 个文件 → 全部可打开
# 2. 一键生成进度回调:验证回调被调用了 4 次(每个文件一次)
# 3. 错误隔离:模拟 packing 生成失败 → invoice/contract/customs 仍然生成
# 4. xlsx 断言通过:生成的文件字体/边框/合并与模板一致
# 5. xlsx 断言失败:模拟字体被篡改 → 断言报告显示 error
# 6. docx 断言通过:表格数量,表头行数,占位符全部正确
# 7. docx 断言失败:模拟表格缺失 → 断言报告显示 error
# 8. 模板损坏恢复:删除 packing 模板 → 自动从 backup_templates 恢复
# 9. 断言分级:字体大小偏差 0.5pt → 报 warning(不阻断),合并单元格丢失 → 报 error

# 预期:9 个测试全部 PASSED
```

---

## 阶段 8️⃣:数据导入器 + 诊断包

**📥 你需要提供给 Agent 的文件**:
- 阶段 0-7 产出的所有文件
- 你的原始订单 Excel 表格样本(即你们业务中实际使用的订单表格)

**Agent 任务**:

| 子任务 | 具体内容 |
|--------|---------|
| 8.1 | 编写 `src/importer/excel_importer.py`:
| | - 读取用户上传的订单 Excel 表格 |
| | - 通过列名匹配(如"产品名称"→`product_name`)自动映射到 SSOT 字段 |
| | - 自动计算托盘体积 = 长×宽×高 |
| | - 自动汇总总毛重,总净重,总体积,总金额 |
| | - 输出完整的 `OrderData` 对象 |
| | - 对无法自动映射的列标注 `TODO:待确认` |
| 8.2 | 编写 `src/importer/template_loader.py`:从 SQLite 加载已保存的订单模板 |
| 8.3 | 编写 `src/utils/diagnostic_exporter.py`:
| | - `DiagnosticExporter.export(order, error_info)` → 生成 `diagnostic_YYYYMMDD_HHMMSS.zip` |
| | - 包含:脱敏后的订单 JSON,运行日志,系统环境信息 |
| 8.4 | 编写 `src/utils/data_sanitizer.py`:
| | - 字段级脱敏:公司名截取首两字+***,电话号码替换为 [REDACTED],单价覆写为 0.00 |
| | - 路径脱敏:绝对路径替换为相对路径 |

**脱敏矩阵(必须严格实现)**:

| 字段路径 | 脱敏方式 |
|---------|---------|
| `customer.company_name_en` | 截取首两字 + `***` |
| `customer.phone` | 替换为 `[REDACTED]` |
| `customer.mobile` | 替换为 `[REDACTED]` |
| `customer.address` | 截取前 10 字符 + `...` |
| `products[*].unit_price` | 强制覆写为 `0.00` |
| 异常堆栈中的文件路径 | 替换为相对路径 |
| `order_meta.invoice_no` | 保留原样(便于对账) |
| 产品名称,HS Code,规格 | 保留原样 |

**✅ 里程碑 8 验证方法**:
```bash
python -m pytest tests/test_importer.py tests/test_diagnostic.py -v

# 测试文件必须覆盖:
# 1. Excel 导入:读取样本订单 Excel → 输出 OrderData → 字段映射正确
# 2. Excel 导入未知列名 → 标注 TODO
# 3. 自动计算:体积 = 长×宽×高(验证 1.2×1.0×1.5 = 1.8)
# 4. 自动汇总:总毛重 = 所有纸箱毛重之和
# 5. 模板加载:从 SQLite 加载模板 → 反序列化为 OrderData
# 6. 诊断包导出:生成 zip 文件 → 解压后包含 3 个文件
# 7. 脱敏:公司名 "LG CHEM. LTD." → "LG ***"
# 8. 脱敏:电话号码 "+82 123456789" → "[REDACTED]"
# 9. 脱敏:单价 0.63 → 0.00

# 预期:9 个测试全部 PASSED
```

---

## 阶段 9️⃣:GUI 界面(ttkbootstrap)

**📥 你需要提供给 Agent 的文件**:
- 阶段 0-8 产出的所有文件

**Agent 任务**:

| 子任务 | 具体内容 |
|--------|---------|
| 9.1 | 编写 `src/gui/app.py`:主应用窗口
| | - 基于 ttkbootstrap(Flatly 主题) |
| | - 入口激活 DPI 感知(`ctypes.windll.shcore.SetProcessDpiAwareness(1)`) |
| | - 字体回退池(Microsoft YaHei → Segoe UI → TkDefaultFont) |
| | - 左侧导航栏(新建单据 / 历史模板 / 客户管理 / 产品库) |
| | - 右侧工作区(根据导航切换页面) |
| 9.2 | 编写 `src/gui/pages/order_info_page.py`:订单信息录入页
| | - 订单元信息(发票号,合同号,日期) |
| | - 客户信息(公司名,地址,国家) |
| | - 运输与贸易信息(运输方式,贸易术语,币制) |
| | - 境内信息(默认值预填) |
| 9.3 | 编写 `src/gui/pages/tree_editor_page.py`:托盘-纸箱-商品树状编辑器
| | - 左侧 `ttk.Treeview` 显示三级层级(托盘 → 纸箱 → 商品) |
| | - 选中节点时右侧刷新对应属性表单 |
| | - 右键菜单:新增/克隆/删除 节点 |
| | - 支持批量纸箱输入(is_batch + batch_count) |
| 9.4 | 编写 `src/gui/pages/import_page.py`:表格导入页 |
| | - 选择 Excel 文件 → 预览映射结果 → 确认导入 |
| 9.5 | 编写 `src/gui/pages/template_page.py`:模板管理页 |
| | - 保存当前订单为模板 / 加载已有模板 / 删除模板 |
| 9.6 | 编写 `src/gui/pages/generate_page.py`:生成与预览页 |
| | - 一键生成按钮 → 进度条 → 完成提示 |
| | - 诊断包导出按钮(仅出错时显示) |
| | - 打开输出文件夹按钮 |

**✅ 里程碑 9 验证方法**:
```bash
# 启动 GUI:
python main.py --gui

# 人工验证清单:
# □ 窗口正常打开,DPI 缩放下无模糊
# □ 左侧导航 4 个按钮可切换页面
# □ 订单信息页:所有输入框可录入,下拉框(运输方式等)可选值
# □ 树状编辑器:可新增托盘 → 新增纸箱 → 新增商品,三级结构正确
# □ 右键菜单:克隆托盘(含其下所有纸箱和商品)功能正常
# □ 表格导入:选择一个 Excel 文件 → 预览数据 → 确认后填充到树状编辑器
# □ 模板保存/加载:保存当前订单 → 关闭程序 → 重新打开 → 加载模板 → 数据一致
# □ 一键生成:点击生成按钮 → 进度条走完 → 提示成功 → output/ 目录有 4 个文件
# □ 完整性校验:总毛重 < 总净重时 → 红色警告,禁止生成
# □ 诊断包导出:故意制造错误 → 点击导出 → 生成 zip 文件
```

---

## 阶段 🔟:打包 + CI 验证 + 签名 SOP

**📥 你需要提供给 Agent 的文件**:
- 阶段 0-9 产出的所有文件

**Agent 任务**:

| 子任务 | 具体内容 |
|--------|---------|
| 10.1 | 编写 `build.spec`(PyInstaller 配置):
| | - `--onefile` 单文件模式 |
| | - 显式 excludes:`pandas`, `numpy`, `scipy`, `matplotlib`, `PyQt5`, `PySide6`, `PIL` |
| | - datas:打包 `templates/`,`config/`,`src/assets/backup_templates/` |
| | - hiddenimports:`openpyxl.cell._writer`,`ttkbootstrap` 等 |
| 10.2 | 编写 `build_upx.bat`:带 UPX 压缩的打包脚本 |
| 10.3 | 编写 `build_standard.bat`:不带 UPX 的备用打包脚本 |
| 10.4 | 编写 `verify_build.py`:CI 验证脚本
| | - 检查 exe 文件存在且体积 < 50MB |
| | - 在干净环境运行 exe → 检查环境自检是否通过 |
| | - 检查 templates 是否打包进去 |
| 10.5 | 编写 `ci_assert_template_integrity.py`:CI 模板完整性断言(作为合并请求阻断门禁) |
| 10.6 | 编写 `sign_exe.ps1`:代码签名 PowerShell 脚本(使用企业证书) |
| 10.7 | 编写分发 SOP 文档 `docs/DISTRIBUTION.md` |

**✅ 里程碑 10 验证方法**:
```bash
# 1. 打包
build_upx.bat          # 带 UPX 版本
build_standard.bat     # 备用无 UPX 版本

# 2. 验证
python verify_build.py
# 预期输出:
# ✅ dist/CustomsFileGenerator.exe 存在
# ✅ 文件体积:41.2 MB(< 50MB 红线)
# ✅ 环境自检:通过
# ✅ 模板文件:4/4 已打包
# 🚀 构建验证通过

# 3. 人工验证(在干净 Windows 虚拟机或无 Python 环境的电脑上):
# □ 双击 exe 能正常启动 GUI
# □ 录入一份简单订单 → 生成 4 个文件 → 文件可正常打开
# □ 不报缺少 DLL 或 ImportError
```

---

## 📋 阶段依赖关系图

```
阶段 0(骨架+环境自检)
  ↓
阶段 1(数据模型)
  ↓
阶段 2(数据库)
  ↓
阶段 3(XLSX 工具库)  ← 关键!后续所有 xlsx 生成器依赖此阶段
  ↓
阶段 4(装箱单生成器)  ← 可并行:4,5,6 都依赖阶段 3
阶段 5(发票+合同生成器)
阶段 6(报关单生成器 — docx)
  ↓
阶段 7(一键生成+断言)  ← 依赖 4,5,6 全部完成
  ↓
阶段 8(导入器+诊断包)  ← 可与阶段 9 并行
阶段 9(GUI 界面)      ← 可与阶段 8 并行
  ↓
阶段 🔟(打包+CI+签名) ← 依赖所有前序阶段
```

---

## 🔗 附录 A:完整 JSON Schema(Agent 写阶段 1 时必须严格遵循)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "CustomsOrderData",
  "type": "object",
  "required": ["order_meta", "customer", "pallets", "totals"],
  "properties": {
    "order_meta": {
      "type": "object",
      "required": ["invoice_no", "contract_no", "date"],
      "properties": {
        "invoice_no":        {"type": "string", "minLength": 1},
        "contract_no":       {"type": "string", "minLength": 1},
        "order_no":          {"type": "string"},
        "date":              {"type": "string", "format": "date"},
        "transport_mode":    {"type": "string", "enum": ["海运", "空运", "陆运"]},
        "vessel_flight":     {"type": "string"},
        "bill_of_lading_no": {"type": "string"},
        "trade_term":        {"type": "string", "enum": ["FOB", "CIF", "DAP", "DDP", "EXW", "CFR"]},
        "payment_term":      {"type": "string"},
        "currency":          {"type": "string", "default": "USD"},
        "package_type":      {"type": "string", "enum": ["pallet", "carton", "package"]},
        "country_of_origin": {"type": "string", "description": "原产国,装箱单D6"},
        "goods_summary":     {"type": "string", "description": "货品名称摘要,发票B8"},
        "declaration_elements_template": {"type": "string"}
      }
    },
    "customer": {
      "type": "object",
      "required": ["company_name_en", "country"],
      "properties": {
        "company_name_en": {"type": "string"},
        "company_name_cn": {"type": "string"},
        "address":         {"type": "string"},
        "contact_person":  {"type": "string"},
        "phone":           {"type": "string"},
        "mobile":          {"type": "string", "description": "手机号,发票E12"},
        "country":         {"type": "string"},
        "destination":     {"type": "string"}
      }
    },
    "origin": {
      "type": "object",
      "properties": {
        "export_port":      {"type": "string", "default": ""},
        "domestic_source":  {"type": "string", "default": "深圳特区"},
        "manufacturer":     {"type": "string", "default": "长园长通新材料股份有限公司"},
        "business_entity":  {"type": "string", "default": "长园长通新材料股份有限公司"},
        "trade_mode":       {"type": "string", "default": "一般贸易"},
        "tax_nature":       {"type": "string", "default": "一般征税"},
        "settlement_method":{"type": "string", "default": "电汇"},
        "tax_rebate":       {"type": "string", "default": "申请退税"}
      }
    },
    "pallets": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["pallet_no", "length_m", "width_m", "height_m", "pallet_weight_kg", "cartons"],
        "properties": {
          "pallet_no":        {"type": "integer", "minimum": 1},
          "length_m":         {"type": "number", "exclusiveMinimum": 0},
          "width_m":          {"type": "number", "exclusiveMinimum": 0},
          "height_m":         {"type": "number", "exclusiveMinimum": 0},
          "pallet_weight_kg": {"type": "number", "minimum": 0},
          "cartons": {
            "type": "array",
            "minItems": 1,
            "items": {
              "type": "object",
              "required": ["carton_label", "is_batch", "batch_count", "length_cm", "width_cm", "height_cm", "gross_weight_kg", "products"],
              "properties": {
                "carton_label":    {"type": "string"},
                "is_batch":        {"type": "boolean", "default": false},
                "batch_count":     {"type": "integer", "minimum": 1, "default": 1},
                "length_cm":       {"type": "number", "exclusiveMinimum": 0},
                "width_cm":        {"type": "number", "exclusiveMinimum": 0},
                "height_cm":       {"type": "number", "exclusiveMinimum": 0},
                "gross_weight_kg": {"type": "number", "exclusiveMinimum": 0},
                "products": {
                  "type": "array",
                  "minItems": 1,
                  "items": {
                    "type": "object",
                    "required": ["seq_no", "product_name", "hs_code", "unit", "qty_per_carton", "unit_price", "net_weight_per_unit_kg", "destination_country"],
                    "properties": {
                      "seq_no":                 {"type": "integer", "minimum": 1},
                      "product_name":           {"type": "string", "minLength": 1},
                      "specification":          {"type": "string"},
                      "hs_code":                {"type": "string", "minLength": 1},
                      "declaration_elements":   {"type": "string"},
                      "unit":                   {"type": "string", "minLength": 1},
                      "qty_per_carton":         {"type": "number", "minimum": 0},
                      "unit_price":             {"type": "number", "minimum": 0},
                      "currency":               {"type": "string", "default": "USD"},
                      "net_weight_per_unit_kg": {"type": "number", "minimum": 0},
                      "destination_country":    {"type": "string", "minLength": 1}
                    }
                  }
                }
              }
            }
          }
        }
      }
    },
    "totals": {
      "type": "object",
      "required": ["total_pallets", "total_cartons", "total_gross_weight_kg", "total_net_weight_kg", "total_volume_cbm", "total_amount"],
      "properties": {
        "total_pallets":          {"type": "integer", "minimum": 1},
        "total_cartons":          {"type": "integer", "minimum": 1},
        "total_gross_weight_kg":  {"type": "number", "exclusiveMinimum": 0},
        "total_net_weight_kg":    {"type": "number", "exclusiveMinimum": 0},
        "total_volume_cbm":       {"type": "number", "exclusiveMinimum": 0},
        "total_amount":           {"type": "number", "minimum": 0},
        "total_amount_upper":     {"type": "string", "description": "英文大写金额,生成时再填充"}
      }
    },
    "template_meta": {
      "type": "object",
      "properties": {
        "template_name": {"type": "string"},
        "created_at":    {"type": "string", "format": "date-time"},
        "description":   {"type": "string"}
      }
    }
  }
}
```

---

## 🔗 附录 B:XLSX 模板字段映射表(阶段 3–5 必读)

> **说明**:本附录提取自 `报关资料自动生成程序.md`,定义三个 xlsx 模板(装箱单,形式发票,形式合同)中各字段对应的单元格位置,字体字号,格式信息.
> **⚠️ 重要**:下方列出的行号均为**模板出厂时的初始行号**.阶段 3 实现的动态锚点扫描引擎会自动定位数据起始行和汇总行,**生成器代码不得硬编码行号**.
> **真实订单数据参考**:见 `RealOrderData.md`.

---

### B.1 装箱单(Packing List)

**文件格式**:`.xlsx`

#### B.1.1 表头 — 客户与订单信息

| 行 | 字段 | 单元格 | 备注 |
|----|------|--------|------|
| 3 | 客户抬头 | D3:K3 | 合并单元格区域 |
| 4 | 发票号 | D4 | |
| 4 | 日期 | J4:K4 | 合并单元格区域 |
| 5 | 合同号 | D5 | |
| 5 | 付款方式 | J5:K5 | 合并单元格区域 |
| 6 | 原产地 | D6 | |
| 6 | 目的地 | I6:K6 | 合并单元格区域 |

#### B.1.2 商品明细

| 行 | 角色 | 列映射 |
|----|------|--------|
| **7** | **标题行** | (表头,不可删除) |
| **8** | **数据起始行(锚点行)** | A=序号, B:C=商品描述(合并), D=规格, E=单位, F=单箱数量, G=箱数, H=托板号, I=净重(kg), J=毛重(kg), K=体积(m³) |
| 8~57 | 预留数据行 | 共 50 行,锚点扫描定位后按需缩容/扩容 |
| **58** | **汇总行(锚点行)** | G58=总箱数(公式), I58=总净重(公式), J58=总毛重(公式), K58=总体积(公式) |

#### B.1.3 字体字号

| 区域 | 字体 | 字号 |
|------|------|------|
| 表头 | Arial | 11pt |
| 商品明细 | Arial | 12pt |

---

### B.2 形式发票(Proforma Invoice)

**文件格式**:`.xlsx`

#### B.2.1 表头 — 订单与客户信息

| 行 | 字段 | 单元格 | 格式/备注 |
|----|------|--------|-----------|
| 6 | 日期 | D6:F6 | 格式 `Date: MMMM DDth, YYYY`(如 `Date: December 26th, 2025`) |
| 7 | 发票号 | B7:F7 | 合并单元格区域 |
| 8 | 货品名称 | B8:F8 | |
| 9 | 客户抬头 | B9:F9 | 客户公司全称,合并单元格区域 |
| 10 | 客户地址 | B10:F10 | 客户地址全称,合并单元格区域 |
| 11 | 联系人 | B11 | |
| 11 | 电话 | E11:F11 | 合并单元格区域 |
| 12 | 手机号 | E12:F12 | 合并单元格区域 |
| 12 | 装运港 | B12 | |
| 13 | 合同号码 | B13 | |
| 13 | 卸货港 | E13:F13 | 合并单元格区域 |

#### B.2.2 商品明细

| 行 | 角色 | 列映射 |
|----|------|--------|
| **14** | **标题行** | (表头,不可删除) |
| **15** | **数据起始行(锚点行)** | A=产品(Product), B=规格(Specification), C=单位(Unit), D=数量(Qty), E=单价(Unit Price), F=金额(Amount) |
| 15~64 | 预留数据行 | 共 50 行,锚点扫描定位后按需缩容/扩容 |
| **65** | **汇总行(锚点行)** | E65:F65=总金额小写(公式), A66:F66=总金额大写(公式/N/A) |

#### B.2.3 字体字号

| 区域 | 字体 | 字号 | 样式 |
|------|------|------|------|
| 表头-日期 | Times New Roman | 14pt | |
| 表头-其他 | Times New Roman | 16pt | **加粗** |
| 商品明细 | Times New Roman | 14pt | |
| 汇总行 | Times New Roman | 16pt | |

---

### B.3 形式合同(Sales Contract)

**文件格式**:`.xlsx`

#### B.3.1 表头 — 订单信息

| 行 | 字段 | 单元格 | 格式/备注 |
|----|------|--------|-----------|
| 3 | 抬头人(客户公司名) | C3:G3 | 合并单元格区域 |
| 4 | 发票号 | C4 | |
| 4 | 日期 | G4 | |
| 5 | 合同号 | C5 | |
| 6 | 订单号 | C6 | |
| 6 | 发货口岸 | D6:G6 | 格式 `From {装运港} To {卸货港}`(如 `From Shenzhen To Ankara`) |

#### B.3.2 商品明细

| 行 | 角色 | 列映射 |
|----|------|--------|
| **7** | **标题行** | (表头,不可删除) |
| **8** | **数据起始行(锚点行)** | A=序号(No.), B=产品(Product), C=规格(Specification), D=单位(Unit), E=数量(Qty), F=单价(Unit Price), G=金额(Amount) |
| 8~57 | 预留数据行 | 共 50 行,锚点扫描定位后按需缩容/扩容 |
| **58** | **汇总行(锚点行)** | F58:G58=总金额小写(公式), A59:G59=总金额大写(公式/N/A) |

#### B.3.3 字体字号

| 区域 | 字体 | 字号 | 样式 |
|------|------|------|------|
| 表头 | Times New Roman | 14pt | **加粗** |
| 商品明细 | Times New Roman | 12pt | |
| 汇总行 | Times New Roman | 12pt | |

---

> **Agent 执行提醒**:
> 1. 每个阶段开始前,先读取该阶段的"你需要提供给 Agent 的文件"清单,确认用户已提供
> 2. 每个阶段结束后,主动运行里程碑验证命令,确认通过后再告知用户该阶段完成
> 3. 如果用户说"继续下一阶段",自动进入下一阶段,不需要用户重新描述上下文
> 4. 所有生成的代码必须符合根 `Claude.md` 的硬约束卡要求
