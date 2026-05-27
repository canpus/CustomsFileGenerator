"""报关资料自动生成系统 — 程序入口.

功能：环境自检 + 启动（CLI / GUI 模式）。
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# 确保项目根目录在 sys.path 中
PROJECT_ROOT: Path = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def setup_logging() -> None:
    """配置双文件滚动日志系统.

    在 logs/ 目录下创建：
    - operations.log：仅 INFO 级别，记录用户操作与核心进度
    - errors.log：WARNING 及以上级别，记录异常详情
    """
    logs_dir: Path = PROJECT_ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    from config.constants import LOG_BACKUP_COUNT, LOG_MAX_BYTES

    # 根 logger
    root_logger: logging.Logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # 日志格式
    formatter: logging.Formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ---- operations.log：仅 INFO ----
    ops_handler: RotatingFileHandler = RotatingFileHandler(
        filename=logs_dir / "operations.log",
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    ops_handler.setLevel(logging.INFO)
    ops_handler.addFilter(lambda record: record.levelno == logging.INFO)
    ops_handler.setFormatter(formatter)
    root_logger.addHandler(ops_handler)

    # ---- errors.log：WARNING 及以上 ----
    err_handler: RotatingFileHandler = RotatingFileHandler(
        filename=logs_dir / "errors.log",
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    err_handler.setLevel(logging.WARNING)
    err_handler.setFormatter(formatter)
    root_logger.addHandler(err_handler)

    # 控制台输出（INFO 级别）
    console: logging.StreamHandler = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(console)

    logger: logging.Logger = logging.getLogger(__name__)
    logger.info("日志系统初始化完成")


# ---------- 环境自检 ----------


def check_python_version() -> bool:
    """检查 Python 版本是否满足最低要求."""
    from config.constants import MIN_PYTHON_VERSION

    current = (sys.version_info.major, sys.version_info.minor)
    if current < MIN_PYTHON_VERSION:
        required_str = f"{MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]}"
        current_str = f"{current[0]}.{current[1]}"
        print("  [错误]: Python 版本不满足要求")
        print(f"  [原因]: 当前版本: {current_str}，要求: >= {required_str}")
        print(f"  [排查]: 请从 https://www.python.org/downloads/ 下载并安装 Python {required_str}+")
        return False

    print(f"  Python 版本: {current[0]}.{current[1]}.{sys.version_info.micro} — 通过")
    return True


def check_dependencies() -> bool:
    """检查核心依赖是否已安装."""
    # 核心依赖列表（不含测试和打包工具）
    core_deps: dict[str, str] = {
        "ttkbootstrap": "ttkbootstrap",
        "openpyxl": "openpyxl",
        "docx": "python-docx",
        "msgspec": "msgspec",
        "dotenv": "python-dotenv",
    }

    missing: list[str] = []
    for import_name, pkg_name in core_deps.items():
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg_name)

    if missing:
        print(f"  [错误]: 缺少必要依赖: {', '.join(missing)}")
        print("  [原因]: 依赖未安装或虚拟环境未激活")
        print("  [排查]: 请在终端运行: pip install -r requirements.txt")
        return False

    print("  依赖检查: 全部已安装 — 通过")
    return True


def check_template_files() -> bool:
    """检查模板文件是否存在."""
    from config.constants import ALL_TEMPLATE_FILES, TEMPLATES_DIR

    missing: list[str] = []
    for filename in ALL_TEMPLATE_FILES:
        filepath: Path = TEMPLATES_DIR / filename
        if not filepath.exists():
            missing.append(filename)

    total = len(ALL_TEMPLATE_FILES)
    present = total - len(missing)

    if missing:
        print(f"  [错误]: 模板文件缺失 {len(missing)}/{total}")
        for fn in missing:
            print(f"    - templates/{fn}")
        print("  [原因]: 模板文件未放入 templates/ 目录")
        print(f"  [排查]: 请将模板文件复制到 {TEMPLATES_DIR} 目录下")
        return False

    print(f"  模板文件: {present}/{total} 存在 — 通过")
    return True


def check_output_dir() -> bool:
    """确保输出目录存在."""
    from config.constants import OUTPUT_DIR

    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        print(f"  [错误]: 无法创建输出目录: {OUTPUT_DIR}")
        print("  [原因]: 磁盘权限不足或路径无效")
        print("  [排查]: 请检查磁盘权限，或手动创建目录")
        return False


def run_env_checks() -> bool:
    """运行所有环境自检.

    Returns:
        True 表示所有检查通过，False 表示存在阻塞性问题.
    """
    from config.constants import APP_NAME, APP_VERSION

    print("=" * 50)
    print(f"{APP_NAME} v{APP_VERSION}")
    print("=" * 50)
    print("正在进行环境自检...\n")

    checks = [
        ("Python 版本", check_python_version),
        ("依赖检查", check_dependencies),
        ("模板文件", check_template_files),
        ("输出目录", check_output_dir),
    ]

    all_ok: bool = True
    for name, check_fn in checks:
        try:
            if not check_fn():
                all_ok = False
        except Exception as e:
            print(f"  [错误]: {name} 检查时发生异常: {e}")
            all_ok = False

    print()
    if all_ok:
        print(" 环境自检通过，程序就绪")
    else:
        print(" 环境自检未通过，请修复上述问题后重新运行")
        print()
        print("=" * 50)

    return all_ok


# ========== 主入口 ==========


def main() -> None:
    """程序主入口."""
    setup_logging()
    logger: logging.Logger = logging.getLogger(__name__)

    if not run_env_checks():
        logger.error("环境自检未通过，程序退出")
        sys.exit(1)

    # 解析命令行参数
    if "--gui" in sys.argv:
        logger.info("启动 GUI 模式")
        try:
            from src.gui.app import launch_gui

            launch_gui()
        except ImportError as e:
            logger.error(
                "[错误]: GUI 模块导入失败\n"
                "[原因]: ttkbootstrap 或相关依赖未安装\n"
                "[排查]: 请运行 pip install -r requirements.txt",
            )
            print(f"  [错误]: GUI 启动失败 — {e}")
            print("  [排查]: 请确认已安装 ttkbootstrap: pip install ttkbootstrap")
            sys.exit(1)
    else:
        logger.info("环境自检模式完成")
        print()
        print("使用方式:")
        print("  python main.py          # 环境自检")
        print("  python main.py --gui    # 启动 GUI 界面（阶段 9）")


if __name__ == "__main__":
    main()
