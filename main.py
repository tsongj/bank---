"""家庭成长银行 · 程序总入口。

职责：
1. 初始化数据库并写入预设账户 / 规则 / 奖品；
2. 搭建页面外壳（AppBar + 底部导航），按角色路由到不同界面；
3. 统一提供登录切换、审批密码、提示条等公共服务。
"""
import flet as ft

import config
from database.db import init_db, session_scope
from services.bank_service import BankService
from services.task_service import TaskService
from views import BG_APP, DANGER, PRIMARY
from views.bill_history_view import BillHistoryView
from views.kid_home_view import KidHomeView
from views.kid_mall_view import KidMallView
from views.login_view import LoginView
from views.parent_admin_view import ParentAdminView


def bootstrap():
    """建表 + 写入预设数据（幂等）。"""
    init_db()
    with session_scope() as session:
        BankService.seed_default_accounts(session)
        BankService.seed_default_wishes(session)
        TaskService.seed_default_rules(session)


class FamilyBankApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.current = None            # 当前登录账户
        self.tab = 0                   # 当前底部导航索引
        self.selected_kid_id = None    # 家长端选中的孩子
        self.bill_account_id = None    # 账单页查看的账户
        self._tabs = []                # [(标题, 图标, View 类)]

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    def start(self):
        p = self.page
        p.title = config.APP_TITLE
        p.theme = ft.Theme(color_scheme_seed=PRIMARY)
        p.theme_mode = ft.ThemeMode.LIGHT
        p.bgcolor = BG_APP
        p.padding = 0
        self.show_login()

    # ------------------------------------------------------------------ #
    # 登录 / 切换角色
    # ------------------------------------------------------------------ #
    def show_login(self):
        self.current = None
        self.page.appbar = None
        self.page.navigation_bar = None
        self._render(LoginView(self).build())

    def login(self, account_id: int):
        account = BankService.get_account(account_id)
        self.current = account
        self.tab = 0
        kids = TaskService.list_kids()
        kid_ids = [k.id for k in kids]
        if account.role == "kid":
            self.selected_kid_id = account.id
            self.bill_account_id = account.id
        else:
            self.selected_kid_id = kid_ids[0] if kid_ids else None
            self.bill_account_id = kid_ids[0] if kid_ids else None

        self._build_shell()
        self.refresh()

    # ------------------------------------------------------------------ #
    # 页面外壳
    # ------------------------------------------------------------------ #
    def _role_tabs(self):
        if self.current is not None and self.current.role == "kid":
            return [
                ("我的账户", ft.Icons.HOME, KidHomeView),
                ("心愿超市", ft.Icons.STORE, KidMallView),
                ("电子账单", ft.Icons.RECEIPT_LONG, BillHistoryView),
            ]
        return [
            ("管理台", ft.Icons.WALLET, ParentAdminView),
            ("电子账单", ft.Icons.RECEIPT_LONG, BillHistoryView),
        ]

    def _build_shell(self):
        role_name = "行长" if self.current.role == "parent" else "储户"
        self.page.appbar = ft.AppBar(
            title=ft.Text(f"{config.APP_TITLE} · {self.current.name}（{role_name}）"),
            bgcolor=PRIMARY,
            color=ft.Colors.WHITE,
            actions=[
                ft.IconButton(
                    icon=ft.Icons.SWAP_HORIZ,
                    tooltip="切换账号",
                    icon_color=ft.Colors.WHITE,
                    on_click=lambda e: self.show_login(),
                )
            ],
        )
        self._sync_nav()

    def _sync_nav(self):
        self._tabs = self._role_tabs()
        if self.tab >= len(self._tabs):
            self.tab = 0
        pending = TaskService.pending_count() if self.current.role == "parent" else 0
        destinations = []
        for index, (label, icon, _) in enumerate(self._tabs):
            destinations.append(
                ft.NavigationBarDestination(
                    icon=icon,
                    label=label,
                    badge=str(pending) if (index == 0 and pending) else None,
                )
            )
        self.page.navigation_bar = ft.NavigationBar(
            selected_index=self.tab,
            on_change=self._on_nav_change,
            destinations=destinations,
        )

    def _on_nav_change(self, e):
        self.tab = e.control.selected_index
        self.refresh()

    def switch_tab(self, index: int):
        self.tab = index
        if self.page.navigation_bar is not None:
            self.page.navigation_bar.selected_index = index
        self.refresh()

    # ------------------------------------------------------------------ #
    # 渲染
    # ------------------------------------------------------------------ #
    def refresh(self):
        if self.current is None:
            return
        self._sync_nav()
        view_cls = self._tabs[self.tab][2]
        self._render(view_cls(self).build())

    def _render(self, control):
        self.page.clean()
        self.page.add(control)
        self.page.update()

    # ------------------------------------------------------------------ #
    # 公共服务：提示条 / 密码验证
    # ------------------------------------------------------------------ #
    def snack(self, text: str, color: str = None):
        self.page.show_dialog(
            ft.SnackBar(
                content=ft.Text(text, color=ft.Colors.WHITE),
                bgcolor=color or "#24352B",
                duration=2400,
            )
        )

    def ask_pin(self, title: str, expected: str, on_ok):
        """弹出 4 位密码框，校验通过后执行 on_ok。"""
        field = ft.TextField(
            password=True,
            keyboard_type=ft.KeyboardType.NUMBER,
            max_length=4,
            width=200,
            text_align=ft.TextAlign.CENTER,
            autofocus=True,
            label="4 位密码",
            border_radius=12,
        )
        error = ft.Text("", size=12, color=DANGER)

        def submit(e=None):
            if (field.value or "").strip() == expected:
                self.page.pop_dialog()
                on_ok()
            else:
                error.value = "密码不正确，请重试"
                self.page.update()

        field.on_submit = submit
        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(title),
                content=ft.Column([field, error], spacing=10, width=240),
                actions=[
                    ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
                    ft.FilledButton("确认", on_click=submit),
                ],
            )
        )


def main(page: ft.Page):
    bootstrap()
    FamilyBankApp(page).start()


if __name__ == "__main__":
    ft.run(main)
