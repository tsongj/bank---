"""核心数据表定义。

设计原则（银行账本严谨性）：
- Account.balance 只是“缓存余额”，任何变动都必须同时写入一条 Transaction 流水；
  真实对账以流水累加为准，可随时用 BankService.recalc_balance 重算校验。
- 流水只增不改不删（append-only），保证账目可追溯、防篡改。
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Float,
)
from sqlalchemy.orm import relationship

import config
from database.db import Base


class Account(Base):
    """账户：家长（行长）与孩子（储户）共用一张表，用 role 区分。"""

    __tablename__ = "account"

    id = Column(Integer, primary_key=True)
    name = Column(String(32), nullable=False)
    role = Column(String(16), nullable=False, default="kid")   # parent / kid
    card_no = Column(String(32), unique=True, nullable=True)    # 虚拟卡号（孩子）
    avatar = Column(String(64), default="🧒")                   # 头像（emoji）
    pin = Column(String(64), default=config.KID_DEFAULT_PIN)    # 登录/审批密码
    balance = Column(Float, default=0.0)                        # 成长币缓存余额
    cny_balance = Column(Float, default=0.0)                    # 人民币钱包（结汇所得/家长存入）
    credit_score = Column(Integer, default=config.INIT_CREDIT_SCORE)  # 征信分
    overdraft = Column(Boolean, default=False)                  # 是否处于透支状态
    created_at = Column(DateTime, default=datetime.now)

    transactions = relationship(
        "Transaction", back_populates="account", cascade="all, delete-orphan"
    )
    requests = relationship(
        "TaskRequest", back_populates="account", cascade="all, delete-orphan"
    )
    deposits = relationship(
        "Deposit", back_populates="account", cascade="all, delete-orphan"
    )
    holdings = relationship(
        "StockHolding", back_populates="account", cascade="all, delete-orphan"
    )
    investments = relationship(
        "Investment", back_populates="account", cascade="all, delete-orphan"
    )

    @property
    def is_parent(self) -> bool:
        return self.role == "parent"

    def __repr__(self) -> str:
        return f"<Account {self.id} {self.name} {self.role} 余额={self.balance}>"


class Transaction(Base):
    """流水账单：任何余额变动都必须留痕，只增不改不删。"""

    __tablename__ = "transaction"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("account.id"), nullable=False)
    amount = Column(Float, nullable=False)               # 正=存入，负=支出
    balance_after = Column(Float, nullable=False)        # 交易后余额快照
    type = Column(String(16), nullable=False)            # 见 TxType
    reason = Column(String(128), default="")             # 变动原因
    operator = Column(String(32), default="")            # 经办人
    created_at = Column(DateTime, default=datetime.now)

    account = relationship("Account", back_populates="transactions")

    def __repr__(self) -> str:
        return f"<Tx {self.type} {self.amount:+g} 余额={self.balance_after}>"


class TxType:
    """流水类型常量。"""

    REWARD = "reward"        # 奖励入账（收款）
    PENALTY = "penalty"      # 违规扣款（消费）
    REDEEM = "redeem"        # 心愿兑换
    DEPOSIT = "deposit"      # 转入定期
    WITHDRAW = "withdraw"    # 取回定期本金
    INTEREST = "interest"    # 定期利息
    ADJUST = "adjust"        # 手动调整
    FX = "fx"                # 结汇 / 购汇（成长币侧）
    STOCK_BUY = "stock_buy"  # 买入股票
    STOCK_SELL = "stock_sell"  # 卖出股票


class TaskRule(Base):
    """奖惩规则库：3-8 岁预设习惯任务，家长可增删改。"""

    __tablename__ = "task_rule"

    id = Column(Integer, primary_key=True)
    title = Column(String(64), nullable=False)       # 如“按时完成作业”
    icon = Column(String(16), default="⭐")           # 图标（emoji）
    amount = Column(Float, nullable=False)           # 正=奖励，负=处罚
    category = Column(String(16), default="good")    # good 好习惯 / bad 坏习惯
    enabled = Column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<Rule {self.title} {self.amount:+g}>"


class TaskRequest(Base):
    """任务申请：孩子提交后处于 pending，需家长审批才入账（防误触）。"""

    __tablename__ = "task_request"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("account.id"), nullable=False)
    rule_id = Column(Integer, ForeignKey("task_rule.id"), nullable=True)
    title = Column(String(64), default="")           # 冗余标题，规则删除后仍可读
    amount = Column(Float, default=0.0)
    status = Column(String(16), default="pending")   # pending/approved/rejected
    created_at = Column(DateTime, default=datetime.now)
    reviewed_at = Column(DateTime, nullable=True)

    account = relationship("Account", back_populates="requests")

    def __repr__(self) -> str:
        return f"<Req {self.title} {self.status}>"


class WishItem(Base):
    """心愿兑换超市的商品（实物或特权）。"""

    __tablename__ = "wish_item"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False)
    icon = Column(String(16), default="🎁")
    price = Column(Float, nullable=False)
    stock = Column(Integer, default=-1)              # -1 表示不限量
    enabled = Column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<Wish {self.name} {self.price}>"


class Deposit(Base):
    """定期存款（梦想存钱罐）：锁定一段时间后发利息。"""

    __tablename__ = "deposit"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("account.id"), nullable=False)
    amount = Column(Float, nullable=False)           # 本金
    rate = Column(Float, default=config.DEFAULT_INTEREST_RATE)
    lock_days = Column(Integer, default=config.DEFAULT_LOCK_DAYS)
    start_at = Column(DateTime, default=datetime.now)
    mature_at = Column(DateTime, nullable=False)     # 到期日
    status = Column(String(16), default="locked")    # locked/matured/settled

    account = relationship("Account", back_populates="deposits")

    def __repr__(self) -> str:
        return f"<Deposit {self.amount} {self.status}>"


# ======================================================================= #
# V2 新增模块：外币兑换 / 父母投资 / 股票
# ======================================================================= #
class CurrencyRate(Base):
    """汇率行情快照：成长币兑人民币（历史序列即“K 线”）。

    buy_rate  银行买入价：孩子卖出成长币时使用（偏低）
    sell_rate 银行卖出价：孩子买入成长币时使用（偏高）
    两者差价构成银行点差，天然让孩子理解“买卖不同价”。
    """

    __tablename__ = "currency_rate"

    id = Column(Integer, primary_key=True)
    mid_rate = Column(Float, nullable=False)              # 中间价
    buy_rate = Column(Float, nullable=False)              # 银行买入价（结汇价）
    sell_rate = Column(Float, nullable=False)             # 银行卖出价（购汇价）
    change_pct = Column(Float, default=0.0)               # 相对上一快照的涨跌幅（%）
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<Rate {self.mid_rate} 涨跌={self.change_pct}%>"


class FxTrade(Base):
    """结汇 / 购汇凭证（人民币侧单独记账，与成长币流水解耦）。"""

    __tablename__ = "fx_trade"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("account.id"), nullable=False)
    direction = Column(String(16), nullable=False)        # sell_coin 结汇 / buy_coin 购汇
    coin_amount = Column(Float, nullable=False)           # 成长币数量
    cny_amount = Column(Float, nullable=False)            # 人民币金额
    rate = Column(Float, nullable=False)                  # 成交汇率
    operator = Column(String(32), default="本人")
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<Fx {self.direction} {self.coin_amount}币 -> {self.cny_amount}元>"


class Investment(Base):
    """父母投资款：家长对孩子的人民币投入，单独一本账。

    与孩子的成长币账户完全隔离，孩子端只读展示，体现“父母为我花了多少钱”。
    """

    __tablename__ = "investment"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("account.id"), nullable=False)
    amount = Column(Float, nullable=False)                # 人民币金额
    purpose = Column(String(128), default="")             # 用途，如“钢琴课学费”
    operator = Column(String(32), default="")             # 出资家长
    invested_at = Column(DateTime, default=datetime.now)  # 业务发生时间（家长可指定）
    created_at = Column(DateTime, default=datetime.now)   # 录入时间

    account = relationship("Account", back_populates="investments")

    def __repr__(self) -> str:
        return f"<Invest {self.amount}元 {self.purpose}>"


class Stock(Base):
    """家庭股票：由家长发行并设定发行价，价格随孩子成绩波动。"""

    __tablename__ = "stock"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False)
    code = Column(String(16), unique=True, nullable=False)
    icon = Column(String(16), default="📈")
    base_price = Column(Float, default=config.STOCK_BASE_PRICE)   # 发行价
    price = Column(Float, default=config.STOCK_BASE_PRICE)        # 最新价
    enabled = Column(Boolean, default=True)                       # False=停牌
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<Stock {self.code} {self.price}>"


class StockHolding(Base):
    """持仓：同一账户同一只股票只保留一行，shares/cost 累加维护。"""

    __tablename__ = "stock_holding"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("account.id"), nullable=False)
    stock_id = Column(Integer, ForeignKey("stock.id"), nullable=False)
    shares = Column(Float, default=0.0)      # 持有股数
    cost = Column(Float, default=0.0)        # 累计买入成本（成长币）

    account = relationship("Account", back_populates="holdings")
    stock = relationship("Stock")

    def __repr__(self) -> str:
        return f"<Holding stock={self.stock_id} shares={self.shares}>"


class StockGrade(Base):
    """成绩记录：家长录入后按分数换算涨跌幅，直接驱动股价。"""

    __tablename__ = "stock_grade"

    id = Column(Integer, primary_key=True)
    stock_id = Column(Integer, ForeignKey("stock.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("account.id"), nullable=True)
    subject = Column(String(32), default="")             # 科目
    score = Column(Float, default=0.0)
    max_score = Column(Float, default=100.0)
    change_pct = Column(Float, default=0.0)              # 本次带来的涨跌幅（%）
    price_after = Column(Float, default=0.0)             # 记录后股价
    note = Column(String(128), default="")
    created_at = Column(DateTime, default=datetime.now)

    stock = relationship("Stock")

    def __repr__(self) -> str:
        return f"<Grade {self.subject} {self.score}/{self.max_score} {self.change_pct:+g}%>"


class StockTrade(Base):
    """股票买卖流水（成长币计价，同时会在主账本留一条流水）。"""

    __tablename__ = "stock_trade"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("account.id"), nullable=False)
    stock_id = Column(Integer, ForeignKey("stock.id"), nullable=False)
    direction = Column(String(8), nullable=False)        # buy / sell
    shares = Column(Float, nullable=False)
    price = Column(Float, nullable=False)                # 成交价
    amount = Column(Float, nullable=False)               # 成交金额（成长币）
    created_at = Column(DateTime, default=datetime.now)

    stock = relationship("Stock")

    def __repr__(self) -> str:
        return f"<StockTrade {self.direction} {self.shares}@{self.price}>"
