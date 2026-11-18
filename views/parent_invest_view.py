import flet as ft
import config
from database.db import session_scope
from database.models import TxType, InvestmentRequest, Account
from services.bank_service import BankError, BankService
from services.task_service import TaskService
from . import ACCENT, BLUE, DANGER, MUTED, PRIMARY, card, fmt, money, section

class ParentInvestView:
    def __init__(self, app):
        self.app = app

    def build(self) -> ft.Control:
        kids = TaskService.list_kids()
        if not kids:
            return ft.Container(content=ft.Text("请先添加孩子账户", color=MUTED), padding=20)

        # 确保有选中的孩子
        if self.app.selected_kid_id not in [k.id for k in kids]:
            self.app.selected_kid_id = kids[0].id
        kid = next(k for k in kids if k.id == self.app.selected_kid_id)

        content_list = [
            ft.Row([ft.Icon(ft.Icons.ACCOUNT_BALANCE_WALLET, color=PRIMARY, size=28), ft.Text("投资与理财频道", size=20, weight=ft.FontWeight.BOLD)]),
            self._kid_selector(kids, kid),
            self._direct_invest_section(kid),
            self._investment_approval_section(),
            self._deposit_product_section(),
            self._fund_product_section(),
            self._investment_history_section(kid),
        ]

        return ft.Container(
            expand=True,
            padding=14,
            content=ft.Column(
                content_list,
                scroll=ft.ScrollMode.AUTO,
                spacing=14,
                expand=True,
            ),
        )

    def _kid_selector(self, kids, current) -> ft.Control:
        chips = [
            ft.Text("查看投资账户：", size=13, color=MUTED),
            *[
                ft.TextButton(
                    k.name,
                    on_click=lambda e, kid_id=k.id: self._select_kid(kid_id),
                    style=ft.ButtonStyle(color=PRIMARY if k.id == current.id else MUTED)
                )
                for k in kids
            ],
        ]
        return card(
            ft.Row(
                [
                    *chips,
                    ft.Container(expand=True),
                    ft.IconButton(ft.Icons.PERSON_ADD_ALT_1, on_click=lambda e: self._add_kid_dlg()),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER
            )
        )

    def _add_kid_dlg(self):
        name = ft.TextField(label="成员姓名", hint_text="如：小明")
        avatar = ft.TextField(label="头像 Emoji", value="🧒")
        pin = ft.TextField(label="初始密码", value="0000", password=True)
        role = ft.Dropdown(
            options=[ft.dropdown.Option("kid", "孩子"), ft.dropdown.Option("parent", "家长")],
            value="kid"
        )
        
        def submit(e):
            BankService.add_account(name.value, role.value, avatar.value, pin.value)
            self.app.page.pop_dialog()
            self.app.snack("新账户已创建", PRIMARY)
            self.app.refresh()

        self.app.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("添加新成员账户"),
                content=ft.Column([name, role, avatar, pin], tight=True, spacing=10),
                actions=[ft.TextButton("取消", on_click=lambda e: self.app.page.pop_dialog()), ft.FilledButton("创建", on_click=submit)],
            )
        )

    def _select_kid(self, kid_id: int):
        self.app.selected_kid_id = kid_id
        self.app.refresh()

    def _direct_invest_section(self, kid) -> ft.Control:
        amount = ft.TextField(label="投资金额", value="100", width=120, keyboard_type=ft.KeyboardType.NUMBER, border_radius=12)
        purpose = ft.TextField(label="投资用途", hint_text="如：钢琴课、乐高、书本", expand=True, border_radius=12)
        currency = ft.Dropdown(
            options=[ft.dropdown.Option("cny", "人民币"), ft.dropdown.Option("coin", "金币")],
            value="cny",
            width=100,
            border_radius=12
        )

        def submit(e):
            try:
                amt = float(amount.value or 0)
                if amt <= 0: raise ValueError
                BankService.direct_invest(kid.id, amt, purpose.value, currency.value, self.app.current.name)
                self.app.snack(f"已成功为 {kid.name} 注入投资", PRIMARY)
                self.app.refresh()
            except ValueError:
                self.app.snack("请输入有效金额", DANGER)
            except BankError as exc:
                self.app.snack(str(exc), DANGER)

        return ft.Column([
            section(f"为 {kid.name} 增加投资"),
            card(
                ft.Column([
                    ft.Row([currency, amount, purpose], spacing=10),
                    ft.FilledButton("确认投入", icon=ft.Icons.ADD_CIRCLE, on_click=submit, expand=True)
                ], spacing=12)
            )
        ], spacing=10)

    def _investment_approval_section(self) -> ft.Control:
        pending = BankService.list_investment_requests(status="pending")
        if not pending:
            return ft.Container()
        
        body = ft.Column([self._investment_approval_row(req) for req in pending], spacing=10)
        return ft.Column([section(f"待处理投资申请（{len(pending)}）"), card(body)], spacing=10)

    def _investment_approval_row(self, req) -> ft.Control:
        kid = BankService.get_account(req.account_id)
        unit = "元" if req.currency == "cny" else "金币"
        return ft.Row(
            [
                ft.Text("💰", size=18),
                ft.Column(
                    [
                        ft.Text(f"{kid.name} · {req.amount}{unit}", size=14, weight=ft.FontWeight.W_600),
                        ft.Text(req.purpose, size=11, color=MUTED),
                    ],
                    spacing=2,
                ),
                ft.Container(expand=True),
                ft.TextButton("驳回", on_click=lambda e: self._reject_investment(req.id)),
                ft.FilledButton("批准投资", on_click=lambda e: self._approve_investment(req.id)),
            ],
            spacing=6,
        )

    def _approve_investment(self, request_id: int):
        self.app.ask_pin("审批验证", self.app.current.pin, lambda: self._do_approve_investment(request_id))

    def _do_approve_investment(self, request_id: int):
        BankService.approve_investment_request(request_id, self.app.current.name)
        self.app.snack("投资已批准", PRIMARY)
        self.app.refresh()

    def _reject_investment(self, request_id: int):
        with session_scope() as s:
            req = s.get(InvestmentRequest, request_id)
            if req:
                req.status = "rejected"
        self.app.snack("已驳回申请", ACCENT)
        self.app.refresh()

    def _deposit_product_section(self) -> ft.Control:
        products = BankService.list_deposit_products(only_enabled=False)
        rows = [self._deposit_product_row(p) for p in products]
        return ft.Column(
            [
                ft.Row([section("定期存单发行"), ft.Container(expand=True), ft.TextButton("＋ 发布新存单", on_click=lambda e: self._add_deposit_dlg())]),
                card(ft.Column(rows, spacing=8) if rows else ft.Text("暂无定期产品", size=13, color=MUTED)),
            ],
            spacing=10,
        )

    def _deposit_product_row(self, p) -> ft.Control:
        return ft.Row(
            [
                ft.Icon(ft.Icons.SAVINGS_OUTLINED, color=PRIMARY, size=20),
                ft.Text(f"{p.title} ({p.lock_days}天)", size=14, expand=True),
                ft.Text(f"{p.rate:.0%}", size=14, weight=ft.FontWeight.BOLD, color=PRIMARY),
                ft.Switch(value=p.enabled, on_change=lambda e: self._toggle_deposit(p.id)),
            ],
            spacing=8,
        )

    def _toggle_deposit(self, pid):
        BankService.toggle_deposit_product(pid)
        self.app.refresh()

    def _add_deposit_dlg(self):
        title = ft.TextField(label="产品名称", value="教育储备金")
        rate = ft.TextField(label="年利率 (如 0.1)", value="0.1")
        days = ft.TextField(label="存期 (天)", value="30")

        def submit(e):
            BankService.add_deposit_product(title.value, float(rate.value), int(days.value))
            self.app.page.pop_dialog()
            self.app.refresh()

        dlg = ft.AlertDialog(
            title=ft.Text("发布定期存款产品"),
            content=ft.Column([title, rate, days], tight=True),
            actions=[ft.TextButton("取消", on_click=lambda e: self.app.page.pop_dialog()), ft.FilledButton("发布", on_click=submit)],
        )
        self.app.page.show_dialog(dlg)

    def _fund_product_section(self) -> ft.Control:
        funds = BankService.list_funds(only_enabled=False)
        rows = [self._fund_product_row(f) for f in funds]
        return ft.Column(
            [
                ft.Row([section("家庭理财产品发行"), ft.Container(expand=True), ft.TextButton("＋ 发行新理财", on_click=lambda e: self._add_fund_dlg())]),
                card(ft.Column(rows, spacing=8) if rows else ft.Text("暂无理财产品", size=13, color=MUTED)),
            ],
            spacing=10,
        )

    def _fund_product_row(self, f) -> ft.Control:
        return ft.Row(
            [
                ft.Text(f.icon, size=18),
                ft.Column([ft.Text(f.name, size=14), ft.Text(f.code, size=11, color=MUTED)], spacing=0),
                ft.Container(expand=True),
                ft.Text(f"净值: {f.nav:.4f}", size=13, weight=ft.FontWeight.BOLD),
                ft.IconButton(ft.Icons.TRENDING_UP, tooltip="调整净值", on_click=lambda e: self._update_nav_dlg(f)),
            ],
            spacing=8,
        )

    def _add_fund_dlg(self):
        name = ft.TextField(label="理财名称", value="小目标混合基金")
        code = ft.TextField(label="基金代码", value="KID001")
        nav = ft.TextField(label="初始净值", value="1.0")

        def submit(e):
            BankService.add_fund_product(name.value, code.value, "🏦", float(nav.value))
            self.app.page.pop_dialog()
            self.app.refresh()

        dlg = ft.AlertDialog(
            title=ft.Text("发行家庭理财"),
            content=ft.Column([name, code, nav], tight=True),
            actions=[ft.TextButton("取消", on_click=lambda e: self.app.page.pop_dialog()), ft.FilledButton("发行", on_click=submit)],
        )
        self.app.page.show_dialog(dlg)

    def _update_nav_dlg(self, fund):
        nav = ft.TextField(label="最新净值", value=str(fund.nav))
        def submit(e):
            BankService.update_fund_nav(fund.id, float(nav.value))
            self.app.page.pop_dialog()
            self.app.refresh()

        dlg = ft.AlertDialog(
            title=ft.Text(f"调整理财净值: {fund.name}"),
            content=nav,
            actions=[ft.TextButton("取消", on_click=lambda e: self.app.page.pop_dialog()), ft.FilledButton("保存", on_click=submit)],
        )
        self.app.page.show_dialog(dlg)

    def _investment_history_section(self, kid) -> ft.Control:
        invests = BankService.list_investments(account_id=kid.id)
        if not invests:
            return ft.Container()
        
        def inv_row(inv):
            unit = "元" if inv.currency == "cny" else "金币"
            return ft.Row([
                ft.Text(inv.invested_at.strftime("%Y-%m-%d"), size=11, color=MUTED),
                ft.Text(inv.purpose, size=13, expand=True),
                ft.Text(f"+{inv.amount}{unit}", weight=ft.FontWeight.BOLD, color=PRIMARY)
            ])

        return ft.Column([
            section(f"{kid.name} 的投资记录"),
            card(ft.Column([inv_row(i) for i in invests], spacing=10))
        ], spacing=10)
