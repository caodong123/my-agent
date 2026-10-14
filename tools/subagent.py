
from tools.base import Tool


class SubAgentTool(Tool):
    name = "agent"
    description = (
        "Spawn a sub-agent with a fresh conversation for a multi-step subtask. "
        "It cannot spawn further sub-agents."
    )
    parameters = {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "What the sub-agent should do"},
        },
        "required": ["task"],
    }

    # Agent.__init__ 里会把父 Agent 填到这里
    _parent = None

    def execute(self,task:str) -> str:
        if self._parent is None:
            return "Error: agent tool has no parent"
        
        # 放在函数里再 import，避免 agent.py 和这个文件互相在文件顶部导入
        from agent import Agent
        from tools.bash import get_cwd, set_cwd

        parent = self._parent
        child = Agent(
            llm=parent.llm,
            tools=[t for t in parent.tools if t.name != "agent"],
            max_rounds=20,
            permission=parent.permission,
            max_context_tokens=parent.context.max_tokens,
        )
        parent_cwd = get_cwd()
        try:
            result = child.chat(task)
            if len(result) > 5000:
                result = result[:4500] + "\n... (sub-agent output truncated)"
            return f"[Sub-agent completed]\n{result}"
        except Exception as e:
            return f"[Sub-agent error]\n{e}"
        finally:
            # finally 无论成功还是异常都会走。把父线程的当前目录恢复回去。
            if get_cwd() != parent_cwd:
                set_cwd(parent_cwd)