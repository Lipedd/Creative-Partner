"""Manual browser fixture for the child-friendly progress card."""
import time
from pathlib import Path

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from agentdesk.api import create_app
from agentdesk.runtime import Runner


class VisualProgressModel(BaseChatModel):
    @property
    def _llm_type(self):
        return "visual-progress-fixture"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if isinstance(messages[-1], ToolMessage):
            time.sleep(4)
            message = AIMessage(content="第一版已经做好了，快打开看看吧！")
        else:
            time.sleep(3)
            message = AIMessage(content="我开始制作第一版。", tool_calls=[{
                "name": "write_file", "args": {"path": "index.html", "content": "<h1>进度测试作品</h1>"},
                "id": "visual_write", "type": "tool_call",
            }])
        return ChatResult(generations=[ChatGeneration(message=message)])


class VisualRunner(Runner):
    def start(self, *args, **kwargs):
        return super().start(*args, **kwargs, model_override=VisualProgressModel())


app = create_app(Path("output/ui-progress-data"), VisualRunner)
