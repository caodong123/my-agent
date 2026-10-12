
from cgitb import reset
from dataclasses import dataclass, field
import json
from pyexpat import model

import time
from openai import APIConnectionError, APIError, APITimeoutError, BadRequestError, RateLimitError

from openai import OpenAI
from openai.types.admin.organization.audit_log_list_response import UserUpdatedChangesRequested


_PRICING = {
    "deepseek-chat": (0.27, 1.10),
}



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

    def chat(self,message, tools=None, on_token=None, on_reasoning = None) -> LLMResponse:
        params = {
            "model": self.model,
            "messages": message,
            "stream": True,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream_options": {
                "include_usage": True,
            }
        }
        if tools:
            params["tools"] = tools
        
        last_err = None
        for attempt in range(3):
            try:
                stream = self._call_with_retry(params)
                return self._drain(stream,on_token,on_reasoning)
            except BadRequestError:
                if "stream_options" in params:
                    params.pop("stream_options")
                    continue
                raise
            except(RateLimitError, APITimeoutError,APIConnectionError) as e:
                last_err = e
            except APIError as e:
                status = getattr(e,"status_code",None)
                if not status or status < 500:
                    raise
                last_err = e
            if attempt < 2:
                time.sleep(2 ** attempt)
        raise last_err
    
    def _drain(self,stream,on_token,on_reasoning) -> LLMResponse:
        content_parts: list[str] = []
        # index 是本轮第几个工具调用。碎片可能交错到来，所以按序号分桶。
        buckets: dict[int,dict] = {}
        prompt_tok = 0
        completion_tok = 0

        for chunk in stream:
            usage = getattr(chunk,"usage",None)
            if usage:
                prompt_tok += getattr(usage,"prompt_tokens",0) or 0
                completion_tok += getattr(usage,"completion_tokens",0) or 0
            if not getattr(chunk,"choices",[]):
                continue
            delta = chunk.choices[0].delta

            reasoning = getattr(delta,"reasoning_content",None) or getattr(delta,"reasoning",None)

            if reasoning and on_reasoning:
                on_reasoning(reasoning)
            
            if getattr(delta,"content",None):
                content_parts.append(delta.content)
                if on_token:
                    on_token(delta.content)
            
            if getattr(delta,"tool_calls",None):
                for piece in delta.tool_calls:
                    bucket = buckets.setdefault(piece.index,{"id":"","name":"","args":""})
                    if piece.id:
                        bucket["id"] = piece.id
                    if piece.function and piece.function.name:
                        bucket["name"] = piece.function.name
                    if piece.function and piece.function.arguments:
                        bucket["args"] += piece.function.arguments

        calls = []
        for index in sorted(buckets):
            raw = buckets[index]
            try:
                args = json.loads(raw["args"]) if raw["args"] else {}
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(id=raw["id"],name=raw["name"],arguments=args))

        self.total_prompt_tokens += prompt_tok
        self.total_completions_tokens += completion_tok
        return LLMResponse(content="".join(content_parts),tool_calls=calls)
    
    def _call_with_retry(self,params:dict, max_retries: int = 3) :
        """只负责把『流对象』要回来。流读到一半断开，由 chat() 的外层重试。"""
        for attempt in range(max_retries):
            try:
                return self.client.chat.completions.create(**params)
            except (RateLimitError, APITimeoutError,APIConnectionError):
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)
            except APIError as e:
                status = getattr(e,"status_code",None)
                if status and status >= 500 and attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise
    
    

            
    @property
    def estimated_cost(self):
        rates = _PRICING.get(self.model)
        if not rates:
            return None
        in_rate, out_rate = rates
        return (
            self.total_prompt_tokens * in_rate / 1_000_000
            + self.total_completions_tokens * out_rate / 1_000_000
        )


