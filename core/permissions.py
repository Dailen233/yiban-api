"""鉴权占位依赖：真实账号体系尚未接入，所有权限入口默认拒绝。

保留模板导入名以便基础包装配；不创建学校 SsoUser，不接受模拟登录标记。
"""

from typing import Any, NoReturn

from fastapi import HTTPException


async def get_current_user() -> NoReturn:
    """鉴权未实现，明确返回服务尚不可用。"""
    raise HTTPException(status_code=503, detail="账号与权限服务尚未接入")


# 仅保持模板导入兼容；这些别名都执行同一个默认拒绝的依赖。
get_current_sso_user = get_current_user
get_current_active_user = get_current_user
require_admin = get_current_user
require_teacher = get_current_user
require_student = get_current_user


class PermissionChecker:
    """占位检查器不授予任何角色或资源访问权限。"""

    @staticmethod
    def check_user_access_to_resource(*args: Any, **kwargs: Any) -> bool:
        return False

    @staticmethod
    def check_admin_permission(*args: Any, **kwargs: Any) -> bool:
        return False

    @staticmethod
    def check_teacher_permission(*args: Any, **kwargs: Any) -> bool:
        return False


def check_resource_ownership(resource_owner_id: str, resource_type: str = "general"):
    """属主校验未接入时，同样返回默认拒绝的依赖。"""
    return get_current_user
