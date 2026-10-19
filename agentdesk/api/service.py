import os
import threading
import time
from pathlib import Path
from fastapi import HTTPException
from agentdesk.config import DEFAULT_CONFIG, PROVIDERS
from agentdesk.creative import creative_fingerprint, friendly_project_name, unique_project_path
from agentdesk.runtime import Runner
from agentdesk.project_runtime import launch_web_app, port_open
from agentdesk.secrets import protect_secret, unprotect_secret
from agentdesk.storage import Store

class DeskService:
    """Application service shared by REST and SSE; contains no UI dependencies."""
    def __init__(self, data: Path, runner_factory=Runner):
        data.mkdir(parents=True, exist_ok=True)
        self.workspace = data / "workspace"
        self.workspace.mkdir(exist_ok=True)
        configured = os.environ.get("AGENTDESK_PROJECTS_DIR", "").strip()
        if configured:
            self.projects_root = Path(configured).expanduser()
        elif data.name == ".agentdesk" and Path("D:/").is_dir():
            self.projects_root = Path("D:/AI作品")
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
                if session["config"] != DEFAULT_CONFIG:
                    self.store.update_session(item["id"], config=dict(DEFAULT_CONFIG))
        if self.store.setting("config") != DEFAULT_CONFIG:
            self.store.set_setting("config", dict(DEFAULT_CONFIG))

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

    def create_project(self, idea, placement="auto", workspace=None, title=None):
        idea = idea.strip()
        if not idea:
            raise HTTPException(400, "先告诉我你想做什么吧")
        name = friendly_project_name(idea)
        if placement == "manual":
            path = Path(workspace or "").expanduser()
            if not path.is_absolute() or not path.is_dir():
                raise HTTPException(400, "请选择一个已经存在的文件夹")
            path = path.resolve()
            try:
                test = path / ".agentdesk-write-check"
                test.write_text("ok", encoding="utf-8")
                test.unlink()
            except OSError:
                raise HTTPException(400, "这个位置不能保存作品，请换一个文件夹")
        else:
            path = unique_project_path(self.projects_root, idea)
            path.mkdir(parents=True)
        sid = self.store.new_session(path, self.config(), title or name)
        fingerprint = creative_fingerprint(sid, self.store.recent_project_signatures())
        self.store.add_project(sid, name, idea, fingerprint)
        return self.session(sid)

    def idle(self, sid):
        session = self.session(sid)
        if self.runner.active(sid) or session["pending"]:
            raise HTTPException(409, "请先结束运行或处理待确认操作")
        return session

    def api_key(self, client, provider):
        if provider not in PROVIDERS:
            raise HTTPException(400, "未知供应商")
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
            raise HTTPException(400, "请在模型设置中填写 API Key")
        return key

    def default_workspace(self):
        value = self.store.setting("workspace", str(self.workspace))
        return value if Path(value).is_dir() else str(self.workspace)

    def sessions(self, archived=False):
        result = []
        for item in self.store.sessions(archived):
            s = self.session(item["id"])
            s["running"] = self.runner.active(s["id"])
            result.append(s)
        return result

    def snapshot(self, sid):
        session = self.session(sid)
        run = self.runner.get(sid)
        state = run.snapshot() if run else {"status": "approval" if session["pending"] else "idle", "text": "", "error": ""}
        state.pop("events", None)
        return {"session": session, "run": state, "messages": self.store.messages(sid), "events": self.store.events(sid)}

    def config(self):
        return dict(DEFAULT_CONFIG)
