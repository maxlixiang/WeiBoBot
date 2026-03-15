import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
# 同样支持多个用户，用逗号隔开
ALLOWED_USERS = [int(x) for x in os.getenv("ALLOWED_USERS", "").split(",") if x]

# 定义数据文件名
HISTORY_FILE = "history.json"
STATS_FILE = "stats.json"