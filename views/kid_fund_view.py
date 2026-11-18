"""孩子端理财视图：查看理财产品、持仓及净值走势。"""
import flet as ft
from services.bank_service import BankService, BankError
from views import PRIMARY, ACCENT, MUTED, card, section, fmt, money

class KidFundView:
    def __init__(self, app):
        self.app = app

    def build(self) -> ft.Control:
        account = BankService.get_account(self.app.current.id)
        funds = BankService.list_funds()
        holdings = {h.fund_id: h for h in account.holdings}

        return ft.Container(
            expand=True,
            padding=14,
            content=ft.Column(
                [
                    section("我的持仓"),
                    self._holding_section(holdings, funds),
                    section("理财超市"),
                    ft.Column([self._fund_card(f, holdings.get(f.id)) for f in funds], spacing=10),
                ],
                scroll=ft.ScrollMode.AUTO,
                spacing=14,
                expand=True,
            ),
        )

    def _holding_section(self, holdings, funds) -> ft.Control:
        if not holdings:
            return card(ft.Text("还没有持有任何理财产品，去超市看看吧", size=13, color=MUTED))
        
        total_market_value = 0
        total_profit = 0
        for fund_id, h in holdings.items():
            fund = next((f for f in funds if f.id == fund_id), None)
            if fund:
                market_value = h.shares * fund.nav
                profit = market_value - h.cost
                total_market_value += market_value
                total_profit += profit

        return card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column([ft.Text("总市值", size=12, color=MUTED), ft.Text(money(total_market_value), size=20, weight=ft.FontWeight.BOLD)]),
                            ft.VerticalDivider(),
                            ft.Column([ft.Text("昨日收益", size=12, color=MUTED), ft.Text(f"+{fmt(total_profit)}", size=20, weight=ft.FontWeight.BOLD, color=ACCENT)]),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_AROUND
                    )
                ]
            )
        )

    def _fund_card(self, fund, holding) -> ft.Control:
        profit_pct = 0
        if holding and holding.cost > 0:
            profit_pct = (holding.shares * fund.nav - holding.cost) / holding.cost * 100

        return card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(fund.icon, size=24),
                            ft.Column([ft.Text(fund.name, size=16, weight=ft.FontWeight.BOLD), ft.Text(fund.code, size=11, color=MUTED)], spacing=0),
                            ft.Container(expand=True),
                            ft.Column(
                                [
                                    ft.Text(f"净值 {fund.nav:.4f}", size=14, weight=ft.FontWeight.W_600),
                                    ft.Text(f"持有: {holding.shares:.2f}份" if holding else "未持有", size=11, color=MUTED),
                                ],
                                horizontal_alignment=ft.CrossAxisAlignment.END
                            )
                        ]
                    ),
                    ft.Divider(height=1, color="#F0F0F0"),
                    ft.Row(
                        [
                            ft.FilledButton("买入", icon=ft.Icons.ADD, on_click=lambda e: self._buy_dlg(fund), expand=True),
                            ft.OutlinedButton("卖出", icon=ft.Icons.REMOVE, on_click=lambda e: self._sell_dlg(fund, holding), expand=True, disabled=not holding or holding.shares <= 0),
                        ],
                        spacing=10
                    )
                ],
                spacing=12
            )
        )

    def _buy_dlg(self, fund):
        amount = ft.TextField(label="买入金额 (金币)", keyboard_type=ft.KeyboardType.NUMBER, border_radius=12)
        def submit(e):
            try:
                BankService.buy_fund(self.app.current.id, fund.id, float(amount.value))
                self.app.page.pop_dialog()
                self.app.snack(f"成功买入 {fund.name}", PRIMARY)
                self.app.refresh()
            except Exception as exc:
                self.app.snack(str(exc), DANGER)

        dlg = ft.AlertDialog(
            title=ft.Text(f"买入 {fund.name}"),
            content=amount,
            actions=[ft.TextButton("取消", on_click=lambda e: self.app.page.pop_dialog()), ft.FilledButton("确定买入", on_click=submit)],
        )
        self.app.page.show_dialog(dlg)

    def _sell_dlg(self, fund, holding):
        shares = ft.TextField(label=f"卖出份额 (最多 {holding.shares:.2f})", value=str(holding.shares), keyboard_type=ft.KeyboardType.NUMBER, border_radius=12)
        def submit(e):
            try:
                BankService.sell_fund(self.app.current.id, fund.id, float(shares.value))
                self.app.page.pop_dialog()
                self.app.snack(f"成功赎回 {fund.name}", PRIMARY)
                self.app.refresh()
            except Exception as exc:
                self.app.snack(str(exc), DANGER)

        dlg = ft.AlertDialog(
            title=ft.Text(f"卖出 {fund.name}"),
            content=shares,
            actions=[ft.TextButton("取消", on_click=lambda e: self.app.page.pop_dialog()), ft.FilledButton("确定卖出", on_click=submit)],
        )
        self.app.page.show_dialog(dlg)
