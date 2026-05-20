# Claude.python.md — Python 开发规范

> **地位**:Python 项目的专项规范.需与根 `Claude.md` 配合使用.

---

## 一,代码风格 `[强制]`

- 遵循 **PEP 8**(但 Ruff 会自动化处理缩进/引号/行长度,见附录 A)
- 字符串:统一使用**双引号** `"`
- f-string 优先于 `.format()` 和 `%`
- 文件头:`# -*- coding: utf-8 -*-`

### 1.1 常见陷阱规避

以下 Python 底层陷阱是隐蔽 Bug 常见来源,必须严格规避:

- **禁止可变默认参数**:禁止使用 `[]`,`{}`,`set()` 等可变对象作为默认值.必须使用 `None` 并在函数体内初始化.

```python
#  正确
def add_item(item: str, items: list | None = None) -> list:
    if items is None:
        items = []
    items.append(item)
    return items

#  禁止
def add_item(item: str, items: list = []) -> list:
    items.append(item)
    return items
```

- **闭包变量晚绑定规避**:在循环内创建 lambda 或内部函数时,必须显式传参捕获循环变量.

```python
#  正确
funcs = [lambda x=i: x * 2 for i in range(5)]

#  禁止——所有函数返回同一值
funcs_bad = [lambda: i * 2 for i in range(5)]
```

### 1.2 导入规范

导入顺序(组间空一行):

```python
# 1. 标准库
import os
from pathlib import Path

# 2. 第三方库
import openpyxl
from fastapi import FastAPI

# 3. 本地模块
from src.utils import formatter
from src.database import repository
```

- 禁止 `from module import *`
- 禁止在函数内部导入(除非处理循环导入——但循环导入本身应被消除)

### 1.3 类型注解与文档

- 所有公共函数/方法**必须使用 type hints**(参数 + 返回值)
- 所有函数/方法**必须包含 docstring**:

```python
def calculate_total(quantity: int, unit_price: float, tax_rate: float = 0.13) -> float:
    """计算含税总价.

    Args:
        quantity: 数量.
        unit_price: 单价(元).
        tax_rate: 税率,默认 0.13.

    Returns:
        含税总价(元),保留两位小数.

    Raises:
        ValueError: 数量或单价为负数时抛出.
    """
    if quantity < 0 or unit_price < 0:
        raise ValueError("数量和单价不能为负数")
    return round(quantity * unit_price * (1 + tax_rate), 2)
```

---

## 二,软件工程原则

### 2.1 模块化与文件组织 `[强制]`

- 单 `.py` 文件 **≤ 300 行**,超过必须拆分
- 函数遵循**单一职责原则**,圈复杂度 **≤ 10**
- **禁止循环导入**
- 配置与代码分离:路径,密钥,URL,端口号等一律走配置文件或环境变量

### 2.2 目录结构 `[强制]`

```
project_root/
├── .venv/                # 虚拟环境(不入 Git)
├── requirements.txt      # 或 pyproject.toml
├── README.md
├── CHANGELOG.md          # [建议] 变更日志
├── CLAUDE.md             # 项目级 AI 规则
├── plan.md               # 分阶段执行计划
├── .env.example
├── .gitignore
├── src/                  # 或 app/,backend/
├── tests/                # 测试代码
├── config/               # 配置文件(模板,settings 等)
├── docs/                 # 文档
│   ├── prompts/          # LLM Prompt 模板(版本化)
│   └── schemas/          # JSON Schema 定义
└── output/               # 生成物目录
```

### 2.3 错误处理与日志 `[强制]`

- 所有外部调用 **必须用 try/except 包裹**
- 异常**不得静默吞掉**
- 日志统一使用标准库 `logging`,每个模块独立获取 logger:

```python
import logging
logger = logging.getLogger(__name__)
```

- 日志分级:`INFO`(关键节点),`WARNING`(可恢复异常),`ERROR`(不可恢复)
- 用户可见错误信息用**中文**;技术细节写入日志

### 2.4 依赖管理 `[强制]`

- 维护 `requirements.txt` 或 `pyproject.toml`
- **依赖版本必须锁定**(如 `openpyxl==3.1.2`),禁止 `>=`
- **新增依赖必须先更新依赖文件,再执行安装**
- 虚拟环境命名 `.venv`,位于项目根目录,已加入 `.gitignore`

### 2.5 大规模 I/O 与内存管理 `[强制]`

- 读取超过 **50MB** 的文件,禁止 `read()` 一次性载入,必须用生成器:

```python
def read_large_file(file_path: str, chunk_size: int = 8192):
    """按块读取大文件,避免内存溢出."""
    with open(file_path, "r", encoding="utf-8") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk
```

- 临时文件**必须使用 `with tempfile.TemporaryDirectory()` 或 `try/finally` 确保自动清理**

### 2.6 并发控制 `[强制]`

- **严禁无限制并发**,使用 `Semaphore` 限制最大并发数(建议 ≤ 10)
- 每个并发任务独立 try/except,单任务失败不影响其他
- 并发结果汇总打印:`处理完成:成功 48/50,失败 2/50`
- **并发状态隔离(防竞态)**:多个协程或线程**禁止共享并直接修改同一个可变对象**(如全局 List/Dict).各任务必须返回独立结果,通过 `asyncio.gather()` 等机制汇总,或使用 `asyncio.Lock` / `threading.Lock` 保护临界区
- `[建议]` 批量处理应设计中间状态落盘与断点恢复机制
- `[建议]` 复杂并发逻辑封装在独立管理器类中(如 `BatchProcessor`)

### 2.7 数据不可变性 `[强制]`

函数不得修改通过参数传入的可变对象(字典,列表等),必须基于传入数据生成并返回新对象.嵌套数据结构复制须使用 `copy.deepcopy()`

```python
#  正确:返回新对象,不修改原数据
def mark_as_processed(record: dict) -> dict:
    new_record = copy.deepcopy(record)
    new_record["status"] = "processed"
    return new_record

#  禁止:直接修改入参,产生副作用
def mark_as_processed(record: dict) -> None:
    record["status"] = "processed"  # 悄无声息地篡改了原始数据
```

嵌套数据结构复制须使用 `copy.deepcopy()`,绝不依赖隐式浅拷贝:

```python
#  正确:deepcopy 完整隔离
import copy
nested = copy.deepcopy(original)

#  禁止:浅拷贝只复制顶层,内层仍共享引用
nested = original.copy()      # 字典浅拷贝
nested = list(original)       # 列表浅拷贝
nested = original[:]          # 切片浅拷贝
```

- **例外**:只读遍历操作无需拷贝
- **例外**:如确需原地修改,函数 docstring 第一行必须标注 `⚠️ MUTATES INPUT`,调用方须知晓

### 2.8 Fail-Fast 校验 `[强制]`

非 Optional 的关键函数入参在入口处必须做真值断言,为 `None` 时立即抛出含业务含义的异常,禁止静默向下传递.

```python
#  正确:入口断言
def generate_report(template_path: str, output_dir: str) -> str:
    if not template_path:
        raise ValueError("[错误]: template_path 为空,无法加载模板文件")
    if not output_dir:
        raise ValueError("[错误]: output_dir 为空,无法确定输出位置")
    # ... 正常逻辑

#  禁止:None 沿调用链传递到深层才崩溃
def generate_report(template_path: str, output_dir: str) -> str:
    # template_path 为 None → 传到 open() 才报 FileNotFoundError
    # 报错位置距真正的原因入口隔了多层调用,溯源困难
    with open(template_path) as f:
        ...
```

注意:Pydantic 模型已自带类型校验和 None 拦截,此规则主要针对**非 Pydantic 入口的普通函数**和**内部工具函数**.

---

## 三,业务层规范

### 3.1 数据库操作 `[强制]`

- 操作**统一通过 Repository 层**(如 `src/database/repository.py`)
- **禁止业务代码直接拼接 SQL 字符串**
- 表结构定义在独立 `schema.sql` 文件中
- 所有查询使用**参数化查询**

### 3.2 配置管理

- 环境配置(密钥,数据库路径,API URL)→ `.env` 文件
- 业务配置(公司抬头,模板路径,字体字号)→ `config/settings.json`
- 配置读取统一入口:`config.py` 或 `src/config/__init__.py`
- `.env` 绝不提交 Git,提供 `.env.example`

### 3.3 数据模型

- 使用 **Pydantic** 定义请求/响应模型和内部数据结构
- 数据库表结构与代码模型保持对应,差异在 Repository 层转换
- **Pydantic 全链路传递**:Pydantic 模型进入业务逻辑层后,必须保持对象形态(通过 `.` 属性访问),**禁止在存入数据库或返回前端前提前调用 `.model_dump()` 降级为裸字典传递**

```python
#  正确:业务层保持 Pydantic 对象,仅在 I/O 边界序列化
def process_order_service(order: OrderModel) -> OrderResult:
    # 业务逻辑全程使用 . 属性
    total = order.quantity * order.unit_price
    return OrderResult(order_id=order.id, total=total)

def save_to_db(order: OrderModel):
    # I/O 边界处才序列化
    row = order.model_dump()
    repository.insert(row)

#  禁止:业务层拿到模型立刻 dump,丧失类型安全
def process_order_service(order: OrderModel) -> dict:
    d = order.model_dump()          # 防弹衣脱了
    d["total"] = d["quantity"] * d["unit_price"]  # dict.get() 不安全
    return d                         # 后面的人全用裸字典
```

### 3.4 数据格式

| 项目 | 规范 |
|------|------|
| 文件编码 | **UTF-8** |
| JSON 序列化 | 展示/日志用 `indent=2`;落盘/网络传输时**禁止缩进**,仅 `ensure_ascii=False` |
| 日期格式 | **ISO 8601**:`YYYY-MM-DD` 或 `YYYY-MM-DDTHH:MM:SS` |
| 金额存储 | 以**分**为单位的整数,展示时转换为元 |
| 时区 | 统一 **UTC** 存储,展示时按需转换 |

### 3.5 异步编程 `[建议]`

- I/O 密集型操作优先使用 `async/await`
- CPU 密集型操作使用线程池或进程池,避免阻塞事件循环

---

## 四,测试规范

### 4.1 基本要求 `[强制]`

- 每个工具函数和业务逻辑模块**至少一个对应的单元测试**
- 测试文件与源码对应:`tests/test_<module>.py` ↔ `src/<module>.py`
- 复杂业务逻辑**必须覆盖边缘情况**:正常输入,边界值,异常输入
- 测试使用 `pytest`,运行 `pytest tests/` 应全部通过
- 测试应独立可重复:不依赖执行顺序,不依赖外部服务(使用 mock)

### 4.2 LLM 测试特殊规范 `[强制]`

- **单元测试中绝对禁止发起真实的 LLM API 请求**,必须用 `pytest-mock` 拦截
- `[建议]` RAG 检索准确率评测应从标准单元测试中抽离,作为独立评测脚本

---

## 五,文档与版本控制

### 5.1 必备文档 `[强制]`

| 文件 | 内容 |
|------|------|
| `README.md` | 项目简介,技术栈,快速启动命令,目录结构,修订历史 |
| `plan.md` | 分阶段执行计划,当前进度,技术选型理由 |
| `CHANGELOG.md` | `[建议]` 独立变更日志,按版本记录 |

### 5.2 注释规范 `[强制]`

- 注释使用**中文**
- 说明**"为什么这样做"**,而非"做了什么"
- 临时代码必须标注原因和预计移除时间

### 5.3 Git 提交信息

格式:`<type>: <简短中文描述>`

| Type | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | 修复 Bug |
| `docs` | 文档更新 |
| `refactor` | 代码重构(无功能变更) |
| `test` | 测试相关 |
| `chore` | 构建/工具/依赖变更 |

- 每次提交应是**原子性**的:一个逻辑变更 = 一个提交

---

## 六,代码示例

### 6.1 环境自检代码

每个程序的入口必须包含:

```python
import sys
import os

if __name__ == "__main__":
    # 1. 检查 Python 版本
    if sys.version_info < (3, 10):
        print("[错误]: 本程序需要 Python 3.10 或更高版本")
        print(f"[原因]: 当前版本:{sys.version}")
        print("[排查]: 请从 https://www.python.org/downloads/ 下载最新版 Python")
        sys.exit(1)

    # 2. 检查必要依赖
    missing = []
    try:
        import openpyxl
    except ImportError:
        missing.append("openpyxl")
    if missing:
        print(f"[错误]: 缺少必要依赖:{', '.join(missing)}")
        print(f"[排查]: 请在终端运行:pip install {' '.join(missing)}")
        sys.exit(1)

    # 3. 检查必要文件
    required_files = ["config/settings.json"]
    for f in required_files:
        if not os.path.exists(f):
            print(f"[错误]: 缺少必要文件:{f}")
            print(f"[原因]: 确保项目已正确克隆,文件结构完整")
            sys.exit(1)

    print(" 环境检查通过,开始运行...")
```

> 涉及加载本地大模型或超大文件时,应在加载前检查可用内存/显存.

### 6.2 进度打印示例

```python
print("=" * 50)
print(f"程序名称 v1.0.0 启动")
print(f"输出目录:{output_dir}")
print(f"数据库:{db_path}")
print("=" * 50)
```

### 6.3 运行说明注释块

```python
# ========== 运行说明 ==========
# 依赖安装:pip install openpyxl python-docx
# 运行命令:python generate_invoice.py
# 预期输出:在 output/ 目录下生成 发票_20260509.xlsx 文件
# =============================
```

### 6.4 错误自解释模式

```python
print("[错误]：连接翻译服务器失败")
print("[原因]：1) 网络未连通  2) API Key 无效或已过期")
print("[排查]：")
print("   1. 打开 .env 文件, 确认 DEEPSEEK_API_KEY 是否正确")
print("   2. 访问 https://platform.deepseek.com 检查 API Key 余额")
```

---

## 附录 A:Ruff 配置建议

在 `pyproject.toml` 中配置以下规则,替代人工记忆代码风格:

```toml
[tool.ruff]
line-length = 100
indent-width = 4

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

---

## 七,交付物自检清单

AI 输出代码前必须逐项确认:
- [ ] 包含所有 `import` 语句
- [ ] 包含 `if __name__ == "__main__"` 入口块
- [ ] 所有函数有 type hints 和 docstring
- [ ] 所有外部调用有 try/except 包裹(含中文错误提示)
- [ ] 无硬编码路径/密钥/URL
- [ ] 耗时操作有进度打印
- [ ] 末尾有运行说明注释块
- [ ] 入口有环境自检代码

---

## 八,常见错误速查表

| 错误模式 | 正确做法 | 参考章节 |
|---------|---------|:-------:|
| 可变默认参数 `def f(x=[])` | 用 `None` + 函数体内初始化 | 1.1 |
| 浅拷贝穿透 `obj.copy()` 修改了嵌套数据 | 用 `copy.deepcopy()` | 2.7 |
| 业务层使用 `.model_dump()` 后的裸字典 | 保持 Pydantic 对象形态,仅在 I/O 边界序列化 | 3.3 |
| None 沿调用链传递到底层才崩溃 | 入口处做真值断言,为空立即抛异常 | 2.8 |
| 函数内直接修改传入参数 | 生成并返回新对象(纯函数模式) | 2.7 |
| 未锁版本号 `pip install openpyxl` | 锁定 `openpyxl==3.1.2` | 2.4 |
| 并发无限制 | 使用 `Semaphore` 限制 ≤ 10 | 2.6 |
| SQL 字符串拼接 | 使用参数化查询 | 3.1 |

---

> **修订历史**
> - 2026-05-10(v2.0.0):新增数据不可变性(2.7),Fail-Fast 校验(2.8),Pydantic 全链路传递(3.3),交付物自检清单(七),常见错误速查表(八);移除部分与根总纲重叠的说明文本.
> - 2026-05-10(v1.0.0):从根总纲拆分,独立为 Python 专项规范.
