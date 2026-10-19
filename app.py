"""ASGI entry point: python -m uvicorn app:app --host 127.0.0.1 --port 8501."""
from agentdesk.api import create_app

app = create_app()
