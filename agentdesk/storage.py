import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

def now():
    return datetime.now(timezone.utc).isoformat()

class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                  id TEXT PRIMARY KEY, title TEXT NOT NULL, workspace TEXT NOT NULL,
                  created TEXT NOT NULL, updated TEXT NOT NULL, archived INTEGER DEFAULT 0,
                  config TEXT NOT NULL, pending TEXT, graph_id TEXT NOT NULL,
                  project_proposal TEXT, project_proposal_name TEXT);
                CREATE TABLE IF NOT EXISTS messages (
                  id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, role TEXT NOT NULL,
                  content TEXT NOT NULL, attachments TEXT NOT NULL, created TEXT NOT NULL,
                  kind TEXT NOT NULL DEFAULT 'final',
                  project_link INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS memories (
                  id TEXT PRIMARY KEY, workspace TEXT NOT NULL, content TEXT NOT NULL,
                  created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                  id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, kind TEXT NOT NULL,
                  data TEXT NOT NULL, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS projects (
                  session_id TEXT PRIMARY KEY, name TEXT NOT NULL, idea TEXT NOT NULL,
                  fingerprint TEXT NOT NULL, preview_entry TEXT,
                  preview_kind TEXT NOT NULL DEFAULT 'static', run_command TEXT,
                  run_port INTEGER, run_pid INTEGER,
                  created TEXT NOT NULL, updated TEXT NOT NULL);
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(projects)")}
            for name, definition in {
                "preview_kind": "TEXT NOT NULL DEFAULT 'static'", "run_command": "TEXT",
                "run_port": "INTEGER", "run_pid": "INTEGER",
            }.items():
                if name not in columns:
                    db.execute(f"ALTER TABLE projects ADD COLUMN {name} {definition}")
            message_columns = {row[1] for row in db.execute("PRAGMA table_info(messages)")}
            if "kind" not in message_columns:
                db.execute("ALTER TABLE messages ADD COLUMN kind TEXT NOT NULL DEFAULT 'final'")
                # Older runs stored every assistant note before a tool as a chat
                # message. Within each consecutive assistant group only the final
                # item is a real reply; mark the rest as historical progress.
                rows = db.execute("SELECT id,session_id,role FROM messages ORDER BY session_id,id").fetchall()
                group = []
                current_session = None
                for row in rows:
                    if row[1] != current_session or row[2] != "assistant":
                        if len(group) > 1:
                            db.executemany("UPDATE messages SET kind='progress' WHERE id=?", [(mid,) for mid in group[:-1]])
                        group = []
                        current_session = row[1]
                    if row[2] == "assistant":
                        group.append(row[0])
                if len(group) > 1:
                    db.executemany("UPDATE messages SET kind='progress' WHERE id=?", [(mid,) for mid in group[:-1]])
            session_columns = {row[1] for row in db.execute("PRAGMA table_info(sessions)")}
            if "project_proposal" not in session_columns:
                db.execute("ALTER TABLE sessions ADD COLUMN project_proposal TEXT")
            if "project_proposal_name" not in session_columns:
                db.execute("ALTER TABLE sessions ADD COLUMN project_proposal_name TEXT")
            message_columns = {row[1] for row in db.execute("PRAGMA table_info(messages)")}
            if "project_link" not in message_columns:
                db.execute("ALTER TABLE messages ADD COLUMN project_link INTEGER NOT NULL DEFAULT 0")

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def setting(self, key, default=None):
        with self.db() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, json.dumps(value)))

    def delete_setting(self, key):
        with self.db() as db:
            db.execute("DELETE FROM settings WHERE key=?", (key,))

    def new_session(self, workspace, config, title="新的对话", sid=None):
        sid = sid or uuid.uuid4().hex
        with self.db() as db:
            db.execute(
                "INSERT INTO sessions(id,title,workspace,created,updated,archived,config,pending,graph_id,project_proposal,project_proposal_name) VALUES (?,?,?,?,?,0,?,NULL,?,NULL,NULL)",
                (sid, title, str(Path(workspace).resolve()), now(), now(), json.dumps(config), sid),
            )
        return sid

    def sessions(self, archived=False):
        with self.db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM sessions WHERE archived=? ORDER BY updated DESC", (int(archived),))]

    def session(self, sid):
        with self.db() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
            if row is None:
                raise KeyError(sid)
            r = dict(row)
        r["config"] = json.loads(r["config"])
        r["pending"] = json.loads(r["pending"]) if r["pending"] else None
        return r

    def add_project(self, sid, name, idea, fingerprint):
        stamp = now()
        with self.db() as db:
            db.execute(
                "INSERT OR REPLACE INTO projects(session_id,name,idea,fingerprint,preview_entry,preview_kind,run_command,run_port,run_pid,created,updated) VALUES (?,?,?,?,NULL,'static',NULL,NULL,NULL,?,?)",
                (sid, name, idea, json.dumps(fingerprint, ensure_ascii=False), stamp, stamp),
            )

    def attach_project(self, sid, workspace, name, idea, fingerprint, old_workspace):
        stamp = now()
        with self.db() as db:
            if db.execute("SELECT 1 FROM projects WHERE session_id=?", (sid,)).fetchone():
                raise ValueError("这个对话已经有作品了。")
            db.execute(
                "UPDATE sessions SET workspace=?,title=?,project_proposal=NULL,project_proposal_name=NULL,updated=? WHERE id=?",
                (str(Path(workspace).resolve()), name, stamp, sid),
            )
            db.execute(
                "INSERT INTO projects(session_id,name,idea,fingerprint,preview_entry,preview_kind,run_command,run_port,run_pid,created,updated) VALUES (?,?,?,?,NULL,'static',NULL,NULL,NULL,?,?)",
                (sid, name, idea, json.dumps(fingerprint, ensure_ascii=False), stamp, stamp),
            )
            db.execute(
                "UPDATE memories SET workspace=? WHERE workspace=?",
                (str(Path(workspace).resolve()), str(Path(old_workspace).resolve())),
            )

    def project(self, sid):
        with self.db() as db:
            row = db.execute("SELECT * FROM projects WHERE session_id=?", (sid,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["fingerprint"] = json.loads(result["fingerprint"])
        return result

    def recent_project_signatures(self, limit=24):
        with self.db() as db:
            rows = db.execute("SELECT fingerprint FROM projects ORDER BY updated DESC LIMIT ?", (limit,)).fetchall()
        signatures = set()
        for row in rows:
            try:
                value = json.loads(row[0])
                if value.get("signature"):
                    signatures.add(value["signature"])
            except (TypeError, ValueError):
                continue
        return signatures

    def publish_project(self, sid, entry):
        with self.db() as db:
            result = db.execute(
                "UPDATE projects SET preview_entry=?,preview_kind='static',run_command=NULL,run_port=NULL,run_pid=NULL,updated=? WHERE session_id=?",
                (entry, now(), sid),
            )
            if not result.rowcount:
                raise ValueError("这个作品还没有准备好。")

    def publish_web_app(self, sid, command, port, pid):
        with self.db() as db:
            result = db.execute(
                "UPDATE projects SET preview_entry='web-app',preview_kind='service',run_command=?,run_port=?,run_pid=?,updated=? WHERE session_id=?",
                (command, port, pid, now(), sid),
            )
            if not result.rowcount:
                raise ValueError("这个作品还没有准备好。")

    def update_project_process(self, sid, pid):
        with self.db() as db:
            db.execute("UPDATE projects SET run_pid=?,updated=? WHERE session_id=?", (pid, now(), sid))

    def update_session(self, sid, **values):
        allowed = {"title", "archived", "config", "pending", "graph_id", "workspace", "project_proposal", "project_proposal_name"}
        if not values or not set(values) <= allowed:
            raise ValueError("Invalid session fields")
        for k in ("config", "pending"):
            if k in values:
                values[k] = json.dumps(values[k], ensure_ascii=False) if values[k] is not None else None
        values["updated"] = now()
        with self.db() as db:
            db.execute("UPDATE sessions SET " + ",".join(f"{k}=?" for k in values) + " WHERE id=?", [*values.values(), sid])

    def add_message(self, sid, role, content, attachments=None, kind="final", project_link=False):
        with self.db() as db:
            cursor = db.execute(
                "INSERT INTO messages(session_id,role,content,attachments,created,kind,project_link) VALUES (?,?,?,?,?,?,?)",
                (sid, role, content, json.dumps(attachments or [], ensure_ascii=False), now(), kind, int(project_link)),
            )
            db.execute("UPDATE sessions SET updated=? WHERE id=?", (now(), sid))
            return cursor.lastrowid

    def messages(self, sid):
        with self.db() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM messages WHERE session_id=? ORDER BY id", (sid,))]
        for r in rows:
            r["attachments"] = json.loads(r["attachments"])
            r["project_link"] = bool(r.get("project_link", 0))
        return rows

    def set_message_project_link(self, message_id, visible=True):
        if message_id is None:
            return
        with self.db() as db:
            db.execute("UPDATE messages SET project_link=? WHERE id=?", (int(visible), message_id))

    def event(self, sid, kind, data):
        with self.db() as db:
            db.execute("INSERT INTO events(session_id,kind,data,created) VALUES (?,?,?,?)", (sid, kind, json.dumps(data, ensure_ascii=False, default=str), now()))

    def events(self, sid):
        with self.db() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM events WHERE session_id=? ORDER BY id DESC LIMIT 100", (sid,))]
        for r in rows:
            r["data"] = json.loads(r["data"])
        return rows

    def memories(self, workspace, query=""):
        with self.db() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM memories WHERE workspace=? ORDER BY created DESC", (str(Path(workspace).resolve()),))]
        return [r for r in rows if query.casefold() in r["content"].casefold()]

    def remember(self, workspace, content):
        content = content.strip()
        if not content or len(content) > 4000:
            raise ValueError("记忆必须为 1–4000 个字符。")
        mid = uuid.uuid4().hex
        with self.db() as db:
            db.execute("INSERT INTO memories VALUES (?,?,?,?)", (mid, str(Path(workspace).resolve()), content, now()))
        return mid

    def forget(self, workspace, mid):
        with self.db() as db:
            db.execute("DELETE FROM memories WHERE workspace=? AND id=?", (str(Path(workspace).resolve()), mid))
