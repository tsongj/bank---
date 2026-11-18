"""SQLite 数据库连接与会话管理。

对外只暴露三个东西：
- Base：所有 ORM 模型的基类
- init_db()：建表
- SessionLocal / session_scope()：获取会话
"""
import os
from contextlib import contextmanager

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

import config

os.makedirs(config.DB_DIR, exist_ok=True)

engine = create_engine(
    config.DB_URL,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False},  # 允许 Flet 线程中访问
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()

# 老版本数据库缺少的列：{表名: [(列名, 建列 SQL 片段)]}
# create_all 只会新建表，不会给已有表补列，所以这里做一次轻量迁移。
_ADDED_COLUMNS = {
    "account": [
        ("cny_balance", "FLOAT DEFAULT 0"),
        ("real_balance", "FLOAT DEFAULT 0"),
    ],
    "transaction": [
        ("currency", "VARCHAR(16) DEFAULT 'coin'"),
    ],
    "investment": [
        ("currency", "VARCHAR(16) DEFAULT 'cny'"),
    ],
    "investment_request": [
        ("currency", "VARCHAR(16) DEFAULT 'cny'"),
    ],
}


def _migrate_columns():
    """给已存在的旧库补上新增列（幂等）。"""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns:
                if name not in present:
                    conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN {name} {ddl}'))


def init_db():
    """建表（幂等）。需先 import 模型，确保元数据已注册。"""
    from database import models  # noqa: F401  仅为触发模型注册

    Base.metadata.create_all(engine)
    _migrate_columns()


@contextmanager
def session_scope():
    """事务上下文：正常提交，异常回滚，结束关闭。"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
