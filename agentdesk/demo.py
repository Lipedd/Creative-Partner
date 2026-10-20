"""Short-lived, isolated visitor workspaces for the public demo."""
from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException

from agentdesk.api.service import DeskService
from agentdesk.runtime import Runner


@dataclass(frozen=True)
class DemoContext:
    service: DeskService
    visitor_id: str
    ip_id: str


class DemoVisitorManager:
    def __init__(self, root: Path, runner_factory=Runner):
        self.root = root.resolve()
        self.visitors_root = self.root / "visitors"
        self.visitors_root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "visitors.sqlite"
        self.limit = max(1, int(os.environ.get("AGENTDESK_DEMO_MESSAGE_LIMIT", "10")))
        self.lifetime = max(60, int(os.environ.get("AGENTDESK_DEMO_SESSION_SECONDS", "3600")))
        self.runner_factory = runner_factory
        self.services: dict[str, DeskService] = {}
        self.lock = threading.RLock()
        self.closed = threading.Event()
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS visitors (
                  id TEXT PRIMARY KEY, ip_id TEXT NOT NULL, created REAL NOT NULL,
                  expires REAL NOT NULL, messages INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS ip_windows (
                  id TEXT PRIMARY KEY, created REAL NOT NULL, expires REAL NOT NULL,
                  messages INTEGER NOT NULL DEFAULT 0);
            """)
        self.worker = threading.Thread(target=self._cleanup_loop, daemon=True, name="demo-cleanup")
        self.worker.start()

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
        finally:
            db.close()

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()

    def context(self, token: str, address: str) -> DemoContext:
        visitor_id = self._hash("visitor:" + token)
        ip_id = self._hash("address:" + (address or "unknown"))
        now = time.time()
        expired = False
        with self.lock, self._db() as db:
            row = db.execute("SELECT * FROM visitors WHERE id=?", (visitor_id,)).fetchone()
            if row and float(row["expires"]) <= now:
                db.execute("DELETE FROM visitors WHERE id=?", (visitor_id,))
                expired = True
                row = None
            if row is None:
                db.execute(
                    "INSERT INTO visitors(id,ip_id,created,expires,messages) VALUES (?,?,?,?,0)",
                    (visitor_id, ip_id, now, now + self.lifetime),
                )
            ip_row = db.execute("SELECT * FROM ip_windows WHERE id=?", (ip_id,)).fetchone()
            if not ip_row or float(ip_row["expires"]) <= now:
                db.execute("INSERT OR REPLACE INTO ip_windows VALUES (?,?,?,0)", (ip_id, now, now + self.lifetime))
            db.commit()
        if expired:
            self._remove_files(visitor_id)
        with self.lock:
            service = self.services.get(visitor_id)
            if service is None:
                service = DeskService(self.visitors_root / visitor_id, self.runner_factory, demo=True)
                self.services[visitor_id] = service
        return DemoContext(service, visitor_id, ip_id)

    def status(self, visitor_id: str, ip_id: str) -> dict:
        now = time.time()
        with self.lock, self._db() as db:
            visitor = db.execute("SELECT expires,messages FROM visitors WHERE id=?", (visitor_id,)).fetchone()
            ip_window = db.execute("SELECT expires,messages FROM ip_windows WHERE id=?", (ip_id,)).fetchone()
        if not visitor:
            return {"enabled": True, "limit": self.limit, "remaining": 0, "expires_at": now}
        used = int(visitor["messages"])
        if ip_window and float(ip_window["expires"]) > now:
            used = max(used, int(ip_window["messages"]))
        return {
            "enabled": True,
            "limit": self.limit,
            "remaining": max(0, self.limit - used),
            "expires_at": float(visitor["expires"]),
        }

    def consume(self, visitor_id: str, ip_id: str) -> dict:
        now = time.time()
        with self.lock, self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            visitor = db.execute("SELECT expires,messages FROM visitors WHERE id=?", (visitor_id,)).fetchone()
            ip_window = db.execute("SELECT expires,messages FROM ip_windows WHERE id=?", (ip_id,)).fetchone()
            if not visitor or float(visitor["expires"]) <= now:
                raise HTTPException(410, "这次体验已经结束，请刷新页面重新开始")
            visitor_used = int(visitor["messages"])
            ip_used = int(ip_window["messages"]) if ip_window and float(ip_window["expires"]) > now else 0
            if max(visitor_used, ip_used) >= self.limit:
                raise HTTPException(429, "本小时的 10 次体验已经用完，可以下载作品或稍后再来")
            db.execute("UPDATE visitors SET messages=messages+1 WHERE id=?", (visitor_id,))
            db.execute("UPDATE ip_windows SET messages=messages+1 WHERE id=?", (ip_id,))
            db.commit()
        return self.status(visitor_id, ip_id)

    def cleanup(self):
        now = time.time()
        with self.lock, self._db() as db:
            expired = [row[0] for row in db.execute("SELECT id FROM visitors WHERE expires<=?", (now,))]
            db.execute("DELETE FROM visitors WHERE expires<=?", (now,))
            db.execute("DELETE FROM ip_windows WHERE expires<=?", (now,))
            db.commit()
        for visitor_id in expired:
            self._remove_files(visitor_id)

    def _remove_files(self, visitor_id: str):
        with self.lock:
            service = self.services.pop(visitor_id, None)
        if service:
            for run in list(service.runner.runs.values()):
                run.cancel.set()
        shutil.rmtree(self.visitors_root / visitor_id, ignore_errors=True)

    def _cleanup_loop(self):
        while not self.closed.wait(30):
            self.cleanup()

    def close(self):
        self.closed.set()
        self.cleanup()
