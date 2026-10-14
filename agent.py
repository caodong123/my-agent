
import concurrent.futures
import inspect
from re import S
from unittest import result
from webbrowser import get

from context import ContextManager
from llm import ToolCall
from prompt import System_Prompt
from tools import ALL_TOOLS


class Agent:
    
    def __init__(self,llm,tools=None,max_rounds: int = 10, permission = None, max_context_tokens:int = 128_000):
        self.llm = llm
        # tools 是普通函数字典：{"read_file": 某个函数}
        if tools is None:
            
            tools = ALL_TOOLS

        self.tools = tools 
        self._tool_by_name = {t.name: t for t in tools}
        self.messages: list[dict] = []
        self.max_rounds = max_rounds
        self.permission = permission
        self.context = ContextManager(max_tokens = max_context_tokens)
        # 任务列表
        self._todo = next((t for t in tools if t.name == "todo_write"),None)

        for t in self.tools:
            if t.name == "agent":
                t._parent = self

    def chat(self, user_input:str, on_tool=None, on_token=None, on_reasoning=None) -> str:
        self.messages.append({"role": "user", "content": user_input})
        self.context.maybe_compress(self.messages, self.llm)

        for _ in range(self.max_rounds):
            resp = self.llm.chat(
                self.full_messages(),
                tools=self._tool_schemas(),
                on_token=on_token,
                on_reasoning=on_reasoning,
            )

            # 把模型回复放进历史，加上工具调用。
            self.messages.append(resp.message)

            # 如果模型没要求调用工具，就结束。
            if not resp.tool_calls:
                return resp.content
            try:
                if len(resp.tool_calls) == 1:
                    tc = resp.tool_calls[0]
                    if on_tool:
                        on_tool(tc.name, tc.arguments)
                    result = self._permit(tc)
                    if result is None:
                        result = self._exec(tc)
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
                else:
                    results = self._exec_parallel(resp.tool_calls, on_tool)
                    for tc, result in zip(resp.tool_calls, results):
                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result,
                        })
                self.context.maybe_compress(self.messages, self.llm)
            except KeyboardInterrupt:
                self._answer_pending(resp.tool_calls)
                raise    
        raise RuntimeError(f"Agent: 对话超过最大轮数 {self.max_rounds} 轮，仍然没有得到模型回复。")
    
    def _answer_pending(self, tool_calls: list[ToolCall]) -> None:
        answered = {
            m.get("tool_call_id")
            for m in self.messages
            if m.get("role") == "tool"
        }

        for tc in tool_calls:
            if tc.id not in answered:
                # 如果工具调用没有被回答，则回答它。
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": "Tool execution interrupted by user.",
                })


    def _permit(self, tc: ToolCall) -> str | None:
        if self.permission is None:
            return None
        return self.permission.check(tc.name, tc.arguments)
    
    def _tool_schemas(self) -> list[dict]:
        return [t.schema() for t in self.tools]
    
    def full_messages(self) -> list[dict]:
        # 新列表 =  系统提示 + 历史对话
        system = System_Prompt(self.tools)
        if self._todo is not None:
            system += f"\nCurrent task list:\n{self._todo.render()}"
        return [{"role": "system", "content": system}, *self.messages]
    
    def reset(self):
        self.messages.clear()
        if self._todo is not None:
            self._todo._tasks.clear()

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
    

    def _exec_parallel(self,tool_calls,on_tool=None) -> list[str]:
        from tools.bash import get_cwd,set_cwd

        for tc in tool_calls:
            if on_tool:
                on_tool(tc.name, tc.arguments)
        
        # 现在主线程问完权限
        results= [self._permit(tc) for tc in tool_calls]
        base_cwd = get_cwd()

        def run(tc):
            if tc.name == "bash" and base_cwd is not None:
                set_cwd(base_cwd)
            out = self._exec(tc)
            moved = None
            if tc.name == "bash":
                after = get_cwd()
                if after != base_cwd:
                    moved = after
            return out, moved
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = {
                i : pool.submit(run,tc)
                for i, tc in enumerate(tool_calls)
                if results[i] is None
            }

            for i, future in futures.items():
                out, moved = future.result()
                results[i] = out
                if moved is not None:
                    set_cwd(moved)
        return results