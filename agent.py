
from re import S
from unittest import result

from llm import ToolCall

class Agent:
    
    def __init__(self,llm,tools=None,max_rounds: int = 10):
        self.llm = llm
        # tools 是普通函数字典：{"read_file": 某个函数}
        # 阶段 2 会换成工具对象列表。这里先用函数，让循环先跑起来。
        self.tools = tools or []
        self.messages: list[dict] = []
        self.max_rounds = max_rounds

    def chat(self, user_input:str, on_tool=None, on_token=None, on_reasoning=None) -> str:
        self.messages.append({"role": "user", "content": user_input})

        for _ in range(self.max_rounds):
            resp = self.llm.chat(
                self.messages,
                on_token=on_token,
                on_reasoning=on_reasoning,
            )

            # 把模型回复放进历史，加上工具调用。
            self.messages.append(resp.message)

            # 如果模型没要求调用工具，就结束。
            if not resp.tool_calls:
                return resp.content
            
            # 如果模型要求调用工具，就调用工具。
            for tc in resp.tool_calls:
                if on_tool:
                    on_tool(tc.name, tc.arguments)
                result = self._exec(tc)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        raise RuntimeError(f"Agent: 对话超过最大轮数 {self.max_rounds} 轮，仍然没有得到模型回复。")
    
    def _exec(self, tc: ToolCall) -> str:
        fn = self.tools.get(tc.name)
        if fn is None:
            return f"工具 {tc.name} 不存在。"
        try:
            return fn(**tc.arguments)
        except Exception as e:
            return f"工具 {tc.name} 执行失败: {e}"