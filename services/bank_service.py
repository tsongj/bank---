"""交易引擎：存取款、违规扣款、透支征信、心愿兑换、定期存款。

核心规则（金融级记账）：
1. 余额由 BankService 统一维护，业务代码不得直接改 Account.balance。
2. 每一笔余额变动都会写一条 Transaction 流水（append-only）。
3. 余额不允许为负时抛 BankError；允许透支时（扣款场景）触发征信降级。
4. 透支（余额为负）未还清前禁止一切兑换类支出。
"""
from datetime import datetime, timedelta

from sqlalchemy import func

import config
from database.db import session_scope
from database.models import Account, Deposit, Transaction, TxType, WishItem
from services import voice_service


class BankError(Exception):
    """业务异常：余额不足、透支受限、定期未到期等。"""


# --------------------------------------------------------------------------- #
# 预设账户 / 商品
# --------------------------------------------------------------------------- #
DEFAULT_WISHES = [
    ("看电视 30 分钟", "📺", 20),
    ("免做一次家务", "🧽", 50),
    ("选今晚的晚餐", "🍜", 30),
    ("玩平板 30 分钟", "🎮", 30),
    ("买一个冰淇淋", "🍦", 25),
    ("周末去游乐园", "🎡", 300),
]


class BankService:
    # ------------------------------------------------------------------ #
    # 账户初始化与查询
    # ------------------------------------------------------------------ #
    @staticmethod
    def seed_default_accounts(session):
        """首次运行创建 1 位家长 + 2 位孩子账户（姐姐 / 弟弟）。"""
        if session.query(Account).count() > 0:
            return
        session.add_all(
            [
                Account(
                    name="爸爸",
                    role="parent",
                    avatar="👨",
                    pin=config.PARENT_PIN,
                    credit_score=config.INIT_CREDIT_SCORE,
                ),
                Account(
                    name="姐姐",
                    role="kid",
                    avatar="👧",
                    card_no="6228 4800 0000 0001",
                    pin=config.KID_DEFAULT_PIN,
                    balance=0.0,
                ),
                Account(
                    name="弟弟",
                    role="kid",
                    avatar="👦",
                    card_no="6228 4800 0000 0002",
                    pin=config.KID_DEFAULT_PIN,
                    balance=0.0,
                ),
            ]
        )

    @staticmethod
    def seed_default_wishes(session):
        if session.query(WishItem).count() > 0:
            return
        for name, icon, price in DEFAULT_WISHES:
            session.add(WishItem(name=name, icon=icon, price=price))

    @staticmethod
    def list_accounts(role: str | None = None):
        with session_scope() as s:
            q = s.query(Account)
            if role:
                q = q.filter(Account.role == role)
            return q.order_by(Account.id).all()

    @staticmethod
    def get_account(account_id: int):
        with session_scope() as s:
            return s.get(Account, account_id)

    @staticmethod
    def list_wishes(only_enabled: bool = True):
        with session_scope() as s:
            q = s.query(WishItem)
            if only_enabled:
                q = q.filter(WishItem.enabled.is_(True))
            return q.order_by(WishItem.price).all()

    @staticmethod
    def add_wish(name: str, icon: str, price: float):
        with session_scope() as s:
            s.add(WishItem(name=name, icon=icon or "🎁", price=float(price)))

    # ------------------------------------------------------------------ #
    # 流水与对账
    # ------------------------------------------------------------------ #
    @staticmethod
    def recalc_balance(account_id: int) -> float:
        """以流水累加重算余额，用于对账校验。"""
        with session_scope() as s:
            total = (
                s.query(func.coalesce(func.sum(Transaction.amount), 0.0))
                .filter(Transaction.account_id == account_id)
                .scalar()
            )
            return round(float(total), 2)

    @staticmethod
    def list_transactions(account_id: int, limit: int = 100):
        with session_scope() as s:
            return (
                s.query(Transaction)
                .filter(Transaction.account_id == account_id)
                .order_by(Transaction.created_at.desc(), Transaction.id.desc())
                .limit(limit)
                .all()
            )

    @staticmethod
    def flow_between(account_id: int, start: datetime, end: datetime):
        """返回区间内 (收入, 支出) 合计。"""
        with session_scope() as s:
            rows = (
                s.query(Transaction.amount)
                .filter(
                    Transaction.account_id == account_id,
                    Transaction.created_at >= start,
                    Transaction.created_at <= end,
                )
                .all()
            )
        income = round(sum(r[0] for r in rows if r[0] > 0), 2)
        expense = round(sum(-r[0] for r in rows if r[0] < 0), 2)
        return income, expense

    # ------------------------------------------------------------------ #
    # 内部：写一笔流水（唯一的余额入口）
    # ------------------------------------------------------------------ #
    @staticmethod
    def _apply(session, account, amount, tx_type, reason, operator, allow_overdraft):
        new_balance = round(account.balance + amount, 2)
        if new_balance < 0 and not allow_overdraft:
            raise BankError("余额不足，本笔交易无法完成")

        was_overdraft = bool(account.overdraft)
        account.balance = new_balance

        if new_balance < 0:
            account.overdraft = True
            # 仅从“正常”首次跌入负值时扣征信，避免反复扣分
            if not was_overdraft:
                account.credit_score = max(0, account.credit_score - config.CREDIT_PENALTY)
        else:
            account.overdraft = False  # 还清欠款，恢复兑换资格

        tx = Transaction(
            account_id=account.id,
            amount=amount,
            balance_after=new_balance,
            type=tx_type,
            reason=reason,
            operator=operator,
        )
        session.add(tx)
        session.flush()
        return tx

    # ------------------------------------------------------------------ #
    # 对外的交易操作（各自管理会话，返回流水 id）
    # ------------------------------------------------------------------ #
    @classmethod
    def reward(cls, account_id: int, amount: float, reason: str, operator: str) -> int:
        """存款/奖励（正向往入）。"""
        amount = abs(float(amount))
        with session_scope() as s:
            acc = s.get(Account, account_id)
            tx = cls._apply(s, acc, amount, TxType.REWARD, reason, operator, allow_overdraft=True)
            tx_id = tx.id
        voice_service.announce(amount, reason)
        return tx_id

    @classmethod
    def penalty(cls, account_id: int, amount: float, reason: str, operator: str) -> int:
        """扣款/处罚（负向支出），允许透支并触发征信降级。"""
        amount = abs(float(amount))
        with session_scope() as s:
            acc = s.get(Account, account_id)
            tx = cls._apply(s, acc, -amount, TxType.PENALTY, reason, operator, allow_overdraft=True)
            tx_id = tx.id
        voice_service.announce(-amount, reason)
        return tx_id

    @classmethod
    def redeem(cls, account_id: int, wish_id: int, operator: str) -> int:
        """心愿兑换：透支受限 + 余额校验。"""
        with session_scope() as s:
            acc = s.get(Account, account_id)
            wish = s.get(WishItem, wish_id)
            if wish is None or not wish.enabled:
                raise BankError("该奖品不存在或已下架")
            if acc.overdraft:
                raise BankError("账户存在透支，征信受限，请先还清欠款")
            if acc.balance < wish.price:
                raise BankError("余额不足，继续加油攒币吧")
            if wish.stock == 0:
                raise BankError("该奖品已被兑完")

            cls._apply(
                s, acc, -wish.price, TxType.REDEEM, f"兑换：{wish.name}", operator,
                allow_overdraft=False,
            )
            if wish.stock > 0:
                wish.stock -= 1
            price = wish.price
            name = wish.name
        voice_service.announce(-price, f"兑换{name}")
        return int(price)

    # ------------------------------------------------------------------ #
    # 梦想存钱罐（定期）
    # ------------------------------------------------------------------ #
    @classmethod
    def open_deposit(cls, account_id: int, amount: float, lock_days: int, rate: float) -> int:
        amount = float(amount)
        if amount <= 0:
            raise BankError("存入金额需大于 0")
        with session_scope() as s:
            acc = s.get(Account, account_id)
            if acc.overdraft:
                raise BankError("透支账户暂不能办理定期存款")
            if acc.balance < amount:
                raise BankError("余额不足，无法存入定期")

            dep = Deposit(
                account_id=acc.id,
                amount=amount,
                rate=rate,
                lock_days=lock_days,
                mature_at=datetime.now() + timedelta(days=lock_days),
                status="locked",
            )
            s.add(dep)
            cls._apply(
                s, acc, -amount, TxType.DEPOSIT,
                f"存入定期 {lock_days} 天（年化 {rate:.0%}）", "本人",
                allow_overdraft=False,
            )
            dep_id = dep.id
        voice_service.announce(-amount, "定期存款")
        return dep_id

    @classmethod
    def settle_deposit(cls, deposit_id: int, operator: str = "家长") -> float:
        """到期支取：返还本金 + 利息，返回利息金额。"""
        with session_scope() as s:
            dep = s.get(Deposit, deposit_id)
            if dep is None:
                raise BankError("该笔定期不存在")
            if dep.status == "settled":
                raise BankError("该笔定期已结算")
            if datetime.now() < dep.mature_at:
                raise BankError("尚未到期，不能提前支取")

            acc = s.get(Account, dep.account_id)
            interest = round(dep.amount * dep.rate, 2)
            cls._apply(s, acc, dep.amount, TxType.WITHDRAW, "定期到期取回本金", operator, False)
            if interest > 0:
                cls._apply(s, acc, interest, TxType.INTEREST, f"定期利息（{dep.rate:.0%}）", operator, False)
            dep.status = "settled"
        if interest > 0:
            voice_service.announce(interest, "定期利息")
        return interest

    @staticmethod
    def list_deposits(account_id: int):
        with session_scope() as s:
            return (
                s.query(Deposit)
                .filter(Deposit.account_id == account_id)
                .order_by(Deposit.status.desc(), Deposit.mature_at.asc())
                .all()
            )
