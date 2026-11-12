"""电子账单：银行流水 + 本月收支汇总，红蓝图标区分奖惩。"""
from datetime import datetime

import flet as ft

from services.bank_service import BankService
from services.task_service import TaskService
from views import (
    ACCENT,
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


class BillHistoryView:
    def __init__(self, app):
        self.app = app

    def build(self) -> ft.Control:
        # 家长可切换查看不同孩子的账单
        kids = TaskService.list_kids()
        if self.app.current.role == "parent" and kids:
            if self.app.bill_account_id not in [k.id for k in kids]:
                self.app.bill_account_id = kids[0].id
            account = next(k for k in kids if k.id == self.app.bill_account_id)
            selector = ft.Row(
                [ft.Text("查看账户：", size=13, color=MUTED)]
                + [
                    ft.TextButton(k.name, on_click=lambda e, kid_id=k.id: self._switch(kid_id))
                    for k in kids
                ],
                spacing=6,
            )
        else:
            account = BankService.get_account(self.app.current.id)
            selector = ft.Text(f"账户：{account.name}", size=13, color=MUTED)

        now = datetime.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        income, expense = BankService.flow_between(account.id, month_start, now)
        rows = BankService.list_transactions(account.id, limit=200)

        body = [
            selector,
            self._summary(account, now, income, expense),
            section(f"流水明细（{len(rows)} 笔）"),
        ]
        if rows:
            body.append(card(ft.Column([self._tx_row(tx) for tx in rows], spacing=12)))
        else:
            body.append(card(ft.Text("本月还没有流水记录", size=13, color=MUTED)))

        return ft.Container(
            expand=True,
            padding=14,
            content=ft.Column(body, scroll=ft.ScrollMode.AUTO, spacing=14, expand=True),
        )

    def _switch(self, kid_id: int):
        self.app.bill_account_id = kid_id
        self.app.refresh()

    # ------------------------------------------------------------------ #
    def _summary(self, account, now, income, expense) -> ft.Control:
        return card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(f"{now.year} 年 {now.month} 月账单", size=15, weight=ft.FontWeight.W_600),
                            ft.Container(expand=True),
                            ft.Text(f"余额 {money(account.balance)}", size=13, color=PRIMARY),
                        ]
                    ),
                    ft.Divider(height=1, color=ft.Colors.GREY_200),
                    ft.Row(
                        [
                            self._stat("本月收入", f"+{fmt(income)}", PRIMARY),
                            self._stat("本月支出", f"-{fmt(expense)}", DANGER),
                            self._stat("净结余", f"{fmt(income - expense)}", BLUE),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_AROUND,
                    ),
                ],
                spacing=12,
            )
        )

    def _stat(self, label, value, color) -> ft.Control:
        return ft.Column(
            [
                ft.Text(value, size=18, weight=ft.FontWeight.BOLD, color=color),
                ft.Text(label, size=11, color=MUTED),
            ],
            spacing=2,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _tx_row(self, tx) -> ft.Control:
        icon, color, bg = tx_visual(tx.type, tx.amount)
        return ft.Row(
            [
                ft.Container(
                    content=ft.Icon(icon, color=color, size=18),
                    width=40,
                    height=40,
                    bgcolor=bg,
                    border_radius=12,
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Column(
                    [
                        ft.Text(tx_title(tx), size=14, weight=ft.FontWeight.W_600),
                        ft.Text(f"{tx.reason or '-'}", size=12, color=MUTED, max_lines=1),
                        ft.Text(
                            f"{tx.created_at.strftime('%m-%d %H:%M')} · 经办:{tx.operator or '-'}",
                            size=11,
                            color=MUTED,
                        ),
                    ],
                    spacing=2,
                    expand=True,
                ),
                ft.Column(
                    [
                        ft.Text(
                            f"{'+' if tx.amount >= 0 else ''}{fmt(tx.amount)}",
                            size=16,
                            weight=ft.FontWeight.BOLD,
                            color=color,
                        ),
                        ft.Text(f"余 {fmt(tx.balance_after)}", size=11, color=MUTED),
                    ],
                    spacing=2,
                    horizontal_alignment=ft.CrossAxisAlignment.END,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
