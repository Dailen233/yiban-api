"""共享列类型：无时区 DATETIME(6) 存 UTC。

写入前转 UTC、存为 naive；读回后恢复 UTC 语义（标记 aware UTC）。
"""

from datetime import datetime, timezone

from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """MySQL DATETIME(6) 无时区列，语义为 UTC。

    - 写入前：aware datetime 转 UTC 并去掉 tzinfo（存 naive UTC）；
    - 读回后：naive datetime 标记为 aware UTC（恢复 UTC 语义）；
    - 已是 naive 的输入按 UTC 语义原样存储（调用方负责保证为 UTC，如 ``utcnow()``）。
    """

    impl = DATETIME
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(DATETIME(fsp=6))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
