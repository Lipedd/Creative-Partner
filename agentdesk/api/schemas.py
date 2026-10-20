from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from agentdesk.config import DEFAULT_CONFIG, PROVIDERS

class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = DEFAULT_CONFIG["provider"]
    base_url: str = DEFAULT_CONFIG["base_url"]
    model: str = Field(default=DEFAULT_CONFIG["model"], min_length=1, max_length=200)
    reasoning_effort: Literal["low", "high", "max"] = DEFAULT_CONFIG["reasoning_effort"]
    temperature: float = Field(default=0.3, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=256, le=32768)
    max_steps: int = Field(default=40, ge=5, le=200)
    vision: bool = False
    tools: list[Literal["files", "calculator", "memory", "plan", "web", "terminal"]] = Field(default_factory=lambda: list(DEFAULT_CONFIG["tools"]))
    system_prompt: str = Field(default=DEFAULT_CONFIG["system_prompt"], max_length=20000)

    @field_validator("provider")
    @classmethod
    def provider_exists(cls, value):
        if value not in PROVIDERS:
            raise ValueError("未知供应商")
        return value

    @field_validator("base_url")
    @classmethod
    def valid_url(cls, value):
        from urllib.parse import urlparse
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("请输入有效的 HTTP(S) API 地址，不要在地址中包含密钥")
        return value.rstrip("/")

class NewSession(BaseModel):
    kind: Literal["chat", "project"] = "project"
    idea: str = Field(default="", max_length=4000)
    name: str | None = Field(default=None, max_length=100)
    placement: Literal["auto", "manual"] = "auto"
    workspace: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=100)

class NewProject(BaseModel):
    idea: str = Field(min_length=1, max_length=4000)
    name: str | None = Field(default=None, max_length=100)
    placement: Literal["auto", "manual"] = "auto"
    workspace: str | None = None

class ProjectNameInput(BaseModel):
    idea: str = Field(min_length=1, max_length=4000)

class EditSession(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    archived: bool | None = None

class Credentials(BaseModel):
    provider: str
    api_key: str = Field(max_length=4000)
    persistent: bool = True

class MessageInput(BaseModel):
    text: str = Field(default="", max_length=100000)
    attachments: list[str] = Field(default_factory=list, max_length=8)

class Decision(BaseModel):
    type: Literal["approve", "reject"]
    message: str = Field(default="用户拒绝了此操作。", max_length=2000)

class ResumeInput(BaseModel):
    decisions: list[Decision] = Field(min_length=1, max_length=30)

class MemoryInput(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
