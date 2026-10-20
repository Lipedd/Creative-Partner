import secrets
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from agentdesk.config import DATA, ROOT
from agentdesk.runtime import Runner
from .routes import router
from .service import DeskService
from agentdesk.demo import DemoVisitorManager

def create_app(data: Path | None = None, runner_factory=Runner, mode: str | None = None):
    mode = (mode or os.environ.get("AGENTDESK_MODE", "local")).strip().lower()
    demo = mode == "demo"
    root = data or DATA
    manager = DemoVisitorManager(root, runner_factory) if demo else None

    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            if manager:
                manager.close()

    app = FastAPI(title="Agent Desk API", version="2.0.0", docs_url="/api/docs",
                  openapi_url="/api/openapi.json", lifespan=lifespan)
    app.state.demo_manager = manager
    app.state.desk = None if demo else DeskService(root, runner_factory)
    allowed_hosts = ["*"] if demo else ["127.0.0.1", "localhost", "[::1]", "testserver"]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    @app.middleware("http")
    async def local_client(request: Request, call_next):
        origin = request.headers.get("origin")
        allowed = {request.headers.get("host"), "127.0.0.1:5173", "localhost:5173"}
        if origin and urlparse(origin).netloc not in allowed:
            return JSONResponse({"detail": "只允许工作台页面访问本机接口"}, status_code=403)
        client = request.cookies.get("agentdesk_client")
        fresh = not client or len(client) != 43
        request.state.client = secrets.token_urlsafe(32) if fresh else client
        if demo:
            context = app.state.demo_manager.context(request.state.client, request.client.host if request.client else "unknown")
            request.state.desk = context.service
            request.state.demo_context = context
        else:
            request.state.desk = app.state.desk
            request.state.demo_context = None
        response = await call_next(request)
        if fresh:
            response.set_cookie("agentdesk_client", request.state.client, httponly=True, samesite="strict",
                                max_age=app.state.demo_manager.lifetime if demo else None)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(OSError)
    async def filesystem_error(request, exc):
        return JSONResponse({"detail": "无法访问该文件或目录，请检查路径和访问权限"}, status_code=400)

    app.include_router(router)
    dist = ROOT / "frontend" / "dist"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "接口不存在")
        if not (dist / "index.html").is_file():
            return JSONResponse({"detail": "请先在 frontend 目录运行 npm install 和 npm run build"}, status_code=503)
        requested = (dist / path).resolve()
        if requested.is_file() and (requested.parent == dist.resolve() or dist.resolve() in requested.parents):
            return FileResponse(requested, headers={"Cache-Control": "public, max-age=3600"})
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})
    return app
