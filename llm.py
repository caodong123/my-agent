
from cgitb import reset
from dataclasses import dataclass, field
import json
from pyexpat import model

from openai import OpenAI
from openai.types.admin.organization.audit_log_list_response import UserUpdatedChangesRequested

@dataclass
class ToolCall:
    """模型提出的一次工具调用"""
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """一轮模型回复，可以只有正文，也可以同时有工具调用"""
    content: str
    # 每个响应自己一份空列表
    tool_calls: list[ToolCall] = field(default_factory=list)


    """助手回复消息,按照符合openai api规范的assistant消息格式返回"""
    @property
    def message(self) -> dict:
        """resp.meaasge,不要加括号，拼成要放进历史的 assistant 消息"""
        msg = {"role": "assistant", "content": self.content or None}
        
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        # 参数转成json字符串，不要转义
                        "arguments": json.dumps(tc.arguments,ensure_ascii=False),
                    }    
                }
                for tc in self.tool_calls
            ]
        return msg

class ScriptedLLM:
    """按剧本吐回复。剧本用完还在循环，就立刻报错，避免你以为它卡住了。"""

    model = "scripted"
    total_prompts_tokens = 0
    total_completions_tokens = 0
    estimated_cost = None

    def __init__(self, script: list[LLMResponse]):
        self._turns = list(script)

    def chat(self, message, tools = None, on_token=None, on_reasoning = None) -> LLMResponse:
        if not self._turns:
            raise RuntimeError("ScriptedLLM: 剧本用完了还在循环，可能卡住了。")
        
        resp = self._turns.pop(0)
        # 后面的命令行会把 on_token 传进来。假模型把整段正文一次交出去。
        if on_token and resp.content:
            on_token(resp.content)
        return resp

class LLM:
    """一个通用的 LLM 接口，可以对接不同的 LLM 模型"""
    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ):
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.total_prompt_tokens = 0
        self.total_completions_tokens = 0

    def chat(self, messages, tools=None, on_token=None, on_reasoning = None) -> LLMResponse:
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
        
        # 使用openai api创建聊天完成
        resp = self.client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message

        calls = []
        for tc in msg.tool_calls or []:
            raw = tc.function.arguments or "{}"
            try:
                args = json.loads(raw)
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        
        usage = resp.usage
        if usage:
            self.total_prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
            self.total_completions_tokens += getattr(usage, "completion_tokens", 0) or 0
        
        text = msg.content or ""
        if on_token and text:
            on_token(text)
        return LLMResponse(content=text,tool_calls=calls)