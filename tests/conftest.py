"""测试固定为开发配置；显式关闭数据库，不创建或连接任何业务数据库。"""

import os

os.environ["FASTAPI_ENV"] = "development"
os.environ["DATABASE_ENABLED"] = "false"
