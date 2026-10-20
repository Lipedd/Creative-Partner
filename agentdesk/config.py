from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("AGENTDESK_DATA_DIR", ROOT / ".agentdesk")).resolve()
DATA.mkdir(parents=True, exist_ok=True)
DEFAULT_WORKSPACE = DATA / "workspace"
DEFAULT_WORKSPACE.mkdir(exist_ok=True)

# Provider adapters remain available internally for future extensions. The product UI
# intentionally exposes only DeepSeek for now.
PROVIDERS = {
    "OpenAI": ("openai", "https://api.openai.com/v1", "gpt-4.1-mini", "OPENAI_API_KEY"),
    "DeepSeek": ("openai", "https://api.deepseek.com", "deepseek-flash", "DEEPSEEK_API_KEY"),
    "通义千问": ("openai", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus", "DASHSCOPE_API_KEY"),
    "智谱 GLM": ("openai", "https://open.bigmodel.cn/api/paas/v4", "glm-4.5", "ZHIPU_API_KEY"),
    "OpenRouter": ("openai", "https://openrouter.ai/api/v1", "openai/gpt-4.1-mini", "OPENROUTER_API_KEY"),
    "Anthropic": ("anthropic", "https://api.anthropic.com", "claude-sonnet-4-5", "ANTHROPIC_API_KEY"),
    "Google Gemini": ("google", "https://generativelanguage.googleapis.com", "gemini-2.5-flash", "GOOGLE_API_KEY"),
    "Ollama（本地）": ("ollama", "http://localhost:11434", "qwen3:8b", ""),
    "自定义 OpenAI 兼容": ("openai", "http://localhost:8000/v1", "", ""),
}

DEFAULT_CONFIG = {
    "provider": "DeepSeek", "base_url": PROVIDERS["DeepSeek"][1],
    # deepseek-flash is the stable API alias for the current V4.1 Flash model.
    "model": "deepseek-flash", "reasoning_effort": "high",
    "temperature": 1.0, "max_tokens": 4096,
    "vision": True, "tools": ["files", "calculator", "memory", "plan", "web", "terminal"],
    "system_prompt": "你是孩子的创作伙伴。用简短、温暖、容易听懂的中文，把想法真正做成能看到、能操作的作品。",
    "max_steps": 40,
}

DEMO_CONFIG = {
    **DEFAULT_CONFIG,
    # The public demo only creates static browser projects. It never exposes a
    # shell or starts model-generated services on the host machine.
    "tools": ["files", "calculator", "memory", "plan", "web"],
    "max_steps": 28,
    "system_prompt": DEFAULT_CONFIG["system_prompt"] + (
        " 你正在公开体验版中，只能制作由 HTML、CSS、JavaScript 和浏览器可直接使用的资源组成的作品。"
        "不要要求安装软件，不要尝试运行命令或启动额外服务。"
    ),
}

def create_model(config: dict, api_key: str):
    kind = PROVIDERS[config["provider"]][0]
    common = dict(model=config["model"])
    if config["provider"] != "DeepSeek":
        common["temperature"] = config["temperature"]
    if not common["model"].strip():
        raise ValueError("请先在模型设置中填写模型名称。")
    if kind != "ollama" and not api_key:
        raise ValueError("请先在模型设置中填写 API Key。")
    if kind == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(**common, api_key=api_key, base_url=config["base_url"],
                             max_tokens=config["max_tokens"], timeout=60, max_retries=1)
    if kind == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(**common, google_api_key=api_key,
            max_output_tokens=config["max_tokens"], timeout=60, max_retries=1,
            base_url=config["base_url"])
    if kind == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(**common, base_url=config["base_url"], num_predict=config["max_tokens"],
                         client_kwargs={"timeout": 60})
    from langchain_openai import ChatOpenAI
    if config["provider"] == "DeepSeek":
        import httpx
        common.update(reasoning_effort=config.get("reasoning_effort", "high"),
                      extra_body={"thinking": {"type": "enabled"}},
                      # DeepSeek is reached directly. This local app must not inherit
                      # stale HTTP_PROXY/HTTPS_PROXY values from the desktop process.
                      http_client=httpx.Client(trust_env=False),
                      http_async_client=httpx.AsyncClient(trust_env=False))
    return ChatOpenAI(**common, api_key=api_key, base_url=config["base_url"],
                     max_tokens=config["max_tokens"], timeout=60, max_retries=1,
                     streaming=True)

def list_models(config: dict, api_key: str) -> list[str]:
    import httpx
    kind = PROVIDERS[config["provider"]][0]
    base = config["base_url"].rstrip("/")
    headers = {}
    params = {}
    if kind == "ollama":
        url = base + "/api/tags"
    elif kind == "anthropic":
        url = base + "/v1/models"
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    elif kind == "google":
        url = base + "/v1beta/models"
        headers = {"x-goog-api-key": api_key}
    else:
        url = base + "/models"
        headers = {"Authorization": f"Bearer {api_key}"}
    with httpx.Client(trust_env=False, timeout=15) as client:
        response = client.get(url, headers=headers, params=params)
    response.raise_for_status()
    body = response.json()
    if kind == "ollama":
        return sorted(item["name"] for item in body.get("models", []))
    if kind == "google":
        return sorted(item["name"].removeprefix("models/") for item in body.get("models", [])
                      if "generateContent" in item.get("supportedGenerationMethods", []))
    return sorted(item["id"] for item in body.get("data", []))
