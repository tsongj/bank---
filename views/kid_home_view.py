"""孩子端首页：虚拟银行卡 + 成长金库 + 任务申请 + 梦想存钱罐。

适龄设计：大图标、少文字、点击即朗读，任务提交后进入“黄灯待审核”。
"""
from datetime import datetime, timedelta

import flet as ft

import config
from database.db import session_scope
from database.models import Account
from services.bank_service import BankError, BankService
from services.task_service import TaskService
from services import voice_service
from . import (
    ACCENT,
    BG_APP,
    BLUE,
    DANGER,
    MUTED,
    PRIMARY,
    card,
    fmt,
    money,
    section,
    tx_title,
    tx_visual,
)

JAR_GOAL = 300  # 存钱罐可视化目标（满罐）


class KidHomeView:
    def __init__(self, app):
        self.app = app

    # ------------------------------------------------------------------ #
    def build(self) -> ft.Control:
        account = BankService.get_account(self.app.current.id)
        self.app.current = account
        self._account = account
        self.show_investment = getattr(self.app, "show_investment", False)

        return ft.Container(
            expand=True,
            padding=14,
            content=ft.Column(
                [
                    self._bank_card(account),
                    self._flow_row(account),
                    self._quick_entries(account),
                    self._transfer_section(account),
                    self._fx_section(account),
                    self._real_transfer_section(account),
                    self._investment_fund_section(account),
                    self._task_section(account),
                    self._jar_section(account),
                    self._recent_section(account),
                    self._account_settings_section(account),
                ],
                scroll=ft.ScrollMode.AUTO,
                spacing=14,
                expand=True,
            ),
        )

    # ------------------------------------------------------------------ #
    # 转账
    # ------------------------------------------------------------------ #
    def _transfer_section(self, account) -> ft.Control:
        return ft.Column(
            [
                section("转账服务"),
                card(
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.SEND, color=PRIMARY, size=20),
                            ft.Text("转账给家人", size=14, weight=ft.FontWeight.W_600),
                            ft.Container(expand=True),
                            ft.TextButton("去转账", on_click=lambda e: self._transfer_dlg(account)),
                        ]
                    )
                ),
            ],
            spacing=10,
        )

    def _transfer_dlg(self, account):
        kids = BankService.list_accounts(role="kid")
        others = [k for k in kids if k.id != account.id]
        parent = BankService.list_accounts(role="parent")[0]
        
        target = ft.Dropdown(
            label="收款人",
            options=[
                ft.dropdown.Option(str(k.id), f"{k.name} (姐姐/弟弟)") for k in others
            ] + [ft.dropdown.Option(str(parent.id), f"{parent.name} (爸爸)")],
            border_radius=12
        )
        currency = ft.Dropdown(
            label="选择币种",
            options=[ft.dropdown.Option("coin", "金币"), ft.dropdown.Option("cny", "人民币")],
            value="coin",
            border_radius=12
        )
        amount = ft.TextField(label="金额", keyboard_type=ft.KeyboardType.NUMBER, border_radius=12)
        reason = ft.TextField(label="备注", hint_text="想对他说的话", border_radius=12)

        def submit(e):
            try:
                BankService.transfer(account.id, int(target.value), float(amount.value), reason.value, currency=currency.value)
                self.app.page.pop_dialog()
                self.app.snack("转账成功！", PRIMARY)
                self.app.refresh()
            except Exception as exc:
                self.app.snack(str(exc), DANGER)

        dlg = ft.AlertDialog(
            title=ft.Text("家人转账"),
            content=ft.Column([target, currency, amount, reason], tight=True, spacing=12),
            actions=[ft.TextButton("取消", on_click=lambda e: self.app.page.pop_dialog()), ft.FilledButton("立即转账", on_click=submit)],
        )
        self.app.page.show_dialog(dlg)

    # ------------------------------------------------------------------ #
    # 外汇兑换
    # ------------------------------------------------------------------ #
    def _fx_section(self, account) -> ft.Control:
        return ft.Column(
            [
                section("外汇功能 (RMB/金币)"),
                card(
                    ft.Column(
                        [
                            ft.Row([ft.Text("人民币账户余额:", size=12, color=MUTED), ft.Text(f"¥ {account.cny_balance:.2f}", size=14, weight=ft.FontWeight.BOLD)]),
                            ft.Row([ft.Text("当前汇率:", size=12, color=MUTED), ft.Text(f"1金币 = {config.FX_MID_RATE}元")]),
                            ft.Row(
                                [
                                    ft.FilledButton("金币换人民币", icon=ft.Icons.CURRENCY_EXCHANGE, on_click=lambda e: self._fx_dlg(account, "sell"), expand=True),
                                    ft.FilledButton("人民币换金币", icon=ft.Icons.CURRENCY_YEN, on_click=lambda e: self._fx_dlg(account, "buy"), expand=True),
                                ],
                                spacing=10
                            )
                        ],
                        spacing=8
                    )
                ),
            ],
            spacing=10,
        )

    def _fx_dlg(self, account, mode):
        title = "金币换人民币" if mode == "sell" else "人民币换金币"
        coin = ft.TextField(label="金币数量", keyboard_type=ft.KeyboardType.NUMBER, border_radius=12)
        
        def submit(e):
            try:
                BankService.exchange_currency(account.id, float(coin.value), mode, config.FX_MID_RATE)
                self.app.page.pop_dialog()
                self.app.snack("兑换成功！", PRIMARY)
                self.app.refresh()
            except Exception as exc:
                self.app.snack(str(exc), DANGER)

        dlg = ft.AlertDialog(
            title=ft.Text(title),
            content=coin,
            actions=[ft.TextButton("取消", on_click=lambda e: self.app.page.pop_dialog()), ft.FilledButton("确定兑换", on_click=submit)],
        )
        self.app.page.show_dialog(dlg)

    # ------------------------------------------------------------------ #
    # 真实账户转账
    # ------------------------------------------------------------------ #
    def _real_transfer_section(self, account) -> ft.Control:
        return ft.Column(
            [
                section("真实世界转账 (人民币/实物)"),
                card(
                    ft.Column(
                        [
                            ft.Text("在这里可以将人民币转入或转出真实银行账户", size=12, color=MUTED),
                            ft.Row(
                                [
                                    ft.FilledButton("转入真实账户", icon=ft.Icons.OUTGOING_MAIL, on_click=lambda e: self._real_transfer_dlg(account, "to_real"), expand=True),
                                    ft.FilledButton("从真实账户转入", icon=ft.Icons.MOVE_TO_INBOX, on_click=lambda e: self._real_transfer_dlg(account, "from_real"), expand=True),
                                ],
                                spacing=10
                            )
                        ],
                        spacing=8
                    )
                ),
            ],
            spacing=10,
        )

    def _real_transfer_dlg(self, account, mode):
        title = "转入真实账户" if mode == "to_real" else "从真实账户转入"
        amount = ft.TextField(label="金额 (元)", keyboard_type=ft.KeyboardType.NUMBER, border_radius=12)
        
        def submit(e):
            try:
                BankService.transfer_cny_real(account.id, float(amount.value), mode)
                self.app.page.pop_dialog()
                self.app.snack("操作成功！", PRIMARY)
                self.app.refresh()
            except Exception as exc:
                self.app.snack(str(exc), DANGER)

        dlg = ft.AlertDialog(
            title=ft.Text(title),
            content=amount,
            actions=[ft.TextButton("取消", on_click=lambda e: self.app.page.pop_dialog()), ft.FilledButton("确定", on_click=submit)],
        )
        self.app.page.show_dialog(dlg)

    # ------------------------------------------------------------------ #
    # 投资基金申请
    # ------------------------------------------------------------------ #
    def _investment_fund_section(self, account) -> ft.Control:
        return ft.Column(
            [
                section("学习投资基金"),
                card(
                    ft.Column(
                        [
                            ft.Text("想要为学习申请一笔投资吗？", size=13),
                            ft.FilledButton("申请投资基金", icon=ft.Icons.SCHOOL, on_click=lambda e: self._invest_req_dlg(account)),
                        ]
                    )
                ),
            ],
            spacing=10,
        )

    def _invest_req_dlg(self, account):
        amount = ft.TextField(label="申请金额 (元)", keyboard_type=ft.KeyboardType.NUMBER, border_radius=12)
        purpose = ft.TextField(label="用途备注", hint_text="例如：购买奥数网课", border_radius=12)

        def submit(e):
            BankService.submit_investment_request(account.id, float(amount.value), purpose.value)
            self.app.page.pop_dialog()
            self.app.snack("申请已提交，等待家长审批", PRIMARY)
            self.app.refresh()

        dlg = ft.AlertDialog(
            title=ft.Text("申请投资基金"),
            content=ft.Column([amount, purpose], tight=True, spacing=12),
            actions=[ft.TextButton("取消", on_click=lambda e: self.app.page.pop_dialog()), ft.FilledButton("提交申请", on_click=submit)],
        )
        self.app.page.show_dialog(dlg)

    # ------------------------------------------------------------------ #
    # 账户设置
    # ------------------------------------------------------------------ #
    def _account_settings_section(self, account) -> ft.Control:
        return ft.Column(
            [
                section("安全与账户"),
                card(
                    ft.Column(
                        [
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.LOCK_OUTLINED),
                                title=ft.Text("修改我的卡片密码"),
                                on_click=lambda e: self._change_pin_dlg(account),
                            ),
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.ACCOUNT_BALANCE),
                                title=ft.Text("真实世界账户 (取款)"),
                                subtitle=ft.Text(f"余额: ¥ {account.real_balance:.2f}"),
                                on_click=lambda e: self._withdraw_dlg(account),
                            ),
                        ]
                    )
                ),
            ],
            spacing=10,
        )

    def _change_pin_dlg(self, account):
        new_pin = ft.TextField(label="新密码 (4位数字)", password=True, max_length=4, keyboard_type=ft.KeyboardType.NUMBER)
        def submit(e):
            BankService.update_pin(account.id, new_pin.value)
            self.app.snack("密码已修改", PRIMARY)
            self.app.page.pop_dialog()
        
        dlg = ft.AlertDialog(
            title=ft.Text("修改卡片密码"),
            content=new_pin,
            actions=[ft.TextButton("取消", on_click=lambda e: self.app.page.pop_dialog()), ft.FilledButton("保存", on_click=submit)],
        )
        self.app.page.show_dialog(dlg)

    def _withdraw_dlg(self, account):
        amount = ft.TextField(label="取款金额 (元)", keyboard_type=ft.KeyboardType.NUMBER)
        def submit(e):
            try:
                BankService.withdraw_to_real_account(account.id, float(amount.value))
                self.app.snack("已取款到真实世界账户！", PRIMARY)
                self.app.page.pop_dialog()
                self.app.refresh()
            except Exception as exc:
                self.app.snack(str(exc), DANGER)

        dlg = ft.AlertDialog(
            title=ft.Text("取款到真实账户"),
            content=ft.Column([ft.Text("只能取出人民币账户里的钱哦", size=12, color=MUTED), amount], tight=True),
            actions=[ft.TextButton("取消", on_click=lambda e: self.app.page.pop_dialog()), ft.FilledButton("确认取款", on_click=submit)],
        )
        self.app.page.show_dialog(dlg)

    # ------------------------------------------------------------------ #
    # 虚拟银行卡
    # ------------------------------------------------------------------ #
    def _bank_card(self, account) -> ft.Control:
        status = "征信良好" if not account.overdraft else "⚠ 已透支，征信降级"
        
        # 计算投资总额
        total_invested_cny = sum(i.amount for i in account.investments if i.currency == "cny")
        total_invested_coin = sum(i.amount for i in account.investments if i.currency == "coin")
        
        def toggle_view(e):
            self.app.show_investment = not getattr(self.app, "show_investment", False)
            self.app.refresh()

        display_label = "投资资金总额 (RMB)" if self.show_investment else "账户余额"
        display_amount = total_invested_cny if self.show_investment else account.balance
        display_symbol = "元" if self.show_investment else config.CURRENCY_SYMBOL
        card_color = ["#6A11CB", "#2575FC"] if self.show_investment else ["#12A65B", "#0B7A42"]

        return ft.GestureDetector(
            on_horizontal_drag_update=lambda e: None, # 模拟滑动，实际用点击切换
            on_tap=toggle_view,
            content=ft.Container(
                padding=20,
                border_radius=22,
                gradient=ft.LinearGradient(
                    colors=card_color,
                    begin=ft.Alignment.TOP_LEFT,
                    end=ft.Alignment.BOTTOM_RIGHT,
                ),
                shadow=ft.BoxShadow(blur_radius=16, color="#33000000", offset=ft.Offset(0, 6)),
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(config.APP_TITLE, color="#EAFBEF", size=13, weight=ft.FontWeight.W_600),
                                ft.Container(expand=True),
                                ft.Icon(ft.Icons.SWAP_HORIZ, color="#EAFBEF", size=20),
                            ]
                        ),
                        ft.Container(height=12),
                        ft.Text(display_label, color="#CDEFD9", size=12),
                        ft.Row(
                            [
                                ft.Text(money(display_amount, symbol=display_symbol), color=ft.Colors.WHITE, size=34, weight=ft.FontWeight.BOLD),
                                ft.Container(expand=True),
                                ft.Column(
                                    [
                                        ft.Text("其他账户", color="#CDEFD9", size=12, weight=ft.FontWeight.W_500),
                                        ft.Text(
                                             f"¥ {account.cny_balance:.2f} | 实: ¥{account.real_balance:.2f}" if not self.show_investment else f"{total_invested_coin:g} 金币",
                                             color=ft.Colors.WHITE, size=16, weight=ft.FontWeight.BOLD
                                         ),
                                    ],
                                    horizontal_alignment=ft.CrossAxisAlignment.END,
                                    spacing=0
                                )
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.END
                        ),
                        ft.Container(height=10),
                        ft.Row(
                            [
                                ft.Text(account.card_no or "—", color="#CDEFD9", size=13),
                                ft.Container(expand=True),
                                ft.Text(f"征信 {account.credit_score}", color="#CDEFD9", size=13),
                            ]
                        ),
                        ft.Container(height=6),
                        ft.Row(
                            [
                                ft.Text(status, color="#FFF7CC" if account.overdraft else "#CDEFD9", size=12),
                                ft.Container(expand=True),
                                ft.Text("点击切换视图", color="#CDEFD9", size=10, italic=True),
                            ]
                        )
                    ],
                    spacing=2,
                ),
            )
        )

    # ------------------------------------------------------------------ #
    # 本周收支
    # ------------------------------------------------------------------ #
    def _flow_row(self, account) -> ft.Control:
        now = datetime.now()
        curr = "cny" if self.show_investment else "coin"
        income, expense = BankService.flow_between(account.id, now - timedelta(days=7), now, currency=curr)
        
        # 统计投资总额
        total_invested_cny = sum(i.amount for i in account.investments if i.currency == "cny")
        
        return ft.Row(
            [
                self._mini_stat("本周收入", f"+{fmt(income)}", PRIMARY, ft.Icons.TRENDING_UP),
                self._mini_stat("本周支出", f"-{fmt(expense)}", DANGER, ft.Icons.TRENDING_DOWN),
                self._mini_stat(
                    "投资总额" if self.show_investment else "活期余额", 
                    fmt(total_invested_cny if self.show_investment else account.balance), 
                    BLUE, 
                    ft.Icons.SCHOOL if self.show_investment else ft.Icons.WALLET
                ),
            ],
            spacing=10,
        )

    def _mini_stat(self, label, value, color, icon) -> ft.Control:
        return card(
            ft.Column(
                [
                    ft.Icon(icon, color=color, size=20),
                    ft.Text(value, size=17, weight=ft.FontWeight.BOLD, color=color),
                    ft.Text(label, size=11, color=MUTED),
                ],
                spacing=3,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=12,
            expand=True,
        )

    # ------------------------------------------------------------------ #
    # 快捷入口
    # ------------------------------------------------------------------ #
    def _quick_entries(self, account) -> ft.Control:
        def read_balance(e):
            voice_service.speak(
                f"你好{account.name}，你的余额是 {fmt(account.balance)} {config.CURRENCY_SYMBOL}"
            )
            self.app.snack("正在语音播报余额…", PRIMARY)

        def go_mall(e):
            self.app.switch_tab(1)

        def go_tasks(e):
            self.app.snack("在下方“我的任务”里点选就可以打卡啦", ACCENT)

        return card(
            ft.Row(
                [
                    self._quick_item(ft.Icons.VOLUME_UP, "语音播报", read_balance, PRIMARY),
                    self._quick_item(ft.Icons.STORE, "心愿单", go_mall, ACCENT),
                    self._quick_item(ft.Icons.CHECK_CIRCLE, "打卡任务", go_tasks, BLUE),
                ],
                alignment=ft.MainAxisAlignment.SPACE_AROUND,
            ),
            padding=14,
        )

    def _quick_item(self, icon, label, on_click, color) -> ft.Control:
        return ft.Container(
            on_click=on_click,
            padding=6,
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Icon(icon, color=ft.Colors.WHITE, size=26),
                        width=52,
                        height=52,
                        bgcolor=color,
                        border_radius=16,
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Text(label, size=12, color="#24352B"),
                ],
                spacing=6,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    # ------------------------------------------------------------------ #
    # 我的任务（打卡申请）
    # ------------------------------------------------------------------ #
    def _task_section(self, account) -> ft.Control:
        rules = TaskService.list_rules(only_enabled=True, category="good")
        pending = {
            r.rule_id
            for r in TaskService.list_requests(status="pending", account_id=account.id)
        }
        return ft.Column(
            [
                section("我的任务（点图标打卡）"),
                ft.Row(
                    [self._task_card(rule, rule.id in pending) for rule in rules],
                    wrap=True,
                    spacing=10,
                    run_spacing=10,
                ),
            ],
            spacing=10,
        )

    def _task_card(self, rule, is_pending: bool) -> ft.Control:
        badge = (
            ft.Container(
                content=ft.Text("待审核", size=10, color=ft.Colors.WHITE),
                bgcolor=ACCENT,
                padding=ft.Padding(left=8, top=2, right=8, bottom=2),
                border_radius=10,
            )
            if is_pending
            else ft.Text(f"+{fmt(rule.amount)}", size=12, color=PRIMARY, weight=ft.FontWeight.W_600)
        )

        def on_click(e):
            if is_pending: return
            
            def confirm(e):
                self.app.page.pop_dialog()
                self._submit(rule.id, rule.title)

            dlg = ft.AlertDialog(
                title=ft.Text("确认打卡"),
                content=ft.Text(f"确定完成了“{rule.title}”吗？"),
                actions=[
                    ft.TextButton("取消", on_click=lambda e: self.app.page.pop_dialog()),
                    ft.FilledButton("确定", on_click=confirm),
                ],
            )
            self.app.page.show_dialog(dlg)

        return ft.Container(
            width=132,
            padding=12,
            bgcolor="#FBFEFC",
            border_radius=16,
            on_click=on_click,
            shadow=ft.BoxShadow(blur_radius=8, color="#0F000000", offset=ft.Offset(0, 2)),
            content=ft.Column(
                [
                    ft.Text(rule.icon or "⭐", size=30),
                    ft.Text(rule.title, size=12, color="#24352B", max_lines=2, text_align=ft.TextAlign.CENTER),
                    badge,
                ],
                spacing=5,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def _submit(self, rule_id: int, title: str):
        try:
            TaskService.submit_request(self.app.current.id, rule_id)
            voice_service.speak(f"{title}，已提交，等待家长确认")
            self.app.snack("已提交，等待家长确认（黄灯待审核）", ACCENT)
            self.app.refresh()
        except BankError as exc:
            self.app.snack(str(exc), DANGER)

    # ------------------------------------------------------------------ #
    # 梦想存钱罐（定期）
    # ------------------------------------------------------------------ #
    def _jar_section(self, account) -> ft.Control:
        deposits = BankService.list_deposits(account.id)
        locked = sum(d.amount for d in deposits if d.status == "locked")
        ratio = min(1.0, locked / JAR_GOAL) if JAR_GOAL else 0

        items = [self._progress_jar(locked, ratio)]
        for dep in deposits:
            if dep.status == "locked":
                items.append(self._deposit_row(dep, account))
        items.append(
            ft.FilledButton(
                "存入定期（锁仓生息）",
                icon=ft.Icons.SAVINGS,
                on_click=lambda e: self._deposit_dialog(account),
            )
        )
        return ft.Column([section("梦想存钱罐"), card(ft.Column(items, spacing=10))], spacing=10)

    def _progress_jar(self, locked: float, ratio: float) -> ft.Control:
        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.SPA, color=PRIMARY, size=20),
                        ft.Text(f"已锁定 {money(locked)}", size=14, weight=ft.FontWeight.W_600),
                        ft.Container(expand=True),
                        ft.Text(f"目标 {fmt(JAR_GOAL)}", size=12, color=MUTED),
                    ]
                ),
                ft.ProgressBar(value=ratio, color=PRIMARY, bgcolor="#E3F2E8", bar_height=12),
                ft.Text(
                    "满罐就开花啦！定期到期后家长会发利息哦 🌱" if ratio < 1 else "存钱罐满啦，太棒了！🎉",
                    size=12,
                    color=MUTED,
                ),
            ],
            spacing=6,
        )

    def _deposit_row(self, dep, account) -> ft.Control:
        matured = datetime.now() >= dep.mature_at
        return ft.Row(
            [
                ft.Icon(ft.Icons.LOCK_OPEN if matured else ft.Icons.LOCK, color=BLUE, size=20),
                ft.Column(
                    [
                        ft.Text(f"{fmt(dep.amount)} 币 · {dep.lock_days} 天", size=13),
                        ft.Text(
                            "已到期，可支取" if matured else f"到期 {dep.mature_at.strftime('%m-%d %H:%M')}",
                            size=11,
                            color=PRIMARY if matured else MUTED,
                        ),
                    ],
                    spacing=2,
                ),
                ft.Container(expand=True),
                ft.TextButton(
                    "支取",
                    disabled=not matured,
                    on_click=lambda e, did=dep.id: self._settle(did),
                ),
            ]
        )

    def _deposit_dialog(self, account):
        amount = ft.TextField(label="存入金额", value="50", keyboard_type=ft.KeyboardType.NUMBER, border_radius=12)
        days = ft.TextField(label="锁定期（天）", value=str(config.DEFAULT_LOCK_DAYS), keyboard_type=ft.KeyboardType.NUMBER, border_radius=12)

        def submit(e):
            try:
                self.app.page.pop_dialog()
                BankService.open_deposit(
                    account.id,
                    float(amount.value or 0),
                    int(days.value or config.DEFAULT_LOCK_DAYS),
                    config.DEFAULT_INTEREST_RATE,
                )
                self.app.snack("定期存入成功，到期自动算利息", PRIMARY)
                self.app.refresh()
            except (BankError, ValueError) as exc:
                self.app.snack(str(exc) or "请输入有效数字", DANGER)

        self.app.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("存入定期"),
                content=ft.Column(
                    [amount, days, ft.Text(f"年化利率 {config.DEFAULT_INTEREST_RATE:.0%}", size=12, color=MUTED)],
                    spacing=12,
                    width=260,
                ),
                actions=[
                    ft.TextButton("取消", on_click=lambda e: self.app.page.pop_dialog()),
                    ft.FilledButton("确认存入", on_click=submit),
                ],
            )
        )

    def _settle(self, deposit_id: int):
        try:
            interest = BankService.settle_deposit(deposit_id, "系统")
            self.app.snack(f"支取成功，获得利息 {money(interest)}", PRIMARY)
            self.app.refresh()
        except BankError as exc:
            self.app.snack(str(exc), DANGER)

    # ------------------------------------------------------------------ #
    # 最近流水
    # ------------------------------------------------------------------ #
    def _recent_section(self, account) -> ft.Control:
        rows = BankService.list_transactions(account.id, limit=5)
        if not rows:
            body = ft.Text("还没有交易记录，快去打卡赚币吧～", size=13, color=MUTED)
        else:
            body = ft.Column([self._tx_row(tx) for tx in rows], spacing=10)
        return ft.Column([section("最近交易"), card(body)], spacing=10)

    def _tx_row(self, tx) -> ft.Control:
        icon, color, bg = tx_visual(tx.type, tx.amount)
        unit = config.CURRENCY_SYMBOL if tx.currency == "coin" else "元"
        return ft.Row(
            [
                ft.Container(
                    content=ft.Icon(icon, color=color, size=18),
                    width=38,
                    height=38,
                    bgcolor=bg,
                    border_radius=12,
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Column(
                    [
                        ft.Text(tx_title(tx), size=14, weight=ft.FontWeight.W_600),
                        ft.Text(
                            f"{tx.created_at.strftime('%m-%d %H:%M')} · {tx.reason or '-'}",
                            size=11,
                            color=MUTED,
                        ),
                    ],
                    spacing=2,
                ),
                ft.Container(expand=True),
                ft.Text(
                    f"{'+' if tx.amount >= 0 else ''}{fmt(tx.amount)} {unit}",
                    size=14,
                    weight=ft.FontWeight.BOLD,
                    color=color,
                ),
            ]
        )
