import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import health
from app.config import REPO_ROOT, get_settings
from app.db.session import engine

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


class SPAStaticFiles(StaticFiles):
    """Serves the built frontend, falling back to index.html for client-side routes.

    Unknown /api/... paths stay a 404, so a mistyped endpoint doesn't return HTML.
    """

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            # On Windows the path arrives with backslashes ("api\\watchs").
            first_segment = path.replace("\\", "/").split("/")[0]
            if exc.status_code != 404 or first_segment == "api":
                raise
            return await super().get_response("index.html", scope)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # The monitor will be started here when MONITOR_ENABLED is true (phase 2).
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    app = FastAPI(title="SiteMonitor", lifespan=lifespan)
    app.include_router(health.router, prefix="/api")

    # Mounted last so /api routes take priority. Run `npm run build` in frontend/ first.
    if FRONTEND_DIST.is_dir():
        app.mount("/", SPAStaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")

    return app


app = create_app()
