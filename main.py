

import os
from pathlib import Path

import agent
from config import Config
from llm import LLM, LLMResponse, ScriptedLLM, ToolCall
from agent import Agent


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
    agent = Agent(llm=llm)
    answer = agent.chat(
        "读一下 hello.py，用三句话说明它做什么",
        on_tool=lambda name, args: print(f"\n[tool] {name} {args}"),
    )
    print("\n[answer]", answer)

if __name__ == "__main__":
    main()