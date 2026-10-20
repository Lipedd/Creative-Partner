import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from fastapi import HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from agentdesk.config import DEFAULT_CONFIG, DEMO_CONFIG, PROVIDERS, create_model
from agentdesk.creative import create_unique_project_path, creative_fingerprint, friendly_project_name, sanitize_project_name
from agentdesk.runtime import Runner, content_text
from agentdesk.project_runtime import launch_web_app, port_open
from agentdesk.secrets import protect_secret, unprotect_secret
from agentdesk.storage import Store

class DeskService:
    """Application service shared by REST and SSE; contains no UI dependencies."""
    def __init__(self, data: Path, runner_factory=Runner, demo: bool = False):
        self.demo = demo
        data.mkdir(parents=True, exist_ok=True)
        self.workspace = data / "workspace"
        self.workspace.mkdir(exist_ok=True)
        self.chats_root = data / "chats"
        self.chats_root.mkdir(exist_ok=True)
        configured = os.environ.get("AGENTDESK_PROJECTS_DIR", "").strip()
        if configured and not demo:
            self.projects_root = Path(configured).expanduser()
        elif not demo and data.name == ".agentdesk" and Path("D:/").is_dir():
            self.projects_root = Path("D:/AI作品-创想伙伴")
        else:
            self.projects_root = data / "projects"
        self.projects_root.mkdir(parents=True, exist_ok=True)
        self.store = Store(data / "desk.sqlite")
        self.runner = runner_factory(self.store, data / "checkpoints.sqlite")
        self.keys: dict[str, dict[str, str]] = {}
        self.lock = threading.RLock()
        self.runtime_attempts: dict[str, float] = {}
        self._apply_product_defaults()

    def _apply_product_defaults(self):
        """Move existing sessions to the current one-model product configuration."""
        for archived in (False, True):
            for item in self.store.sessions(archived):
                session = self.store.session(item["id"])
                if session["config"] != self.config():
                    self.store.update_session(item["id"], config=self.config())
        if self.store.setting("config") != self.config():
            self.store.set_setting("config", self.config())

    def session(self, sid):
        try:
            value = self.store.session(sid)
            project = self.store.project(sid)
            if project:
                entry = project.get("preview_entry")
                project["preview_ready"] = bool(entry)
                if entry and project.get("preview_kind") == "service":
                    port = int(project.get("run_port") or 0)
                    project["preview_url"] = f"http://127.0.0.1:{port}/" if port else ""
                    if port and not port_open(port) and time.monotonic() - self.runtime_attempts.get(sid, 0) > 5:
                        self.runtime_attempts[sid] = time.monotonic()
                        try:
                            _, pid = launch_web_app(value["workspace"], project.get("run_command") or "", port)
                            self.store.update_project_process(sid, pid)
                        except (OSError, RuntimeError, ValueError):
                            pass
                else:
                    project["preview_url"] = f"/api/sessions/{sid}/project/" if entry else ""
            value["project"] = project
            return value
        except KeyError:
            raise HTTPException(404, "会话不存在")

    def public_session(self, value):
        if not self.demo:
            return value
        result = dict(value)
        result["workspace"] = "临时工作区"
        return result

    def create_project(self, idea, placement="auto", workspace=None, title=None, name=None):
        self._ensure_session_capacity()
        idea = idea.strip()
        if not idea:
            raise HTTPException(400, "先告诉我你想做什么吧")
        name = sanitize_project_name(name or "", friendly_project_name(idea))
        path = self._project_path(name, placement, workspace)
        sid = self.store.new_session(path, self.config(), title or name)
        fingerprint = creative_fingerprint(sid, self.store.recent_project_signatures())
        self.store.add_project(sid, name, idea, fingerprint)
        return self.public_session(self.session(sid))

    def create_chat(self, title=None):
        self._ensure_session_capacity()
        sid = uuid.uuid4().hex
        path = self.chats_root / sid
        path.mkdir(parents=True)
        self.store.new_session(path, self.config(), title or "新的对话", sid=sid)
        return self.public_session(self.session(sid))

    def attach_project(self, sid, idea, placement="auto", workspace=None, name=None):
        session = self.idle(sid)
        if session.get("project"):
            raise HTTPException(409, "这个对话已经有作品了")
        idea = idea.strip()
        if not idea:
            raise HTTPException(400, "先告诉我你想做什么吧")
        name = sanitize_project_name(name or session.get("project_proposal_name") or "", friendly_project_name(idea))
        path = self._project_path(name, placement, workspace)
        old_workspace = Path(session["workspace"]).resolve()
        uploads = old_workspace / "uploads"
        if uploads.is_dir() and path.resolve() != old_workspace:
            shutil.copytree(uploads, path / "uploads", dirs_exist_ok=True)
        fingerprint = creative_fingerprint(sid, self.store.recent_project_signatures())
        self.store.attach_project(sid, path, name, idea, fingerprint, old_workspace)
        return self.public_session(self.session(sid))

    def dismiss_project_proposal(self, sid):
        session = self.idle(sid)
        if session.get("project"):
            raise HTTPException(409, "作品已经开始制作了")
        self.store.update_session(sid, project_proposal=None, project_proposal_name=None)
        return self.public_session(self.session(sid))

    def suggest_project_name(self, idea, client):
        idea = idea.strip()
        fallback = friendly_project_name(idea)
        if self.demo:
            return fallback
        if not idea:
            return fallback
        config = self.config()
        key = self.api_key(client, config["provider"])
        if not key and PROVIDERS[config["provider"]][0] != "ollama":
            return fallback
        try:
            naming_config = dict(config)
            naming_config["max_tokens"] = min(256, int(config.get("max_tokens", 4096)))
            response = create_model(naming_config, key).invoke([
                SystemMessage(content=(
                    "你只负责给儿童作品取一个简短中文名称。提炼核心对象、作品类型或最有辨识度的功能；"
                    "名称控制在4到12个汉字左右，不要出现‘我要做’‘帮我做’等请求语，不要标点、引号、解释或换行，只输出名称。"
                )),
                HumanMessage(content=idea),
            ])
            return sanitize_project_name(content_text(response.content), fallback)
        except Exception:
            return fallback

    def _project_path(self, name, placement, workspace):
        if self.demo and placement == "manual":
            raise HTTPException(403, "体验版会自动准备临时工作区")
        if placement == "manual":
            parent = Path(workspace or "").expanduser()
            if not parent.is_absolute() or not parent.is_dir():
                raise HTTPException(400, "请选择一个已经存在的文件夹")
            parent = parent.resolve()
            try:
                return create_unique_project_path(parent, name)
            except OSError:
                raise HTTPException(400, "这个位置不能保存作品，请换一个文件夹")
        try:
            return create_unique_project_path(self.projects_root, name)
        except OSError:
            raise HTTPException(400, "默认位置不能保存作品，请选择其他位置")

    def _ensure_session_capacity(self):
        if self.demo and len(self.store.sessions(False)) + len(self.store.sessions(True)) >= 6:
            raise HTTPException(429, "体验版最多保留 6 个对话，请先使用已有对话")

    def idle(self, sid):
        session = self.session(sid)
        if self.runner.active(sid) or session["pending"]:
            raise HTTPException(409, "请先结束运行或处理待确认操作")
        return session

    def api_key(self, client, provider):
        if provider not in PROVIDERS:
            raise HTTPException(400, "未知供应商")
        if self.demo:
            return os.environ.get(PROVIDERS[provider][3], "")
        with self.lock:
            memory = self.keys.get(client, {}).get(provider, "")
        if memory:
            return memory
        saved = self.store.setting("credential_" + provider, "")
        if saved:
            try:
                return unprotect_secret(saved)
            except (OSError, RuntimeError, ValueError):
                self.store.delete_setting("credential_" + provider)
        return os.environ.get(PROVIDERS[provider][3], "")

    def set_api_key(self, client, provider, api_key, persistent=True):
        if self.demo:
            raise HTTPException(403, "体验版已经准备好模型，无需填写密钥")
        value = api_key.strip()
        with self.lock:
            if value:
                self.keys.setdefault(client, {})[provider] = value
            else:
                self.keys.get(client, {}).pop(provider, None)
            if persistent:
                if value:
                    self.store.set_setting("credential_" + provider, protect_secret(value))
                else:
                    self.store.delete_setting("credential_" + provider)

    def credential_status(self, client):
        return {name: bool(self.api_key(client, name)) or entry[0] == "ollama" for name, entry in PROVIDERS.items()}

    def require_key(self, client, provider):
        key = self.api_key(client, provider)
        if not key and PROVIDERS[provider][0] != "ollama":
            message = "体验服务暂时没有准备好，请稍后再来" if self.demo else "请在模型设置中填写 API Key"
            raise HTTPException(503 if self.demo else 400, message)
        return key

    def default_workspace(self):
        if self.demo:
            return "临时工作区"
        value = self.store.setting("workspace", str(self.workspace))
        return value if Path(value).is_dir() else str(self.workspace)

    def sessions(self, archived=False):
        result = []
        for item in self.store.sessions(archived):
            s = self.session(item["id"])
            s["running"] = self.runner.active(s["id"])
            result.append(self.public_session(s))
        return result

    def snapshot(self, sid):
        session = self.session(sid)
        run = self.runner.get(sid)
        state = run.snapshot() if run else {
            "status": "approval" if session["pending"] else "idle", "text": "", "error": "",
            "mode": "project" if session.get("project") else "chat",
        }
        state.pop("events", None)
        return {"session": self.public_session(session), "run": state, "messages": self.store.messages(sid), "events": self.store.events(sid)}

    def config(self):
        source = DEMO_CONFIG if self.demo else DEFAULT_CONFIG
        return {**source, "tools": list(source["tools"])}
