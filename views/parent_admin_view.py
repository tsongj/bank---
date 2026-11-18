"""家长端控制台：快捷奖惩 + 任务审批 + 规则库 + 奖品库。

审批是关键闸门：孩子提交的任务必须家长输入密码后才真正入账（防误触）。
"""
import flet as ft

import config
from database.db import session_scope
from database.models import TxType, InvestmentRequest
from services.bank_service import BankError, BankService
from services.task_service import TaskService
from . import ACCENT, BLUE, DANGER, MUTED, PRIMARY, card, fmt, money, section


class ParentAdminView:
    def __init__(self, app):
        self.app = app

    # ------------------------------------------------------------------ #
    def build(self) -> ft.Control:
        kids = TaskService.list_kids()
        parent = BankService.list_accounts(role="parent")[0]
        
        if not kids:
            kid = None
        else:
            if self.app.selected_kid_id not in [k.id for k in kids]:
                self.app.selected_kid_id = kids[0].id
            kid = next(k for k in kids if k.id == self.app.selected_kid_id)

        content_list = [
            self._kid_selector(kids, kid),
            self._central_bank_section(parent),
        ]
        
        if kid:
            content_list.append(self._quick_panel(kid))
            content_list.append(self._approval_section())

        content_list.extend([
            self._fx_rate_section(),
            self._rule_section(),
            self._wish_section(),
            self._account_settings_section(),
        ])

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

    # ------------------------------------------------------------------ #
    def _kid_selector(self, kids, current) -> ft.Control:
        if not kids:
            return card(
                ft.Row(
                    [
                        ft.Text("还没有孩子账户", color=MUTED),
                        ft.Container(expand=True),
                        ft.TextButton("＋ 添加新成员", on_click=lambda e: self._add_kid_dlg()),
                    ]
                )
            )
        
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
                    ft.Column(chips, spacing=0),
                    ft.Container(expand=True),
                    ft.Column(
                        [
                            ft.Text(money(current.balance), size=16, weight=ft.FontWeight.BOLD, color=PRIMARY),
                            ft.Text(f"RMB: ¥{current.cny_balance:.2f}", size=11, color=MUTED),
                        ],
                        spacing=0,
                        horizontal_alignment=ft.CrossAxisAlignment.END,
                    ),
                    ft.IconButton(ft.Icons.DELETE_FOREVER, icon_color=DANGER, tooltip="注销该成员", on_click=lambda e: self._delete_acc_dlg(current)),
                    ft.IconButton(ft.Icons.PERSON_ADD_ALT_1, on_click=lambda e: self._add_kid_dlg()),
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
    def _quick_panel(self, current_kid) -> ft.Control:
        kids = TaskService.list_kids()
        kid_options = [ft.dropdown.Option(str(k.id), k.name) for k in kids]
        
        kid_selector = ft.Dropdown(
            label="目标账户",
            options=kid_options,
            value=str(current_kid.id) if current_kid else None,
            width=120,
            border_radius=12
        )
        amount = ft.TextField(
            label="金额", value="10", width=80, keyboard_type=ft.KeyboardType.NUMBER, border_radius=12
        )
        reason = ft.TextField(label="事由", hint_text="如：主动收拾房间", expand=True, border_radius=12)
        currency = ft.Dropdown(
            options=[ft.dropdown.Option("coin", "金币"), ft.dropdown.Option("cny", "人民币")],
            value="coin",
            width=90,
            border_radius=12
        )

        def do_reward(e):
            selected_kid = next((k for k in kids if str(k.id) == kid_selector.value), current_kid)
            
            def confirm(e):
                self.app.page.pop_dialog()
                self._apply(selected_kid, amount.value, reason.value, is_reward=True, currency=currency.value)

            self.app.page.show_dialog(
                ft.AlertDialog(
                    title=ft.Text("确认奖励"),
                    content=ft.Text(f"确定给 {selected_kid.name} 奖励 {amount.value}{'元' if currency.value=='cny' else '金币'} 吗？\n事由：{reason.value}"),
                    actions=[
                        ft.TextButton("取消", on_click=lambda e: self.app.page.pop_dialog()),
                        ft.FilledButton("确定奖励", on_click=confirm),
                    ],
                )
            )

        def do_penalty(e):
            selected_kid = next((k for k in kids if str(k.id) == kid_selector.value), current_kid)
            
            def confirm(e):
                self.app.page.pop_dialog()
                self._apply(selected_kid, amount.value, reason.value, is_reward=False, currency=currency.value)

            self.app.page.show_dialog(
                ft.AlertDialog(
                    title=ft.Text("确认处罚"),
                    content=ft.Text(f"确定对 {selected_kid.name} 处以 {amount.value}{'元' if currency.value=='cny' else '金币'} 罚款吗？\n事由：{reason.value}"),
                    actions=[
                        ft.TextButton("取消", on_click=lambda e: self.app.page.pop_dialog()),
                        ft.FilledButton("确定处罚", on_click=confirm, bgcolor=DANGER),
                    ],
                )
            )

        return ft.Column(
            [
                section("快捷奖惩（柜员操作）"),
                card(
                    ft.Column(
                        [
                            ft.Row([kid_selector, currency, amount, reason], spacing=10),
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

    def _apply(self, kid, raw_amount, raw_reason, is_reward: bool, currency: str = "coin"):
        try:
            amount = abs(float(raw_amount or 0))
            if amount <= 0:
                raise ValueError
        except ValueError:
            self.app.snack("请输入有效金额", DANGER)
            return
        reason = (raw_reason or "").strip() or ("奖励" if is_reward else "违规")
        if is_reward:
            BankService.reward(kid.id, amount, reason, self.app.current.name, currency=currency)
        else:
            BankService.penalty(kid.id, amount, reason, self.app.current.name, currency=currency)
        
        symbol = config.CURRENCY_SYMBOL if currency == "coin" else "元"
        self.app.snack(f"{'奖励' if is_reward else '扣款'} {fmt(amount)} {symbol} 已入账", PRIMARY)
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
                ft.IconButton(ft.Icons.EDIT_OUTLINED, icon_size=16, on_click=lambda e: self._edit_rule_dialog(rule)),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=16, icon_color=DANGER, on_click=lambda e: self._delete_rule(rule.id)),
                ft.Switch(value=bool(rule.enabled), on_change=lambda e, rid=rule.id: self._toggle_rule(rid)),
            ],
            spacing=4,
        )

    def _delete_rule(self, rule_id: int):
        TaskService.delete_rule(rule_id)
        self.app.snack("规则已删除", PRIMARY)
        self.app.refresh()

    def _edit_rule_dialog(self, rule):
        title = ft.TextField(label="任务名称", value=rule.title, border_radius=12)
        icon = ft.TextField(label="图标 emoji", value=rule.icon, width=110, border_radius=12)
        amount = ft.TextField(label="分数", value=str(rule.amount), width=150, keyboard_type=ft.KeyboardType.NUMBER, border_radius=12)

        def submit(e):
            try:
                TaskService.update_rule(rule.id, title.value, icon.value, float(amount.value),
                                        "good" if float(amount.value) >= 0 else "bad")
            except ValueError:
                self.app.snack("请输入有效分数", DANGER)
                return
            self.app.page.pop_dialog()
            self.app.snack("规则已更新", PRIMARY)
            self.app.refresh()

        dlg = ft.AlertDialog(
            title=ft.Text("编辑规则"),
            content=ft.Column([title, ft.Row([icon, amount], spacing=10)], spacing=12, width=300, tight=True),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self.app.page.pop_dialog()),
                ft.FilledButton("保存", on_click=submit),
            ],
        )
        self.app.page.show_dialog(dlg)

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

    def _central_bank_section(self, parent) -> ft.Control:
        return ft.Column(
            [
                section("中央银行控制台（行长）"),
                card(
                    ft.Column([
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.ACCOUNT_BALANCE, color=PRIMARY, size=30),
                                ft.Column(
                                    [
                                        ft.Text("央行储备总额 (Vault)", size=12, color=MUTED),
                                        ft.Row([
                                            ft.Text(f"{parent.balance:g} {config.CURRENCY_SYMBOL}", size=16, weight=ft.FontWeight.BOLD),
                                            ft.Text(" / ", color=MUTED),
                                            ft.Text(f"¥{parent.cny_balance:.2f}", size=16, weight=ft.FontWeight.BOLD, color=ACCENT),
                                            ft.Text(" / ", color=MUTED),
                                            ft.Text(f"实: ¥{parent.real_balance:.2f}", size=16, weight=ft.FontWeight.BOLD, color=BLUE),
                                        ])
                                    ],
                                    spacing=0,
                                ),
                                ft.Container(expand=True),
                                ft.Column([
                                    ft.FilledButton("投放金币", icon=ft.Icons.ADD, on_click=lambda e: self._inject_dlg(parent, "coin"), height=30, style=ft.ButtonStyle(padding=8)),
                                    ft.FilledButton("投放人民币", icon=ft.Icons.ADD, on_click=lambda e: self._inject_dlg(parent, "cny"), height=30, style=ft.ButtonStyle(padding=8)),
                                ], spacing=5),
                            ],
                            spacing=15,
                        ),
                        ft.Divider(height=1, color=ft.Colors.BLACK_12),
                        ft.TextButton("查看央行流水账单", icon=ft.Icons.LIST_ALT, on_click=lambda e: self._show_parent_tx_dlg(parent))
                    ])
                ),
            ],
            spacing=10,
        )

    def _show_parent_tx_dlg(self, parent):
        txs = BankService.list_transactions(parent.id, limit=20)
        
        def tx_row(tx):
            positive = tx.amount >= 0
            unit = config.CURRENCY_SYMBOL if tx.currency == "coin" else "元"
            return ft.Row([
                ft.Text(tx.created_at.strftime("%m-%d %H:%M"), size=11, color=MUTED),
                ft.Text(tx.reason, size=13, expand=True),
                ft.Text(f"{'+' if positive else ''}{tx.amount:g}{unit}", color=PRIMARY if positive else DANGER, weight=ft.FontWeight.BOLD)
            ])

        self.app.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("央行流水账单"),
                content=ft.Column([tx_row(t) for t in txs], scroll=ft.ScrollMode.AUTO, tight=True, width=400),
                actions=[ft.TextButton("关闭", on_click=lambda e: self.app.page.pop_dialog())]
            )
        )

    def _inject_dlg(self, parent, currency):
        title = f"央行{'金币' if currency=='coin' else '人民币'}投放"
        amount = ft.TextField(label="投放金额", value="1000", keyboard_type=ft.KeyboardType.NUMBER, border_radius=12)
        
        def submit(e):
            try:
                amt = float(amount.value or 0)
                if amt <= 0: raise ValueError
                BankService.inject_currency(parent.id, amt, currency)
                self.app.page.pop_dialog()
                self.app.snack(f"{'金币' if currency=='coin' else '人民币'}投放成功！", PRIMARY)
                self.app.refresh()
            except ValueError:
                self.app.snack("请输入有效金额", DANGER)
        
        self.app.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text(title),
                content=amount,
                actions=[ft.TextButton("取消", on_click=lambda e: self.app.page.pop_dialog()), ft.FilledButton("确定投放", on_click=submit)],
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

    def _wish_row(self, wish) -> ft.Control:
        return ft.Row(
            [
                ft.Text(wish.icon or "🎁", size=20),
                ft.Text(wish.name, size=14, expand=True),
                ft.Text(f"{fmt(wish.price)} 币", size=13, weight=ft.FontWeight.W_600, color=ACCENT),
                ft.Text("不限量" if wish.stock < 0 else f"剩 {wish.stock}", size=11, color=MUTED),
                ft.IconButton(ft.Icons.EDIT_OUTLINED, icon_size=16, on_click=lambda e: self._edit_wish_dialog(wish)),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=16, icon_color=DANGER, on_click=lambda e: self._delete_wish(wish.id)),
            ],
            spacing=4,
        )

    def _delete_wish(self, wish_id: int):
        BankService.delete_wish(wish_id)
        self.app.snack("奖品已删除", PRIMARY)
        self.app.refresh()

    def _edit_wish_dialog(self, wish):
        name = ft.TextField(label="奖品名称", value=wish.name, border_radius=12)
        icon = ft.TextField(label="图标 emoji", value=wish.icon, width=110, border_radius=12)
        price = ft.TextField(label="所需币数", value=str(wish.price), width=130, keyboard_type=ft.KeyboardType.NUMBER, border_radius=12)

        def submit(e):
            try:
                BankService.update_wish(wish.id, name.value, icon.value, float(price.value))
            except ValueError:
                self.app.snack("请输入有效分数", DANGER)
                return
            self.app.page.pop_dialog()
            self.app.snack("奖品已更新", PRIMARY)
            self.app.refresh()

        dlg = ft.AlertDialog(
            title=ft.Text("编辑奖品"),
            content=ft.Column([name, ft.Row([icon, price], spacing=10)], spacing=12, width=300, tight=True),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self.app.page.pop_dialog()),
                ft.FilledButton("保存", on_click=submit),
            ],
        )
        self.app.page.show_dialog(dlg)

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

    # ------------------------------------------------------------------ #
    # 投资金审批
    # ------------------------------------------------------------------ #
    def _investment_approval_section(self) -> ft.Control:
        pending = BankService.list_investment_requests(status="pending")
        if not pending:
            return ft.Container()
        
        body = ft.Column([self._investment_approval_row(req) for req in pending], spacing=10)
        return ft.Column([section(f"投资基金申请（{len(pending)}）"), card(body)], spacing=10)

    def _investment_approval_row(self, req) -> ft.Control:
        kid = BankService.get_account(req.account_id)
        return ft.Row(
            [
                ft.Text("💰", size=18),
                ft.Column(
                    [
                        ft.Text(f"{kid.name} · {req.amount}元", size=14, weight=ft.FontWeight.W_600),
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
        self.app.snack("投资已批准，人民币已发放", PRIMARY)
        self.app.refresh()

    def _reject_investment(self, request_id: int):
        # 简单逻辑：直接删除或更新状态
        with session_scope() as s:
            req = s.get(InvestmentRequest, request_id)
            if req:
                req.status = "rejected"
        self.app.snack("已驳回申请", ACCENT)
        self.app.refresh()

    # ------------------------------------------------------------------ #
    # 汇率设置
    # ------------------------------------------------------------------ #
    def _fx_rate_section(self) -> ft.Control:
        return ft.Column(
            [
                section("外汇汇率设置"),
                card(
                    ft.Row(
                        [
                            ft.Text("金币 / 人民币 汇率：", size=14),
                            ft.Text(f"1:{config.FX_MID_RATE}", weight=ft.FontWeight.BOLD),
                            ft.Container(expand=True),
                            ft.TextButton("调整汇率", on_click=lambda e: self._update_fx_dlg()),
                        ]
                    )
                ),
            ],
            spacing=10,
        )

    def _update_fx_dlg(self):
        rate = ft.TextField(label="人民币/金币 中间价", value=str(config.FX_MID_RATE))
        def submit(e):
            # 这里简单修改内存 config，实际应持久化
            try:
                config.FX_MID_RATE = float(rate.value)
                self.app.snack("汇率已更新（暂存）", PRIMARY)
            except: pass
            self.app.page.pop_dialog()
            self.app.refresh()

        dlg = ft.AlertDialog(
            title=ft.Text("汇率调整"),
            content=rate,
            actions=[ft.TextButton("取消", on_click=lambda e: self.app.page.pop_dialog()), ft.FilledButton("更新", on_click=submit)],
        )
        self.app.page.show_dialog(dlg)

    # ------------------------------------------------------------------ #
    # 账户设置
    # ------------------------------------------------------------------ #
    def _account_settings_section(self) -> ft.Control:
        kids = TaskService.list_kids()
        kid_list = ft.Column([self._account_row(k) for k in kids], spacing=0)

        return ft.Column(
            [
                section("安全与成员管理"),
                card(
                    ft.Column([
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.LOCK_OUTLINED),
                            title=ft.Text("修改家长管理密码"),
                            on_click=lambda e: self._change_pin_dlg(),
                        ),
                        ft.Divider(height=1, color=ft.Colors.BLACK_12),
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.PERSON_ADD_OUTLINED),
                            title=ft.Text("添加新账户成员"),
                            on_click=lambda e: self._add_kid_dlg(),
                        ),
                        ft.Divider(height=1, color=ft.Colors.BLACK_12),
                        ft.Container(padding=ft.Padding(left=16, top=10, right=0, bottom=5), content=ft.Text("成员销户 (慎重)", size=12, color=MUTED)),
                        kid_list
                    ], spacing=0)
                ),
            ],
            spacing=10,
        )

    def _account_row(self, acc) -> ft.Control:
        return ft.ListTile(
            leading=ft.Text(acc.avatar or "🧒", size=18),
            title=ft.Text(acc.name, size=14),
            trailing=ft.IconButton(ft.Icons.DELETE_FOREVER, icon_color=DANGER, on_click=lambda e: self._delete_acc_dlg(acc)),
        )

    def _delete_acc_dlg(self, acc):
        def confirm(e):
            BankService.delete_account(acc.id)
            self.app.page.pop_dialog()
            self.app.snack(f"账户 {acc.name} 已注销", PRIMARY)
            self.app.refresh()

        self.app.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("确认销户"),
                content=ft.Text(f"确定要注销 {acc.name} 的账户吗？此操作不可撤销，所有余额和流水将丢失。"),
                actions=[
                    ft.TextButton("取消", on_click=lambda e: self.app.page.pop_dialog()),
                    ft.FilledButton("确定注销", on_click=confirm, bgcolor=DANGER),
                ],
            )
        )

    def _change_pin_dlg(self):
        new_pin = ft.TextField(label="新密码", password=True, can_reveal_password=True)
        def submit(e):
            BankService.update_pin(self.app.current.id, new_pin.value)
            self.app.snack("密码已修改", PRIMARY)
            self.app.page.pop_dialog()
        
        dlg = ft.AlertDialog(
            title=ft.Text("修改密码"),
            content=new_pin,
            actions=[ft.TextButton("取消", on_click=lambda e: self.app.page.pop_dialog()), ft.FilledButton("保存", on_click=submit)],
        )
        self.app.page.show_dialog(dlg)
