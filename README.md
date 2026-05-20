# 报关资料自动生成系统（CustomsFileGenerator）

> **版本**: 6.0.1-a | **状态**: 阶段 0 完成 — 项目骨架与环境自检就绪
> **技术栈**: tkinter + ttkbootstrap + openpyxl + python-docx + msgspec + sqlite3

---

## 一、项目简介

自动生成报关所需的四类文件：装箱单、形式发票、形式合同、报关单（暂缓）。
基于真实订单数据（Excel 或手动录入），通过 GUI 界面管理订单信息，一键生成标准格式的 xlsx/docx 文件。

## 二、快速启动

```bash
# 1. 创建虚拟环境
python -m venv .venv

# 2. 激活虚拟环境（Windows）
.venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 环境自检
python main.py

# 5. 启动 GUI（阶段 9 实现）
python main.py --gui
```

## 三、目录结构

```
CustomsFileGenerator/
├── main.py                  # 程序入口 + 环境自检
├── requirements.txt         # 依赖清单（版本锁定）
├── .env.example             # 环境变量模板
├── .gitignore
├── config/
│   ├── settings.py          # 配置管理（.env + settings.json）
│   ├── constants.py         # 常量、枚举、默认值
│   └── settings.json        # 业务配置
├── src/
│   ├── models/              # 数据模型（msgspec）
│   ├── db/                  # SQLite 数据库层
│   ├── generators/          # 文件生成器
│   ├── importer/            # Excel 导入器
│   └── gui/                 # GUI 界面
├── templates/               # 模板文件（只读）
├── output/                  # 生成文件输出目录
├── docs/
│   ├── pyproject.toml       # Ruff/mypy/pytest 配置
│   └── schemas/             # JSON Schema 定义
├── tests/                   # 单元测试
└── logs/                    # 运行日志
```

## 四、配置说明

### 环境变量（.env）

- 复制 `.env.example` 为 `.env`
- 当前阶段无需配置 API Key
- `LOG_LEVEL` 默认 INFO

### 业务配置（settings.json）

- 公司抬头、发货人信息
- 默认值（贸易条款、币种等）
- 模板坐标映射（阶段 3 后填入）
- 断言规则（阶段 7 后填入）

---

## 修订历史

| 版本 | 日期 | 变更说明 |
|------|------|---------|
| 6.0.1-a | 2026-05-20 | 阶段 0 完成：项目骨架搭建、环境自检、配置管理、依赖锁定 |
