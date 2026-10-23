"""会话 JWT 签发/验签与密钥校验（任务 3）。

签发与验签使用同一个最终生效密钥（``effective_jwt_secret_key``）。
JWT ``exp`` 与数据库 ``expires_at`` 由同一 UTC 到期时刻产生：``expires_at``
按微秒存 DATETIME(6)，``exp`` 由 PyJWT 编码时向下取整到秒，验签时 PyJWT
以秒比较；数据库侧以微秒比较，二者来自同一时刻，不会各自独立计算造成偏差。
"""

from datetime import datetime, timezone
from typing import Dict

import jwt

from config import settings
from utils.custom_exceptions import AuthenticationException

# 教学默认值前缀与占位符（拒绝使用）
_TEACHING_SECRET_PREFIXES = (
    "dev-secret-key-",
    "test-secret-key-",
    "staging-secret-key-",
)
_DEFAULT_SECRET = "your-secret-key-change-in-production"
# 会话 Token 固定 HS256，不接受 settings.algorithm 等其他算法
_SESSION_ALGORITHM = "HS256"


def validate_jwt_secret_key(secret: str) -> None:
    """校验最终生效的 JWT 密钥，拒绝空值、短密钥、教学默认值与未替换占位符。

    HS256 密钥不得短于 32 字节（256 位）UTF-8 编码，否则熵不足（RFC 7518 3.2）。
    """
    if not secret:
        raise ValueError("JWT 密钥为空")
    if len(secret.encode("utf-8")) < 32:
        raise ValueError("JWT 密钥长度不足 32 字节")
    if secret == _DEFAULT_SECRET:
        raise ValueError("JWT 密钥不能使用教学默认值")
    if secret.startswith(_TEACHING_SECRET_PREFIXES):
        raise ValueError("JWT 密钥不能使用教学默认值")
    if secret.startswith("${") and secret.endswith("}"):
        raise ValueError("JWT 密钥不能使用未替换的占位符")


def effective_secret_key() -> str:
    """返回并校验最终生效的 JWT 密钥。"""
    secret = settings.effective_jwt_secret_key
    validate_jwt_secret_key(secret)
    return secret


def create_session_token(sub: str, jti: str, aud: str, expires_at: datetime) -> str:
    """签发会话 JWT（固定 HS256）。``exp`` 与 ``expires_at`` 为同一 UTC 到期时刻。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "jti": jti,
        "aud": aud,
        "iat": now,
        "exp": expires_at,
    }
    return jwt.encode(
        payload, effective_secret_key(), algorithm=_SESSION_ALGORITHM
    )


def decode_session_token(token: str, aud: str) -> Dict:
    """验签并验证签名、exp、aud，要求 sub/jti/aud/exp 声明存在（固定 HS256）。"""
    try:
        return jwt.decode(
            token,
            effective_secret_key(),
            algorithms=[_SESSION_ALGORITHM],
            audience=aud,
            options={"require": ["exp", "sub", "jti", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthenticationException("无效或过期的令牌") from exc
