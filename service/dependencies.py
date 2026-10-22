"""服务依赖工厂（FastAPI 原生 Depends）

约定：
- Resource 统一注入 get_*_service
- Service 内部组合 Repository（不要在 Resource 注入 Repository）
- 本文件由脚手架在生成新表时追加 get_*_service /（可选）get_*_repository
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_async_session

# ---- 脚手架追加区：import Service / Repository，并注册 get_*_service ----
# 示例（生成 student 表后）：
# from .student_service import StudentService
# from repository.student_repository import StudentRepository
#
# def get_student_service(db: AsyncSession = Depends(get_async_session)) -> StudentService:
#     return StudentService(db)
#
# def get_student_repository(db: AsyncSession = Depends(get_async_session)) -> StudentRepository:
#     return StudentRepository(db)  # 仅供 Service/测试使用，Resource 勿注入
