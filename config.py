"""全局配置：货币单位、家长 PIN、语音开关、皮肤模式等。

所有可调参数集中在此，业务层与界面层统一从这里读取，避免散落的魔法值。
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---- 应用信息 ----
APP_TITLE = "家庭成长银行"
APP_SUBTITLE = "小小农行"

# ---- 数据库（单文件 SQLite）----
# 打包成手机 App 后程序自身目录只读，Flet 会提供可写目录 FLET_APP_STORAGE_DATA；
# 桌面端直接运行时则落到项目内的 data/ 目录。
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.getenv("FLET_APP_STORAGE_DATA") or os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DB_DIR, "bank.db")
DB_URL = f"sqlite:///{DB_PATH}"

# ---- 虚拟货币（可自定义名称）----
CURRENCY_NAME = "成长币"      # 例如：星星币 / 能量豆
CURRENCY_SYMBOL = "币"

# ---- 家长安全 ----
PARENT_PIN = "1234"           # 家长审批用的 4 位密码
KID_DEFAULT_PIN = "0000"

# ---- 语音播报 ----
VOICE_ENABLED = True
VOICE_RATE = 180              # 语速，越大越快

# ---- 理财（梦想存钱罐）----
DEFAULT_INTEREST_RATE = 0.05  # 定期到期利率
DEFAULT_LOCK_DAYS = 14        # 默认锁定期天数

# ---- 征信 ----
INIT_CREDIT_SCORE = 100       # 初始征信分
CREDIT_PENALTY = 20           # 每次发生透支扣减的征信分

# ---- 外币兑换（成长币 ↔ 人民币）----
CNY_NAME = "人民币"
CNY_SYMBOL = "元"
FX_BASE_RATE = 0.10           # 中间价基准：1 成长币 ≈ 0.10 元
FX_VOLATILITY = 0.30          # 行情波动幅度（±30%，双正弦叠加）
FX_SPREAD = 0.06              # 买卖点差：买入价低于中间价、卖出价高于中间价
FX_MIN_RATE = 0.05            # 汇率地板
FX_MAX_RATE = 0.25            # 汇率天花板
FX_REFRESH_SECONDS = 60       # 行情快照刷新间隔（秒）
FX_HISTORY_LIMIT = 24         # 汇率走势展示条数

# ---- 股票 ----
STOCK_BASE_PRICE = 100.0      # 新股默认发行价（成长币/股）
STOCK_MIN_PRICE = 1.0         # 股价下限，防止跌穿
STOCK_GRADE_BENCHMARK = 0.75  # 成绩基准线（75 分不涨不跌）
STOCK_GRADE_MAX_DELTA = 0.10  # 单次成绩最大涨跌幅 ±10%

# ---- 父母投资款（人民币记账）----
INVEST_CURRENCY = "CNY"

# ---- 界面皮肤 ----
THEME_MODE = "cartoon"        # cartoon 卡通大字版 / standard 拟真专业版
