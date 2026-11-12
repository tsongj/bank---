"""孩子端首页：虚拟银行卡 + 成长金库 + 任务申请 + 梦想存钱罐。

适龄设计：大图标、少文字、点击即朗读，任务提交后进入“黄灯待审核”。
"""
from datetime import datetime, timedelta

import flet as ft

import config
from services.bank_service import BankError, BankService
from services.task_service import TaskService
from services import voice_service
from views import (
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

        return ft.Container(
            expand=True,
            padding=14,
            content=ft.Column(
                [
                    self._bank_card(account),
                    self._flow_row(account),
                    self._quick_entries(account),
                    self._task_section(account),
                    self._jar_section(account),
                    self._recent_section(account),
                ],
                scroll=ft.ScrollMode.AUTO,
                spacing=14,
                expand=True,
            ),
        )

    # ------------------------------------------------------------------ #
    # 虚拟银行卡
    # ------------------------------------------------------------------ #
    def _bank_card(self, account) -> ft.Control:
        status = "征信良好" if not account.overdraft else "⚠ 已透支，征信降级"
        return ft.Container(
            padding=20,
            border_radius=22,
            gradient=ft.LinearGradient(
                colors=["#12A65B", "#0B7A42"],
                begin=ft.Alignment.TOP_LEFT,
                end=ft.Alignment.BOTTOM_RIGHT,
            ),
            shadow=ft.BoxShadow(blur_radius=16, color="#330B7A42", offset=ft.Offset(0, 6)),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(config.APP_TITLE, color="#EAFBEF", size=13, weight=ft.FontWeight.W_600),
                            ft.Container(expand=True),
                            ft.Icon(ft.Icons.CARD_GIFTCARD, color="#EAFBEF", size=20),
                        ]
                    ),
                    ft.Container(height=12),
                    ft.Text("账户余额", color="#CDEFD9", size=12),
                    ft.Text(money(account.balance), color=ft.Colors.WHITE, size=34, weight=ft.FontWeight.BOLD),
                    ft.Container(height=10),
                    ft.Row(
                        [
                            ft.Text(account.card_no or "—", color="#CDEFD9", size=13),
                            ft.Container(expand=True),
                            ft.Text(f"征信 {account.credit_score}", color="#CDEFD9", size=13),
                        ]
                    ),
                    ft.Container(height=6),
                    ft.Text(status, color="#FFF7CC" if account.overdraft else "#CDEFD9", size=12),
                ],
                spacing=2,
            ),
        )

    # ------------------------------------------------------------------ #
    # 本周收支
    # ------------------------------------------------------------------ #
    def _flow_row(self, account) -> ft.Control:
        now = datetime.now()
        income, expense = BankService.flow_between(account.id, now - timedelta(days=7), now)
        return ft.Row(
            [
                self._mini_stat("本周收入", f"+{fmt(income)}", PRIMARY, ft.Icons.TRENDING_UP),
                self._mini_stat("本周支出", f"-{fmt(expense)}", DANGER, ft.Icons.TRENDING_DOWN),
                self._mini_stat("活期余额", fmt(account.balance), BLUE, ft.Icons.WALLET),
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
        return ft.Container(
            width=132,
            padding=12,
            bgcolor="#FBFEFC",
            border_radius=16,
            on_click=None if is_pending else (lambda e, rid=rule.id: self._submit(rid, rule.title)),
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
                    f"{'+' if tx.amount >= 0 else ''}{fmt(tx.amount)}",
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    color=color,
                ),
            ]
        )
