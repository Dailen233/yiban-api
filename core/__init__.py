"""核心基础设施包

分层约定：
- database / cache / queue：运行时基础设施（lifespan 初始化）
- token / permissions：会话 JWT（固定 HS256）与鉴权依赖；密码哈希在 utils.security
- 服务工厂：``service.dependencies``（勿再放 core）

推荐显式导入，例如::

    from core.database import get_async_session
    from core.permissions import get_current_user, require_admin
"""

from .database import (
    Base,
    metadata,
    async_engine,
    AsyncSessionLocal,
    pool_stats,
    create_database_pool,
    close_database_pool,
    get_async_session,
    check_database_health,
    get_pool_status,
)
from .cache import (
    MemoryCache,
    cache_manager,
    init_cache,
    close_cache,
)
from .queue import (
    MemoryQueue,
    task_queue,
    start_queue,
    stop_queue,
)
from .permissions import (
    get_current_user,
    get_current_sso_user,
    get_current_active_user,
    require_admin,
    require_teacher,
    require_student,
    PermissionChecker,
)

__all__ = [
    "Base",
    "metadata",
    "async_engine",
    "AsyncSessionLocal",
    "pool_stats",
    "create_database_pool",
    "close_database_pool",
    "get_async_session",
    "check_database_health",
    "get_pool_status",
    "MemoryCache",
    "cache_manager",
    "init_cache",
    "close_cache",
    "MemoryQueue",
    "task_queue",
    "start_queue",
    "stop_queue",
    "get_current_user",
    "get_current_sso_user",
    "get_current_active_user",
    "require_admin",
    "require_teacher",
    "require_student",
    "PermissionChecker",
]
