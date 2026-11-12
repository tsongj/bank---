"""心愿兑换超市：用余额购买特权/实物，透支状态禁止兑换。"""
import flet as ft

from services.bank_service import BankError, BankService
from services import voice_service
from views import ACCENT, DANGER, MUTED, PRIMARY, card, fmt, money, section


class KidMallView:
    def __init__(self, app):
        self.app = app

    def build(self) -> ft.Control:
        account = BankService.get_account(self.app.current.id)
        self.app.current = account
        wishes = BankService.list_wishes()

        body = [self._balance_bar(account)]
        if account.overdraft:
            body.append(self._overdraft_banner())
        body.append(section("心愿超市"))
        body.append(
            ft.Row(
                [self._wish_card(account, w) for w in wishes],
                wrap=True,
                spacing=12,
                run_spacing=12,
            )
        )
        return ft.Container(
            expand=True,
            padding=14,
            content=ft.Column(body, scroll=ft.ScrollMode.AUTO, spacing=14, expand=True),
        )

    # ------------------------------------------------------------------ #
    def _balance_bar(self, account) -> ft.Control:
        return card(
            ft.Row(
                [
                    ft.Icon(ft.Icons.WALLET, color=PRIMARY, size=26),
                    ft.Column(
                        [
                            ft.Text("我的余额", size=12, color=MUTED),
                            ft.Text(money(account.balance), size=20, weight=ft.FontWeight.BOLD, color=PRIMARY),
                        ],
                        spacing=2,
                    ),
                    ft.Container(expand=True),
                    ft.Text(f"征信 {account.credit_score}", size=13, color=MUTED),
                ]
            )
        )

    def _overdraft_banner(self) -> ft.Control:
        return ft.Container(
            padding=14,
            bgcolor="#FFEBEE",
            border_radius=16,
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.INFO_OUTLINE, color=DANGER, size=22),
                    ft.Text(
                        "账户透支中，征信受限，暂时不能兑换\n请先通过打卡赚币还清欠款",
                        size=13,
                        color="#B3261E",
                    ),
                ],
                spacing=10,
            ),
        )

    def _wish_card(self, account, wish) -> ft.Control:
        afford = account.balance >= wish.price and not account.overdraft
        sold_out = wish.stock == 0
        return ft.Container(
            width=160,
            padding=14,
            bgcolor=ft.Colors.WHITE,
            border_radius=18,
            shadow=ft.BoxShadow(blur_radius=10, color="#12000000", offset=ft.Offset(0, 3)),
            on_click=None if sold_out else (lambda e, wid=wish.id: self._redeem(account, wid, wish.name)),
            opacity=0.5 if sold_out else 1.0,
            content=ft.Column(
                [
                    ft.Text(wish.icon or "🎁", size=38),
                    ft.Text(wish.name, size=13, weight=ft.FontWeight.W_600, max_lines=2, text_align=ft.TextAlign.CENTER),
                    ft.Container(height=2),
                    ft.Text(f"{fmt(wish.price)} 币", size=15, weight=ft.FontWeight.BOLD, color=ACCENT),
                    ft.Text(
                        "已兑完" if sold_out else ("立即兑换" if afford else "余额不足"),
                        size=11,
                        color=MUTED if not afford else PRIMARY,
                    ),
                ],
                spacing=4,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def _redeem(self, account, wish_id: int, name: str):
        def do_redeem():
            try:
                BankService.redeem(account.id, wish_id, account.name)
                voice_service.speak(f"恭喜你，成功兑换{name}")
                self.app.snack(f"兑换成功：{name}", PRIMARY)
                self.app.refresh()
            except BankError as exc:
                self.app.snack(str(exc), DANGER)

        self.app.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("确认兑换"),
                content=ft.Text(f"确定用余额兑换「{name}」吗？"),
                actions=[
                    ft.TextButton("再想想", on_click=lambda e: self.app.page.pop_dialog()),
                    ft.FilledButton("确认兑换", on_click=lambda e: (self.app.page.pop_dialog(), do_redeem())),
                ],
            )
        )
