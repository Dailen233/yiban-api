"""译伴开发入口。"""

import uvicorn

from app import create_app
from config import settings

app = create_app()


def main() -> None:
    uvicorn.run(
        "start:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
