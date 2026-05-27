"""客户管理页 — P7 客户库功能.

提供：
- 客户列表浏览与搜索
- 新增/编辑/删除客户
- 套用到当前订单
- 可复用的客户选择对话框
"""

from __future__ import annotations

import logging
from tkinter import messagebox
from typing import TYPE_CHECKING, Any

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from src.db.repository import CustomerRepository
from src.gui.page_base import PageBase

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ==================== 客户编辑对话框 ====================


class CustomerEditDialog:
    """客户新增/编辑对话框."""

    FIELD_LABELS: list[tuple[str, str, int]] = [
        ("company_name_en", "客户公司名（英文）*", 45),
        ("company_name_cn", "客户公司名（中文）", 45),
        ("country", "国家 *", 30),
        ("address", "客户地址", 45),
        ("contact_person", "联系人", 30),
        ("phone", "电话", 30),
        ("mobile", "手机号", 30),
        ("destination", "目的地/卸货港", 30),
    ]

    def __init__(
        self,
        parent: ttk.Frame,
        title: str,
        customer: dict[str, Any] | None = None,
    ):
        """初始化对话框.

        Args:
            parent: 父级容器.
            title: 对话框标题.
            customer: 编辑模式下的现有客户数据，None 为新增模式.
        """
        self._customer = customer
        self._result: dict[str, Any] | None = None

        self._dialog = ttk.Toplevel(parent, title=title)
        self._dialog.geometry("520x480")
        self._dialog.transient(parent)
        self._dialog.grab_set()

        self._vars: dict[str, ttk.StringVar] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        """构建对话框 UI."""
        ttk.Label(
            self._dialog,
            text="客户信息",
            font=("Microsoft YaHei", 12, "bold"),
            bootstyle="primary",
        ).pack(padx=20, pady=(15, 10))

        for field, label, width in self.FIELD_LABELS:
            row = ttk.Frame(self._dialog)
            row.pack(fill=X, padx=20, pady=2)

            ttk.Label(row, text=label, font=("Microsoft YaHei", 10), width=18, anchor=W).pack(
                side=LEFT
            )

            default = ""
            if self._customer:
                default = str(self._customer.get(field, ""))

            var = ttk.StringVar(value=default)
            self._vars[field] = var
            ttk.Entry(row, textvariable=var, width=width).pack(side=LEFT, fill=X, expand=YES)

        # 按钮
        btn_frame = ttk.Frame(self._dialog)
        btn_frame.pack(fill=X, padx=20, pady=(15, 10))

        ttk.Button(
            btn_frame,
            text="保存",
            bootstyle="success",
            command=self._on_save,
        ).pack(side=LEFT, padx=(0, 10))

        ttk.Button(
            btn_frame,
            text="取消",
            bootstyle="secondary-outline",
            command=self._dialog.destroy,
        ).pack(side=LEFT)

    def _on_save(self) -> None:
        """保存按钮回调 — 校验并返回数据."""
        company_name_en = self._vars["company_name_en"].get().strip()
        country = self._vars["country"].get().strip()

        if not company_name_en:
            messagebox.showwarning("必填字段缺失", "客户公司名（英文）不能为空。")
            return
        if not country:
            messagebox.showwarning("必填字段缺失", "国家不能为空。")
            return

        self._result = {field: var.get().strip() for field, var in self._vars.items()}
        self._dialog.destroy()

    def show(self) -> dict[str, Any] | None:
        """显示对话框并等待用户操作.

        Returns:
            用户输入的数据，取消则返回 None.
        """
        self._dialog.wait_window()
        return self._result


# ==================== 客户选择对话框 ====================


class CustomerSelectDialog:
    """客户选择对话框 — 供订单信息页等外部页面使用."""

    def __init__(self, parent: ttk.Frame):
        """初始化.

        Args:
            parent: 父级容器.
        """
        self._result: dict[str, Any] | None = None

        self._dialog = ttk.Toplevel(parent, title="选择客户")
        self._dialog.geometry("780x500")
        self._dialog.transient(parent)
        self._dialog.grab_set()

        self._build_ui()
        self._load_customers()

    def _build_ui(self) -> None:
        """构建对话框 UI."""
        # 搜索栏
        search_frame = ttk.Frame(self._dialog)
        search_frame.pack(fill=X, padx=15, pady=(15, 5))

        ttk.Label(
            search_frame,
            text="搜索客户:",
            font=("Microsoft YaHei", 10),
        ).pack(side=LEFT, padx=(0, 10))

        self._search_var = ttk.StringVar()
        ttk.Entry(
            search_frame,
            textvariable=self._search_var,
            width=30,
        ).pack(side=LEFT, padx=(0, 10))
        self._search_var.trace_add("write", lambda *args: self._on_search())

        ttk.Button(
            search_frame,
            text="搜索",
            bootstyle="info-outline",
            command=self._on_search,
        ).pack(side=LEFT)

        # 列表
        list_frame = ttk.Labelframe(
            self._dialog, text="客户列表（双击选中）", padding=10, bootstyle="info"
        )
        list_frame.pack(fill=BOTH, expand=YES, padx=15, pady=(0, 10))

        columns = ("id", "name_en", "name_cn", "country", "contact", "phone")
        self._tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            height=14,
        )
        self._tree.heading("id", text="ID")
        self._tree.heading("name_en", text="公司名（英文）")
        self._tree.heading("name_cn", text="公司名（中文）")
        self._tree.heading("country", text="国家")
        self._tree.heading("contact", text="联系人")
        self._tree.heading("phone", text="电话")
        self._tree.column("id", width=50, anchor=CENTER)
        self._tree.column("name_en", width=200)
        self._tree.column("name_cn", width=200)
        self._tree.column("country", width=100, anchor=CENTER)
        self._tree.column("contact", width=80, anchor=CENTER)
        self._tree.column("phone", width=120, anchor=CENTER)

        scrollbar = ttk.Scrollbar(list_frame, orient=VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)

        self._tree.pack(side=LEFT, fill=BOTH, expand=YES)
        scrollbar.pack(side=RIGHT, fill=Y)

        self._tree.bind("<Double-1>", lambda e: self._on_select())

        # 按钮
        btn_frame = ttk.Frame(self._dialog)
        btn_frame.pack(fill=X, padx=15, pady=(0, 15))

        ttk.Button(
            btn_frame,
            text="选中客户",
            bootstyle="primary",
            command=self._on_select,
        ).pack(side=LEFT, padx=(0, 10))

        ttk.Button(
            btn_frame,
            text="取消",
            bootstyle="secondary-outline",
            command=self._dialog.destroy,
        ).pack(side=LEFT)

    def _load_customers(self, keyword: str = "") -> None:
        """加载客户列表."""
        try:
            if keyword:
                customers = CustomerRepository.search(keyword, limit=100)
            else:
                customers = CustomerRepository.list_all(limit=100)
            self._populate_tree(customers)
        except Exception as e:
            logger.exception("[错误]: 加载客户列表失败")
            messagebox.showerror(
                "加载失败",
                f"[错误]: 加载客户列表失败\n[原因]: {e}\n[排查]: 请检查数据库连接是否正常",
            )

    def _populate_tree(self, customers: list[dict[str, Any]]) -> None:
        """填充客户列表."""
        for item in self._tree.get_children():
            self._tree.delete(item)

        for c in customers:
            self._tree.insert(
                "",
                END,
                values=(
                    c.get("id", ""),
                    c.get("company_name_en", ""),
                    c.get("company_name_cn", ""),
                    c.get("country", ""),
                    c.get("contact_person", ""),
                    c.get("phone", ""),
                ),
                tags=(str(c.get("id", "")),),
            )

    def _on_search(self) -> None:
        """搜索."""
        keyword = self._search_var.get().strip()
        self._load_customers(keyword)

    def _on_select(self) -> None:
        """选中客户."""
        selection = self._tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请先选择一个客户（双击或点击列表行）。")
            return

        item = self._tree.item(selection[0])
        customer_id = item["values"][0]

        try:
            customer = CustomerRepository.get_by_id(int(customer_id))
            if customer:
                self._result = customer
                self._dialog.destroy()
            else:
                messagebox.showerror("错误", "所选客户不存在或已被删除。")
        except Exception as e:
            logger.exception("[错误]: 获取客户详情失败")
            messagebox.showerror("错误", f"[错误]: {e}")

    def show(self) -> dict[str, Any] | None:
        """显示对话框并等待用户操作.

        Returns:
            选中的客户数据，取消则返回 None.
        """
        self._dialog.wait_window()
        return self._result


# ==================== 客户管理页 ====================


class CustomerPage(PageBase):
    """客户管理页.

    显示所有客户列表，支持搜索、新增、编辑、删除及套用到当前订单。
    """

    def __init__(self, parent: ttk.Frame, app: object):
        """初始化.

        Args:
            parent: 父级容器.
            app: 主应用控制器.
        """
        super().__init__(parent, app)
        self._customer_tree: ttk.Treeview | None = None
        self._customers: list[dict[str, Any]] = []

    def build(self) -> None:
        """构建客户管理页 UI."""
        self.frame = ttk.Frame(self.parent)
        self.frame.pack(fill=BOTH, expand=YES, padx=10, pady=10)

        # ---- 标题 ----
        title_frame = ttk.Frame(self.frame)
        title_frame.pack(fill=X, padx=5, pady=(5, 10))

        ttk.Label(
            title_frame,
            text="客户管理",
            font=self.app.get_heading_font(),
            bootstyle="primary",
        ).pack(side=LEFT)

        # ---- 工具栏 ----
        toolbar = ttk.Frame(self.frame)
        toolbar.pack(fill=X, pady=(0, 5))

        ttk.Button(
            toolbar,
            text="新增客户",
            bootstyle="success-outline",
            command=self._on_add_customer,
        ).pack(side=LEFT, padx=(0, 10))

        ttk.Button(
            toolbar,
            text="编辑客户",
            bootstyle="primary-outline",
            command=self._on_edit_customer,
        ).pack(side=LEFT, padx=(0, 10))

        ttk.Button(
            toolbar,
            text="删除客户",
            bootstyle="danger-outline",
            command=self._on_delete_customer,
        ).pack(side=LEFT, padx=(0, 10))

        ttk.Button(
            toolbar,
            text="套用到当前订单",
            bootstyle="warning-outline",
            command=self._on_apply_to_order,
        ).pack(side=LEFT, padx=(0, 10))

        ttk.Button(
            toolbar,
            text="刷新列表",
            bootstyle="secondary-outline",
            command=self._refresh_list,
        ).pack(side=LEFT)

        # 搜索框
        search_frame = ttk.Frame(toolbar)
        search_frame.pack(side=RIGHT)

        self._search_var = ttk.StringVar()
        ttk.Entry(
            search_frame,
            textvariable=self._search_var,
            width=25,
        ).pack(side=LEFT, padx=(0, 5))
        self._search_var.trace_add("write", lambda *args: self._on_search())

        ttk.Button(
            search_frame,
            text="搜索",
            bootstyle="info-outline",
            command=self._on_search,
        ).pack(side=LEFT)

        # ---- 客户列表 ----
        list_frame = ttk.Labelframe(self.frame, text="客户列表", padding=10, bootstyle="info")
        list_frame.pack(fill=BOTH, expand=YES)

        columns = ("id", "name_en", "name_cn", "country", "contact", "phone", "destination")
        self._customer_tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            height=18,
        )
        self._customer_tree.heading("id", text="ID")
        self._customer_tree.heading("name_en", text="公司名（英文）")
        self._customer_tree.heading("name_cn", text="公司名（中文）")
        self._customer_tree.heading("country", text="国家")
        self._customer_tree.heading("contact", text="联系人")
        self._customer_tree.heading("phone", text="电话")
        self._customer_tree.heading("destination", text="目的地")
        self._customer_tree.column("id", width=50, anchor=CENTER)
        self._customer_tree.column("name_en", width=180)
        self._customer_tree.column("name_cn", width=160)
        self._customer_tree.column("country", width=80, anchor=CENTER)
        self._customer_tree.column("contact", width=80, anchor=CENTER)
        self._customer_tree.column("phone", width=100, anchor=CENTER)
        self._customer_tree.column("destination", width=100, anchor=CENTER)

        scrollbar = ttk.Scrollbar(list_frame, orient=VERTICAL, command=self._customer_tree.yview)
        self._customer_tree.configure(yscrollcommand=scrollbar.set)

        self._customer_tree.pack(side=LEFT, fill=BOTH, expand=YES)
        scrollbar.pack(side=RIGHT, fill=Y)

        self._customer_tree.bind("<Double-1>", lambda e: self._on_edit_customer())

        # ---- 底部状态 ----
        self._status_var = ttk.StringVar(value="共 0 个客户")
        ttk.Label(
            self.frame,
            textvariable=self._status_var,
            font=self.app.get_font(size=10),
            bootstyle="secondary",
        ).pack(anchor=W, padx=5, pady=(5, 0))

    # ==================== 客户操作 ====================

    def _on_add_customer(self) -> None:
        """新增客户."""
        dialog = CustomerEditDialog(self.frame, "新增客户")
        data = dialog.show()

        if data is None:
            return

        try:
            company_name_en = data.pop("company_name_en")
            country = data.pop("country")
            CustomerRepository.insert(
                company_name_en=company_name_en,
                country=country,
                **{k: v for k, v in data.items() if v},
            )
            messagebox.showinfo("新增成功", f"客户「{company_name_en}」已添加。")
            self._refresh_list()
            self.app.set_status(f"已新增客户: {company_name_en}")
        except Exception as e:
            logger.exception("[错误]: 新增客户失败")
            messagebox.showerror(
                "新增失败",
                f"[错误]: 新增客户失败\n[原因]: {e}\n[排查]: 请检查数据库连接是否正常",
            )

    def _on_edit_customer(self) -> None:
        """编辑选中客户."""
        if self._customer_tree is None:
            return

        selection = self._customer_tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请先在列表中选择一个客户。")
            return

        item = self._customer_tree.item(selection[0])
        customer_id = item["values"][0]

        try:
            customer = CustomerRepository.get_by_id(int(customer_id))
            if customer is None:
                messagebox.showerror("错误", "客户不存在或已被删除。")
                return
        except Exception as e:
            logger.exception("[错误]: 获取客户详情失败")
            messagebox.showerror("错误", f"[错误]: {e}")
            return

        dialog = CustomerEditDialog(self.frame, "编辑客户", customer=customer)
        data = dialog.show()

        if data is None:
            return

        try:
            company_name_en = data.pop("company_name_en")
            data["company_name_en"] = company_name_en
            country = data.pop("country")
            data["country"] = country

            CustomerRepository.update(customer_id=int(customer_id), **data)
            messagebox.showinfo("更新成功", f"客户「{company_name_en}」已更新。")
            self._refresh_list()
            self.app.set_status(f"已更新客户: {company_name_en}")
        except Exception as e:
            logger.exception("[错误]: 更新客户失败")
            messagebox.showerror(
                "更新失败",
                f"[错误]: 更新客户失败\n[原因]: {e}\n[排查]: 请检查数据库连接是否正常",
            )

    def _on_delete_customer(self) -> None:
        """删除选中客户."""
        if self._customer_tree is None:
            return

        selection = self._customer_tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请先在列表中选择一个客户。")
            return

        item = self._customer_tree.item(selection[0])
        customer_id = item["values"][0]
        customer_name = item["values"][1]

        if not messagebox.askyesno(
            "确认删除",
            f"确定要删除客户「{customer_name}」吗？\n此操作将软删除该客户记录。",
        ):
            return

        try:
            success = CustomerRepository.delete(customer_id=int(customer_id))
            if success:
                messagebox.showinfo("删除成功", f"客户「{customer_name}」已删除。")
                self._refresh_list()
                self.app.set_status(f"已删除客户: {customer_name}")
            else:
                messagebox.showerror("删除失败", "客户不存在或已被删除。")
        except Exception as e:
            logger.exception("[错误]: 删除客户失败")
            messagebox.showerror(
                "删除失败",
                f"[错误]: 删除客户失败\n[原因]: {e}\n[排查]: 请检查数据库连接是否正常",
            )

    def _on_apply_to_order(self) -> None:
        """将选中客户套用到当前订单."""
        if self._customer_tree is None:
            return

        selection = self._customer_tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请先在列表中选择一个客户。")
            return

        item = self._customer_tree.item(selection[0])
        customer_id = item["values"][0]

        try:
            customer = CustomerRepository.get_by_id(int(customer_id))
            if customer is None:
                messagebox.showerror("错误", "客户不存在或已被删除。")
                return
        except Exception as e:
            logger.exception("[错误]: 获取客户详情失败")
            messagebox.showerror("错误", f"[错误]: {e}")
            return

        # 将客户数据写入 current_order_data
        current_data = self.app.current_order_data
        if not current_data:
            current_data = {}

        customer_data: dict[str, str] = {}
        field_map = {
            "company_name_en": "company_name_en",
            "company_name_cn": "company_name_cn",
            "country": "country",
            "address": "address",
            "contact_person": "contact_person",
            "phone": "phone",
            "mobile": "mobile",
            "destination": "destination",
        }
        for db_field, data_field in field_map.items():
            val = customer.get(db_field, "")
            if val:
                customer_data[data_field] = str(val)

        current_data["customer"] = customer_data
        self.app.current_order_data = current_data

        self.app.set_status(f"已套用客户「{customer.get('company_name_en', '')}」到当前订单")

        messagebox.showinfo(
            "套用成功",
            f"客户「{customer.get('company_name_en', '')}」信息已填入当前订单。\n\n"
            f"请切换到「新建单据」页面查看和继续编辑。",
        )

        self.app.switch_page("order_info")

    # ==================== 列表操作 ====================

    def _on_search(self) -> None:
        """搜索客户."""
        keyword = self._search_var.get().strip()
        try:
            if keyword:
                customers = CustomerRepository.search(keyword, limit=100)
            else:
                customers = CustomerRepository.list_all(limit=100)
            self._customers = customers
            self._populate_tree(customers)
        except Exception as e:
            logger.exception("[错误]: 搜索客户失败")
            self._status_var.set(f"搜索失败: {e}")

    def _refresh_list(self) -> None:
        """刷新客户列表."""
        self._search_var.set("")
        try:
            self._customers = CustomerRepository.list_all(limit=100)
            self._populate_tree(self._customers)
            self.app.set_status("客户列表已刷新")
        except Exception as e:
            logger.exception("[错误]: 刷新客户列表失败")
            self._status_var.set(f"刷新失败: {e}")

    def _populate_tree(self, customers: list[dict[str, Any]]) -> None:
        """填充客户列表."""
        if self._customer_tree is None:
            return

        for item in self._customer_tree.get_children():
            self._customer_tree.delete(item)

        for c in customers:
            self._customer_tree.insert(
                "",
                END,
                values=(
                    c.get("id", ""),
                    c.get("company_name_en", ""),
                    c.get("company_name_cn", ""),
                    c.get("country", ""),
                    c.get("contact_person", ""),
                    c.get("phone", ""),
                    c.get("destination", ""),
                ),
            )

        self._status_var.set(f"共 {len(customers)} 个客户")

    def on_enter(self) -> None:
        """进入页面时刷新列表."""
        self._refresh_list()
        self.app.set_status("客户管理 — 浏览和管理客户信息")


# ========== 运行说明 ==========
# 依赖安装: pip install ttkbootstrap
# 此页面由 GuiApp 自动加载，无需单独运行
# =============================
