"""登录页：点头像 + 输密码即可切换角色（模拟银行多账号切换）。"""
import flet as ft

import config
from services.bank_service import BankService
from views import PRIMARY, PRIMARY_DARK


class LoginView:
    def __init__(self, app):
        self.app = app

    def build(self) -> ft.Control:
        accounts = BankService.list_accounts()
        return ft.Container(
            expand=True,
            bgcolor="#EAF4EC",
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.ACCOUNT_BALANCE, size=70, color=PRIMARY),
                    ft.Text(config.APP_TITLE, size=28, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
                    ft.Text(f"{config.APP_SUBTITLE} · 让孩子体验掌上银行", size=13, color="#4C6B57"),
                    ft.Container(height=10),
                    ft.Text("请点击头像登录", size=15, color="#4C6B57"),
                    ft.Container(height=6),
                    ft.Row(
                        [self._avatar(a) for a in accounts],
                        alignment=ft.MainAxisAlignment.CENTER,
                        wrap=True,
                        spacing=22,
                        run_spacing=22,
                    ),
                    ft.Container(height=18),
                    ft.Text(
                        f"家长默认密码 {config.PARENT_PIN} · 孩子默认密码 {config.KID_DEFAULT_PIN}",
                        size=12,
                        color="#7A8C81",
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                scroll=ft.ScrollMode.AUTO,
            ),
        )

    def _avatar(self, account) -> ft.Control:
        role_tag = "行长 / 家长" if account.is_parent else "VIP 储户"
        return ft.Container(
            width=140,
            padding=18,
            bgcolor=ft.Colors.WHITE,
            border_radius=20,
            shadow=ft.BoxShadow(blur_radius=12, color="#12000000", offset=ft.Offset(0, 3)),
            on_click=lambda e, aid=account.id: self._tap(aid),
            content=ft.Column(
                [
                    ft.CircleAvatar(
                        content=ft.Text(account.avatar or "🙂", size=34),
                        bgcolor="#E3F2E8",
                        radius=38,
                    ),
                    ft.Text(account.name, size=17, weight=ft.FontWeight.W_600),
                    ft.Text(role_tag, size=12, color=PRIMARY),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
        )

    def _tap(self, account_id: int):
        account = BankService.get_account(account_id)
        self.app.ask_pin(
            f"{account.name} 请验证密码",
            account.pin,
            lambda: self.app.login(account_id),
        )
