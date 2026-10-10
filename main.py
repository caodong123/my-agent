

from pathlib import Path

import agent
from llm import LLMResponse, ScriptedLLM, ToolCall
from agent import Agent


# def read_file(file_path: str) -> str:
#     path = Path(file_path)
#     if not path.exists():
#         return f"文件 {file_path} 不存在。"
#     return path.read_text(encoding="utf-8")

def main():
    script = [
        LLMResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="read_file",
                    arguments={"file_path": "hello.py"},
                )
            ]
        ),
        LLMResponse(content="这个文件会输出 hello, world!")
    ]

    agent = Agent(ScriptedLLM(script))

    def show_tool(name, args):
        print(f"工具 {name} 被调用，参数: {args}")
    
    answer = agent.chat("请读取 hello.py 文件，并告诉我文件内容。", on_tool=show_tool)
    print("[answer]", answer)
    print("--- messages ---")
    for m in agent.messages:
        print(m)

if __name__ == "__main__":
    main()