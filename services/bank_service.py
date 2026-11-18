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
from database.models import (
    Account,
    Deposit,
    Transaction,
    TxType,
    WishItem,
    DepositProduct,
    InvestmentRequest,
    Investment,
    FundProduct,
    FundHolding,
    FundNavHistory,
)
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
        from sqlalchemy.orm import joinedload
        with session_scope() as s:
            q = s.query(Account).options(
                joinedload(Account.investments),
                joinedload(Account.holdings)
            )
            if role:
                q = q.filter(Account.role == role)
            return q.order_by(Account.id).all()

    @staticmethod
    def get_account(account_id: int):
        from sqlalchemy.orm import joinedload
        with session_scope() as s:
            return s.query(Account).options(
                joinedload(Account.investments),
                joinedload(Account.holdings)
            ).filter(Account.id == account_id).first()

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

    @staticmethod
    def update_wish(wish_id: int, name: str, icon: str, price: float):
        with session_scope() as s:
            wish = s.get(WishItem, wish_id)
            if wish:
                wish.name = name
                wish.icon = icon
                wish.price = float(price)

    @staticmethod
    def delete_wish(wish_id: int):
        with session_scope() as s:
            wish = s.get(WishItem, wish_id)
            if wish:
                s.delete(wish)

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
    def flow_between(account_id: int, start: datetime, end: datetime, currency: str = "coin"):
        """返回区间内 (收入, 支出) 合计。"""
        with session_scope() as s:
            rows = (
                s.query(Transaction.amount)
                .filter(
                    Transaction.account_id == account_id,
                    Transaction.created_at >= start,
                    Transaction.created_at <= end,
                    Transaction.currency == currency
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
    def _apply(session, account, amount, tx_type, reason, operator, allow_overdraft, currency="coin"):
        if currency == "coin":
            new_balance = round(account.balance + amount, 2)
            if new_balance < 0 and not allow_overdraft:
                raise BankError("金币余额不足，本笔交易无法完成")
            account.balance = new_balance
        else:
            new_balance = round(account.cny_balance + amount, 2)
            if new_balance < 0 and not allow_overdraft:
                raise BankError("人民币余额不足，本笔交易无法完成")
            account.cny_balance = new_balance

        was_overdraft = bool(account.overdraft)
        if currency == "coin" and new_balance < 0:
            account.overdraft = True
            if not was_overdraft:
                account.credit_score = max(0, account.credit_score - config.CREDIT_PENALTY)
        elif currency == "coin":
            account.overdraft = False

        tx = Transaction(
            account_id=account.id,
            amount=amount,
            currency=currency,
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
    def reward(cls, account_id: int, amount: float, reason: str, operator_name: str, currency: str = "coin") -> int:
        """存款/奖励（从爸爸账户支出，入账到孩子）。"""
        amount = abs(float(amount))
        with session_scope() as s:
            acc = s.get(Account, account_id)
            parent = s.query(Account).filter(Account.role == "parent").first()
            
            # 孩子入账
            tx = cls._apply(s, acc, amount, TxType.REWARD, reason, operator_name, allow_overdraft=True, currency=currency)
            # 爸爸支出（回流逻辑）
            if parent:
                cls._apply(s, parent, -amount, TxType.REWARD, f"奖励支出({acc.name}): {reason}", "系统", True, currency=currency)
            
            tx_id = tx.id
        voice_service.announce(amount, reason)
        return tx_id

    @classmethod
    def penalty(cls, account_id: int, amount: float, reason: str, operator_name: str, currency: str = "coin") -> int:
        """扣款/处罚（从孩子扣除，回流到爸爸账户）。"""
        amount = abs(float(amount))
        with session_scope() as s:
            acc = s.get(Account, account_id)
            parent = s.query(Account).filter(Account.role == "parent").first()
            
            # 孩子扣款
            tx = cls._apply(s, acc, -amount, TxType.PENALTY, reason, operator_name, allow_overdraft=True, currency=currency)
            # 爸爸回流
            if parent:
                cls._apply(s, parent, amount, TxType.PENALTY, f"违规回流({acc.name}): {reason}", "系统", True, currency=currency)
            
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

    # ------------------------------------------------------------------ #
    # 定期产品管理
    # ------------------------------------------------------------------ #
    @staticmethod
    def add_deposit_product(title: str, rate: float, lock_days: int):
        with session_scope() as s:
            s.add(DepositProduct(title=title, rate=rate, lock_days=lock_days))

    @staticmethod
    def list_deposit_products(only_enabled: bool = True):
        with session_scope() as s:
            q = s.query(DepositProduct)
            if only_enabled:
                q = q.filter(DepositProduct.enabled.is_(True))
            return q.all()

    @staticmethod
    def toggle_deposit_product(product_id: int):
        with session_scope() as s:
            p = s.get(DepositProduct, product_id)
            if p:
                p.enabled = not p.enabled

    # ------------------------------------------------------------------ #
    # 转账功能
    # ------------------------------------------------------------------ #
    @classmethod
    def transfer(cls, from_id: int, to_id: int, amount: float, reason: str, currency: str = "coin") -> int:
        amount = abs(float(amount))
        with session_scope() as s:
            from_acc = s.get(Account, from_id)
            to_acc = s.get(Account, to_id)
            if from_acc is None or to_acc is None:
                raise BankError("账户不存在")
            
            curr_balance = from_acc.balance if currency == "coin" else from_acc.cny_balance
            if curr_balance < amount:
                raise BankError("余额不足")

            cls._apply(s, from_acc, -amount, TxType.TRANSFER, f"转账给 {to_acc.name}: {reason}", "本人", False, currency=currency)
            cls._apply(s, to_acc, amount, TxType.TRANSFER, f"收到 {from_acc.name} 的转账: {reason}", "系统", True, currency=currency)
            voice_service.announce(-amount, f"向{to_acc.name}转账")
        return 0

    # ------------------------------------------------------------------ #
    # 投资金申请
    # ------------------------------------------------------------------ #
    # ------------------------------------------------------------------ #
    # 投资金 (Investment)
    # ------------------------------------------------------------------ #
    @staticmethod
    def submit_investment_request(account_id: int, amount: float, purpose: str, currency: str = "cny"):
        with session_scope() as s:
            req = InvestmentRequest(
                account_id=account_id, 
                amount=float(amount), 
                purpose=purpose,
                currency=currency
            )
            s.add(req)

    @classmethod
    def approve_investment_request(cls, request_id: int, reviewer: str = "家长"):
        with session_scope() as s:
            req = s.get(InvestmentRequest, request_id)
            if req and req.status == "pending":
                req.status = "approved"
                req.reviewed_at = datetime.now()
                
                acc = s.get(Account, req.account_id)
                # 投资金根据币种进入相应账户
                if req.currency == "cny":
                    acc.cny_balance += req.amount
                else:
                    acc.balance += req.amount
                
                # 记录投资记录
                s.add(Investment(
                    account_id=acc.id, 
                    amount=req.amount, 
                    currency=req.currency,
                    purpose=req.purpose, 
                    operator=reviewer
                ))
                unit = "元" if req.currency == "cny" else "金币"
                voice_service.announce(req.amount, f"收到投资{unit}")

    @classmethod
    def direct_invest(cls, account_id: int, amount: float, purpose: str, currency: str, operator: str):
        """家长直接对孩子进行投资。"""
        with session_scope() as s:
            acc = s.get(Account, account_id)
            if not acc:
                raise BankError("账户不存在")
            
            if currency == "cny":
                acc.cny_balance += amount
            else:
                acc.balance += amount
            
            s.add(Investment(
                account_id=acc.id,
                amount=amount,
                currency=currency,
                purpose=purpose,
                operator=operator
            ))

    @staticmethod
    def list_investment_requests(status: str = "pending"):
        with session_scope() as s:
            return s.query(InvestmentRequest).filter(InvestmentRequest.status == status).all()

    @staticmethod
    def list_investments(account_id: int = None):
        with session_scope() as s:
            q = s.query(Investment)
            if account_id:
                q = q.filter_by(account_id=account_id)
            return q.order_by(Investment.invested_at.desc()).all()

    # ------------------------------------------------------------------ #
    # 理财产品 (Fund)
    # ------------------------------------------------------------------ #
    @staticmethod
    def add_fund_product(name: str, code: str, icon: str, nav: float = 1.0):
        with session_scope() as s:
            s.add(FundProduct(name=name, code=code, icon=icon, nav=nav))
            # 初始净值历史
            # s.add(FundNavHistory(fund_id=fund.id, nav=nav)) # 需要先获取 ID

    @staticmethod
    def list_funds(only_enabled: bool = True):
        with session_scope() as s:
            q = s.query(FundProduct)
            if only_enabled:
                q = q.filter(FundProduct.enabled.is_(True))
            return q.all()

    @classmethod
    def buy_fund(cls, account_id: int, fund_id: int, amount: float):
        """购买理财（使用成长币）。"""
        with session_scope() as s:
            acc = s.get(Account, account_id)
            fund = s.get(FundProduct, fund_id)
            if acc.balance < amount:
                raise BankError("余额不足")
            
            shares = round(amount / fund.nav, 4)
            holding = s.query(FundHolding).filter_by(account_id=account_id, fund_id=fund_id).first()
            if holding:
                holding.shares += shares
                holding.cost += amount
            else:
                s.add(FundHolding(account_id=account_id, fund_id=fund_id, shares=shares, cost=amount))
            
            cls._apply(s, acc, -amount, TxType.FUND_BUY, f"买入理财: {fund.name}", "本人", False)

    @classmethod
    def sell_fund(cls, account_id: int, fund_id: int, shares: float):
        """赎回理财。"""
        with session_scope() as s:
            acc = s.get(Account, account_id)
            fund = s.get(FundProduct, fund_id)
            holding = s.query(FundHolding).filter_by(account_id=account_id, fund_id=fund_id).first()
            if not holding or holding.shares < shares:
                raise BankError("份额不足")
            
            amount = round(shares * fund.nav, 2)
            holding.shares -= shares
            holding.cost -= (holding.cost / (holding.shares + shares)) * shares # 简单平摊成本
            
            cls._apply(s, acc, amount, TxType.FUND_SELL, f"赎回理财: {fund.name}", "本人", True)

    @staticmethod
    def update_fund_nav(fund_id: int, new_nav: float):
        with session_scope() as s:
            fund = s.get(FundProduct, fund_id)
            if fund:
                fund.nav = new_nav
                s.add(FundNavHistory(fund_id=fund_id, nav=new_nav))

    # ------------------------------------------------------------------ #
    # 外汇兑换
    # ------------------------------------------------------------------ #
    @classmethod
    def exchange_currency(cls, account_id: int, coin_amount: float, mode: str, mid_rate: float):
        """外汇兑换：金币 <-> 人民币，记录流水。"""
        coin_amount = abs(float(coin_amount))
        cny_amount = round(coin_amount * mid_rate, 2)
        
        with session_scope() as s:
            acc = s.get(Account, account_id)
            if mode == "sell": # 金币换人民币
                cls._apply(s, acc, -coin_amount, TxType.ADJUST, f"兑换卖出: {coin_amount}金币 -> {cny_amount}元", "本人", False, currency="coin")
                cls._apply(s, acc, cny_amount, TxType.ADJUST, f"兑换买入: {cny_amount}元 (来自{coin_amount}金币)", "系统", True, currency="cny")
            else: # 人民币换金币
                cls._apply(s, acc, -cny_amount, TxType.ADJUST, f"兑换卖出: {cny_amount}元 -> {coin_amount}金币", "本人", False, currency="cny")
                cls._apply(s, acc, coin_amount, TxType.ADJUST, f"兑换买入: {coin_amount}金币 (来自{cny_amount}元)", "系统", True, currency="coin")

    # ------------------------------------------------------------------ #
    # 真实账户与取款
    # ------------------------------------------------------------------ #
    @classmethod
    def transfer_cny_real(cls, account_id: int, amount: float, mode: str):
        """人民币与真实账户互转。"""
        amount = abs(float(amount))
        with session_scope() as s:
            acc = s.get(Account, account_id)
            if mode == "to_real": # 转入真实账户
                cls._apply(s, acc, -amount, TxType.WITHDRAW_REAL, f"转出到真实账户: {amount}元", "本人", False, currency="cny")
                acc.real_balance = round(acc.real_balance + amount, 2)
            else: # 从真实账户转入
                if acc.real_balance < amount:
                    raise BankError("真实账户余额不足")
                acc.real_balance = round(acc.real_balance - amount, 2)
                cls._apply(s, acc, amount, TxType.WITHDRAW_REAL, f"从真实账户转入: {amount}元", "本人", True, currency="cny")

    @staticmethod
    def add_account(name: str, role: str, avatar: str, pin: str, card_no: str = None):
        with session_scope() as s:
            acc = Account(
                name=name,
                role=role,
                avatar=avatar,
                pin=pin,
                card_no=card_no,
                balance=0.0,
                cny_balance=0.0
            )
            s.add(acc)

    @staticmethod
    def delete_account(account_id: int):
        with session_scope() as s:
            acc = s.get(Account, account_id)
            if acc:
                s.delete(acc)

    @classmethod
    def inject_currency(cls, parent_id: int, amount: float, currency: str):
        """中央银行投放货币：增加爸爸账户的余额。"""
        with session_scope() as s:
            parent = s.get(Account, parent_id)
            if not parent or parent.role != "parent":
                raise BankError("只有行长账户可以投放货币")
            
            cls._apply(
                s, parent, amount, TxType.INJECTION, 
                f"央行投放{'金币' if currency=='coin' else '人民币'}", 
                "行长", True, currency=currency
            )

    # ------------------------------------------------------------------ #
    # 安全
    # ------------------------------------------------------------------ #
    @staticmethod
    def update_pin(account_id: int, new_pin: str):
        with session_scope() as s:
            acc = s.get(Account, account_id)
            if acc:
                acc.pin = new_pin
