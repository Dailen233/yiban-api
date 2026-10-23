"""账号请求/响应模型（任务 2：注册）。"""

from pydantic import BaseModel, Field, field_validator

from utils.validators import EMAIL_PATTERN


class RegisterRequest(BaseModel):
    """注册请求。role 由服务端固定为 'user'，忽略请求体中的 role。"""

    email: str = Field(..., description="邮箱")
    password: str = Field(..., description="密码")
    display_name: str = Field(..., description="昵称/显示名")

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        email = v.strip().lower()
        if not email or not EMAIL_PATTERN.match(email):
            raise ValueError("邮箱格式不正确")
        return email

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        # 原样校验，不 strip/lower；bcrypt 仅取前 72 字节，超限必须拒绝而非截断
        if len(v) < 8:
            raise ValueError("密码至少 8 个字符")
        if len(v.encode("utf-8")) > 72:
            raise ValueError("密码 UTF-8 编码后不得超过 72 字节")
        return v

    @field_validator("display_name")
    @classmethod
    def _validate_display_name(cls, v: str) -> str:
        name = v.strip()
        if not name:
            raise ValueError("昵称不能为空")
        if len(name) > 100:
            raise ValueError("昵称长度不得超过 100 字符")
        return name


class RegisterResponse(BaseModel):
    """注册响应（绝不返回 password_hash）。"""

    id: str
    email: str
    display_name: str
    role: str
