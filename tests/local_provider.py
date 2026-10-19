"""Local OpenAI-compatible fixture for manual browser integration checks. No external API."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"data": [{"id": "local-integration-test", "object": "model"}]}).encode())

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        messages = body["messages"]
        last = messages[-1]
        content = str(last.get("content", ""))
        tool_call = None
        if last["role"] == "tool":
            answer = "工具运行完成，结果：" + content
        elif "写入测试" in content:
            answer = ""
            tool_call = {"index": 0, "id": "test_write", "type": "function", "function": {"name": "write_file", "arguments": json.dumps({"path": "browser-test.txt", "content": "浏览器端到端验证成功"}, ensure_ascii=False)}}
        elif "计算测试" in content:
            answer = ""
            tool_call = {"index": 0, "id": "test_calc", "type": "function", "function": {"name": "calculator", "arguments": '{"expression":"6 * 7"}'}}
        elif "OK only" in content:
            answer = "OK"
        else:
            count = sum(m["role"] == "user" for m in messages)
            has_image = any(isinstance(m.get("content"), list) and any(b.get("type") == "image_url" for b in m["content"]) for m in messages)
            answer = f"本地集成验证成功。已收到 {count} 轮消息；图片输入：{has_image}。"
        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            delta = {"role": "assistant", "content": answer}
            if tool_call:
                delta["tool_calls"] = [tool_call]
            chunk = {"id": "test-completion", "object": "chat.completion.chunk", "created": 1, "model": "local-integration-test", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}
            self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
            chunk["choices"] = [{"index": 0, "delta": {}, "finish_reason": "tool_calls" if tool_call else "stop"}]
            self.wfile.write(("data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n").encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"id": "test", "object": "chat.completion", "created": 1, "model": "local-integration-test", "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}]}).encode())

if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 18502), Handler).serve_forever()
