# revPlan_v1.md — AI 可执行的分阶段改进行动计划

> **版本**: 1.0.0
> **编制日期**: 2026-05-27
> **数据来源**: [改进计划.md](改进计划.md) (Code Review) + [gui_xlsx_refactor_plan.md](gui_xlsx_refactor_plan.md) (GUI 重构计划)
> **使用方法**: 按优先级从 P0→P8 依次执行。每个优先级内的问题可并行处理（除非标注⚠️耦合组）。

---

# ⚠️ 全文耦合警告（执行前必读）

以下耦合组内的问题**必须在一个对话窗口中一起修复**，因为它们修改相同的文件、相同的函数、或存在强依赖关系：

| 耦合组 | 包含问题 | 冲突原因 |
|--------|----------|----------|
| **A** | P04 + P01 + P08/P16 | 都修改 `base_generator.py` + `packing_generator.py`，P01 重构后的代码如不包含 P04 的修复，裸 except 仍残留；P08 提取到基类的方法依赖 P01 完成后的类层次 |
| **B** | P15 + P07 | P15 统一 TradeTerm/TransportMode 类型定义，P07 将 GUI 层 `Any` 改为具体类型，类型来源依赖 P15 的统一结果 |
| **C** | P05 + P06 + P13 | P05 拆分大文件后 import 路径变更，P06 消除循环导入依赖拆分后的文件结构；P13 修改的 `order_info_page.py` 也在 P05/P06 的修改范围内 |
| **D** | 模板容量 + 生成器功能 | `template_rules.json` + `base_generator.py` + 3 个子生成器 + `orchestrator.py` + `xlsx_utils.py` 联动修改 |
| **E** | GUI 现代化 | `styles.py` + `app.py` + 全部 page 文件联动，样式定义和布局重构不可拆分 |
| **F** | 商品录入重构 | `editable_table.py` + `line_item_table_page.py` + `app.py` 导航联动 |
| **G** | 客户库/产品库 | `customer_page.py` + `product_page.py` + `schema.sql` + `repository.py` 联动 |
| **H** | 分块模板/草稿 | `template_block_service.py` + `draft_service.py` + `app.py` 生命周期联动 |

**如果你的对话窗口足够大**（>200K tokens），可以将 P0+P1+P2 三个优先级合并到一个窗口执行。

---

# 优先级 P0 — 独立紧急修复（零耦合，3 个问题可并行）

> **总预估**: ~15 分钟
> **风险**: 零（单行/单文件改动）
> **可拆分**: 是（每个问题可独立在一个对话窗口中执行）

---

### 问题 P02 — `num2words` 未列入 `requirements.txt`

**严重程度**: 🔴 严重
**耦合**: 无
**描述**: `num2words` 被 `invoice_generator.py:400` 导入用于金额大写转换，当前代码有 `ImportError` 降级处理，但作为运行时必需依赖不应缺失。新环境部署时功能静默降级。

**需修改文件 1**: `requirements.txt`

**文件修改办法**:
1. 在 `requirements.txt` 中 `python-dotenv==1.0.1` 行之后，添加一行：
   ```
   num2words==0.5.14
   ```
2. 建议插入位置：第 25 行（`python-dotenv` 和 `pytest` 之间），并添加注释 `# ========== 金额大写转换 ==========`

**验收**: `pip install -r requirements.txt` 在新虚拟环境中执行后，`python -c "from num2words import num2words"` 不报错。

---

### 问题 P14 — `add_warning()` 错误地将 `passed=False`

**严重程度**: 🔴 严重
**耦合**: 无
**描述**: `src/models/validators.py:81-84` — `add_warning()` 方法中 `self.passed = False` 导致 WARNING 级别消息（如 W001 毛重<净重）也让 `report.passed = False`。根据 validator 文档语义，只有 `error` 级别才应导致不通过。

**需修改文件 1**: `src/models/validators.py`

**文件修改办法**:
1. 定位到第 81-84 行的 `add_warning()` 方法
2. 删除第 83 行的 `self.passed = False`
3. 修改后的方法应为：
```python
def add_warning(self, code: str, message: str, reason: str, solution: str) -> None:
    """添加一条 warning 级别消息."""
    self.messages.append(ValidationMessage("warning", code, message, reason, solution))
```

**验收**: 运行 validator 后，仅有 WARNING 级别消息时 `report.passed` 为 `True`；有 ERROR 级别消息时才为 `False`。

---

### 问题 P11 — 临时调试脚本未清理

**严重程度**: 🟢 轻微
**耦合**: 无
**描述**: 项目根目录存在两个临时调试脚本 `_check_template.py` 和 `_check_templates2.py`，不应留在版本控制中。

**需修改文件**: 无（仅删除操作）

**文件修改办法**:
1. 删除 `_check_template.py`
2. 删除 `_check_templates2.py`

**验收**: 项目根目录不再包含 `_check_template` 开头的文件。

---

# 优先级 P1 — 生成器链修复

> **总预估**: 2-4 小时
> **注意**: P04 + P01 + P08/P16 组成 ⚠️**耦合组 A**，必须在一个对话窗口中连续修复。P12 独立可并行。

---

## ⚠️ 耦合组 A：生成器继承体系重构（P04 + P01 + P08/P16）

> **必须同一对话窗口执行！** 三个问题都修改 `base_generator.py` + `packing_generator.py`，相互依赖。
> **执行顺序**: 先 P04（最小改动打底）→ 再 P01（重构继承）→ 最后 P08/P16（提取公共方法）

---

### 问题 P04 — `wb.close()` 裸 except 块无日志

**严重程度**: 🔴 严重
**耦合**: 与 P01 耦合（修改相同文件相同区域）
**描述**: `base_generator.py:176-179` 和 `packing_generator.py:266-271` 的内层 `except Exception: pass` 完全静默吞掉 `wb.close()` 失败异常，可能导致资源泄漏且无迹可查。

**需修改文件 1**: `src/generators/base_generator.py`

**文件修改办法**:
1. 定位到第 175-179 行：
```python
        except Exception:
            try:
                wb.close()
            except Exception:
                pass
            raise
```
2. 将内层 `except Exception: pass` 改为 `except Exception: logger.warning(...)`：
```python
        except Exception:
            try:
                wb.close()
            except Exception as close_err:
                logger.warning("[警告]: 工作簿关闭失败: %s", close_err)
            raise
```

**需修改文件 2**: `src/generators/packing_generator.py`

**文件修改办法**:
1. 定位到第 266-271 行，做完全相同的修改：
```python
        except Exception:
            # 确保出错时关闭工作簿
            try:
                wb.close()
            except Exception as close_err:
                logger.warning("[警告]: 工作簿关闭失败: %s", close_err)
            raise
```

**验收**: 异常路径下 `wb.close()` 再次失败时，日志中可见 WARNING 级别记录。

---

### 问题 P01 — `PackingGenerator` 未继承 `BaseGenerator`

**严重程度**: 🔴 严重
**耦合**: 与 P04 + P08/P16 强耦合
**描述**: `PackingGenerator`（阶段 4 编写）未继承 `BaseGenerator`（阶段 5 抽象），导致 ~180 行重复代码（沙箱管理、进度回调、输出路径解析、generate 流程）。对比 `InvoiceGenerator(BaseGenerator)` 和 `ContractGenerator(BaseGenerator)` 已经正确继承。

**当前状态**:
- `class PackingGenerator:` (packing_generator.py:135) — 独立类，无继承
- `class InvoiceGenerator(BaseGenerator):` (invoice_generator.py:113) — 正确继承
- `class ContractGenerator(BaseGenerator):` (contract_generator.py:39) — 正确继承

**需修改文件 1**: `src/generators/packing_generator.py`

**文件修改办法**（核心步骤，详细执行时参考 `InvoiceGenerator` 的实现模式）:

**步骤 1** — 修改 import：
- 添加 `from src.generators.base_generator import BaseGenerator`
- 添加 `from src.generators.xlsx_utils import safe_write_cell, update_sum_formula`（如果当前缺少）
- 确认已有 `from pathlib import Path` 和 `from typing import Callable`

**步骤 2** — 修改类声明：
- 将 `class PackingGenerator:` 改为 `class PackingGenerator(BaseGenerator):`

**步骤 3** — 删除与 BaseGenerator 重复的方法（约 180 行）：
- 删除 `__init__` 方法（BaseGenerator 已提供，含 `_template_path` 初始化）
- 删除 `_create_sandbox_copy` 方法（BaseGenerator 已提供）
- 删除 `_cleanup_sandbox` 方法（BaseGenerator 已提供）
- 删除 `_resolve_output_path` 方法（BaseGenerator 已提供）
- 删除 `_report_progress` 方法（BaseGenerator 已提供）
- 删除 `generate` 方法（BaseGenerator 已提供统一流程）
- 保留 `_get_default_template_path` — 但需要加 `@property` 装饰器（参考 InvoiceGenerator）

**步骤 4** — 将已有方法对齐到 BaseGenerator 接口：
- `_flatten_data(order)` — 保留（已存在，逻辑正确）
- `scan_packing_template(ws)` → 改为 `_scan_anchor(ws, rules)` 或保留调用
- `_fill_packing_header(ws, order)` → 保留，重命名为 `_fill_header(ws, order)`
- `_fill_data_rows(ws, data_start_row, rows, anchor)` → 保留（需确认签名匹配）
- `_fix_summary_formulas(ws, anchor, new_data_end)` → 保留（需确认签名匹配）
- `_get_display_name()` → 实现返回 `"装箱单"`
- `_get_template_type()` → 实现返回 `"packing"`

**步骤 5** — 验证：
- 对比修改后的 `PackingGenerator` 与 `InvoiceGenerator` 的结构一致性
- 确保所有 `self._xxx` 调用在 BaseGenerator 中均有定义

**验收**: 
- `PackingGenerator` 类代码从 ~350 行减少到 ~170 行（仅保留打包特有逻辑）
- 运行现有生成流程，装箱单输出与重构前完全一致

---

### 问题 P08/P16 — `_find_actual_summary_row` 在 invoice/contract 中重复

**严重程度**: 🟡 中等
**耦合**: 与 P01 耦合（P01 完成后 BaseGenerator 接口才稳定，此时提取公共方法才有意义）
**描述**: `_find_actual_summary_row()` 方法在 `invoice_generator.py:342` 和 `contract_generator.py:221` 几乎完全相同（仅搜索关键词不同），应提取到 `BaseGenerator`。

**需修改文件 1**: `src/generators/base_generator.py`

**文件修改办法**:
1. 在 `BaseGenerator` 类中添加 `_find_actual_summary_row()` 方法，接受关键词参数：
```python
def _find_actual_summary_row(
    self, ws: Worksheet, anchor: AnchorResult, keywords: list[str]
) -> int:
    """在锚点附近搜索实际的汇总行位置。
    
    从锚点标记的汇总行开始，向下搜索包含指定关键词的行。
    
    Args:
        ws: 工作表对象
        anchor: 锚点扫描结果
        keywords: 用于识别汇总行的关键词列表
        
    Returns:
        实际汇总行号（1-based）
    """
    search_start: int = anchor.summary_row
    search_end: int = min(search_start + 20, ws.max_row or search_start + 20)
    
    for row in range(search_start, search_end + 1):
        for col in range(1, ws.max_column + 1):
            cell_value = str(ws.cell(row=row, column=col).value or "")
            for keyword in keywords:
                if keyword in cell_value:
                    return row
    return anchor.summary_row
```

**需修改文件 2**: `src/generators/invoice_generator.py`

**文件修改办法**:
1. 删除现有的 `_find_actual_summary_row` 方法（约 340-378 行）
2. 在调用处改为 `self._find_actual_summary_row(ws, anchor, keywords=["TOTAL", "Total", "合计"])`
3. 更新调用点（约第 309 行）

**需修改文件 3**: `src/generators/contract_generator.py`

**文件修改办法**:
1. 删除现有的 `_find_actual_summary_row` 方法（约 221-256 行）
2. 在调用处改为 `self._find_actual_summary_row(ws, anchor, keywords=["TOTAL", "Total", "合计"])`
3. 更新调用点（约第 188 行）

**验收**: 发票和合同生成结果与重构前完全一致；两个子类均不再包含 `_find_actual_summary_row` 方法定义。

---

### 问题 P12 — `os.startfile()` 仅适用于 Windows

**严重程度**: 🟢 轻微
**耦合**: 无（独立问题）
**描述**: `src/gui/pages/generate_page.py:443` 使用 `os.startfile()` 打开文件夹，这是 Windows 专有 API，macOS/Linux 上会抛出 `AttributeError`。

**需修改文件 1**: `src/gui/pages/generate_page.py`

**文件修改办法**:
1. 在文件顶部 import 区域添加 `import sys` 和 `import subprocess`（如果尚未导入）
2. 定位到第 443 行 `os.startfile(str(zip_path.parent))`
3. 替换为跨平台实现：
```python
import sys
import subprocess

def _open_directory(path: str) -> None:
    """跨平台打开文件夹."""
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])
```
4. 将 `os.startfile(str(zip_path.parent))` 替换为 `_open_directory(str(zip_path.parent))`
5. 检查同一文件中是否还有其他 `os.startfile` 调用（如 `_on_open_folder` 方法），一并替换

**验收**: Linux/macOS 环境下点击"打开文件夹"不报 `AttributeError`。

---

# 优先级 P2 — 类型系统统一

> **总预估**: 2-3 小时
> **注意**: P15 + P07 组成 ⚠️**耦合组 B**。P03、P09、P10 独立。

---

## ⚠️ 耦合组 B：类型定义统一（P15 + P07）

> **必须同一对话窗口执行！** P15 先统一类型来源，P07 随后使用统一后的类型。
> **执行顺序**: 先 P15（统一类型定义）→ 再 P07（GUI 类型精确化）

---

### 问题 P15 — `TradeTerm` / `TransportMode` 类型定义重复

**严重程度**: 🟡 中等
**耦合**: 与 P07 耦合（P07 依赖统一后的类型）
**描述**: 
- `src/models/order_data.py:17` 定义 `TradeTerm = Literal["FOB", "CIF", "DAP", "DDP", "EXW", "CFR"]`（TYPE）
- `config/constants.py:67-74` 定义 `class TradeTerm(str, Enum): FOB="FOB", ...`（CLASS）
- `order_data.py:22` 定义 `TransportMode = Literal["海运", "空运", "陆运"]`（中文值）
- `config/constants.py:86-91` 定义 `class TransportMode(str, Enum): SEA="SEA", AIR="AIR", RAIL="RAIL", TRUCK="TRUCK"`（英文码）

**关键发现**: TransportMode 的两套值**完全不同**（中文 vs 英文码），不可简单替换。需要决策：是统一使用中文枚举还是英文枚举。

**决策建议**: 
- `TradeTerm` 的 Literal 值和 Enum 值完全一致 → 直接统一到 Enum
- `TransportMode` 的两套值不同 → **保留两套**，在 `constants.py` 中新增 `TransportModeCN`（中文枚举）供 `order_data.py` 使用，或在 `order_data.py` 中改为从 Enum 取值生成 Literal

**需修改文件 1**: `config/constants.py`

**文件修改办法**:
1. 在现有 `TransportMode` 枚举旁边新增中文运输方式枚举：
```python
class TransportModeCN(str, Enum):
    """运输方式（中文显示值）."""
    SEA = "海运"
    AIR = "空运"
    LAND = "陆运"
```
注意：原 `TransportMode` 保留不动（英文码供外部接口使用）。

**需修改文件 2**: `src/models/order_data.py`

**文件修改办法**:
1. 删除第 17 行的 `TradeTerm = Literal["FOB", "CIF", "DAP", "DDP", "EXW", "CFR"]`
2. 删除第 22 行的 `TransportMode = Literal["海运", "空运", "陆运"]`
3. 在文件顶部添加导入：
```python
from config.constants import TradeTerm, TransportModeCN as TransportMode
```
4. 第 137 行的 `trade_term: TradeTerm` 保持不变（现在引用的是 Enum 类型）
5. 第 142 行的 `transport_mode: TransportMode = msgspec.field(default="海运")` 需要确认默认值是否与 Enum 成员匹配

**需修改文件 3**: `src/importer/excel_importer.py`

**文件修改办法**:
1. 确认第 26 行 `from config.constants import ... TradeTerm ...` 仍然正确（已经从 constants 导入 Enum）
2. 如果导入列表中缺少 `TransportMode`，根据使用情况决定导入英文 Enum 还是中文 Enum

**需修改文件 4**: `src/utils/data_sanitizer.py`

**文件修改办法**:
1. 第 38-39 行 `from src.models.order_data import ... TradeTerm, TransportMode ...` 
2. 改为 `from config.constants import TradeTerm, TransportModeCN as TransportMode`
3. 验证脱敏函数中 `isinstance` 检查仍然正确

**需修改文件 5**: `src/gui/pages/order_info_page.py`

**文件修改办法**:
1. 第 25-26 行 `from config.constants import ... TradeTerm, TransportMode ...` 确认正确（已从 constants 导入）
2. 如果 GUI 需要中文运输方式下拉选项，使用 `TransportModeCN`；如果使用英文，用 `TransportMode`

**验收**: 
- 全项目搜索 `TradeTerm` 仅 `config/constants.py` 一处定义
- `TransportMode` 分英文（`TransportMode`）/中文（`TransportModeCN`）两套 Enum
- `order_data.py` 不再包含 Literal 类型别名
- 现有导入和生成流程不报错

---

### 问题 P07 — GUI 层大量 `Any` 类型（应使用 `OrderData | None`）

**严重程度**: 🟡 中等
**耦合**: 与 P15 耦合（依赖 P15 完成后的类型来源）
**描述**: GUI 层多处使用 `Any` 而非具体的 `OrderData` 类型，失去了类型检查保护。

**涉及文件及修改办法**:

**需修改文件 1**: `src/gui/app.py`

**文件修改办法**:
1. 定位到第 383-384 行附近的 `current_order` property
2. 将返回类型从 `Any` 改为 `OrderData | None`：
```python
from src.models.order_data import OrderData

@property
def current_order(self) -> OrderData | None:
    ...
```

**需修改文件 2**: `src/gui/pages/order_info_page.py`

**文件修改办法**:
1. 定位到第 559 行附近的 `_fill_from_order` 方法
2. 将 `order: Any` 改为 `order: OrderData`

**需修改文件 3**: `src/gui/pages/generate_page.py`

**文件修改办法**:
1. 定位到第 238 行附近的 `_do_generate` 方法
2. 将 `order: Any` 改为 `order: OrderData`

**需修改文件 4**: `src/gui/pages/tree_editor_page.py`

**文件修改办法**:
1. 定位到第 777 行附近的 `build_order_data` 方法
2. 将返回类型从 `Any | None` 改为 `OrderData | None`

**验收**: 所有 GUI 层公共方法的参数/返回值类型标注中不再出现 `Any`（指 OrderData 相关部分）；IDE 类型检查通过。

---

### 问题 P03 — `num2words` 降级链路不完善

**严重程度**: 🔴 严重
**耦合**: 无（独立问题，但与 P02 关联 — P02 安装依赖后 ImportError 路径基本不会触发）
**描述**: `invoice_generator.py:419-431` — `except ImportError` 静默返回降级字符串，`except Exception` 也返回降级字符串。调用方无法区分"正常降级"和"转换失败"。

**需修改文件 1**: `src/generators/invoice_generator.py`

**文件修改办法**:
1. 定位到第 399-431 行的 `_amount_to_words` 函数
2. 修改 `except ImportError` 块（第 419-423 行）：记录 error 级别日志（而非 warning），因为这是环境配置问题
3. 修改 `except Exception` 块（第 424-431 行）：将 `logger.error` 改为 `raise`，因为转换逻辑异常不应静默降级：
```python
    except ImportError:
        logger.error(
            "[错误]: num2words 未安装，金额大写转换不可用\n"
            "[原因]: 缺少运行时依赖\n"
            "[排查]: 执行 pip install num2words==0.5.14"
        )
        return f"USD {amount:,.2f}"
    except Exception:
        logger.exception(
            "[错误]: 金额大写转换失败\n"
            "[原因]: num2words 内部错误，金额=%.2f\n"
            "[排查]: 请检查金额数值是否在合理范围内",
            amount,
        )
        raise ValueError(
            f"金额大写转换失败: {amount}, 请检查 num2words 版本和金额数值"
        ) from None
```

**验收**: 
- `num2words` 未安装时降级返回数字格式 + error 日志
- `num2words` 转换逻辑异常时抛出 `ValueError`（不被静默吞掉）

---

### 问题 P09 — 单例模式缺线程锁

**严重程度**: 🟡 中等
**耦合**: 无
**描述**: `src/generators/orchestrator.py:328-340` — `get_orchestrator()` 模块级单例在多线程首次调用存在竞态条件。

**需修改文件 1**: `src/generators/orchestrator.py`

**文件修改办法**:
1. 在文件顶部 import 区域添加 `import threading`
2. 定位到第 328 行 `_DEFAULT_ORCHESTRATOR: Orchestrator | None = None`
3. 在其后添加 `_ORCHESTRATOR_LOCK = threading.Lock()`
4. 修改 `get_orchestrator()` 函数（第 331-340 行）：
```python
def get_orchestrator() -> Orchestrator:
    """获取默认协调器单例（线程安全）."""
    global _DEFAULT_ORCHESTRATOR
    if _DEFAULT_ORCHESTRATOR is None:
        with _ORCHESTRATOR_LOCK:
            if _DEFAULT_ORCHESTRATOR is None:
                _DEFAULT_ORCHESTRATOR = Orchestrator()
    return _DEFAULT_ORCHESTRATOR
```

**验收**: 多线程同时首次调用 `get_orchestrator()` 不会创建多个实例。

---

### 问题 P10 — SQL 列名 f-string 拼接（低风险，加注释即可）

**严重程度**: 🟡 中等
**耦合**: 无
**描述**: `src/db/repository.py:156-163` — 列名通过 f-string 拼入 SQL，虽然有 `allowed` set 白名单过滤，但不符合"禁止拼接 SQL 字符串"的绝对禁令。

**需修改文件 1**: `src/db/repository.py`

**文件修改办法**:
1. 定位到第 146-163 行
2. 在 `allowed` 变量定义前添加安全边界注释：
```python
        # 安全边界：updates 的 key 已经过 allowed set 白名单过滤，
        # 仅包含已知安全列名（company_name_en 等 8 个字段），
        # 不存在 SQL 注入风险。
        allowed = {
```
3. `set_clause` 行的 f-string 维持不变

**验收**: 代码审查时安全边界的注释清晰可见。

---

# 优先级 P3 — 大文件拆分与导入规范

> **总预估**: 4-8 小时
> **注意**: P05 + P06 + P13 组成 ⚠️**耦合组 C**，强烈建议同一对话窗口执行。

---

## ⚠️ 耦合组 C：文件拆分与导入清理（P05 + P06 + P13）

> **建议同一对话窗口执行！** P05 拆分文件改变 import 路径，P06 随即清理导入；P13 修改的 `order_info_page.py` 在 P05/P06 扫描范围。

---

### 问题 P05 — 8 个文件超 300 行限制

**严重程度**: 🟡 中等
**耦合**: 与 P06 强耦合
**描述**: 以下文件超过 CLAUDE.python.md 规定的 300 行上限：

| 文件 | 当前行数 | 超出 |
|------|----------|------|
| `src/gui/pages/tree_editor_page.py` | 1136 | +836 |
| `src/importer/excel_importer.py` | 908 | +608 |
| `src/generators/template_anchor_scanner.py` | 732 | +432 |
| `src/gui/pages/order_info_page.py` | 651 | +351 |
| `src/db/repository.py` | 632 | +332 |
| `src/generators/xlsx_utils.py` | 452 | +152 |
| `src/gui/pages/generate_page.py` | 513 | +213 |
| `src/generators/template_assertion.py` | 516 | +216 |

**拆分策略**（按优先级，优先处理最大的 3 个）:

---

**需拆分文件 1**: `src/gui/pages/tree_editor_page.py` (1136 行 → ≤500×3)

**文件修改办法**:
1. 分析现有代码结构，识别三类功能：
   - **数据操作**：`build_order_data()`、树节点遍历、OrderData 构建逻辑
   - **UI 构建**：Treeview 创建、列配置、右键菜单、拖拽绑定
   - **事件处理**：新增/删除/编辑节点、剪切/复制/粘贴、拖拽回调
2. 创建 `src/gui/pages/tree_data.py` — 迁移所有数据操作函数（约 300 行）
3. 创建 `src/gui/pages/tree_ui.py` — 迁移所有 UI 构建方法（约 400 行）
4. 创建 `src/gui/pages/tree_events.py` — 迁移所有事件处理方法（约 400 行）
5. `tree_editor_page.py` 保留为薄壳，从三个子模块导入并组合
6. 更新 `src/gui/app.py` 中的 import 路径

---

**需拆分文件 2**: `src/importer/excel_importer.py` (908 行 → ≤400×3)

**文件修改办法**:
1. 分析现有代码，识别三类功能：
   - **列映射**：中文/英文列名 → OrderData 字段路径映射逻辑
   - **KV 解析**：键值对格式（`字段名: 值`）解析
   - **明细解析**：商品明细行解析、托盘/纸箱/商品层级构建
2. 创建 `src/importer/column_mapper.py` — 列名映射表 + 映射函数（约 200 行）
3. 创建 `src/importer/kv_parser.py` — KV 行识别与键值提取（约 300 行）
4. 创建 `src/importer/detail_parser.py` — 明细行解析与层级构建（约 400 行）
5. `excel_importer.py` 保留为门面，从子模块导入

---

**需拆分文件 3**: `src/generators/template_anchor_scanner.py` (732 行 → ≤400×3)

**文件修改办法**:
1. 分析现有扫描函数：`scan_packing_template`、`scan_invoice_template`、`scan_contract_template` 等
2. 每个模板类型的扫描函数独立为子模块：
   - `src/generators/scanners/packing_scanner.py` — 装箱单模板锚点扫描
   - `src/generators/scanners/invoice_scanner.py` — 发票模板锚点扫描
   - `src/generators/scanners/contract_scanner.py` — 合同模板锚点扫描
3. 公共类型（`AnchorResult`）保留在 `template_anchor_scanner.py` 或提取到 `scanners/__init__.py`
4. 更新所有生成器中的 import 路径

---

**需拆分文件 4**: `src/db/repository.py` (632 行 → ≤200×4)

**文件修改办法**:
1. 当前文件中已按类分离（`CustomerRepository`、`ProductRepository`、`OrderRepository`、`TemplateRepository`）
2. 每个 Repository 类提取为独立文件：
   - `src/db/customer_repository.py`
   - `src/db/product_repository.py`
   - `src/db/order_repository.py`
   - `src/db/template_repository.py`
3. `repository.py` 改为从子模块 re-export 的聚合入口（或直接删除，更新所有引用）
4. 更新应用中所有 `from src.db.repository import XxxRepository` 引用

---

### 问题 P06 — 函数内延迟 import

**严重程度**: 🟡 中等
**耦合**: 与 P05 强耦合（P05 拆分后文件结构变化，某些循环导入可能自然消除）
**描述**: 多处函数内部执行 `import`，违反 CLAUDE.python.md 1.2 节"禁止在函数内导入"规则。

**涉及位置**（按修复优先级排列）:

| 位置 | 文件 | 行号 | 内层 import 内容 |
|------|------|------|------------------|
| 1 | `src/gui/app.py` | 309-337 | `_build_page()` 内导入 6 个 page 模块 |
| 2 | `src/gui/pages/tree_editor_page.py` | 783-792 | `build_order_data()` 内导入全部模型 |
| 3 | `src/gui/pages/generate_page.py` | 245 | `_do_generate()` 内导入 Orchestrator |
| 4 | `src/generators/invoice_generator.py` | 358 | `_find_actual_summary_row()` 内导入 `_find_summary_rows` |
| 5 | `src/generators/contract_generator.py` | 237 | 同 invoice |

**文件修改办法**（通用步骤）:

**步骤 1** — 排查循环导入根因：
- 对每一处函数内 import，画出导入链：`A → B → A`
- 确定是"循环导入"还是"为了延迟加载"

**步骤 2** — 消除循环导入（如存在）：
- 方案 a：提取共享接口到独立模块（如 `interfaces.py`）
- 方案 b：使用依赖注入替代直接导入
- 方案 c：调整模块边界（P05 拆分可能已解决部分循环）

**步骤 3** — 将 import 移到文件顶部：
- 确认循环导入已消除后，将函数内 `from xxx import yyy` 移动到文件顶部
- 按标准顺序排列：标准库 → 第三方库 → 项目内部

**重点修复**: `src/gui/app.py` 的 `_build_page()` 方法

**文件修改办法**（针对 app.py）:
1. P05 拆分后 `tree_editor_page` 的导入路径可能变化
2. 将 6 个 page 模块的 import 移到 `app.py` 文件顶部
3. 如果出现循环导入（page 引用了 `app.GuiApp`），解决方式：
   - 在 page 模块中使用 `TYPE_CHECKING` 延迟类型注解
   - 或将 `GuiApp` 的接口提取为 Protocol 类

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.gui.app import GuiApp
```

**验收**: 
- 全项目搜索 `def.*:\s*\n\s*from\s|def.*:\s*\n\s*import\s` 无匹配（正则搜索函数内 import）
- 应用启动不报 `ImportError` / 循环导入错误

---

### 问题 P13 — GUI 字段缺乏实时校验

**严重程度**: 🟢 轻微
**耦合**: 与 P05/P06 松散耦合（修改同一文件 `order_info_page.py`）
**描述**: `order_info_page.py:468-489` — 必填字段校验仅在"下一步"按钮点击时执行，日期字段接受任意字符串无格式校验。

**需修改文件 1**: `src/gui/pages/order_info_page.py`

**文件修改办法**:
1. 在 `_build_form()` 或创建 Entry 的位置，为日期字段添加 `validate="focusout"` 和对应的 `validatecommand`：
```python
import re
from datetime import datetime

def _validate_date(self, value: str) -> bool:
    """校验日期格式 YYYY-MM-DD."""
    if not value:
        return True  # 允许空值，必填校验在提交时处理
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True

def _validate_required(self, value: str) -> bool:
    """校验必填字段非空."""
    return bool(value.strip())
```
2. 注册校验命令：
```python
vcmd_date = (self.register(_validate_date), "%P")
vcmd_required = (self.register(_validate_required), "%P")
```
3. 在 Entry 创建时绑定：
```python
entry.config(validate="focusout", validatecommand=vcmd_date)
```
4. 校验失败时高亮字段（设置 `style="danger.TEntry"` 或修改背景色）
5. 提交时保留二次校验（防御性编程）

**验收**: 
- 日期字段失焦时校验格式
- 必填字段失焦时空值时高亮
- 提交按钮点击时仍执行完整校验

---

# 优先级 P4 — 模板容量与生成器功能增强（耦合组 D）

> **总预估**: 4-6 小时
> **注意**: ⚠️**耦合组 D**，所有修改联动，必须同一对话窗口执行。

---

## ⚠️ 耦合组 D：多容量模板系统

> **必须同一对话窗口执行！** `template_rules.json` + `base_generator.py` + 3 个子生成器 + `orchestrator.py` + `xlsx_utils.py` + 新建模板文件联动。

---

### 概述

**目标**: 
1. 创建 20/100 行容量模板（以现有 50 行模板为基准）
2. 程序根据订单明细行数自动选择模板
3. 数据填充后删除多余预留行
4. 表头字段只写值，不拼接标签文本
5. 容量不足时阻断生成

**整体验收**: 
- 3/20/50/100 行数据自动选择正确容量模板
- 预留空行正确删除，汇总行位置正确，SUM 公式范围正确
- 表头无重复标签

---

### 子任务 D-1 — 创建 20/100 行容量模板

**需操作**: 手动在 Excel 中制作（AI 无法直接操作 .xlsx 二进制）

**文件修改办法**（手动操作指南）:
1. 复制现有 50 行模板作为基准
2. 对于 20 行版本：
   - 打开 `template_invoice.xlsx`，另存为 `template_invoice_20.xlsx`
   - 删除第 35-64 行的预留数据行（保留 20 行数据区）
   - 调整汇总行位置到第 35 行
   - 修正 SUM 公式范围（如 `SUM(B15:B34)`）
   - 对 contract、packing 模板重复上述操作
3. 对于 100 行版本：
   - 复制数据区格式，扩展到 100 行
   - 汇总行移到第 115 行
   - 修正 SUM 公式范围
4. 命名规范（放入 `templates/` 目录）：
```text
template_invoice_20.xlsx    template_invoice_100.xlsx
template_contract_20.xlsx   template_contract_100.xlsx
template_packing_20.xlsx    template_packing_100.xlsx
```

---

### 子任务 D-2 — 配置 `template_rules.json`

**需修改文件 1**: `config/template_rules.json`

**文件修改办法**:
1. 为每个模板类型显式配置容量参数：
```json
{
  "invoice": {
    "20": {
      "template": "template_invoice_20.xlsx",
      "data_start_row": 15,
      "data_end_row": 34,
      "summary_row": 35,
      "formula_columns": ["F", "G", "H"]
    },
    "50": {
      "template": "template_invoice_50.xlsx",
      "data_start_row": 15,
      "data_end_row": 64,
      "summary_row": 65,
      "formula_columns": ["F", "G", "H"]
    },
    "100": {
      "template": "template_invoice_100.xlsx",
      "data_start_row": 15,
      "data_end_row": 114,
      "summary_row": 115,
      "formula_columns": ["F", "G", "H"]
    }
  },
  "contract": { ... },
  "packing": { ... }
}
```
2. 同样配置 `contract` 和 `packing` 类型的容量参数

---

### 子任务 D-3 — `BaseGenerator` 增加模板容量选择 + 预留行删除

**需修改文件 2**: `config/constants.py`

**文件修改办法**:
1. 新增模板容量配置常量（可选，也可以直接从 `template_rules.json` 动态加载）：
```python
# 模板容量与行数选择映射
TEMPLATE_CAPACITY_RULES: dict[str, int] = {
    "20": 20,
    "50": 50,
    "100": 100,
}
MAX_TEMPLATE_ROWS: int = 100
```

**需修改文件 3**: `src/generators/base_generator.py`

**文件修改办法**:
1. 在 `__init__` 或 `generate` 方法中增加容量选择逻辑
2. 新增 `_select_template_by_rows(n_rows: int) -> Path` 方法：
```python
def _select_template_by_rows(self, n_rows: int) -> Path:
    """根据数据行数自动选择合适容量的模板文件."""
    if n_rows <= 20:
        capacity = "20"
    elif n_rows <= 50:
        capacity = "50"
    elif n_rows <= 100:
        capacity = "100"
    else:
        raise ValueError(
            f"[错误]: 数据行数 {n_rows} 超过最大模板容量 100\n"
            f"[原因]: 当前模板最大支持 100 行商品明细\n"
            f"[排查]: 请拆分为多个订单分别生成"
        )
    # 根据容量替换模板文件名中的容量标识
    # 例如 template_invoice_50.xlsx → template_invoice_20.xlsx
    ...
```
3. 新增 `_delete_reserved_rows(ws, data_start, data_end, n_rows)` 方法：
   - 计算实际数据结束行：`actual_end = data_start + n_rows - 1`
   - 从 `actual_end + 1` 到 `data_end` 删除预留空行
4. 在 `generate` 流程中集成容量选择和预留行删除步骤

---

### 子任务 D-4 — 三个生成器修正表头填充

**需修改文件 4**: `src/generators/invoice_generator.py`
**需修改文件 5**: `src/generators/contract_generator.py`
**需修改文件 6**: `src/generators/packing_generator.py`

**文件修改办法**（三个文件类似，以 invoice 为例）:
1. 定位到表头填充方法（`_fill_header`）
2. 检查每个单元格写入逻辑：
   - **改前**: `ws["B7"] = f"Invoice No.: {order.order_meta.invoice_no}"`
   - **改后**: `ws["B7"] = order.order_meta.invoice_no`
3. 规则：模板中已有字段标签的单元格，只写字段值，不拼接标签文本
4. 确认哪些单元格是纯值单元格（需要检查模板结构以确认）
5. 对 contract 和 packing 做相同的检查和修改

---

### 子任务 D-5 — `xlsx_utils.py` 增加预留行删除逻辑

**需修改文件 7**: `src/generators/xlsx_utils.py`

**文件修改办法**:
1. 新增 `delete_reserved_rows(ws, start_row, end_row)` 函数：
```python
def delete_reserved_rows(ws: Worksheet, start_row: int, end_row: int) -> None:
    """删除数据区中未使用的预留行。
    
    Args:
        ws: 工作表对象
        start_row: 要删除的起始行（1-based）
        end_row: 要删除的结束行（1-based）
    """
    if start_row > end_row:
        return
    ws.delete_rows(start_row, end_row - start_row + 1)
```
2. 新增 `fix_formula_after_delete(ws, formula_columns, deleted_count)` 函数（如果需要修正公式范围）

---

### 子任务 D-6 — `Orchestrator` 容量不足阻断 + 模板选择集成

**需修改文件 8**: `src/generators/orchestrator.py`

**文件修改办法**:
1. 在 `generate_all` 或类似入口处，在调用生成器前检查数据行数
2. 如果 `flattened_rows > 100`，阻断生成并返回错误：
```python
if n_rows > MAX_TEMPLATE_ROWS:
    raise ValueError(
        f"[错误]: 订单包含 {n_rows} 行明细，超过最大模板容量 {MAX_TEMPLATE_ROWS}\n"
        f"[原因]: 当前模板仅支持最多 {MAX_TEMPLATE_ROWS} 行\n"
        f"[排查]: 请将订单拆分为多个子订单，每个不超过 {MAX_TEMPLATE_ROWS} 行"
    )
```
3. 确保错误信息在 GUI 中正确展示给用户

**需修改文件 9**: `src/generators/template_anchor_scanner.py`

**文件修改办法**:
1. 扫描逻辑不再估算空白预留区结束位置
2. 改为从 `template_rules.json` 配置中读取 `data_end_row`
3. 仅扫描锚点行（数据起始行、汇总行标记），容量信息由配置提供

---

# 优先级 P5 — GUI 现代化（耦合组 E）

> **总预估**: 5-8 小时
> **注意**: ⚠️**耦合组 E**，样式/布局/窗口状态联动。

---

## ⚠️ 耦合组 E：GUI 视觉与交互现代化

> **必须同一对话窗口执行！** `styles.py` + `app.py` + 全部 page 文件联动。

---

### 概述

**目标**:
1. 统一视觉风格（去掉 Windows98 风格）
2. 重做主窗口布局（标题栏 + 内容区 + 状态栏）
3. 窗口状态记忆（宽度/高度/位置/最大化）
4. 关闭确认对话框
5. 客户/产品页标注"功能开发中"

---

### 子任务 E-1 — 新建统一样式模块

**需新建文件 1**: `src/gui/styles.py`

**文件修改办法**:
```python
# -*- coding: utf-8 -*-
"""GUI 统一样式定义."""

from __future__ import annotations

# 字体
FONT_FAMILY = "Microsoft YaHei"  # Windows 默认中文字体
FONT_SIZE_NORMAL = 10
FONT_SIZE_TITLE = 14
FONT_SIZE_SMALL = 9

# 间距
PADDING_X = 10
PADDING_Y = 8
MARGIN = 5

# 颜色（业务工具风格，低饱和度）
COLOR_BG = "#F5F5F5"
COLOR_SURFACE = "#FFFFFF"
COLOR_PRIMARY = "#1565C0"
COLOR_TEXT = "#212121"
COLOR_TEXT_SECONDARY = "#757575"
COLOR_BORDER = "#E0E0E0"
COLOR_ERROR = "#D32F2F"
COLOR_SUCCESS = "#388E3C"

# 按钮样式
BUTTON_WIDTH = 100
BUTTON_HEIGHT = 32

def apply_theme(root) -> None:
    """应用全局主题样式."""
    ...
```

**验收**: 所有页面引用统一样式常量，视觉一致。

---

### 子任务 E-2 — 重做主窗口布局

**需修改文件 1**: `src/gui/app.py`

**文件修改办法**:
1. 重构窗口布局为三段式结构：
```text
┌──────────────────────────────┐
│  顶部标题/工具栏              │  ← header_frame
├──────────────────────────────┤
│                              │
│  主内容区（页面容器）         │  ← content_frame
│                              │
├──────────────────────────────┤
│  底部状态栏                  │  ← status_frame
└──────────────────────────────┘
```
2. 去掉装饰性 Emoji（页面标题、按钮文本）
3. 侧边导航栏改为顶部 Tab 栏或左侧简洁导航（使用 ttkbootstrap 的 Notebook 或自定义按钮组）
4. 按钮统一使用 `ttk.Button` + `bootstyle` 样式

---

### 子任务 E-3 — 窗口状态记忆

**需新建文件 2**: `src/gui/services/preferences_service.py`

**文件修改办法**:
1. 创建 `PreferencesService` 类，使用 SQLite 或 JSON 文件持久化：
```python
# 保存的内容
preferences = {
    "window_width": 1200,
    "window_height": 800,
    "window_x": 100,
    "window_y": 50,
    "is_maximized": False,
    "last_output_dir": "D:/output/",
    "last_import_dir": "D:/data/",
}
```
2. 启动时从持久化存储加载
3. 窗口关闭/移动/调整大小时保存
4. 在 `app.py` 的窗口初始化代码中调用：
   - `on_closing` 事件保存窗口状态
   - `__init__` 中恢复窗口状态

---

### 子任务 E-4 — 关闭确认对话框

**需修改文件 2**: `src/gui/app.py`（追加修改）

**文件修改办法**:
1. 拦截 `WM_DELETE_WINDOW` 协议：
```python
self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
```
2. 实现 `_on_closing` 方法：
   - 检查是否有未保存数据（通过脏标记 `self._is_dirty`）
   - 如有，弹出确认对话框：保存并退出 / 不保存退出 / 取消
   - 如无，直接退出
3. 各 page 通过 `app.set_dirty(True)` 标记数据变更

---

### 子任务 E-5 — 占位页面标注

**需修改文件 3**: `src/gui/app.py`（追加修改）

**文件修改办法**:
1. 在客户管理和产品管理导航位置添加 "功能开发中" 文字标注
2. 或创建简单的占位 Frame，居中显示 "客户管理 — 开发中，敬请期待"

---

# 优先级 P6 — 单表格商品录入（耦合组 F）

> **总预估**: 6-10 小时
> **注意**: ⚠️**耦合组 F**，组件/页面/转换器联动。

---

## ⚠️ 耦合组 F：商品录入重构

> **必须同一对话窗口执行！** `editable_table.py` + `line_item_table_page.py` + `app.py` 联动。

---

### 概述

**目标**: 新增单表格录入页替代树状录入作为主流程。

**字段**（每行一个商品/纸箱组合）:
`托盘号 | 纸箱号 | 是否批量箱 | 批量箱数 | 长 | 宽 | 高 | 毛重 | 商品名称 | 规格型号 | HS Code | 申报要素 | 单位 | 每箱数量 | 单价 | 币种 | 单件净重 | 目的国`

**支持操作**: 复制行、删除行、批量粘贴、批量填充列、从产品库插入商品、自动汇总

---

### 子任务 F-1 — 新建可编辑表格组件

**需新建文件 1**: `src/gui/components/editable_table.py`

**文件修改办法**:
1. 创建 `EditableTable` 类，基于 `ttk.Treeview` + Entry 叠加编辑
2. 实现功能：
   - 双击单元格进入编辑模式
   - Tab/Enter 移动编辑焦点
   - 右键菜单（插入行、删除行、复制行、粘贴行）
   - 列头排序
   - 多选 + 批量填充列
3. 数据模型：内部维护 `list[dict]`，每个 dict 是一行数据
4. 对外接口：
   - `get_all_rows() -> list[dict]`
   - `set_rows(rows: list[dict])`
   - `get_selected_rows() -> list[int]`
   - `on_change(callback: Callable)` — 数据变更回调

---

### 子任务 F-2 — 新建表格录入页

**需新建文件 2**: `src/gui/pages/line_item_table_page.py`

**文件修改办法**:
1. 创建 `LineItemTablePage` 类，嵌入 `EditableTable`
2. 定义列配置（18 个字段的列名、宽度、编辑类型）
3. 底部放置汇总栏（实时计算并显示）：
   - 总毛重、总净重、总体积、总金额
4. 底部放置操作按钮：
   - 添加行、删除选中行、复制选中行
   - 从产品库插入（打开产品搜索弹窗）
   - 批量填充（选中多行后，填充同一列的值）
5. 在 `__init__.py` 或 `app.py` 中注册页面

---

### 子任务 F-3 — 实现 OrderData 转换器

**需修改文件 1**: `src/gui/pages/line_item_table_page.py`（同一文件）

**文件修改办法**:
1. 实现 `_table_to_order_data() -> OrderData` 方法：
   - 按托盘号分组 → 按纸箱号分组 → 构建 Pallet/Carton/Product 层级
   - 处理批量箱逻辑（`is_batch_box` 为 True 时，`batch_count` 复制纸箱）
   - 填充 `OrderMeta`（从当前订单信息页获取）
   - 调用 `OrderData` 构造器
2. 实现 `_order_data_to_table(order: OrderData) -> None` 方法（反向填充，用于编辑已有订单）
3. 添加数据校验：在转换前检查必填列非空

---

### 子任务 F-4 — 接入生成流程

**需修改文件 2**: `src/gui/app.py`

**文件修改办法**:
1. 在导航中添加"商品明细"页面（指向 `LineItemTablePage`）
2. 调整向导流程：订单信息 → 商品明细（表格）→ 生成
3. 旧 `tree_editor_page.py` 保留在导航中，标记为 "层级视图（旧）" 或 "高级编辑"

**验收**: 用户可通过表格完成完整订单录入并成功生成文件。

---

# 优先级 P7 — 客户库与产品库（耦合组 G）

> **总预估**: 4-6 小时
> **注意**: ⚠️**耦合组 G**，页面/数据库联动。

---

## ⚠️ 耦合组 G：信息库功能

> **必须同一对话窗口执行！** `customer_page.py` + `product_page.py` + `schema.sql` + `repository.py` 联动。

---

### 子任务 G-1 — 新增 `template_blocks` 表

**需修改文件 1**: `src/db/schema.sql`

**文件修改办法**:
1. 新增建表语句：
```sql
CREATE TABLE IF NOT EXISTS template_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    block_type TEXT NOT NULL CHECK(block_type IN ('customer', 'product_set', 'shipping', 'order_full')),
    block_name TEXT NOT NULL,
    block_json TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    is_deleted INTEGER NOT NULL DEFAULT 0
);
```

---

### 子任务 G-2 — 新建客户管理页

**需新建文件 1**: `src/gui/pages/customer_page.py`

**文件修改办法**:
1. 创建 `CustomerPage` 类
2. 功能列表：
   - 客户列表（Treeview，显示 company_name_cn/company_name_en/country/contact）
   - 搜索栏（按公司名中文/英文/国家搜索）
   - 新增客户按钮 → 弹出编辑对话框
   - 编辑客户按钮 → 弹出编辑对话框（预填数据）
   - 删除客户按钮 → 确认后软删除
   - "套用到当前订单"按钮 → 将选中客户信息填充到 `app.current_order`
3. 底层复用 `CustomerRepository`

---

### 子任务 G-3 — 新建产品管理页

**需新建文件 2**: `src/gui/pages/product_page.py`

**文件修改办法**:
1. 创建 `ProductPage` 类
2. 功能列表：
   - 产品列表（Treeview，显示 name/spec/hs_code/unit/price）
   - 搜索栏（按商品名/HS Code 搜索）
   - 新增/编辑/删除产品
   - "插入到商品表格"按钮 → 将选中产品添加到当前录入页的表格中
3. 底层复用 `ProductRepository`

---

### 子任务 G-4 — 订单页集成客户选择

**需修改文件 1**: `src/gui/pages/order_info_page.py`

**文件修改办法**:
1. 在客户信息区域添加"从客户库选择"按钮
2. 点击后弹出客户搜索对话框（或导航到客户管理页）
3. 选中客户后自动填充：公司名（中/英）、国家、联系人、电话、地址

---

### 子任务 G-5 — 商品表格集成产品插入

**需修改文件 2**: `src/gui/pages/line_item_table_page.py`

**文件修改办法**:
1. 实现"从产品库插入"按钮的完整逻辑
2. 点击后弹出产品搜索对话框（搜索→选中→插入到当前行或新行）
3. 插入时自动填充：商品名称、规格型号、HS Code、申报要素、单位、单价

---

# 优先级 P8 — 分块模板与草稿恢复（耦合组 H）

> **总预估**: 5-8 小时
> **注意**: ⚠️**耦合组 H**，模板/草稿/生命周期联动。

---

## ⚠️ 耦合组 H：模板复用与数据持久化

> **必须同一对话窗口执行！** `template_block_service.py` + `draft_service.py` + `app.py` 生命周期联动。

---

### 子任务 H-1 — 新建模板块服务

**需新建文件 1**: `src/gui/services/template_block_service.py`

**文件修改办法**:
1. 创建 `TemplateBlockService` 类
2. 功能：
   - `save_block(block_type, block_name, data: dict, description="")` — 保存分块模板
   - `load_blocks(block_type) -> list` — 按类型加载所有模板
   - `delete_block(block_id)` — 软删除模板
   - `apply_block(block_id, target_order, fields: set)` — 套用模板到订单（仅覆盖指定字段）
3. `block_type` 支持：
   - `customer` — 客户信息块
   - `product_set` — 商品信息块
   - `shipping` — 装运信息块
   - `order_full` — 整单模板

---

### 子任务 H-2 — 套用范围选择 UI

**需修改文件 1**: `src/gui/pages/order_info_page.py`（或新建对话框组件）

**文件修改办法**:
1. 创建"套用模板"按钮
2. 点击后弹出对话框：
   - 模板类型下拉选择（客户/商品/装运/整单）
   - 已保存的模板列表
   - **套用范围多选**：☑ 客户信息 ☑ 商品信息 ☑ 装运信息 ☐ 其他
   - 未勾选的字段不覆盖
3. 套用后更新当前订单数据和 UI

---

### 子任务 H-3 — 新建草稿服务

**需新建文件 2**: `src/gui/services/draft_service.py`

**文件修改办法**:
1. 创建 `DraftService` 类
2. 保存内容（JSON 格式，存储在用户数据目录）：
```python
draft = {
    "order_data": order.to_dict(),  # 订单完整数据
    "current_page": "line_items",   # 当前所在页面
    "updated_at": "2026-05-27 14:30:00",
    "version": "1.0",
}
```
3. 功能：
   - `save_draft(order, current_page)` — 保存草稿
   - `load_draft() -> dict | None` — 加载最新草稿
   - `delete_draft()` — 删除草稿
   - `has_draft() -> bool` — 检查是否存在草稿
4. 草稿文件路径：`~/.customs_generator/drafts/autosave.json` 或项目目录下的 `data/drafts/`

---

### 子任务 H-4 — 启动时草稿检测与恢复

**需修改文件 1**: `src/gui/app.py`

**文件修改办法**:
1. 在 `GuiApp.__init__` 末尾添加草稿检测逻辑：
```python
if self._draft_service.has_draft():
    draft = self._draft_service.load_draft()
    choice = messagebox.askyesnocancel(
        "恢复草稿",
        f"检测到未完成的订单草稿（最后更新: {draft['updated_at']}）。\n\n"
        "是否恢复？\n"
        "  [是] - 恢复草稿\n"
        "  [否] - 忽略并删除草稿\n"
        "  [取消] - 保留草稿，下次再决定"
    )
    if choice is True:
        self._restore_from_draft(draft)
    elif choice is False:
        self._draft_service.delete_draft()
    # choice is None → 取消，保留草稿
```

---

### 子任务 H-5 — 页面切换/关闭时自动保存

**需修改文件 2**: `src/gui/app.py`（追加修改）

**文件修改办法**:
1. 在页面切换时触发自动保存（`switch_page` 方法末尾调用 `_autosave`）
2. 窗口关闭时触发自动保存（在 E-4 的 `_on_closing` 方法中）
3. 自动保存频率控制：至少间隔 5 秒（避免频繁写入）
4. 只有 `_is_dirty = True` 时才触发保存

---

# 附录 A: 执行优先级总览

```
P0 (15min)   → 独立紧急修复 ── 可并行执行
│
├─ P02: requirements.txt 加 num2words
├─ P14: add_warning 去 passed=False
└─ P11: 删除调试脚本
│
P1 (2-4h)    → 生成器链修复
│
├─⚠️耦合组A: P04 → P01 → P08/P16 (必须顺序执行)
└─ P12: os.startfile 跨平台 (可并行)
│
P2 (2-3h)    → 类型系统统一
│
├─⚠️耦合组B: P15 → P07 (必须顺序执行)
├─ P03: num2words 降级链路
├─ P09: 单例锁
└─ P10: SQL 注释
│
P3 (4-8h)    → 大文件拆分
│
└─⚠️耦合组C: P05 + P06 + P13 (建议一起)
│
P4 (4-6h)    → 多容量模板系统
│
└─⚠️耦合组D: D-1~D-6 (必须一起)
│
P5 (5-8h)    → GUI 现代化
│
└─⚠️耦合组E: E-1~E-5 (必须一起)
│
P6 (6-10h)   → 单表格商品录入
│
└─⚠️耦合组F: F-1~F-4 (必须一起)
│
P7 (4-6h)    → 客户库/产品库
│
└─⚠️耦合组G: G-1~G-5 (必须一起)
│
P8 (5-8h)    → 分块模板/草稿
│
└─⚠️耦合组H: H-1~H-5 (必须一起)
```

---

# 附录 B: 文件修改频次统计

以下文件被多个优先级修改，注意执行顺序：

| 文件 | 被修改的优先级 | 说明 |
|------|---------------|------|
| `src/generators/base_generator.py` | P1, P4 | P1 改继承体系 + P4 加模板容量 |
| `src/generators/packing_generator.py` | P1, P4 | P1 重构继承 + P4 改表头 |
| `src/generators/invoice_generator.py` | P1, P2, P4 | P1 提取公共方法 + P2 改 num2words + P4 改表头 |
| `src/generators/contract_generator.py` | P1, P4 | P1 提取公共方法 + P4 改表头 |
| `src/generators/orchestrator.py` | P2, P4 | P2 单例锁 + P4 容量阻断 |
| `src/gui/app.py` | P3, P5, P6, P7, P8 | 几乎每阶段都涉及 |
| `src/gui/pages/order_info_page.py` | P2, P3, P7, P8 | P2 类型 + P3 校验 + P7 客户选择 + P8 套用模板 |
| `src/gui/pages/generate_page.py` | P1, P2, P3 | P1 跨平台 + P2 类型 + P3 导入 |
| `src/models/order_data.py` | P2 | P2 统一类型定义 |
| `config/constants.py` | P4 | P4 模板容量常量 |
| `config/template_rules.json` | P4 | P4 容量规则配置 |
| `src/db/schema.sql` | P7 | P7 template_blocks 表 |

> **策略**: 如果需要在多个对话窗口中分批执行，请按优先级顺序（P0→P8），每个优先级结束后的代码状态即为下一优先级的基线。
