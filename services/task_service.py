"""奖惩规则库与任务审批。

奖惩闭环：
  孩子提交申请(pending 黄灯) -> 家长输入密码审批 -> 通过则入账 / 驳回则作废。
这样做既能防止孩子误触直接加分，也让“奖励来之不易”。
"""
from datetime import datetime

from database.db import session_scope
from database.models import Account, TaskRequest, TaskRule
from services.bank_service import BankError, BankService

# 3-8 岁预设习惯任务（amount 正=奖励，负=处罚）
DEFAULT_RULES = [
    ("按时完成作业", "📚", 10, "good"),
    ("按时上床睡觉", "🛏️", 8, "good"),
    ("自己整理玩具", "🧸", 5, "good"),
    ("认真刷牙洗脸", "🦷", 3, "good"),
    ("主动阅读 20 分钟", "📖", 8, "good"),
    ("帮家人做家务", "🧹", 5, "good"),
    ("主动说谢谢", "🙇", 3, "good"),
    ("拖延不写作业", "⏰", -15, "bad"),
    ("发脾气摔东西", "😡", -15, "bad"),
    ("说脏话", "🤬", -10, "bad"),
    ("熬夜不肯睡觉", "🌙", -8, "bad"),
]


class TaskService:
    # ------------------------------------------------------------------ #
    # 规则库
    # ------------------------------------------------------------------ #
    @staticmethod
    def seed_default_rules(session):
        if session.query(TaskRule).count() > 0:
            return
        for title, icon, amount, category in DEFAULT_RULES:
            session.add(TaskRule(title=title, icon=icon, amount=amount, category=category))

    @staticmethod
    def list_rules(only_enabled: bool = True, category: str | None = None):
        with session_scope() as s:
            q = s.query(TaskRule)
            if only_enabled:
                q = q.filter(TaskRule.enabled.is_(True))
            if category:
                q = q.filter(TaskRule.category == category)
            return q.order_by(TaskRule.category, TaskRule.id).all()

    @staticmethod
    def add_rule(title: str, icon: str, amount: float, category: str = "good"):
        with session_scope() as s:
            s.add(TaskRule(title=title, icon=icon or "⭐", amount=float(amount), category=category))

    @staticmethod
    def update_rule(rule_id: int, title: str, icon: str, amount: float, category: str):
        with session_scope() as s:
            rule = s.get(TaskRule, rule_id)
            if rule:
                rule.title = title
                rule.icon = icon
                rule.amount = float(amount)
                rule.category = category

    @staticmethod
    def delete_rule(rule_id: int):
        with session_scope() as s:
            rule = s.get(TaskRule, rule_id)
            if rule:
                s.delete(rule)

    @staticmethod
    def toggle_rule(rule_id: int):
        with session_scope() as s:
            rule = s.get(TaskRule, rule_id)
            if rule:
                rule.enabled = not rule.enabled

    # ------------------------------------------------------------------ #
    # 任务申请与审批
    # ------------------------------------------------------------------ #
    @staticmethod
    def submit_request(account_id: int, rule_id: int) -> int:
        """孩子提交任务申请，生成一条 pending 记录（不直接入账）。"""
        with session_scope() as s:
            rule = s.get(TaskRule, rule_id)
            if rule is None or not rule.enabled:
                raise BankError("该任务不存在或已停用")
            pending = (
                s.query(TaskRequest)
                .filter(
                    TaskRequest.account_id == account_id,
                    TaskRequest.rule_id == rule_id,
                    TaskRequest.status == "pending",
                )
                .first()
            )
            if pending:
                raise BankError("这个任务已经提交过了，等待家长确认哦")

            req = TaskRequest(
                account_id=account_id,
                rule_id=rule_id,
                title=rule.title,
                amount=rule.amount,
                status="pending",
            )
            s.add(req)
            s.flush()
            return req.id

    @staticmethod
    def list_requests(status: str | None = None, account_id: int | None = None, limit: int = 100):
        with session_scope() as s:
            q = s.query(TaskRequest)
            if status:
                q = q.filter(TaskRequest.status == status)
            if account_id:
                q = q.filter(TaskRequest.account_id == account_id)
            return (
                q.order_by(TaskRequest.status, TaskRequest.created_at.desc())
                .limit(limit)
                .all()
            )

    @classmethod
    def approve_request(cls, request_id: int, reviewer: str = "家长") -> int:
        """审批通过：正式触发入账（奖励）或扣款（处罚）。"""
        with session_scope() as s:
            req = s.get(TaskRequest, request_id)
            if req is None:
                raise BankError("该申请不存在")
            if req.status != "pending":
                raise BankError("该申请已被处理")
            account_id, amount, title = req.account_id, req.amount, req.title
            req.status = "approved"
            req.reviewed_at = datetime.now()

        if amount >= 0:
            tx_id = BankService.reward(account_id, amount, f"任务通过：{title}", reviewer)
        else:
            tx_id = BankService.penalty(account_id, amount, f"违规记录：{title}", reviewer)
        return tx_id

    @staticmethod
    def reject_request(request_id: int):
        with session_scope() as s:
            req = s.get(TaskRequest, request_id)
            if req is None:
                raise BankError("该申请不存在")
            if req.status != "pending":
                raise BankError("该申请已被处理")
            req.status = "rejected"
            req.reviewed_at = datetime.now()

    @staticmethod
    def pending_count() -> int:
        with session_scope() as s:
            return s.query(TaskRequest).filter(TaskRequest.status == "pending").count()

    @staticmethod
    def kid_requests(account_id: int, limit: int = 20):
        with session_scope() as s:
            return (
                s.query(TaskRequest)
                .filter(TaskRequest.account_id == account_id)
                .order_by(TaskRequest.created_at.desc())
                .limit(limit)
                .all()
            )

    @staticmethod
    def list_kids():
        from sqlalchemy.orm import joinedload
        with session_scope() as s:
            return s.query(Account).options(
                joinedload(Account.investments),
                joinedload(Account.holdings)
            ).filter(Account.role == "kid").order_by(Account.id).all()
