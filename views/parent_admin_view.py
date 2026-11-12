"""家长端控制台：快捷奖惩 + 任务审批 + 规则库 + 奖品库。

审批是关键闸门：孩子提交的任务必须家长输入密码后才真正入账（防误触）。
"""
import flet as ft

import config
from database.models import TxType
from services.bank_service import BankError, BankService
from services.task_service import TaskService
from views import ACCENT, DANGER, MUTED, PRIMARY, card, fmt, money, section


class ParentAdminView:
    def __init__(self, app):
        self.app = app

    # ------------------------------------------------------------------ #
    def build(self) -> ft.Control:
        kids = TaskService.list_kids()
        if not kids:
            return ft.Container(
                expand=True,
                alignment=ft.Alignment.CENTER,
                content=ft.Text("还没有孩子账户", color=MUTED),
            )
        if self.app.selected_kid_id not in [k.id for k in kids]:
            self.app.selected_kid_id = kids[0].id
        kid = next(k for k in kids if k.id == self.app.selected_kid_id)

        return ft.Container(
            expand=True,
            padding=14,
            content=ft.Column(
                [
                    self._kid_selector(kids, kid),
                    self._quick_panel(kid),
                    self._approval_section(),
                    self._rule_section(),
                    self._wish_section(),
                ],
                scroll=ft.ScrollMode.AUTO,
                spacing=14,
                expand=True,
            ),
        )

    # ------------------------------------------------------------------ #
    def _kid_selector(self, kids, current) -> ft.Control:
        if len(kids) == 1:
            chips = [ft.Text(f"当前账户：{current.name}", size=14, weight=ft.FontWeight.W_600)]
        else:
            chips = [
                ft.Text("切换账户：", size=13, color=MUTED),
                *[
                    ft.TextButton(
                        k.name,
                        on_click=lambda e, kid_id=k.id: self._select_kid(kid_id),
                    )
                    for k in kids
                ],
            ]
        return card(
            ft.Row(
                [
                    ft.CircleAvatar(content=ft.Text(current.avatar or "🧒", size=20), bgcolor="#E3F2E8", radius=22),
                    *chips,
                    ft.Container(expand=True),
                    ft.Column(
                        [
                            ft.Text(money(current.balance), size=16, weight=ft.FontWeight.BOLD, color=PRIMARY),
                            ft.Text(f"征信 {current.credit_score}", size=11, color=MUTED),
                        ],
                        spacing=0,
                        horizontal_alignment=ft.CrossAxisAlignment.END,
                    ),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )

    def _select_kid(self, kid_id: int):
        self.app.selected_kid_id = kid_id
        self.app.refresh()

    # ------------------------------------------------------------------ #
    # 快捷奖惩
    # ------------------------------------------------------------------ #
    def _quick_panel(self, kid) -> ft.Control:
        amount = ft.TextField(
            label="金额", value="10", width=110, keyboard_type=ft.KeyboardType.NUMBER, border_radius=12
        )
        reason = ft.TextField(label="事由", hint_text="如：主动收拾房间", expand=True, border_radius=12)

        def do_reward(e):
            self._apply(kid, amount.value, reason.value, is_reward=True)

        def do_penalty(e):
            self._apply(kid, amount.value, reason.value, is_reward=False)

        return ft.Column(
            [
                section("快捷奖惩（柜员操作）"),
                card(
                    ft.Column(
                        [
                            ft.Row([amount, reason], spacing=10),
                            ft.Row(
                                [
                                    ft.FilledButton(
                                        "存款 · 奖励",
                                        icon=ft.Icons.TRENDING_UP,
                                        on_click=do_reward,
                                        expand=True,
                                    ),
                                    ft.FilledButton(
                                        "扣款 · 处罚",
                                        icon=ft.Icons.TRENDING_DOWN,
                                        style=ft.ButtonStyle(bgcolor=DANGER),
                                        on_click=do_penalty,
                                        expand=True,
                                    ),
                                ],
                                spacing=10,
                            ),
                        ],
                        spacing=12,
                    )
                ),
            ],
            spacing=10,
        )

    def _apply(self, kid, raw_amount, raw_reason, is_reward: bool):
        try:
            amount = abs(float(raw_amount or 0))
            if amount <= 0:
                raise ValueError
        except ValueError:
            self.app.snack("请输入有效金额", DANGER)
            return
        reason = (raw_reason or "").strip() or ("奖励" if is_reward else "违规")
        if is_reward:
            BankService.reward(kid.id, amount, reason, self.app.current.name)
        else:
            BankService.penalty(kid.id, amount, reason, self.app.current.name)
        self.app.snack(f"{'奖励' if is_reward else '扣款'} {fmt(amount)} {config.CURRENCY_SYMBOL} 已入账", PRIMARY)
        self.app.refresh()

    # ------------------------------------------------------------------ #
    # 待审批
    # ------------------------------------------------------------------ #
    def _approval_section(self) -> ft.Control:
        pending = TaskService.list_requests(status="pending")
        if not pending:
            body = ft.Text("暂无待审批申请", size=13, color=MUTED)
        else:
            body = ft.Column([self._approval_row(req) for req in pending], spacing=10)
        return ft.Column([section(f"待审批（{len(pending)}）"), card(body)], spacing=10)

    def _approval_row(self, req) -> ft.Control:
        kid = BankService.get_account(req.account_id)
        positive = req.amount >= 0
        return ft.Row(
            [
                ft.Text("🟡", size=18),
                ft.Column(
                    [
                        ft.Text(f"{kid.name} · {req.title}", size=14, weight=ft.FontWeight.W_600),
                        ft.Text(req.created_at.strftime("%m-%d %H:%M"), size=11, color=MUTED),
                    ],
                    spacing=2,
                ),
                ft.Container(expand=True),
                ft.Text(
                    f"{'+' if positive else ''}{fmt(req.amount)}",
                    weight=ft.FontWeight.BOLD,
                    color=PRIMARY if positive else DANGER,
                ),
                ft.TextButton("驳回", on_click=lambda e, rid=req.id: self._reject(rid)),
                ft.FilledButton("通过", on_click=lambda e, rid=req.id: self._approve_with_pin(rid)),
            ],
            spacing=6,
        )

    def _approve_with_pin(self, request_id: int):
        self.app.ask_pin(
            "家长密码验证",
            self.app.current.pin,
            lambda: self._approve(request_id),
        )

    def _approve(self, request_id: int):
        try:
            TaskService.approve_request(request_id, self.app.current.name)
            self.app.snack("审批通过，已正式入账", PRIMARY)
            self.app.refresh()
        except BankError as exc:
            self.app.snack(str(exc), DANGER)

    def _reject(self, request_id: int):
        try:
            TaskService.reject_request(request_id)
            self.app.snack("已驳回该申请", ACCENT)
            self.app.refresh()
        except BankError as exc:
            self.app.snack(str(exc), DANGER)

    # ------------------------------------------------------------------ #
    # 规则库
    # ------------------------------------------------------------------ #
    def _rule_section(self) -> ft.Control:
        rules = TaskService.list_rules(only_enabled=False)
        rows = [self._rule_row(r) for r in rules]
        return ft.Column(
            [
                ft.Row(
                    [
                        section("奖惩规则库"),
                        ft.Container(expand=True),
                        ft.TextButton("＋ 添加", on_click=lambda e: self._add_rule_dialog()),
                    ]
                ),
                card(ft.Column(rows, spacing=8)),
            ],
            spacing=10,
        )

    def _rule_row(self, rule) -> ft.Control:
        positive = rule.amount >= 0
        return ft.Row(
            [
                ft.Text(rule.icon or "⭐", size=20),
                ft.Text(rule.title, size=14, expand=True),
                ft.Text(
                    f"{'+' if positive else ''}{fmt(rule.amount)}",
                    size=13,
                    weight=ft.FontWeight.W_600,
                    color=PRIMARY if positive else DANGER,
                ),
                ft.Switch(value=bool(rule.enabled), on_change=lambda e, rid=rule.id: self._toggle_rule(rid)),
            ],
            spacing=8,
        )

    def _toggle_rule(self, rule_id: int):
        TaskService.toggle_rule(rule_id)
        self.app.refresh()

    def _add_rule_dialog(self):
        title = ft.TextField(label="任务名称", border_radius=12)
        icon = ft.TextField(label="图标 emoji", value="⭐", width=110, border_radius=12)
        amount = ft.TextField(label="分数（奖励为正）", value="5", width=150, keyboard_type=ft.KeyboardType.NUMBER, border_radius=12)

        def submit(e):
            try:
                TaskService.add_rule(title.value or "新任务", icon.value, float(amount.value or 0),
                                     "good" if float(amount.value or 0) >= 0 else "bad")
            except ValueError:
                self.app.snack("请输入有效分数", DANGER)
                return
            self.app.page.pop_dialog()
            self.app.snack("规则已添加", PRIMARY)
            self.app.refresh()

        self.app.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("添加奖惩规则"),
                content=ft.Column([title, ft.Row([icon, amount], spacing=10)], spacing=12, width=300),
                actions=[
                    ft.TextButton("取消", on_click=lambda e: self.app.page.pop_dialog()),
                    ft.FilledButton("保存", on_click=submit),
                ],
            )
        )

    # ------------------------------------------------------------------ #
    # 奖品库
    # ------------------------------------------------------------------ #
    def _wish_section(self) -> ft.Control:
        wishes = BankService.list_wishes(only_enabled=False)
        rows = [self._wish_row(w) for w in wishes]
        return ft.Column(
            [
                ft.Row(
                    [
                        section("心愿奖品库"),
                        ft.Container(expand=True),
                        ft.TextButton("＋ 添加", on_click=lambda e: self._add_wish_dialog()),
                    ]
                ),
                card(ft.Column(rows, spacing=8)),
            ],
            spacing=10,
        )

    def _wish_row(self, wish) -> ft.Control:
        return ft.Row(
            [
                ft.Text(wish.icon or "🎁", size=20),
                ft.Text(wish.name, size=14, expand=True),
                ft.Text(f"{fmt(wish.price)} 币", size=13, weight=ft.FontWeight.W_600, color=ACCENT),
                ft.Text("不限量" if wish.stock < 0 else f"剩 {wish.stock}", size=11, color=MUTED),
            ],
            spacing=8,
        )

    def _add_wish_dialog(self):
        name = ft.TextField(label="奖品名称", border_radius=12)
        icon = ft.TextField(label="图标 emoji", value="🎁", width=110, border_radius=12)
        price = ft.TextField(label="所需币数", value="30", width=130, keyboard_type=ft.KeyboardType.NUMBER, border_radius=12)

        def submit(e):
            try:
                BankService.add_wish(name.value or "新奖品", icon.value, float(price.value or 0))
            except ValueError:
                self.app.snack("请输入有效币数", DANGER)
                return
            self.app.page.pop_dialog()
            self.app.snack("奖品已上架", PRIMARY)
            self.app.refresh()

        self.app.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("添加心愿奖品"),
                content=ft.Column([name, ft.Row([icon, price], spacing=10)], spacing=12, width=300),
                actions=[
                    ft.TextButton("取消", on_click=lambda e: self.app.page.pop_dialog()),
                    ft.FilledButton("上架", on_click=submit),
                ],
            )
        )
