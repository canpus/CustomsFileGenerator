# GUI 现代化与报关资料生成系统重构计划

## 1. 总体结论

当前项目不建议推倒重写，应采用 **保留核心、重构边界、分阶段修复** 的策略。

需要保留的核心价值：

- 真实 XLSX 模板适配经验
- `OrderData` 数据模型
- 现有 3 文件生成链路
- SQLite Repository 基础
- 已恢复的测试集
- 当前生成文件的数据区填充逻辑

需要重点重构的部分：

- XLSX 模板数据区容量识别
- 表头字段填充逻辑
- GUI 视觉风格
- 商品录入方式
- 客户库、产品库、分块模板复用
- 草稿保存与恢复
- 窗口状态记忆

---

## 2. 模板策略

### 2.1 是否需要创建 20/50/100 行模板

需要创建。

建议在 `templates/` 中准备三种容量模板：

```text
template_invoice_20.xlsx
template_invoice_50.xlsx
template_invoice_100.xlsx

template_contract_20.xlsx
template_contract_50.xlsx
template_contract_100.xlsx

template_packing_20.xlsx
template_packing_50.xlsx
template_packing_100.xlsx
```

当前已有模板可作为 50 行版本的基准。

### 2.2 模板制作原则

以形式发票为例：

- 商品明细区从第 15 行开始。
- 50 行模板中，第 15 到第 64 行为预留数据区。
- 第 65 行为汇总行。
- 如果实际填充 N 行，则：
  - 填充第 15 到第 `15 + N - 1` 行。
  - 删除第 `15 + N` 到第 64 行。
  - 汇总行自动上移。
  - SUM 公式范围自动修正。

程序不应再通过“遇到第一个空行”判断数据区结束。

### 2.3 自动选择模板规则

生成前先计算明细行数：

- `rows <= 20`：选择 20 行模板
- `21 <= rows <= 50`：选择 50 行模板
- `51 <= rows <= 100`：选择 100 行模板
- `rows > 100`：阻断生成，提示用户拆单或新增更大模板

初版不自动扩行，不自动拆分文件。

---

## 3. 生成器修改计划

### 3.1 需要修改的文件

```text
config/template_rules.json
config/constants.py
src/generators/template_anchor_scanner.py
src/generators/xlsx_utils.py
src/generators/base_generator.py
src/generators/invoice_generator.py
src/generators/contract_generator.py
src/generators/packing_generator.py
src/generators/orchestrator.py
```

### 3.2 修改内容

- 在 `template_rules.json` 中显式配置：
  - 模板类型
  - 模板容量
  - 数据起始行
  - 预留数据结束行
  - 汇总行
  - 公式列
- `template_anchor_scanner.py` 不再估算空白预留区结束位置。
- `xlsx_utils.py` 增加固定预留区删除逻辑。
- `base_generator.py` 增加模板容量选择流程。
- 三个生成器修正表头填充：
  - 模板已有字段名时，只写字段值。
  - 不再写 `Invoice No.: 20251202-01` 这类拼接文本。
- `orchestrator.py` 汇总容量不足错误，并阻断生成。

---

## 4. GUI 重构计划

### 4.1 技术路线

继续使用：

```text
tkinter + ttkbootstrap
```

不切换 PySide6，也不引入 Web 前端。

原因：

- 当前项目已基于 tkinter 实现。
- 打包体积和复杂度可控。
- 初版目标是 Windows 单用户 EXE。
- 迁移 GUI 技术栈会显著增加风险。

### 4.2 视觉目标

改为 **现代简洁业务工具风格**：

- 不再使用 Windows98 风格布局。
- 减少 Emoji。
- 使用统一字体、间距、颜色、按钮样式。
- 页面结构统一为：
  - 顶部标题/工具栏
  - 主内容区
  - 底部状态区
- 强调信息密度和录入效率。
- 不做营销式页面，不做装饰性卡片堆叠。

### 4.3 需要新增的 GUI 文件

```text
src/gui/styles.py
src/gui/components/editable_table.py
src/gui/pages/line_item_table_page.py
src/gui/pages/customer_page.py
src/gui/pages/product_page.py
src/gui/services/preferences_service.py
src/gui/services/draft_service.py
src/gui/services/template_block_service.py
```

### 4.4 需要修改的 GUI 文件

```text
src/gui/app.py
src/gui/pages/tree_editor_page.py
src/gui/pages/template_page.py
src/gui/pages/order_info_page.py
src/gui/pages/generate_page.py
```

---

## 5. 商品录入重构

### 5.1 当前问题

当前树状录入方式是：

```text
托盘 -> 纸箱 -> 商品
```

问题：

- 高频录入效率低。
- 多订单复制困难。
- 商品信息重复输入严重。
- 不适合从 Excel 或历史订单中批量迁移。

### 5.2 新方案

新增单表格录入页，作为主流程。

每一行代表一个商品/纸箱组合，字段包括：

```text
托盘号
纸箱号
是否批量箱
批量箱数
长
宽
高
毛重
商品名称
规格型号
HS Code
申报要素
单位
每箱数量
单价
币种
单件净重
目的国
```

支持：

- 复制行
- 删除行
- 批量粘贴
- 批量填充列
- 从产品库插入商品
- 自动汇总毛重、净重、体积、金额
- 转换为 `OrderData`

旧 `tree_editor_page.py` 暂时保留为辅助层级视图，不作为主录入入口。

---

## 6. 客户库、产品库与分块模板

### 6.1 客户库

新增 `customer_page.py`。

功能：

- 新增客户
- 编辑客户
- 删除客户
- 搜索客户
- 选择客户并套用到当前订单
- 保存当前订单客户信息到客户库

底层复用现有 `CustomerRepository`。

### 6.2 产品库

新增 `product_page.py`。

功能：

- 新增产品
- 编辑产品
- 删除产品
- 按商品名搜索
- 按 HS Code 搜索
- 选择产品并插入到商品表格
- 保存当前表格中的商品到产品库

底层复用现有 `ProductRepository`。

### 6.3 分块模板

新增模板块能力。

支持保存和套用：

```text
客户信息
商品信息
装运信息
整单模板
```

套用时必须允许用户选择覆盖范围：

- 只套用客户信息
- 只套用商品信息
- 只套用装运信息
- 套用整单
- 多项组合套用

未选择的字段不得被覆盖。

---

## 7. 草稿恢复与窗口状态

### 7.1 窗口状态记忆

新增 `preferences_service.py`。

保存：

```text
窗口宽度
窗口高度
窗口位置
是否最大化
最近输出目录
最近导入目录
```

启动时自动恢复。

### 7.2 关闭确认

`GuiApp` 增加 `WM_DELETE_WINDOW` 拦截。

如果存在未保存变更：

- 弹窗确认关闭。
- 提供保存草稿选项。
- 用户确认后才退出。

### 7.3 草稿自动保存

新增 `draft_service.py`。

保存内容：

```text
订单基础信息
客户信息
装运信息
商品表格数据
当前页面
更新时间
```

启动时检测草稿：

- 恢复草稿
- 忽略本次
- 删除草稿

---

## 8. 数据库修改计划

### 8.1 需要修改

```text
src/db/schema.sql
src/db/repository.py
```

### 8.2 新增模板块表

建议新增表：

```text
template_blocks
```

字段方向：

```text
id
block_type
block_name
block_json
description
created_at
updated_at
is_deleted
```

`block_type` 可选：

```text
customer
product_set
shipping
order_full
```

---

## 9. 测试计划

### 9.1 生成器测试

新增或修改测试：

```text
tests/test_template_anchor_scanner.py
tests/test_template_capacity.py
```

覆盖：

- 3 行数据
- 20 行数据
- 21 行数据
- 50 行数据
- 51 行数据
- 100 行数据
- 101 行数据

验证：

- 自动选择正确容量模板
- 删除正确预留行
- 汇总行位置正确
- SUM 公式范围正确
- 表头字段没有重复标签

### 9.2 GUI 数据转换测试

新增：

```text
tests/test_line_item_table.py
```

覆盖：

- 表格行转换为 `OrderData`
- 托盘/纸箱/商品层级正确
- 批量箱数计算正确
- 重量、体积、金额汇总正确

### 9.3 信息库测试

新增：

```text
tests/test_template_blocks.py
```

覆盖：

- 客户块保存/套用
- 商品块保存/套用
- 装运块保存/套用
- 整单模板保存/套用
- 未选择字段不被覆盖

### 9.4 草稿测试

新增：

```text
tests/test_draft_service.py
```

覆盖：

- 草稿保存
- 草稿恢复
- 草稿删除
- 草稿损坏时降级处理

---

## 10. 实施顺序

### 第一阶段：生成器准确性修复

目标：

- 修复预留空行删除。
- 修复表头标签和值混写。
- 增加容量模板选择。

验收：

- 3 文件生成结果格式正确。
- 发票 3 行数据时删除第 18 到 64 行。
- B7:F7 只显示发票号。

### 第二阶段：GUI 现代化基础

目标：

- 建立统一样式。
- 重做主窗口布局。
- 保存窗口大小和位置。
- 关闭时弹窗确认。

验收：

- 界面不再呈现 Windows98 风格。
- 重启后窗口状态保持。
- 有未保存数据时关闭会提示。

### 第三阶段：单表格商品录入

目标：

- 新增表格录入页。
- 支持批量录入和复制。
- 能转换为 `OrderData`。

验收：

- 用户可用表格完成订单商品录入。
- 不再必须逐层展开托盘/纸箱/商品。

### 第四阶段：客户库和产品库

目标：

- 客户管理页可用。
- 产品管理页可用。
- 订单录入和商品表格可直接套用。

验收：

- 同一客户多订单不需要重复输入客户信息。
- 常用产品可直接插入商品表格。

### 第五阶段：分块模板与草稿恢复

目标：

- 支持客户/商品/装运/整单分块模板。
- 支持自动草稿保存和恢复。

验收：

- 同一客户 4 个订单、3 个港口场景可高效复用。
- 意外关闭后可恢复未完成订单。

---

## 11. 明确不做的事项

初版不做：

- DOCX 报关单生成
- 多用户共享数据库
- 自动拆分超过 100 行的大订单
- 自动扩展超过模板容量的数据区
- GUI 技术栈迁移到 PySide6 或 Web 前端

---

## 12. 默认假设

- 20/50/100 行模板的表头和汇总结构一致。
- 只有商品明细预留行数量不同。
- 当前 50 行模板可作为制作其他容量模板的基准。
- 单用户 Windows EXE 仍是初版目标。
- 旧树状编辑器暂时保留，确认表格录入稳定后再决定是否删除。
