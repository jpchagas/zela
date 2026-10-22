from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import webhooks
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import install_error_handlers


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Zela API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )
    install_error_handlers(app)
    app.include_router(api_router)
    app.include_router(webhooks.router)
    if settings.env == "development":
        from app.api import dev

        app.include_router(dev.router)

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
