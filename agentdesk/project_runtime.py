"""Small local web-app launcher used by published Python projects."""
from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def launch_web_app(workspace: str | Path, command: str, port: int = 0) -> tuple[int, int]:
    root = Path(workspace).resolve()
    port = port or free_port()
    if not 1024 <= port <= 65535:
        raise ValueError("端口必须在 1024–65535 之间。")
    if port_open(port):
        return port, 0
    final_command = command.replace("{port}", str(port))
    env = {k: v for k, v in os.environ.items() if not any(s in k.upper() for s in ("API_KEY", "SECRET", "TOKEN", "PASSWORD"))}
    env["PORT"] = str(port)
    log_path = root / ".agentdesk-web.log"
    log = log_path.open("ab")
    args = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", final_command] if os.name == "nt" else ["/bin/sh", "-c", final_command]
    try:
        process = subprocess.Popen(
            args, cwd=root, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env,
            creationflags=(subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0,
            start_new_session=os.name != "nt",
        )
    finally:
        log.close()
    for _ in range(40):
        if port_open(port):
            return port, process.pid
        if process.poll() is not None:
            raise RuntimeError("网页服务没有成功启动，请查看 .agentdesk-web.log。")
        time.sleep(0.1)
    process.terminate()
    raise RuntimeError("网页服务启动超时，请确认它读取 PORT 并监听 127.0.0.1。")
