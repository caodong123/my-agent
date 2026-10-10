
from cgitb import reset
from dataclasses import dataclass, field
import json
from pyexpat import model


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