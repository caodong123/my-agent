

import os
from pathlib import Path

import agent
from config import Config
from llm import LLM, LLMResponse, ScriptedLLM, ToolCall
from agent import Agent
from permission import Permission


# def read_file(file_path: str) -> str:
#     path = Path(file_path)
#     if not path.exists():
#         return f"文件 {file_path} 不存在。"
#     return path.read_text(encoding="utf-8")

def run_demo():
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

    agent = Agent(llm=ScriptedLLM(script))
    print(agent.chat("读一下 hello.py，用一句话说明", on_tool=lambda n, a: print(f"[tool] {n} {a}")))

def ask(tool_name: str, arguments: dict) -> str | None:
    print(f"\n允许 {tool_name} {arguments} 吗？ y=一次  a=这个工具一直允许  其他=拒绝")
    answer = input("> ").strip().lower()
    if answer == "y":
        return "once"
    if answer == "a":
        return "always"
    return "deny"

permission = Permission(ask=ask, persist_path=Path.cwd() / "permission.json")


def main():
    if os.getenv("MYAGENT_DEMO") == "1":
        run_demo()
        return

    cfg = Config.from_env()
    if not cfg.api_key:
        print("Error: OPENAI_API_KEY is not set")
        return
    
    llm = LLM(
        model=cfg.model,
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
    )
    
    agent = Agent(llm=llm, permission=permission)
    print("连续对话已开始。输入 quit 或 exit 结束。")
    while True:
        try:
            line = input("You > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.lower() in ("quit", "exit"):
            break
        answer = agent.chat(
            line,
            on_tool=lambda name, args: print(f"\n[tool] {name} {args}"),
        )
        print("\n[answer]", answer)

if __name__ == "__main__":
    main()