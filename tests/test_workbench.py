import io
import sqlite3
import threading
import time
from pathlib import Path

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from PIL import Image

from agentdesk.config import DEFAULT_CONFIG
from agentdesk.runtime import Runner
from agentdesk.storage import Store
from agentdesk.tools import build_tools, calculate
from agentdesk.workspace import message_content, resolve_inside, save_upload

class ScriptedModel(BaseChatModel):
    """Offline model used to exercise the real LangChain graph and tools."""
    mode: str = "write"

    @property
    def _llm_type(self):
        return "test-scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if isinstance(messages[-1], ToolMessage):
            msg = AIMessage(content="执行完成：" + str(messages[-1].content))
        elif self.mode == "write":
            msg = AIMessage(content="准备写入文件。", tool_calls=[{"name": "write_file", "args": {"path": "result.txt", "content": "hello workspace"}, "id": "call_write", "type": "tool_call"}])
        elif self.mode == "calculate":
            msg = AIMessage(content="", tool_calls=[{"name": "calculator", "args": {"expression": "(19 + 23) * 2"}, "id": "call_calc", "type": "tool_call"}])
        elif self.mode == "index":
            msg = AIMessage(content="", tool_calls=[{"name": "write_file", "args": {"path": "index.html", "content": "<h1>可以玩了</h1>"}, "id": "call_index", "type": "tool_call"}])
        elif self.mode == "terminal":
            msg = AIMessage(content="准备完成。", tool_calls=[{"name": "run_terminal", "args": {"command": "Set-Content -Encoding UTF8 -Path result.txt -Value 'hello workspace'"}, "id": "call_terminal", "type": "tool_call"}])
        elif self.mode == "slow":
            time.sleep(0.4)
            msg = AIMessage(content="晚到的回答", tool_calls=[{"name": "save_memory", "args": {"content": "should not save"}, "id": "call_save", "type": "tool_call"}])
        else:
            count = sum(isinstance(m, HumanMessage) for m in messages)
            msg = AIMessage(content=f"历史用户消息数：{count}")
        return ChatResult(generations=[ChatGeneration(message=msg)])

def wait(run):
    deadline = time.monotonic() + 15
    while run.snapshot()["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.03)
    state = run.snapshot()
    assert state["status"] != "running", "background run timed out"
    assert state["status"] != "error", state["error"]
    return state

@pytest.fixture
def desk(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    store = Store(tmp_path / "desk.sqlite")
    sid = store.new_session(root, DEFAULT_CONFIG)
    return root, store, sid, Runner(store, tmp_path / "graph.sqlite")

def test_terminal_requires_approval_and_resumes_after_restart(desk, tmp_path):
    root, store, sid, runner = desk
    state = wait(runner.start(sid, "", text="run", model_override=ScriptedModel(mode="terminal")))
    assert state["status"] == "approval"
    assert not (root / "result.txt").exists()
    assert store.session(sid)["pending"][0]["action_requests"][0]["name"] == "run_terminal"
    restarted = Runner(Store(tmp_path / "desk.sqlite"), tmp_path / "graph.sqlite")
    state = wait(restarted.start(sid, "", decisions=[{"type": "approve"}], model_override=ScriptedModel(mode="terminal")))
    assert state["status"] == "done"
    assert (root / "result.txt").read_text(encoding="utf-8-sig").strip() == "hello workspace"
    assert store.session(sid)["pending"] is None
    assert any(e["kind"] == "tool_result" for e in store.events(sid))

def test_rejection_does_not_run_terminal(desk):
    root, store, sid, runner = desk
    wait(runner.start(sid, "", text="run", model_override=ScriptedModel(mode="terminal")))
    wait(runner.start(sid, "", decisions=[{"type": "reject", "message": "no"}], model_override=ScriptedModel(mode="terminal")))
    assert not (root / "result.txt").exists()
    assert store.session(sid)["pending"] is None

def test_project_files_write_without_interrupt(desk):
    root, store, sid, runner = desk
    state = wait(runner.start(sid, "", text="write", model_override=ScriptedModel()))
    assert state["status"] == "done"
    assert (root / "result.txt").read_text() == "hello workspace"
    assistant = [message for message in store.messages(sid) if message["role"] == "assistant"]
    assert len(assistant) == 1
    assert assistant[0]["kind"] == "final"
    assert "准备写入文件" not in assistant[0]["content"]

def test_conventional_entry_is_published_automatically(desk):
    root, store, sid, runner = desk
    store.add_project(sid, "测试作品", "做一个小游戏", {"signature": "test"})
    state = wait(runner.start(sid, "", text="开始", model_override=ScriptedModel(mode="index")))
    assert state["status"] == "done"
    assert store.project(sid)["preview_entry"] == "index.html"

def test_real_tool_loop(desk):
    _, store, sid, runner = desk
    wait(runner.start(sid, "", text="calculate", model_override=ScriptedModel(mode="calculate")))
    assert "84" in store.messages(sid)[-1]["content"]

def test_checkpoint_history_and_session_isolation(desk, tmp_path):
    root, store, sid, runner = desk
    model = ScriptedModel(mode="history")
    wait(runner.start(sid, "", text="one", model_override=model))
    restarted = Runner(store, tmp_path / "graph.sqlite")
    wait(restarted.start(sid, "", text="two", model_override=model))
    assert store.messages(sid)[-1]["content"] == "历史用户消息数：2"
    other = store.new_session(root, DEFAULT_CONFIG)
    wait(restarted.start(other, "", text="one", model_override=model))
    assert store.messages(other)[-1]["content"] == "历史用户消息数：1"

def test_cancel_prevents_tools_and_allows_next_turn(desk):
    root, store, sid, runner = desk
    run = runner.start(sid, "", text="slow", model_override=ScriptedModel(mode="slow"))
    progress = run.snapshot()["progress"]
    assert progress["stage"] == "正在理解你的想法"
    assert progress["step"] == 0
    run.cancel.set()
    assert wait(run)["status"] == "stopped"
    assert store.memories(root) == []
    wait(runner.start(sid, "", text="continue", model_override=ScriptedModel(mode="history")))
    assert store.messages(sid)[-1]["content"] == "历史用户消息数：2"

def test_workspace_escape_and_private_paths(desk, tmp_path):
    root, store, sid, runner = desk
    for path in ["../outside.txt", str(tmp_path / "secret.txt"), ".env", ".git/config", ".agentdesk/desk.sqlite"]:
        with pytest.raises(ValueError):
            resolve_inside(root, path, write=True)
    tools = {t.name: t for t in build_tools(root, store, sid, ["files"], threading.Event())}
    with pytest.raises(ValueError):
        tools["write_file"].invoke({"path": "../outside.txt", "content": "no"})

def test_memory_persisted_and_scoped(desk, tmp_path):
    root, store, _, _ = desk
    mid = store.remember(root, "默认中文")
    reopened = Store(store.path)
    assert reopened.memories(root, "中文")[0]["content"] == "默认中文"
    assert reopened.memories(tmp_path) == []
    reopened.forget(tmp_path, mid)
    assert reopened.memories(root)
    reopened.forget(root, mid)
    assert not reopened.memories(root)

def test_upload_text_and_vision_payload(desk):
    root, _, _, _ = desk
    text = save_upload(root, "../../报告.txt", "测试正文".encode())
    assert resolve_inside(root, text["path"]).is_relative_to(root)
    image = io.BytesIO()
    Image.new("RGB", (30, 30), "red").save(image, "PNG")
    photo = save_upload(root, "图.png", image.getvalue())
    assert photo["image"]
    payload = message_content("分析", [text, photo], str(root), True)
    assert any("测试正文" in b.get("text", "") for b in payload)
    assert any(b["type"] == "image" and b["base64"] for b in payload)
    no_vision = message_content("分析", [photo], str(root), False)
    assert not any(b["type"] == "image" for b in no_vision)

def test_calculator_does_not_execute_code():
    assert calculate("(2+3)*4") == 20
    for expression in ["__import__('os').getcwd()", "2 ** 999999", "[1,2]", "9**9**9"]:
        with pytest.raises(ValueError):
            calculate(expression)

def test_old_consecutive_assistant_notes_become_progress(tmp_path):
    path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, attachments TEXT NOT NULL, created TEXT NOT NULL)")
        rows = [
            (1, "s", "user", "开始", "[]", "1"),
            (2, "s", "assistant", "我先看看", "[]", "2"),
            (3, "s", "assistant", "已经做好了", "[]", "3"),
        ]
        db.executemany("INSERT INTO messages VALUES (?,?,?,?,?,?)", rows)
    store = Store(path)
    messages = store.messages("s")
    assert [item["kind"] for item in messages] == ["final", "progress", "final"]
