"""写接口 CSRF/Origin 校验依赖（跨路由复用，置于 core 避免 app/api 循环导入）。"""

from typing import Annotated

from fastapi import Header, HTTPException, Request

from config import settings


async def require_trusted_origin(
    request: Request,
    x_yiban_request: Annotated[str | None, Header(alias="X-Yiban-Request")] = None,
) -> None:
    """写接口 CSRF/Origin 校验。

    要求：Origin 精确匹配可信白名单 + 携带固定请求头 ``X-Yiban-Request: 1``。
    缺失/不可信 Origin 或缺头均 403；不使用 Referer 兜底。
    OPTIONS 预检由 CORSMiddleware 放行，不会进入本依赖。
    """
    origin = request.headers.get("origin")
    if not origin:
        raise HTTPException(status_code=403, detail="缺少 Origin 请求头")
    if origin not in settings.trusted_origins:
        raise HTTPException(status_code=403, detail="Origin 不在可信来源白名单")
    if x_yiban_request != "1":
        raise HTTPException(
            status_code=403, detail="缺少或无效的 X-Yiban-Request 请求头"
        )
