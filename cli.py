

import argparse
from ast import arg
import sys

from agent import Agent
from config import Config
from llm import LLM
from permission import Permission
from session import list_sessions, load_session, save_session


def parse_args():
    p = argparse.ArgumentParser(prog="myagent")
    p.add_argument("-p","--prompt",help="问一句就退出")
    p.add_argument("--yes", action="store_true", help="改动类工具全部放行")
    p.add_argument("--demo", action="store_true", help="假模型走一遍读文件")
    p.add_argument("-r", "--resume", help="恢复一个会话 id")
    p.add_argument("-m", "--model", help="模型名")
    return p.parse_args()

def ask(tool_name,arguments):
    print(f"\n允许 {tool_name} {arguments} 吗？ [y]一次 [a]这个工具一直允许 [n]拒绝")
    try:
        answer = input("> ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("denied")
        return "deny"
    if answer in ("y", "yes"):
        return "once"
    if answer in ("a", "always"):
        return "always"
    return "deny"

def run_once(agent: Agent, prompt: str):
    try:
        agent.chat(
            prompt,
            on_token=lambda t: print(t, end="", flush=True),
            on_tool=lambda name, args: print(f"\n[tool] {name} {args}"),
        )
        print()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)

def repl(agent: Agent):
    from pathlib import Path
    print("myagent. /help 看命令，quit 退出，Ctrl+C 取消当前这一句。")
    while True:
        try:
            line = input("You > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye")
            return
        if not line:
            continue
        if line.lower() in ("quit", "exit", "/quit", "/exit"):
            return
        if line == "/help":
            print("/help  /reset  /tokens  /save  /sessions  quit")
            continue
        if line == "/reset":
            agent.messages.clear()
            print("history cleared")
            continue
        if line == "/tokens":
            llm = agent.llm
            print(f"in={llm.total_prompt_tokens} out={llm.total_completions_tokens} cost={llm.estimated_cost}")
            continue
        if line == "/save":
            sid = save_session(agent.messages, agent.llm.model)
            print("saved", sid)
            continue
        if line == "/sessions":
            for item in list_sessions():
                print(f"{item['id']}  {item['saved_at']}  {item['preview']}")
            continue
        if line.startswith("/"):
            print("unknown command")
            continue
        try:
            agent.chat(
                line,
                on_token=lambda t: print(t, end="", flush=True),
                on_tool=lambda name, args: print(f"\n[tool] {name} {args}"),
            )
            print()
        except KeyboardInterrupt:
            print("\nInterrupted.")


def main():
    args = parse_args()
    if args.demo:
        from main import run_demo
        run_demo()
        return
    
    cfg = Config.from_env()
    if args.model:
        cfg.model = args.model
    if not cfg.api_key:
        print("请设置 OPENAI_API_KEY 环境变量")
        sys.exit(1)
    
    llm = LLM(
        model=cfg.model,
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        temperature=cfg.temperature,
        max_tokens = cfg.max_tokens
    )

    from pathlib import Path
    if args.yes:
        permission = Permission(allow_all=True)
    elif args.prompt:
        # 一次性模式没有人坐在键盘前。不传 ask，改动类工具会被拒绝。
        permission = Permission()
    else:
        permission = Permission(ask=ask, persist_path=Path.home() / ".myagent" / "permissions.json")

    agent = Agent(
        llm = llm,
        permission = permission,
        max_context_tokens=cfg.max_context_tokens,
    )

    if args.resume:
        loaded = load_session(args.resume)
        if not loaded:
            print("找不到这个会话",args.resume)
            sys.exit(1)
        agent.messages, loaded_model = loaded
        if not args.model:
            agent.llm.model = loaded_model
        print("resumed", args.resume)
    
    if args.prompt:
        run_once(agent,args.prompt)
        return
    repl(agent)

if __name__ == "__main__":
    main()
