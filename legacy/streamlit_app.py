"""Archived prototype. The active entry point is app.py (FastAPI + Vue)."""
import json
import os
from pathlib import Path

import streamlit as st

from agentdesk.config import DATA, DEFAULT_CONFIG, DEFAULT_WORKSPACE, PROVIDERS, create_model, list_models
from agentdesk.runtime import Runner
from agentdesk.storage import Store
from agentdesk.workspace import extract_text, list_directory, resolve_inside, save_upload

st.set_page_config(page_title="Agent Desk · 工作台", page_icon="◈", layout="wide", initial_sidebar_state="expanded")

@st.cache_resource
def services():
    storage = Store(DATA / "desk.sqlite")
    return storage, Runner(storage)

store, runner = services()

st.markdown("""<style>
:root {--desk-green:#226a56;}
.stApp {background:#f8f9f6;}
.block-container {padding-top:2rem;padding-bottom:1.4rem;max-width:1680px;}
[data-testid="stSidebar"] {background:#edf0e9;border-right:1px solid #dce2d8;}
[data-testid="stSidebar"] .block-container {padding-top:1.8rem;}
h1,h2,h3 {letter-spacing:-.035em;font-weight:600!important;}
.brand {display:flex;align-items:center;gap:11px;font-size:22px;font-weight:650;letter-spacing:-.5px;margin-bottom:4px;}
.brand-mark {background:#226a56;color:#fff;border-radius:11px;width:35px;height:35px;display:grid;place-items:center;font-size:26px;}
.eyebrow {font-size:11px;letter-spacing:2px;color:#7b897f;margin:24px 0 9px;}
.subtle {font-size:12px;color:#7c897f;line-height:1.7;}
.hero {padding:42px 12px 28px;}
.hero-symbol {color:#226a56;font-size:46px;line-height:1.2;}
.hero h1 {font-size:36px;line-height:1.35;margin:18px 0 8px;}
.hero p {font-size:15px;color:#7b867d;line-height:1.8;}
.stButton>button,.stDownloadButton>button {border-radius:9px;}
[data-testid="stChatMessage"] {background:transparent;border-bottom:1px solid #e8ece4;padding:18px 8px;}
[data-testid="stChatInput"] {border-radius:16px;border:1px solid #d6ded2;background:#fff;}
[data-testid="stExpander"] {background:#fff;border-radius:10px;}
[data-testid="stMetric"] {background:#eff3ed;border-radius:10px;padding:12px;}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {color:#657368!important;}
div[data-testid="stVerticalBlockBorderWrapper"] {border-color:#e0e5dc!important;border-radius:12px;}
@media (max-width:900px) {.block-container{padding:4rem 1rem 1rem;} .hero{padding:20px 0}.hero h1{font-size:28px}}
</style>""", unsafe_allow_html=True)

if "workspace" not in st.session_state:
    saved = store.setting("workspace", str(DEFAULT_WORKSPACE))
    st.session_state.workspace = saved if Path(saved).is_dir() else str(DEFAULT_WORKSPACE)
if "sid" not in st.session_state:
    existing = store.sessions()
    st.session_state.sid = existing[0]["id"] if existing else store.new_session(st.session_state.workspace, store.setting("config", DEFAULT_CONFIG))

def current():
    return store.session(st.session_state.sid)

def key_for(provider):
    return st.session_state.get("api_keys", {}).get(provider, "") or os.environ.get(PROVIDERS[provider][3], "")

def capture_secret(provider):
    keys = dict(st.session_state.get("api_keys", {}))
    keys[provider] = st.session_state.get("secret_" + provider, "")
    st.session_state.api_keys = keys

def new_chat(workspace=None):
    st.session_state.sid = store.new_session(workspace or st.session_state.workspace, store.setting("config", DEFAULT_CONFIG))

@st.dialog("模型与 Agent 设置", width="large")
def settings_dialog():
    session = current()
    locked = runner.active(session["id"]) or bool(session["pending"])
    if locked:
        st.info("运行结束或处理完待确认操作后，可以修改当前会话设置。")
    cfg = session["config"].copy()
    provider = st.selectbox("供应商", list(PROVIDERS), index=list(PROVIDERS).index(cfg["provider"]), disabled=locked)
    kind, base, default_model, _ = PROVIDERS[provider]
    profile = store.setting("profile_" + provider, {})
    source = cfg if provider == cfg["provider"] else profile
    left, right = st.columns([1, 1])
    with left:
        api_key = st.text_input("API Key", type="password", value=st.session_state.get("api_keys", {}).get(provider, ""), key="secret_" + provider, on_change=capture_secret, args=(provider,), help="仅留在本次浏览器会话内存中，不写入数据库。也支持对应供应商的环境变量。", disabled=kind == "ollama")
        if not api_key and key_for(provider):
            st.caption("已检测到环境变量中的密钥。")
    with right:
        base_url = st.text_input("API 地址", value=source.get("base_url", base), key="url_" + provider, disabled=locked)
    model_list_key = "models_" + provider
    candidate = dict(cfg, provider=provider, base_url=base_url)
    if st.button("↻ 获取供应商模型列表", disabled=locked):
        try:
            with st.spinner("正在获取模型…"):
                st.session_state[model_list_key] = list_models(candidate, key_for(provider))
            st.success(f"获取到 {len(st.session_state[model_list_key])} 个模型")
        except Exception as exc:
            st.error("获取失败，请检查密钥和 API 地址；仍可手动填写模型名。" + safe_error(exc, key_for(provider)))
    models = st.session_state.get(model_list_key, [])
    if models:
        selected = st.selectbox("可用模型", ["手动输入"] + models, key="select_" + provider)
    else:
        selected = "手动输入"
    model = st.text_input("模型名称", value=source.get("model", default_model), key="model_" + provider, disabled=locked) if selected == "手动输入" else selected
    a, b, c = st.columns(3)
    temperature = a.slider("Temperature", 0.0, 2.0, float(cfg["temperature"]), 0.1, disabled=locked)
    max_tokens = b.number_input("最大输出 tokens", 256, 32768, int(cfg["max_tokens"]), 256, disabled=locked)
    max_steps = c.number_input("最大执行步数", 5, 200, int(cfg["max_steps"]), 5, disabled=locked)
    vision = st.toggle("图片作为视觉输入发送给模型", value=cfg["vision"], disabled=locked, help="选择支持图片的模型后启用。关闭时，图片仍可上传和预览，但模型只收到文件信息。")
    tool_labels = {"files": "工作区文件读写与搜索", "calculator": "计算器", "memory": "长期记忆", "plan": "任务计划", "web": "联网搜索", "terminal": "终端命令"}
    enabled = st.multiselect("启用工具", list(tool_labels), default=cfg["tools"], format_func=tool_labels.get, disabled=locked)
    if "terminal" in enabled:
        st.caption("终端命令逐次确认，以当前用户权限运行；工作目录不是操作系统沙箱。")
    system_prompt = st.text_area("Agent 系统提示词", value=cfg["system_prompt"], height=100, disabled=locked)
    updated = dict(provider=provider, base_url=base_url.strip().rstrip("/"), model=model.strip(), temperature=temperature,
                   max_tokens=max_tokens, max_steps=max_steps, vision=vision, tools=enabled, system_prompt=system_prompt)
    test, save = st.columns(2)
    if test.button("测试模型连接", use_container_width=True, disabled=locked):
        try:
            with st.spinner("正在发送一条测试消息…"):
                answer = create_model(updated, key_for(provider)).invoke("Reply with OK only.")
            st.success("模型连接成功")
            st.caption(str(answer.content)[:200])
        except Exception as exc:
            st.error(safe_error(exc, key_for(provider)))
    if save.button("保存并使用", type="primary", use_container_width=True, disabled=locked):
        if not updated["model"] or not updated["base_url"].startswith(("http://", "https://")):
            st.error("请填写模型名和完整的 HTTP(S) API 地址。")
        else:
            store.update_session(session["id"], config=updated)
            store.set_setting("config", updated)
            store.set_setting("profile_" + provider, updated)
            st.rerun()

def safe_error(exc, key=""):
    text = str(exc)
    return (text.replace(key, "[已隐藏密钥]") if key else text)[:1200]

@st.dialog("选择工作区", width="large")
def workspace_dialog():
    st.caption("选择本机文件夹作为新会话的工作区。已有会话保留原工作区。")
    path = st.text_input("文件夹绝对路径", value=st.session_state.workspace)
    if "browse_path" not in st.session_state:
        st.session_state.browse_path = st.session_state.workspace
    if st.button("浏览此路径"):
        candidate = Path(path).expanduser()
        if candidate.is_dir():
            st.session_state.browse_path = str(candidate.resolve())
        else:
            st.error("文件夹不存在，请输入已有目录。")
    browse = Path(st.session_state.browse_path)
    st.code(str(browse), language=None)
    if st.button("↑ 上一级", disabled=browse.parent == browse):
        st.session_state.browse_path = str(browse.parent)
        st.rerun(scope="fragment")
    try:
        folders = sorted([p for p in browse.iterdir() if p.is_dir() and not p.name.startswith(".")], key=lambda p: p.name.lower())[:200]
        folder = st.selectbox("子文件夹", [""] + [p.name for p in folders], format_func=lambda v: v or "选择子文件夹…")
        if st.button("打开文件夹 →", disabled=not folder):
            st.session_state.browse_path = str(browse / folder)
            st.rerun(scope="fragment")
    except OSError as exc:
        st.error(str(exc))
    a, b = st.columns(2)
    if a.button("使用输入路径", use_container_width=True):
        choose_workspace(path)
    if b.button("使用当前浏览文件夹", type="primary", use_container_width=True):
        choose_workspace(str(browse))

def choose_workspace(path):
    p = Path(path).expanduser()
    if not p.is_absolute() or not p.is_dir():
        st.error("请选择存在的本机文件夹，使用绝对路径。")
        return
    st.session_state.workspace = str(p.resolve())
    store.set_setting("workspace", st.session_state.workspace)
    new_chat()
    st.rerun()

@st.dialog("会话管理")
def session_dialog():
    s = current()
    title = st.text_input("会话名称", value=s["title"])
    if st.button("保存名称", type="primary") and title.strip():
        store.update_session(s["id"], title=title.strip()[:100])
        st.rerun()
    messages = store.messages(s["id"])
    markdown = f"# {s['title']}\n\n工作区：{s['workspace']}\n\n" + "\n\n".join(f"## {'你' if m['role']=='user' else 'Agent'}\n\n{m['content']}" for m in messages)
    st.download_button("导出 Markdown", markdown, file_name="conversation.md", mime="text/markdown")
    st.download_button("导出 JSON", json.dumps({"session": s, "messages": messages, "events": store.events(s["id"])}, ensure_ascii=False, indent=2), file_name="conversation.json", mime="application/json")
    if st.button("归档会话", disabled=runner.active(s["id"]) or bool(s["pending"])):
        store.update_session(s["id"], archived=1)
        remaining = store.sessions()
        if remaining:
            st.session_state.sid = remaining[0]["id"]
        else:
            new_chat()
        st.rerun()

with st.sidebar:
    st.markdown('<div class="brand"><span class="brand-mark">◈</span> Agent Desk</div><div class="subtle">你的通用 AI 工作空间</div>', unsafe_allow_html=True)
    st.write("")
    if st.button("＋  新建对话", type="primary", use_container_width=True):
        new_chat()
        st.rerun()
    if st.button("▧  选择工作区", use_container_width=True):
        workspace_dialog()
    st.caption(Path(st.session_state.workspace).name)
    st.markdown('<div class="eyebrow">CONVERSATIONS / 会话</div>', unsafe_allow_html=True)
    query = st.text_input("搜索会话", label_visibility="collapsed", placeholder="搜索会话…")
    archived = st.toggle("查看已归档", value=False)
    with st.container(height=330, border=False):
        for s in store.sessions(archived):
            if query.casefold() not in s["title"].casefold():
                continue
            marker = "◌ " if runner.active(s["id"]) else "◷ " if s["pending"] else ""
            if st.button(marker + s["title"], key="session_" + s["id"], use_container_width=True,
                         type="primary" if s["id"] == st.session_state.sid else "tertiary"):
                if archived:
                    store.update_session(s["id"], archived=0)
                st.session_state.sid = s["id"]
                st.rerun()
    st.divider()
    if st.button("⚙  模型与 Agent 设置", use_container_width=True):
        settings_dialog()
    st.markdown('<div class="subtle">LOCAL WORKSPACE<br>会话与记忆保存在本机</div>', unsafe_allow_html=True)

session = current()
header, controls = st.columns([5, 1])
with header:
    st.subheader(session["title"])
    st.caption(f"{session['config']['provider']} / {session['config']['model']}　 ·　 {Path(session['workspace']).name}")
with controls:
    if st.button("会话管理", use_container_width=True):
        session_dialog()
st.divider()
chat_col, context_col = st.columns([3, 1.25], gap="large")

def render_attachment(item, workspace, key):
    try:
        path = resolve_inside(workspace, item["path"])
        if item["image"]:
            st.image(str(path), width=220, caption=item["name"])
        else:
            st.caption(f"📎 {item['name']} · {item['size'] / 1024:.1f} KB")
    except (ValueError, OSError):
        st.caption(f"📎 {item['name']}（文件已移动或不可用）")

@st.fragment(run_every=0.7 if runner.active(session["id"]) else None)
def chat_panel():
    s = current()
    sid = s["id"]
    run = runner.get(sid)
    snapshot = run.snapshot() if run else None
    active = snapshot is not None and snapshot["status"] == "running"
    history = store.messages(sid)
    with st.container(height=510, border=False):
        if not history:
            st.markdown('<div class="hero"><div class="hero-symbol">✳</div><h1>从一个想法开始。</h1><p>一起读文件、整理信息、编写内容，或完成一项工作。<br>带上你的资料，剩下的我们一步步来。</p></div>', unsafe_allow_html=True)
            a, b = st.columns(2)
            with a:
                with st.container(border=True):
                    st.markdown("**▧  探索工作区**")
                    st.caption("读取项目文件，梳理结构与关键内容")
            with b:
                with st.container(border=True):
                    st.markdown("**⌘  把任务交给工具**")
                    st.caption("计算、搜索、写文件，执行过程随时可见")
        for msg in history:
            with st.chat_message(msg["role"], avatar=":material/person:" if msg["role"] == "user" else ":material/auto_awesome:"):
                st.markdown(msg["content"])
                for i, item in enumerate(msg["attachments"]):
                    render_attachment(item, s["workspace"], f"{msg['id']}_{i}")
        if active:
            with st.chat_message("assistant", avatar=":material/auto_awesome:"):
                if snapshot["text"]:
                    st.markdown(snapshot["text"] + " ▍")
                else:
                    st.caption("正在处理…")
                latest = snapshot["events"][-1] if snapshot["events"] else None
                if latest and latest["kind"] == "tool_call":
                    st.caption("正在调用：" + latest["data"]["name"])
        if snapshot and snapshot["status"] == "error":
            st.error(snapshot["error"])
            st.caption("请检查模型配置或网络，然后重新发送。错误详情也保存在执行记录中。")
        if snapshot and snapshot["status"] == "stopped":
            st.info("本轮已停止，已完成的工具操作和对话记录保留。")
    if s["pending"] and not active:
        st.info("Agent 正在等待你确认以下操作。")
        actions = [action for block in s["pending"] for action in block.get("action_requests", [])]
        decisions = []
        for i, action in enumerate(actions):
            with st.expander(action["name"], expanded=True):
                st.json(action["args"])
                choice = st.radio("执行此操作", ["批准", "拒绝"], horizontal=True, key=f"approval_{sid}_{i}")
                decisions.append({"type": "approve"} if choice == "批准" else {"type": "reject", "message": "用户在工作台拒绝了此操作。"})
        if st.button("提交决定并继续", type="primary", key="resume_" + sid):
            if not key_for(s["config"]["provider"]) and PROVIDERS[s["config"]["provider"]][0] != "ollama":
                st.error("请在模型设置中重新输入 API Key。")
            else:
                runner.start(sid, key_for(s["config"]["provider"]), decisions=decisions)
                st.rerun()
    if active and st.button("■  停止生成", key="stop_" + sid):
        run.cancel.set()
        st.caption("正在停止；网络请求或工具将在返回或超时后结束。")
    provider = s["config"]["provider"]
    ready = bool(key_for(provider)) or PROVIDERS[provider][0] == "ollama"
    if not ready:
        st.info("先在左下角「模型与 Agent 设置」中选择供应商，填写 API Key 和模型。")
    entry = st.chat_input("描述你想完成的工作，或添加图片和文件…", accept_file="multiple", disabled=active or bool(s["pending"]) or not ready, key="input_" + sid)
    if entry:
        try:
            if len(entry.files) > 8:
                raise ValueError("每条消息最多上传 8 个附件。")
            attachments = [save_upload(s["workspace"], f.name, f.getvalue()) for f in entry.files]
            runner.start(sid, key_for(provider), text=entry.text, attachments=attachments)
            st.rerun()
        except (ValueError, OSError) as exc:
            st.error(str(exc))
    st.caption("Enter 发送 · Shift + Enter 换行 · 每个附件最多 20 MB")
    if snapshot and snapshot["status"] != "running" and st.session_state.get("finished_" + sid) != id(run):
        st.session_state["finished_" + sid] = id(run)
        st.rerun()

with chat_col:
    chat_panel()

with context_col:
    st.markdown("**工作区**")
    st.caption(session["workspace"])
    files_tab, memory_tab, activity_tab = st.tabs(["文件", "记忆", "执行"])
    with files_tab:
        rel_key = "directory_" + session["id"]
        if rel_key not in st.session_state:
            st.session_state[rel_key] = "."
        relative = st.session_state[rel_key]
        st.caption("/" + (relative if relative != "." else ""))
        if relative != "." and st.button("↑ 返回上级"):
            st.session_state[rel_key] = str(Path(relative).parent)
            st.rerun()
        try:
            entries = list_directory(session["workspace"], relative)
            if not entries:
                st.caption("这个文件夹还是空的。上传一份资料开始吧。")
            with st.container(height=240, border=False):
                for item in entries:
                    if item["directory"]:
                        if st.button("▸ " + item["name"], key="dir_" + item["path"], type="tertiary"):
                            st.session_state[rel_key] = item["path"]
                            st.rerun()
                    else:
                        with st.expander(item["name"]):
                            path = resolve_inside(session["workspace"], item["path"])
                            st.caption(f"{item['size']/1024:.1f} KB")
                            if item["size"] <= 20 * 1024 * 1024:
                                if st.button("打开预览与下载", key="preview_" + item["path"]):
                                    st.session_state["preview_file_" + session["id"]] = item["path"]
                                if st.session_state.get("preview_file_" + session["id"]) == item["path"]:
                                    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
                                        st.image(str(path))
                                    else:
                                        st.code(extract_text(path, 5000), language=None)
                                    st.download_button("下载", path.read_bytes(), file_name=path.name, key="download_" + item["path"])
        except (OSError, ValueError) as exc:
            st.error(str(exc))
        uploads = st.file_uploader("添加到工作区", accept_multiple_files=True, key="upload_" + session["id"], help="保存到工作区 uploads 文件夹。聊天输入框上传的附件会同时传给模型。")
        if uploads and st.button("保存文件", use_container_width=True):
            try:
                for f in uploads:
                    save_upload(session["workspace"], f.name, f.getvalue())
                st.success("已保存到 uploads 文件夹")
            except (OSError, ValueError) as exc:
                st.error(str(exc))
        if st.button("↻ 刷新文件", use_container_width=True):
            st.rerun()
    with memory_tab:
        st.caption("在同一个工作区的所有会话中共享。")
        with st.form("memory_form", clear_on_submit=True):
            note = st.text_area("添加长期记忆", placeholder="例如：默认用中文回答，报告使用 Markdown。", height=90)
            if st.form_submit_button("保存记忆", use_container_width=True):
                try:
                    store.remember(session["workspace"], note)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        notes = store.memories(session["workspace"])
        st.caption(f"{len(notes)} 条记忆")
        for note in notes:
            with st.container(border=True):
                st.write(note["content"])
                if st.button("删除", key="forget_" + note["id"], type="tertiary"):
                    store.forget(session["workspace"], note["id"])
                    st.rerun()
    with activity_tab:
        @st.fragment(run_every=1 if runner.active(session["id"]) else None)
        def activity_panel():
            events = store.events(st.session_state.sid)
            if not events:
                st.caption("运行后的工具调用、任务计划和用量会出现在这里。")
            plans = [e for e in events if e["kind"] == "plan"]
            if plans:
                st.markdown("**当前计划**")
                for step in plans[0]["data"]:
                    st.write(step)
            usage = [e["data"] for e in events if e["kind"] == "usage"]
            if usage:
                st.metric("最近记录的 tokens", sum(u.get("total_tokens", 0) for u in usage))
            labels = {"tool_call": "调用工具", "tool_result": "工具结果", "approval": "等待确认", "run": "开始运行", "error": "运行错误", "stopped": "已停止", "usage": "Token 用量", "plan": "任务计划"}
            for e in events:
                label = labels.get(e["kind"], e["kind"])
                if isinstance(e["data"], dict) and e["data"].get("name"):
                    label += " · " + e["data"]["name"]
                with st.expander(label):
                    if isinstance(e["data"], (dict, list)):
                        st.json(e["data"])
                    else:
                        st.text(e["data"])
        activity_panel()
