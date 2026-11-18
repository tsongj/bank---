"""界面层公共样式与小组件。"""
import flet as ft

import config
from database.models import TxType

# ---- 品牌色（对标农行绿）----
PRIMARY = ft.Colors.GREEN_600
PRIMARY_DARK = ft.Colors.GREEN_800
DANGER = ft.Colors.RED_400
ACCENT = ft.Colors.ORANGE_700
BLUE = ft.Colors.BLUE_600
WARN_BG = "#FFF8E1"
MUTED = ft.Colors.GREY_600
BG_APP = "#F1F6F2"


def fmt(value) -> str:
    """金额格式化：去掉多余小数位。"""
    return f"{round(float(value), 2):g}"


def money(value, symbol=None) -> str:
    if symbol is None:
        symbol = config.CURRENCY_SYMBOL
    return f"{fmt(value)} {symbol}"


def card(content, padding=16, radius=18, bgcolor=ft.Colors.WHITE, on_click=None, expand=None):
    """统一卡片容器：白底 + 圆角 + 柔和投影。"""
    return ft.Container(
        content=content,
        padding=padding,
        bgcolor=bgcolor,
        border_radius=radius,
        on_click=on_click,
        expand=expand,
        shadow=ft.BoxShadow(blur_radius=12, color="#12000000", offset=ft.Offset(0, 3)),
    )


def section(title: str) -> ft.Row:
    """带竖条的小节标题。"""
    return ft.Row(
        [
            ft.Container(width=4, height=18, bgcolor=PRIMARY, border_radius=2),
            ft.Text(title, size=17, weight=ft.FontWeight.W_600, color="#24352B"),
        ],
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


TX_TITLES = {
    TxType.REWARD: "奖励到账",
    TxType.PENALTY: "违规扣款",
    TxType.REDEEM: "心愿兑换",
    TxType.DEPOSIT: "定期存入",
    TxType.WITHDRAW: "定期取回",
    TxType.INTEREST: "利息收入",
    TxType.ADJUST: "账户调整",
    TxType.TRANSFER: "家人转账",
    TxType.FUND_BUY: "理财买入",
    TxType.FUND_SELL: "理财赎回",
    TxType.WITHDRAW_REAL: "真实取款",
}


def tx_title(tx) -> str:
    return TX_TITLES.get(tx.type, tx.type)


def tx_visual(tx_type: str, amount: float):
    """返回流水的 (图标, 主色, 浅底色)，红蓝区分奖惩。"""
    if amount > 0:
        return ft.Icons.TRENDING_UP, PRIMARY, "#E8F5E9"
    if tx_type == TxType.REDEEM:
        return ft.Icons.REDEEM, ACCENT, "#FFF3E0"
    if tx_type == TxType.DEPOSIT:
        return ft.Icons.LOCK, ft.Colors.INDIGO_400, "#E8EAF6"
    if tx_type == TxType.WITHDRAW:
        return ft.Icons.SAVINGS, BLUE, "#E3F2FD"
    if tx_type == TxType.TRANSFER:
        return ft.Icons.SEND, BLUE, "#E3F2FD"
    if tx_type == TxType.FUND_BUY:
        return ft.Icons.ACCOUNT_BALANCE_WALLET, ACCENT, "#FFF3E0"
    if tx_type == TxType.FUND_SELL:
        return ft.Icons.ACCOUNT_BALANCE_WALLET, PRIMARY, "#E8F5E9"
    if tx_type == TxType.WITHDRAW_REAL:
        return ft.Icons.ACCOUNT_BALANCE, ft.Colors.BLUE_GREY_400, "#ECEFF1"
    return ft.Icons.TRENDING_DOWN, DANGER, "#FFEBEE"
