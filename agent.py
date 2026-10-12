
import inspect
from re import S
from unittest import result

from llm import ToolCall
from tools import ALL_TOOLS

SYSTEM_PROMPT = """你是一个代码助手，通过调用工具完成用户的任务。用中文回答。
"""

class Agent:
    
    def __init__(self,llm,tools=None,max_rounds: int = 10):
        self.llm = llm
        # tools 是普通函数字典：{"read_file": 某个函数}
        if tools is None:
            
            tools = ALL_TOOLS

        self.tools = tools 
        self._tool_by_name = {t.name: t for t in tools}
        self.messages: list[dict] = []
        self.max_rounds = max_rounds

    def chat(self, user_input:str, on_tool=None, on_token=None, on_reasoning=None) -> str:
        self.messages.append({"role": "user", "content": user_input})

        for _ in range(self.max_rounds):
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                *self.messages,
            ]
            resp = self.llm.chat(
                messages,
                tools=self._tool_schemas(),
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
    
    def _tool_schemas(self) -> list[dict]:
        return [t.schema() for t in self.tools]

    def _exec(self, tc) -> str:
        tool = self._tool_by_name.get(tc.name)
        if tool is None:
            return f"Error: unknown tool '{tc.name}'"
        try:
            inspect.signature(tool.execute).bind(**tc.arguments)
        except TypeError as e:
            return f"Error: bad arguments for {tc.name}: {e}"
        try:
            return tool.execute(**tc.arguments)
        except TypeError as e:
            return f"Error: bad arguments for {tc.name}: {e}"
        except Exception as e:
            return f"Error executing {tc.name}: {e}"