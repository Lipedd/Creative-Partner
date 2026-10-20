import asyncio
import json
import os
import string
from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from starlette.concurrency import run_in_threadpool
from agentdesk.config import PROVIDERS, create_model, list_models
from agentdesk.runtime import content_text
from agentdesk.workspace import MAX_FILE, extract_text, image_data, list_directory, resolve_inside, save_upload
from .schemas import Credentials, EditSession, MemoryInput, MessageInput, ModelConfig, NewProject, NewSession, ProjectNameInput, ResumeInput

router = APIRouter(prefix="/api")

def desk(request: Request):
    return request.app.state.desk

@router.get("/health")
def health():
    return {"status": "ok", "frontend": "vue", "api_version": 1}

@router.get("/bootstrap")
def bootstrap(request: Request, service=Depends(desk)):
    return {"providers": [{"name": name, "kind": v[0], "base_url": v[1], "model": v[2]} for name, v in PROVIDERS.items()],
            "config": service.config(), "workspace": service.default_workspace(),
            "credentials": service.credential_status(request.state.client), "sessions": service.sessions()}

@router.put("/credentials")
def credentials(body: Credentials, request: Request, service=Depends(desk)):
    if body.provider not in PROVIDERS:
        raise HTTPException(400, "未知供应商")
    service.set_api_key(request.state.client, body.provider, body.api_key, body.persistent)
    return service.credential_status(request.state.client)

@router.post("/models/list")
def models(body: ModelConfig, request: Request, service=Depends(desk)):
    key = service.require_key(request.state.client, body.provider)
    try:
        return {"models": list_models(body.model_dump(), key)}
    except Exception:
        raise HTTPException(502, "无法获取模型列表，请检查 API 地址、密钥或网络；也可手动填写模型名")

@router.post("/models/test")
def model_test(body: ModelConfig, request: Request, service=Depends(desk)):
    key = service.require_key(request.state.client, body.provider)
    try:
        result = create_model(body.model_dump(), key).invoke("Reply with OK only.")
        return {"message": content_text(result.content)[:300]}
    except Exception:
        raise HTTPException(502, "模型连接失败，请检查模型名称、密钥、API 地址和网络")

@router.get("/sessions")
def sessions(archived: bool = False, service=Depends(desk)):
    return service.sessions(archived)

@router.post("/sessions", status_code=201)
def new_session(body: NewSession, service=Depends(desk)):
    if body.kind == "chat":
        return service.create_chat(body.title)
    # Keep old local clients working; the Vue flow always supplies the child's idea.
    if not body.idea.strip() and body.workspace:
        return service.create_project("我的新作品", "manual", body.workspace, body.title, body.name)
    return service.create_project(body.idea, body.placement, body.workspace, body.title, body.name)

@router.post("/project-name")
def project_name(body: ProjectNameInput, request: Request, service=Depends(desk)):
    return {"name": service.suggest_project_name(body.idea, request.state.client)}

@router.post("/sessions/{sid}/project", status_code=201)
def start_project(sid: str, body: NewProject, service=Depends(desk)):
    with service.lock:
        return service.attach_project(sid, body.idea, body.placement, body.workspace, body.name)

@router.delete("/sessions/{sid}/project-proposal")
def dismiss_project_proposal(sid: str, service=Depends(desk)):
    with service.lock:
        return service.dismiss_project_proposal(sid)

@router.get("/sessions/{sid}")
def snapshot(sid: str, service=Depends(desk)):
    return service.snapshot(sid)

@router.patch("/sessions/{sid}")
def edit_session(sid: str, body: EditSession, service=Depends(desk)):
    with service.lock:
        service.session(sid)
        if body.archived is not None:
            service.idle(sid)
        values = body.model_dump(exclude_none=True)
        if values:
            service.store.update_session(sid, **values)
    return service.session(sid)

@router.put("/sessions/{sid}/config")
def update_config(sid: str, body: ModelConfig, service=Depends(desk)):
    with service.lock:
        service.idle(sid)
        config = body.model_dump()
        service.store.update_session(sid, config=config)
        service.store.set_setting("config", config)
    return service.session(sid)

@router.post("/sessions/{sid}/messages", status_code=202)
def send(sid: str, body: MessageInput, request: Request, service=Depends(desk)):
    with service.lock:
        session = service.idle(sid)
        if not body.text.strip() and not body.attachments:
            raise HTTPException(400, "请输入消息或添加附件")
        key = service.require_key(request.state.client, session["config"]["provider"])
        uploads = service.store.setting("uploads_" + sid, {})
        attachments = []
        for path in body.attachments:
            if path not in uploads:
                raise HTTPException(400, "附件不属于当前会话，请重新上传")
            actual = resolve_inside(session["workspace"], path)
            if not actual.is_file():
                raise HTTPException(400, "附件已移动或不存在")
            attachments.append(uploads[path])
        service.runner.start(sid, key, text=body.text, attachments=attachments)
    return {"status": "started"}

@router.post("/sessions/{sid}/stop")
def stop(sid: str, service=Depends(desk)):
    service.session(sid)
    run = service.runner.get(sid)
    if run:
        run.cancel.set()
    return {"status": "stopping"}

@router.post("/sessions/{sid}/resume", status_code=202)
def resume(sid: str, body: ResumeInput, request: Request, service=Depends(desk)):
    with service.lock:
        s = service.session(sid)
        if service.runner.active(sid) or not s["pending"]:
            raise HTTPException(409, "当前没有可恢复的待确认操作")
        actions = [a for block in s["pending"] for a in block.get("action_requests", [])]
        if len(body.decisions) != len(actions):
            raise HTTPException(400, "需要为每一项操作提供一个决定")
        key = service.require_key(request.state.client, s["config"]["provider"])
        service.runner.start(sid, key, decisions=[d.model_dump() for d in body.decisions])
    return {"status": "started"}

@router.get("/sessions/{sid}/stream")
async def stream(sid: str, request: Request, service=Depends(desk)):
    service.session(sid)
    async def events():
        previous = None
        ticks = 0
        while not await request.is_disconnected():
            value = await run_in_threadpool(service.snapshot, sid)
            data = json.dumps(value, ensure_ascii=False)
            if data != previous:
                yield f"event: state\ndata: {data}\n\n"
                previous = data
            elif ticks % 25 == 0:
                yield ": keepalive\n\n"
            ticks += 1
            await asyncio.sleep(0.4)
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@router.get("/sessions/{sid}/export")
def export(sid: str, format: str = "json", service=Depends(desk)):
    state = service.snapshot(sid)
    if format == "md":
        body = f"# {state['session']['title']}\n\n" + "\n\n".join(f"## {m['role']}\n\n{m['content']}\n" + "\n".join(f"附件：{a['name']} ({a['path']})" for a in m["attachments"]) for m in state["messages"])
        return Response(body, media_type="text/markdown", headers={"Content-Disposition": 'attachment; filename="conversation.md"'})
    return Response(json.dumps(state, ensure_ascii=False, indent=2), media_type="application/json", headers={"Content-Disposition": 'attachment; filename="conversation.json"'})

@router.get("/directories")
def directories(path: str = "", service=Depends(desk)):
    p = Path(path or service.default_workspace()).expanduser()
    if not p.is_absolute() or not p.is_dir():
        raise HTTPException(400, "文件夹不存在")
    p = p.resolve()
    children = []
    for item in sorted(p.iterdir(), key=lambda i: i.name.casefold()):
        if item.is_dir() and not item.name.startswith("."):
            children.append({"name": item.name, "path": str(item.resolve())})
        if len(children) >= 250:
            break
    roots = [f"{letter}:/" for letter in string.ascii_uppercase if Path(f"{letter}:/").is_dir()] if os.name == "nt" else ["/"]
    return {"path": str(p), "parent": str(p.parent), "directories": children, "roots": roots}

@router.get("/sessions/{sid}/files")
def files(sid: str, path: str = ".", service=Depends(desk)):
    return list_directory(service.session(sid)["workspace"], path)

@router.post("/sessions/{sid}/uploads", status_code=201)
async def upload(sid: str, files: list[UploadFile] = File(...), service=Depends(desk)):
    session = service.session(sid)
    if len(files) > 8:
        raise HTTPException(400, "每次最多上传 8 个附件")
    payloads = []
    for file in files:
        raw = await file.read(MAX_FILE + 1)
        await file.close()
        if len(raw) > MAX_FILE:
            raise HTTPException(413, "单个文件不能超过 20 MB")
        payloads.append((file.filename or "file", raw))
    def persist():
        with service.lock:
            known = service.store.setting("uploads_" + sid, {})
            result = [save_upload(session["workspace"], name, raw) for name, raw in payloads]
            known.update({item["path"]: item for item in result})
            service.store.set_setting("uploads_" + sid, known)
            return result
    return await run_in_threadpool(persist)

@router.get("/sessions/{sid}/preview")
def preview(sid: str, path: str, service=Depends(desk)):
    p = resolve_inside(service.session(sid)["workspace"], path)
    if not p.is_file():
        raise HTTPException(404, "文件不存在")
    if p.stat().st_size > MAX_FILE:
        raise HTTPException(413, "预览上限为 20 MB")
    if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}:
        return {"image": image_data(p), "text": ""}
    return {"image": "", "text": extract_text(p, 20000)}

@router.get("/sessions/{sid}/project/{asset_path:path}")
def project_preview(sid: str, asset_path: str = "", service=Depends(desk)):
    session = service.session(sid)
    project = session.get("project")
    if not project or not project.get("preview_entry"):
        raise HTTPException(404, "作品还没有准备好")
    root = Path(session["workspace"]).resolve()
    entry = resolve_inside(root, project["preview_entry"])
    base = entry.parent
    candidate = entry if not asset_path else resolve_inside(base, asset_path)
    if not candidate.is_file():
        raise HTTPException(404, "作品里的这个内容不存在")
    return FileResponse(candidate, headers={
        "Cache-Control": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'self' https: data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval' https: blob:; style-src 'self' 'unsafe-inline' https:; connect-src 'self' https: wss:; img-src 'self' https: data: blob:; media-src 'self' https: data: blob:; worker-src 'self' blob:; frame-ancestors 'self'",
    })

@router.get("/sessions/{sid}/download")
def download(sid: str, path: str, service=Depends(desk)):
    p = resolve_inside(service.session(sid)["workspace"], path)
    if not p.is_file():
        raise HTTPException(404, "文件不存在")
    return FileResponse(p, media_type="application/octet-stream", filename=p.name, headers={"X-Content-Type-Options": "nosniff"})

@router.get("/sessions/{sid}/memories")
def memories(sid: str, service=Depends(desk)):
    return service.store.memories(service.session(sid)["workspace"])

@router.post("/sessions/{sid}/memories", status_code=201)
def remember(sid: str, body: MemoryInput, service=Depends(desk)):
    return {"id": service.store.remember(service.session(sid)["workspace"], body.content)}

@router.delete("/sessions/{sid}/memories/{mid}")
def forget(sid: str, mid: str, service=Depends(desk)):
    service.store.forget(service.session(sid)["workspace"], mid)
    return {"status": "deleted"}
