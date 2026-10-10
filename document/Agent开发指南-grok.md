# 从零写一个简易 Coding Agent（代码手册）

这份手册按建造顺序写。每一阶段都给出可以放进项目里的代码，并说明这些 Python 在循环里做什么。你另开一个空目录来写，本仓库当作对照答案。

建议目录：`d:\code\myagent`。写完一阶段，再打开手册里点名的 CoreCoder 文件，看成品多处理了哪些边角。

密钥放环境变量或 `.env`，不要写进 `.py`。`.env` 不要提交到 git。

做完阶段 7，你就已经能让模型自己读文件、改代码、跑测试。后面的阶段是让这件事在更长的对话、中断和命令行里仍然成立。

---

## 0. 先看懂的两样东西

### 0.1 一条循环

模型只产出文字，以及「请调用某个工具」的结构化数据。读文件、改文件、跑命令都是你的 Python 在做。

```text
用户的话追加到 messages
循环（最多 max_rounds 次）:
    把 messages 和工具说明书发给模型
    模型没有要工具 -> 把它的文字返回给用户，结束
    模型要了工具   -> 你在本地执行，把结果追加到 messages，再循环
```

### 0.2 四种消息

`messages` 是一个列表，元素是字典。字典就是别的语言里的 map / JSON 对象。

| role | 谁写的 | 字段 |
|---|---|---|
| `system` | 你的程序 | `content`：行为规则。每轮临时拼到最前面，不长期塞进 `messages` |
| `user` | 用户 | `content`：用户这句话 |
| `assistant` | 模型 | `content`：正文。要工具时还有 `tool_calls` |
| `tool` | 你的程序 | `tool_call_id`：对应哪一次调用。`content`：工具返回的字符串 |

一次「读文件再解释」在列表里长这样（阶段 1 跑完你能在终端里看到同样的结构）：

```python
[
    {"role": "user", "content": "读一下 hello.py，用一句话说明"},
    {"role": "assistant", "content": None, "tool_calls": [
        {"id": "c1", "type": "function",
         "function": {"name": "read_file", "arguments": "{\"file_path\": \"hello.py\"}"}}
    ]},
    {"role": "tool", "tool_call_id": "c1", "content": "1\tprint('hi')"},
    {"role": "assistant", "content": "这个文件会打印 hi。"},
]
```

两条以后一直成立的约定：

1. 先写入带 `tool_calls` 的 assistant，再写入 tool。顺序反了，下一轮请求会被接口拒绝。
2. `tool_call_id` 必须等于那次调用的 `id`。同一轮可以调用两次 `read_file`，靠名字对不上。
3. 发给接口时，`arguments` 是 JSON 字符串。你在 Python 里执行工具时，用的是已经解析好的字典。

### 0.3 这几行 Python 会反复出现

```python
# 类。self 就是别的语言的 this，参数里要自己写出来。
class Agent:
    def __init__(self, llm):      # 构造函数。Agent(llm=x) 时自动进来
        self.llm = llm             # 挂到这个对象上，后面用 self.llm 取
        self.messages = []         # 每个 Agent 自己的一份历史

    def chat(self, user_input: str) -> str:
        # user_input: str 和 -> str 是类型注解，给人看的，运行时不强制检查
        self.messages.append({"role": "user", "content": user_input})
        return "ok"

# f-string：花括号里放变量
name = "read_file"
text = f"Error: unknown tool '{name}'"

# 字典查不到时用 get，不会抛异常。直接 tools[name] 查不到会 KeyError
fn = tools.get("read_file")          # 没有就是 None

# ** 把字典拆成函数参数
args = {"file_path": "hello.py"}
read_file(**args)                    # 等价于 read_file(file_path="hello.py")

# 列表推导：做成一个新列表
schemas = [t.schema() for t in tools]

# 字典推导：做成 名字 -> 对象
by_name = {t.name: t for t in tools}
```

缩进就是代码块。冒号下面缩进去的行，属于那个 `if`、`for`、`def`、`class`。

---

## 1. 用假模型把循环跑通

这一阶段不接网络。假模型按你写好的剧本回答，用来证明循环和消息配对是对的。它不会「看」工具结果，下一句是你预先写死的。真正会根据工具结果思考的，是阶段 3 的模型。

### 1.1 建目录

在 PowerShell 里：

```powershell
mkdir d:\code\myagent
cd d:\code\myagent
python -m venv .venv
.venv\Scripts\Activate.ps1
mkdir tools
```

新建空文件 `tools\__init__.py`。有这个文件，`tools` 才能被 `import`。

再新建 `hello.py`，内容就一行：

```python
print("hi")
```

本阶段新增三个文件：`llm.py`、`agent.py`、`main.py`。

### 1.2 `llm.py`：两种数据，外加一个假模型

```python
import json
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    """模型提出的一次工具调用。创建它不会读文件。"""
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """一轮模型回复。可以只有正文，也可以同时带工具调用。"""
    content: str = ""
    # 每个响应自己一份空列表。写成 tool_calls=[] 会让所有对象共用同一个列表。
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def message(self) -> dict:
        """写成 resp.message，不要加括号。拼成要放进历史的 assistant 消息。"""
        msg = {"role": "assistant", "content": self.content or None}
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        # 接口要求 arguments 是字符串，所以这里把字典转回 JSON
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for tc in self.tool_calls
            ]
        return msg


class ScriptedLLM:
    """按剧本吐回复。剧本用完还在循环，就立刻报错，避免你以为它卡住了。"""

    model = "scripted"
    total_prompt_tokens = 0
    total_completion_tokens = 0
    estimated_cost = None

    def __init__(self, script: list[LLMResponse]):
        self._turns = list(script)

    def chat(self, messages, tools=None, on_token=None, on_reasoning=None) -> LLMResponse:
        if not self._turns:
            raise RuntimeError("剧本演完了，循环还在转")
        resp = self._turns.pop(0)
        # 后面的命令行会把 on_token 传进来。假模型把整段正文一次交出去。
        if on_token and resp.content:
            on_token(resp.content)
        return resp
```

`@dataclass` 会按你写的字段生成构造函数，于是可以写 `ToolCall(id="c1", name="read_file", arguments={...})`。

`@property` 把方法伪装成字段。`resp.message` 会执行上面的函数，得到一个字典。

`list[ToolCall]` 需要 Python 3.9+。本手册按 3.10 来写。

### 1.3 `agent.py`：主循环

```python
from llm import ToolCall


class Agent:
    def __init__(self, llm, tools=None, max_rounds: int = 10):
        self.llm = llm
        # tools 是普通函数字典：{"read_file": 某个函数}
        # 阶段 2 会换成工具对象列表。这里先用函数，让循环先跑起来。
        self.tools = tools or {}
        self.messages: list[dict] = []
        self.max_rounds = max_rounds

    def chat(self, user_input: str, on_tool=None, on_token=None, on_reasoning=None) -> str:
        self.messages.append({"role": "user", "content": user_input})

        # range(10) 产生 0 到 9。变量名用 _ ，表示这里不用循环序号。
        for _ in range(self.max_rounds):
            resp = self.llm.chat(
                self.messages,
                on_token=on_token,
                on_reasoning=on_reasoning,
            )
            # 不管有没有工具，先把模型这句话记下来
            self.messages.append(resp.message)

            # 空列表在 if 里算「假」。not 空列表 就是「这次没要工具」
            if not resp.tool_calls:
                return resp.content

            for tc in resp.tool_calls:
                if on_tool:
                    on_tool(tc.name, tc.arguments)
                result = self._exec(tc)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        return "(reached maximum tool-call rounds)"

    def _exec(self, tc: ToolCall) -> str:
        fn = self.tools.get(tc.name)
        if fn is None:
            return f"Error: unknown tool '{tc.name}'"
        try:
            return fn(**tc.arguments)
        except Exception as e:
            # 工具失败变成一段文字，循环继续。模型下一轮能看见原因。
            return f"Error executing {tc.name}: {e}"
```

下划线开头的 `_exec` 是「给类内部用」的习惯，Python 并不真的禁止外部调用。

`on_tool` 是回调：调用方把自己的函数传进来，循环在执行工具前调用它。命令行后来用它打印「正在调用 read_file」。没传就是 `None`，`if on_tool` 不成立，跳过。

`max_rounds` 限制的是「问模型」的次数。一轮模型回复里仍然可以带多个工具调用。

### 1.4 `main.py`：用剧本走一遍

```python
from pathlib import Path

from agent import Agent
from llm import LLMResponse, ScriptedLLM, ToolCall


def read_file(file_path: str) -> str:
    path = Path(file_path)
    if not path.exists():
        return f"Error: {file_path} not found"
    return path.read_text(encoding="utf-8")


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
            ],
        ),
        LLMResponse(content="这个文件会打印 hi。"),
    ]
    agent = Agent(llm=ScriptedLLM(script), tools={"read_file": read_file})

    def show_tool(name, args):
        print(f"[tool] {name} {args}")

    answer = agent.chat("读一下 hello.py，用一句话说明", on_tool=show_tool)
    print("[answer]", answer)
    print("--- messages ---")
    for m in agent.messages:
        print(m)


if __name__ == "__main__":
    main()
```

`if __name__ == "__main__"` 的意思是：这个文件被直接运行时才执行 `main()`。被别的文件 import 时不执行。

在 `d:\code\myagent` 下运行：

```powershell
python main.py
```

你应该看到类似：

```text
[tool] read_file {'file_path': 'hello.py'}
[answer] 这个文件会打印 hi。
--- messages ---
{'role': 'user', ...}
{'role': 'assistant', ..., 'tool_calls': [...]}
{'role': 'tool', 'tool_call_id': 'c1', 'content': 'print("hi")\n'}
{'role': 'assistant', 'content': '这个文件会打印 hi。'}
```

把 `hello.py` 改名再跑，tool 那条的 `content` 会变成 `Error: hello.py not found`，最后一句剧本仍然会打印。这是假模型的特点：它不看结果。阶段 3 换成真模型后，它会根据 `Error:` 再决定下一步。

对照：`corecoder/agent.py` 的 `chat()`，`corecoder/demo.py` 的 `ScriptedLLM`。成品里还有权限、压缩、并行，那些先别加。

---

## 2. 把「读文件」做成正式工具

模型看不到你的函数。它看到的是一份 JSON 说明书，叫 schema。你本地真正执行的是 `execute()`。

说明书长这样（下面 `schema()` 会生成它）：

```json
{
  "type": "function",
  "function": {
    "name": "read_file",
    "description": "Read a file's contents with line numbers.",
    "parameters": {
      "type": "object",
      "properties": {
        "file_path": {"type": "string", "description": "Path to the file"}
      },
      "required": ["file_path"]
    }
  }
}
```

`description` 是模型决定「要不要调用它」的主要依据，要写它适合干什么。

### 2.1 `tools/base.py`

```python
class Tool:
    name: str
    description: str
    parameters: dict

    def execute(self, **kwargs) -> str:
        raise NotImplementedError

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
```

子类不写 `execute` 就调用时会抛 `NotImplementedError`，用来提醒你这个工具还没实现。

### 2.2 `tools/read.py`

```python
from pathlib import Path

from .base import Tool


class ReadFileTool(Tool):
    name = "read_file"
    description = (
        "Read a file's contents with line numbers. "
        "Always read a file before editing it."
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to the file"},
            "offset": {"type": "integer", "description": "Start line, 1-based. Default 1."},
            "limit": {"type": "integer", "description": "Max lines. Default 2000."},
        },
        "required": ["file_path"],
    }

    def execute(self, file_path: str, offset: int = 1, limit: int = 2000) -> str:
        try:
            path = Path(file_path).expanduser().resolve()
            if not path.exists():
                return f"Error: {file_path} not found"
            if not path.is_file():
                return f"Error: {file_path} is a directory, not a file"

            # errors="replace" 遇到坏字节就换成替代字符，不让解码错误打断循环
            text = path.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            start = max(0, offset - 1)
            chunk = lines[start:start + limit]
            # 行号从 1 开始，方便模型和人对照
            numbered = [f"{start + i + 1}\t{line}" for i, line in enumerate(chunk)]
            result = "\n".join(numbered)
            if len(lines) > start + limit:
                result += f"\n... ({len(lines)} lines total, showing {start + 1}-{start + len(chunk)})"
            return result or "(empty file)"
        except Exception as e:
            return f"Error: {e}"
```

`from .base import Tool` 开头的点表示「当前包」，也就是 `tools`。所以这个文件要通过 `import tools.read` 来用，不要在资源管理器里对 `read.py` 点「运行」。

`Path.expanduser()` 把 `~` 换成用户主目录。`resolve()` 变成绝对路径。

`enumerate(chunk)` 同时给出下标和元素：`(0, 第一行), (1, 第二行), ...`。

切片 `lines[start:start + limit]` 含开头、不含结尾。

工具的返回值永远是字符串。失败也返回以 `Error:` 开头的一句人话，不把堆栈抛进循环。

### 2.3 `tools/__init__.py`

把原来的空文件换成：

```python
from .read import ReadFileTool

ALL_TOOLS = [
    ReadFileTool(),
]
```

`ReadFileTool()` 是在创建对象。列表里放的是对象，不是类本身。

### 2.4 改 `agent.py` 的三处

**换成这个 `__init__`：**

```python
def __init__(self, llm, tools=None, max_rounds: int = 10):
    self.llm = llm
    # 调用方传了 tools=[] 表示「一个工具都不要」，要保留空列表。
    # 所以用 is not None，不用 `tools or ALL_TOOLS`。
    # 空列表在布尔判断里是假，or 会错误地换成默认工具。
    if tools is None:
        from tools import ALL_TOOLS
        tools = ALL_TOOLS
    self.tools = tools
    self._tool_by_name = {t.name: t for t in self.tools}
    self.messages = []
    self.max_rounds = max_rounds
```

**在 `chat` 里，把 `self.llm.chat(...)` 改成把说明书也传过去：**

```python
resp = self.llm.chat(
    self.messages,
    tools=self._tool_schemas(),
    on_token=on_token,
    on_reasoning=on_reasoning,
)
```

**用下面两个方法替换原来的 `_exec`：**

```python
def _tool_schemas(self) -> list[dict]:
    return [t.schema() for t in self.tools]

def _exec(self, tc) -> str:
    tool = self._tool_by_name.get(tc.name)
    if tool is None:
        return f"Error: unknown tool '{tc.name}'"
    try:
        return tool.execute(**tc.arguments)
    except TypeError as e:
        # 少传了 file_path、或多传了不存在的参数，会在这里被接住
        return f"Error: bad arguments for {tc.name}: {e}"
    except Exception as e:
        return f"Error executing {tc.name}: {e}"
```

`TypeError` 单独接，是因为参数不匹配和工具内部自己写错，都可能是 `TypeError`。这一版先合在一起也行。CoreCoder 用 `inspect.signature(tool.execute).bind(**tc.arguments)` 先检查参数名，再调用 `execute`，这样工具内部的 `TypeError` 不会被说成「你参数传错了」。你可以在这一阶段就加上，放在真正调用之前：

```python
import inspect

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
    except Exception as e:
        return f"Error executing {tc.name}: {e}"
```

`signature(...).bind(...)` 只检查参数能不能对上名字，不检查值的类型，也不执行工具。

### 2.5 改 `main.py` 的工具注册

删掉 `main.py` 里手写的 `read_file` 函数。创建 Agent 时不再传 `tools=`，让它用 `ALL_TOOLS`：

```python
agent = Agent(llm=ScriptedLLM(script))
```

再跑 `python main.py`。输出应和阶段 1 类似，只是文件内容前面多了行号，例如 `1\tprint("hi")`。

对照：`corecoder/tools/base.py`、`corecoder/tools/read.py`。

---

## 3. 接上真模型（先不要流式）

这一阶段 `LLM.chat()` 一次把整段回复等回来。终端会停一会儿，然后整段出现。边生成边打印放到阶段 8。非流式已经足够完成「读文件、解释代码」。

```powershell
pip install openai python-dotenv
```

### 3.1 环境变量

在 `d:\code\myagent` 新建 `.env`（这个文件不要进 git）：

```text
OPENAI_API_KEY=你的key
OPENAI_BASE_URL=https://api.deepseek.com
MYAGENT_MODEL=deepseek-chat
```

PowerShell 里也可以不建文件，直接：

```powershell
$env:OPENAI_API_KEY = "你的key"
$env:OPENAI_BASE_URL = "https://api.deepseek.com"
$env:MYAGENT_MODEL = "deepseek-chat"
```

本地 Ollama 则是 `OPENAI_BASE_URL=http://localhost:11434/v1`，`OPENAI_API_KEY=ollama`，`MYAGENT_MODEL` 填你拉下来的模型名。`openai` 这个包能打任何兼容该协议的地址，换服务商通常就是换这三个值。

### 3.2 `config.py`

```python
import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass
class Config:
    model: str
    api_key: str
    base_url: str | None
    max_tokens: int = 4096
    temperature: float = 0.0
    max_context_tokens: int = 128_000

    @classmethod
    def from_env(cls) -> "Config":
        # override=False：系统里已经有的环境变量优先，不被 .env 盖掉
        load_dotenv(override=False)
        return cls(
            model=os.getenv("MYAGENT_MODEL", "deepseek-chat"),
            api_key=os.getenv("OPENAI_API_KEY", ""),
            base_url=os.getenv("OPENAI_BASE_URL") or None,
            max_tokens=int(os.getenv("MYAGENT_MAX_TOKENS", "4096")),
            temperature=float(os.getenv("MYAGENT_TEMPERATURE", "0")),
            max_context_tokens=int(os.getenv("MYAGENT_MAX_CONTEXT", "128000")),
        )
```

`@classmethod` 表示这个方法挂在类上，用 `Config.from_env()` 调用，不需要先有一个 Config 对象。第一个参数习惯写 `cls`，代表类本身。`return cls(...)` 就是在创建一份配置。

`os.getenv("KEY", "默认值")` 在变量不存在时返回默认值。

`128_000` 里的下划线只是方便读，值和 `128000` 相同。

### 3.3 在 `llm.py` 末尾加上真客户端

文件顶部补上：

```python
from openai import OpenAI
```

然后加上这个类（`ScriptedLLM` 留着，后面演示和测试还用它）：

```python
class LLM:
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
        self.total_completion_tokens = 0

    def chat(self, messages, tools=None, on_token=None, on_reasoning=None) -> LLMResponse:
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            kwargs["tools"] = tools

        # **kwargs 把字典拆成 create(model=..., messages=..., ...)
        resp = self.client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message

        calls = []
        for tc in msg.tool_calls or []:
            raw = tc.function.arguments or "{}"
            try:
                args = json.loads(raw)
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

        usage = getattr(resp, "usage", None)
        if usage:
            self.total_prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
            self.total_completion_tokens += getattr(usage, "completion_tokens", 0) or 0

        text = msg.content or ""
        if on_token and text:
            on_token(text)
        return LLMResponse(content=text, tool_calls=calls)
```

这里发生了两步转换：

- 接口给的 `arguments` 是字符串 `'{"file_path": "hello.py"}'`，`json.loads` 把它变成字典，后面 `execute(**arguments)` 才能用。
- 写回历史时，`LLMResponse.message` 又用 `json.dumps` 变回字符串。这个来回是协议要求的，漏一边，下一轮就会 400。

`msg.tool_calls or []`：没有工具调用时这个字段常常是 `None`。`None or []` 的结果是 `[]`，后面的 `for` 就不会报错。

`getattr(resp, "usage", None)`：对象上没有 `usage` 这个属性时返回 `None`，不抛 `AttributeError`。有些服务商把 token 数字填成 `null`，所以后面还要 `or 0`，避免 `整数 + None`。

### 3.4 改 `main.py`，有 key 就走真模型

```python
import os

from agent import Agent
from config import Config
from llm import LLM, LLMResponse, ScriptedLLM, ToolCall


def run_demo():
    script = [
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="c1", name="read_file", arguments={"file_path": "hello.py"})],
        ),
        LLMResponse(content="这个文件会打印 hi。"),
    ]
    agent = Agent(llm=ScriptedLLM(script))
    print(agent.chat("读一下 hello.py，用一句话说明", on_tool=lambda n, a: print(f"[tool] {n} {a}")))


def main():
    if os.getenv("MYAGENT_DEMO") == "1":
        run_demo()
        return

    cfg = Config.from_env()
    if not cfg.api_key:
        print("没有 OPENAI_API_KEY。要看假模型循环，先执行：$env:MYAGENT_DEMO='1'; python main.py")
        return

    llm = LLM(model=cfg.model, api_key=cfg.api_key, base_url=cfg.base_url,
              temperature=cfg.temperature, max_tokens=cfg.max_tokens)
    agent = Agent(llm=llm)
    answer = agent.chat(
        "读一下 hello.py，用三句话说明它做什么",
        on_tool=lambda name, args: print(f"\n[tool] {name} {args}"),
    )
    print("\n[answer]", answer)


if __name__ == "__main__":
    main()
```

`lambda name, args: print(...)` 是匿名函数，等价于先 `def show(name, args): print(...)` 再把 `show` 传进去。

运行：

```powershell
python main.py
```

正常的话先打印一行 `[tool] read_file {...}`，然后是模型根据文件内容写的三句话。如果它没调用工具、直接瞎编文件内容，先别改循环，检查系统提示词——下一阶段会把「改之前先读、读的时候用工具」写进去。这一阶段可以临时在 `chat()` 里、调用模型之前，把消息改成：

```python
messages = [
    {"role": "system", "content": "You are a coding assistant. Use read_file to inspect files before answering about them."},
    *self.messages,
]
resp = self.llm.chat(messages, tools=self._tool_schemas(), ...)
```

`*self.messages` 把历史里的每条字典拆开，放进这个新列表。`self.messages` 本身不变，system 没有被存进去。阶段 4 会把这件事收成 `_full_messages()`。

对照：`corecoder/llm.py` 里的 `LLM` 类前半，`corecoder/config.py` 里从环境变量读取的那种写法。

---

## 4. 让它能改代码

两个写工具，分工写进系统提示词：

- `write_file`：新建文件，或整文件覆盖。
- `edit_file`：替换文件里唯一的一段原文。

行号补丁很容易改错地方，因为模型只要数偏一行就贴错位置。`edit_file` 改成：模型给出 `old_string` 和 `new_string`，这段原文必须在文件里恰好出现一次。

### 4.1 `prompt.py`

```python
import os
import platform


def system_prompt(tools) -> str:
    tool_list = "\n".join(f"- {t.name}: {t.description}" for t in tools)
    uname = platform.uname()
    return f"""You are a coding assistant running in the user's terminal.
You write code, fix bugs, explain code, and run commands by calling tools.

# Environment
- Working directory: {os.getcwd()}
- OS: {uname.system} {uname.release} ({uname.machine})
- Python: {platform.python_version()}

# Tools
{tool_list}

# Rules
1. Read a file before editing it.
2. Use edit_file for small changes. Use write_file only for new files or full rewrites.
3. In edit_file, old_string must appear exactly once. Include surrounding lines to make it unique.
4. After changing code, run the relevant tests or commands.
5. If the request is ambiguous, ask instead of guessing.
"""
```

三引号字符串可以跨行。`f"""...{os.getcwd()}..."""` 会在生成提示词时把当前目录嵌进去。模型看不到你的电脑，这些要你告诉它。

### 4.2 `tools/write.py`

```python
from pathlib import Path

from .base import Tool


class WriteFileTool(Tool):
    name = "write_file"
    description = (
        "Create a new file or completely overwrite an existing one. "
        "For small edits to existing files, prefer edit_file."
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path for the file"},
            "content": {"type": "string", "description": "Full file content"},
        },
        "required": ["file_path", "content"],
    }

    def execute(self, file_path: str, content: str) -> str:
        try:
            path = Path(file_path).expanduser().resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            n_lines = content.count("\n") + (0 if content.endswith("\n") or not content else 1)
            return f"Wrote {n_lines} lines to {file_path}"
        except Exception as e:
            return f"Error: {e}"
```

`mkdir(parents=True, exist_ok=True)`：上级目录一并创建；目录已经在也不报错。

### 4.3 `tools/edit.py`

```python
import difflib
from pathlib import Path

from .base import Tool


class EditFileTool(Tool):
    name = "edit_file"
    description = (
        "Replace an exact string in a file. "
        "old_string must appear exactly once. Include surrounding lines to make it unique."
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to the file"},
            "old_string": {"type": "string", "description": "Exact text to find, must be unique"},
            "new_string": {"type": "string", "description": "Replacement text"},
        },
        "required": ["file_path", "old_string", "new_string"],
    }

    def execute(self, file_path: str, old_string: str, new_string: str) -> str:
        try:
            path = Path(file_path).expanduser().resolve()
            if not path.exists():
                return f"Error: {file_path} not found"
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return f"Error: {file_path} is not a UTF-8 text file"

            found = content.count(old_string)
            if found == 0:
                preview = content[:500] + ("..." if len(content) > 500 else "")
                return (
                    f"Error: old_string not found in {file_path}.\n"
                    f"File starts with:\n{preview}"
                )
            if found > 1:
                return (
                    f"Error: old_string appears {found} times in {file_path}. "
                    "Include more surrounding lines to make it unique."
                )

            new_content = content.replace(old_string, new_string, 1)
            path.write_text(new_content, encoding="utf-8")
            diff = _unified_diff(content, new_content, str(path))
            return f"Edited {file_path}\n{diff}"
        except Exception as e:
            return f"Error: {e}"


def _unified_diff(old: str, new: str, filename: str) -> str:
    diff = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        n=3,
    )
    text = "".join(diff)
    if len(text) > 3000:
        text = text[:2500] + "\n... (diff truncated)\n"
    return text
```

三种结果都要让模型能继续干活：

- 0 次：把文件开头退回去，它照着真实文本重新抄 `old_string`。
- 多于 1 次：叫它多带几行，使这段成为唯一。文件一个字节都不变。
- 恰好 1 次：`replace(..., 1)` 只换第一处（此时已经证明只有一处），再返回 diff。模型下一轮能核对自己改了什么。

`difflib.unified_diff` 是标准库，产出和 `git diff` 类似的文本。

### 4.4 注册，并让每轮请求带上系统提示词

`tools/__init__.py`：

```python
from .edit import EditFileTool
from .read import ReadFileTool
from .write import WriteFileTool

ALL_TOOLS = [
    ReadFileTool(),
    WriteFileTool(),
    EditFileTool(),
]
```

`agent.py` 顶部：

```python
from prompt import system_prompt
```

`__init__` 在建好 `self.tools` 之后加一行：

```python
self._system = system_prompt(self.tools)
```

新增方法：

```python
def _full_messages(self) -> list[dict]:
    # 新列表 = 一条 system + 原来的历史。self.messages 里仍然没有 system。
    return [{"role": "system", "content": self._system}] + self.messages
```

`chat` 里发给模型的第一个参数，从 `self.messages` 改成 `self._full_messages()`。

手动验一次写工具（不经过模型）：

```powershell
python -c "from tools.edit import EditFileTool; print(EditFileTool().execute('hello.py', 'print(\"hi\")', 'print(\"hello\")'))"
```

`hello.py` 应变成 `print("hello")`。再执行一次同一句，因为原文已经不在了，应看到 `old_string not found`，文件不再变化。验完可以把文件改回 `print("hi")`。

然后用真模型跑：

```powershell
python main.py
```

把 `main()` 里的那句提问临时改成：`把 hello.py 里的 hi 改成 hello，改完读一遍确认`。你应看到 `read_file`，然后 `edit_file`，然后可能再一次 `read_file`，最后是一句人话。

对照：`corecoder/tools/edit.py`、`corecoder/tools/write.py`、`corecoder/prompt.py`。

---

## 5. 会改磁盘的调用，先问人

只读工具模型一调就执行。`write_file` 和 `edit_file`（后面还有 `bash`）先问：允许这一次、这个工具一直允许、还是拒绝。

拒绝也写成一条普通 tool 消息，例如 `Permission denied: ...`。模型下一轮看得见，循环不会停在一个永远等不到的键盘输入上。

没人可问的时候（脚本、测试、你把 Agent 嵌进别的程序），改动类调用直接拒绝。另给一个「全部允许」开关，给以后的 `--yes` 用。默认放行，和「没人可问所以拒绝」，是两种不同的构造方式。

### 5.1 `permissions.py`

```python
import json
from pathlib import Path

# 这些工具不改你的源码文件，调用时不询问
READ_ONLY = {"read_file", "glob", "grep", "todo_write"}


class Permission:
    def __init__(self, ask=None, allow_all: bool = False, persist_path: Path | None = None):
        # ask(tool_name, arguments) -> "once" | "always" | "deny"
        self.ask = ask
        self.allow_all = allow_all
        self._always: set[str] = set()
        self._persist_path = persist_path
        if persist_path is not None and persist_path.exists():
            try:
                saved = json.loads(persist_path.read_text(encoding="utf-8"))
                self._always = {x for x in saved.get("always", []) if isinstance(x, str)}
            except (OSError, ValueError):
                self._always = set()

    def check(self, tool_name: str, arguments: dict) -> str | None:
        """返回 None 表示放行。返回字符串表示拒绝，这段文字会变成 tool 消息。"""
        if tool_name in READ_ONLY or self.allow_all or tool_name in self._always:
            return None
        if self.ask is None:
            return (
                f"Permission denied: {tool_name} changes state and nobody can approve it. "
                "Tell the user the exact step so they can run it themselves."
            )
        verdict = self.ask(tool_name, arguments)
        if verdict == "always":
            self._always.add(tool_name)
            self._save()
            return None
        if verdict == "once":
            return None
        return (
            f"Permission denied: the user refused this {tool_name} call. "
            "Do not retry the same call; ask what they want instead."
        )

    def _save(self) -> None:
        if self._persist_path is None:
            return
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"always": sorted(self._always)}
        self._persist_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
```

`set` 是集合，元素不重复。`x in self._always` 用来判断这个工具名是否已经「一直允许」。

`check` 的返回值约定要记牢：`None` 才是允许。任何字符串都是拒绝理由。后面钩子也沿用这条约定。

### 5.2 接到循环上

`agent.py` 的 `__init__` 增加参数 `permission=None`，并保存：

```python
def __init__(self, llm, tools=None, max_rounds: int = 10, permission=None):
    ...
    self.permission = permission
```

新增：

```python
def _permit(self, tc) -> str | None:
    if self.permission is None:
        return None
    return self.permission.check(tc.name, tc.arguments)
```

`chat` 里，原来直接 `_exec` 的地方换成：

```python
for tc in resp.tool_calls:
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
```

`result is None` 用的是「是不是 None」，不用 `if not result`。工具正常返回的空字符串也是「假」，但空字符串是执行结果，不是「请放行」。只有 `None` 表示还没执行、可以执行。

### 5.3 在 `main.py` 里问一句

```python
from pathlib import Path
from permissions import Permission

def ask(tool_name, arguments):
    print(f"\n允许 {tool_name} {arguments} 吗？ y=一次  a=这个工具一直允许  其他=拒绝")
    answer = input("> ").strip().lower()
    if answer in ("y", "yes"):
        return "once"
    if answer in ("a", "always"):
        return "always"
    return "deny"

permission = Permission(
    ask=ask,
    persist_path=Path.home() / ".myagent" / "permissions.json",
)
agent = Agent(llm=llm, permission=permission)
```

`Path.home()` 是用户主目录，Windows 上类似 `C:\Users\你的用户名`。

再跑改文件的提问。出现 `edit_file` 时会停下来等你输入。输入 `n` 回车后，文件应保持原样，模型会收到拒绝文字并通常用一句话收场。

`permission=None`（不传这个参数）表示跳过这层检查，阶段 1 的假模型演示仍然直接执行。这和 `Permission()`（没传 `ask`）不同：后者会拒绝一切改动类工具。

对照：`corecoder/permissions.py`，以及 `corecoder/agent.py` 的 `_permit()`。

---

## 6. 让它自己找文件

### 6.1 `tools/glob_tool.py`

文件名不要叫 `glob.py`，否则会挡住标准库的 `glob` 模块。

```python
from pathlib import Path

from .base import Tool

SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}


class GlobTool(Tool):
    name = "glob"
    description = "Find files by glob pattern, for example **/*.py."
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern, e.g. **/*.py"},
            "path": {"type": "string", "description": "Directory to search. Default is cwd."},
        },
        "required": ["pattern"],
    }

    def execute(self, pattern: str, path: str = ".") -> str:
        try:
            base = Path(path).expanduser().resolve()
            if not base.exists():
                return f"Error: {path} not found"
            if not base.is_dir():
                return f"Error: {path} is not a directory"
            hits = []
            for item in base.glob(pattern):
                if any(part in SKIP for part in item.parts):
                    continue
                hits.append(item)
            hits.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
            shown = hits[:100]
            lines = [str(p) for p in shown]
            text = "\n".join(lines)
            if len(hits) > 100:
                text += f"\n... ({len(hits)} matches, showing first 100)"
            return text or "No files matched."
        except Exception as e:
            return f"Error: {e}"
```

`any(...)` 里只要有一个目录名落在 `SKIP` 里就为真。`lambda p: p.stat().st_mtime` 是按修改时间排序用的小函数。

### 6.2 `tools/grep.py`

```python
import re
from pathlib import Path

from .base import Tool

SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}


class GrepTool(Tool):
    name = "grep"
    description = "Search file contents with a regex. Returns path, line number, and the line."
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern"},
            "path": {"type": "string", "description": "File or directory. Default is cwd."},
            "include": {"type": "string", "description": "Only files matching this glob, e.g. *.py"},
        },
        "required": ["pattern"],
    }

    def execute(self, pattern: str, path: str = ".", include: str | None = None) -> str:
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"Error: invalid regex: {e}"
        try:
            base = Path(path).expanduser().resolve()
            if not base.exists():
                return f"Error: {path} not found"
            files = [base] if base.is_file() else list(base.rglob(include or "*"))
            matches = []
            for file in files:
                if not file.is_file():
                    continue
                if any(part in SKIP for part in file.parts):
                    continue
                try:
                    text = file.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for i, line in enumerate(text.splitlines(), start=1):
                    if regex.search(line):
                        matches.append(f"{file}:{i}:{line}")
                        if len(matches) >= 50:
                            return "\n".join(matches) + "\n... (stopped at 50 matches)"
            return "\n".join(matches) or "No matches."
        except Exception as e:
            return f"Error: {e}"
```

`re.compile` 把正则编译成可重复使用的对象。用户给的 pattern 不合法时，`re.error` 变成一句错误返回。

`enumerate(..., start=1)` 让行号从 1 开始。

结果最多 50 条。工具输出从这里开始养成一个习惯：太长就截断，并写明截断了。后面的 bash、抓网页、上下文压缩都是同一手法。测试失败的最后几行常常在输出尾部，所以阶段 7 的截断会留头又留尾，不只留开头。

### 6.3 注册

`tools/__init__.py` 的 `ALL_TOOLS` 加上 `GlobTool()` 和 `GrepTool()`。它们的名字已经在 `permissions.py` 的 `READ_ONLY` 里，不会弹确认。

改 `__init__` 之后，系统提示词是在 `Agent()` 创建时生成的。新开一次进程才会把 `glob`、`grep` 写进提示词。

手动看一眼：

```powershell
python -c "from tools.grep import GrepTool; print(GrepTool().execute('print', '.', '*.py'))"
```

对照：`corecoder/tools/glob_tool.py`、`corecoder/tools/grep.py`。

---

## 7. 让它跑命令

你在 Windows 上。`subprocess` 使用 `shell=True` 时走的是 `cmd.exe`，模型和文档里常见的 `ls`、`&&` 会失败。本机装了 Git for Windows 时，用它自带的 `bash.exe -c` 来跑。

### 7.1 `shell_util.py`

```python
import os
import shutil
import subprocess


def git_bash() -> str | None:
    if os.name != "nt":
        return None
    candidate = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Git", "bin", "bash.exe")
    if os.path.isfile(candidate):
        return candidate
    git = shutil.which("git")
    if git:
        derived = os.path.join(os.path.dirname(os.path.dirname(git)), "bin", "bash.exe")
        if os.path.isfile(derived):
            return derived
    return None


def run_shell(command: str, **kwargs) -> subprocess.CompletedProcess:
    bash = git_bash()
    if bash:
        # 列表形式 + shell=False，命令字符串交给 bash -c，不经过 cmd.exe
        return subprocess.run([bash, "-c", command], shell=False, **kwargs)
    return subprocess.run(command, shell=True, **kwargs)
```

`os.name != "nt"` 在 macOS / Linux 上为真，那里的 `shell=True` 已经是 `/bin/sh`，直接用即可。

`**kwargs` 让 `run_shell("ls", capture_output=True, text=True, timeout=30)` 里多出来的参数原样传给 `subprocess.run`。

### 7.2 `tools/bash.py`

```python
import os
import re
import subprocess

from shell_util import run_shell
from .base import Tool

# 先放在模块级变量里。阶段 11 并发之后要改成「每个线程一份」，否则两条命令会抢同一个目录。
_cwd: str | None = None

_DANGEROUS = [
    (r"\brm\s+(-\w*)?-r\w*\s+(/|~|\$HOME)", "recursive delete on home or root"),
    (r"\brm\b(?=(?:.*\s)?-\w*[rR])(?=(?:.*\s)?-\w*f)", "force recursive delete"),
    (r"\bmkfs\b", "format filesystem"),
    (r"\bdd\s+.*of=/dev/", "raw disk write"),
    (r":\(\)\s*\{.*:\|:.*\}", "fork bomb"),
    (r"\bcurl\b.*\|\s*(sudo\s+)?(ba)?sh\b", "pipe curl to shell"),
    (r"\bwget\b.*\|\s*(sudo\s+)?(ba)?sh\b", "pipe wget to shell"),
]


class BashTool(Tool):
    name = "bash"
    description = (
        "Run a shell command. Returns stdout, stderr, and the exit code. "
        "Use it for tests, git, and other commands."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The command to run"},
            "timeout": {"type": "integer", "description": "Timeout in seconds. Default 120."},
        },
        "required": ["command"],
    }

    def execute(self, command: str, timeout: int = 120) -> str:
        reason = _danger(command)
        if reason:
            return f"Blocked: {reason}\nCommand: {command}"

        global _cwd
        cwd = _cwd or os.getcwd()
        try:
            proc = run_shell(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                cwd=cwd,
            )
        except subprocess.TimeoutExpired:
            return f"Error: timed out after {timeout}s"
        except Exception as e:
            return f"Error running command: {e}"

        if proc.returncode == 0:
            _cwd = _track_cd(command, cwd)

        out = proc.stdout or ""
        if proc.stderr:
            out += f"\n[stderr]\n{proc.stderr}"
        if proc.returncode != 0:
            out += f"\n[exit code: {proc.returncode}]"
        if len(out) > 15000:
            out = out[:6000] + f"\n\n... truncated ({len(out)} chars total) ...\n\n" + out[-3000:]
        return out.strip() or "(no output)"


def _danger(command: str) -> str | None:
    for pattern, reason in _DANGEROUS:
        if re.search(pattern, command):
            return reason
    return None


def _track_cd(command: str, cwd: str) -> str:
    """只跟踪一条以 cd 开头、或用 && / ; 串起来的 cd。够用即可。"""
    current = cwd
    # 用 && 和 ; 切开。引号里的分隔符这里先不处理，成品见 corecoder/tools/bash.py
    for part in re.split(r"&&|;", command):
        words = part.strip().split()
        if not words or words[0] != "cd":
            continue
        target = words[1] if len(words) > 1 else "~"
        target = os.path.expanduser(target)
        new_dir = target if os.path.isabs(target) else os.path.normpath(os.path.join(current, target))
        if os.path.isdir(new_dir):
            current = new_dir
    return current
```

`global _cwd` 表示这个函数要改模块顶部的那个变量，而不是新建一个同名局部变量。

危险命令名单防的是手滑。它挡不住换一种写法，也不是安全沙箱。Agent 只在你自己的机器上、执行你自己的指令时，这份名单够用。

`bash` 不在 `READ_ONLY` 里，所以阶段 5 的询问会罩住它。

注册：`ALL_TOOLS` 加上 `BashTool()`。

验三条：

```powershell
python -c "from tools.bash import BashTool; t=BashTool(); print(t.execute('python -c \"print(1+1)\"'))"
python -c "from tools.bash import BashTool; print(BashTool().execute('python -c \"import time; time.sleep(5)\"', timeout=1))"
python -c "from tools.bash import BashTool; print(BashTool().execute('rm -rf ~'))"
```

期望分别是：输出里有 `2`；返回超时错误；返回 `Blocked`，并且没有真的执行。

然后把 `main()` 的提问换成一个完整任务，例如：新建 `add.py`，里面的 `add(a, b)` 写成了减法，让 Agent 找到它、改对、用 bash 跑一段断言。这是第一条「它真的会干活」的基线。

对照：`corecoder/shell.py`、`corecoder/tools/bash.py`。成品的 `cd` 跟踪会处理引号和括号，教学版用简单切分，先把命令跑通。

---

## 8. 流式输出、断线重试

非流式要等模型生成完才有第一个字。流式接口把回复切成很多小块推过来。正文可以边到边打印。工具参数也会被切开，例如先到 `{"file_`，再到 `path": "hello.py"}`。拼完之前它不是合法 JSON，只能先按字符串接起来，流结束再 `json.loads`。

同一轮可以有多个工具调用，小块还会交错。用「序号 → {id, 名字, 参数字符串}」攒，最后按序号排序。

思考模型还有一块思考过程（字段名常见 `reasoning_content` 或 `reasoning`）。可以打印，不要写进 `messages`。很多服务商拒绝你把思考过程原样发回去。

重试只针对暂时故障：限流 429、超时、连接断开、5xx。间隔 1 秒、2 秒、4 秒，最多 3 次。其余 4xx（key 错、模型名错、参数错）直接抛出。流读到一半断了，整次请求重发。这时工具还没执行，重发是安全的。屏幕上已经打出的半截字不会自动擦掉。

把 `llm.py` 里 `LLM` 的 `chat` 换成下面这一版，并新增 `_drain`、`_call_with_retry`。`__init__` 不用改。文件顶部补上：

```python
import time
from openai import APIConnectionError, APIError, APITimeoutError, BadRequestError, RateLimitError
```

```python
def chat(self, messages, tools=None, on_token=None, on_reasoning=None) -> LLMResponse:
    params = {
        "model": self.model,
        "messages": messages,
        "stream": True,
        "temperature": self.temperature,
        "max_tokens": self.max_tokens,
        # 让最后一个片段带上 token 用量。对方不认识这个字段时，下面会删掉再试一次。
        "stream_options": {"include_usage": True},
    }
    if tools:
        params["tools"] = tools

    last_err = None
    for attempt in range(3):
        try:
            stream = self._call_with_retry(params)
            return self._drain(stream, on_token, on_reasoning)
        except BadRequestError:
            if "stream_options" in params:
                params.pop("stream_options")
                continue
            raise
        except (RateLimitError, APITimeoutError, APIConnectionError) as e:
            last_err = e
        except APIError as e:
            status = getattr(e, "status_code", None)
            if not status or status < 500:
                raise
            last_err = e
        if attempt < 2:
            time.sleep(2 ** attempt)
    raise last_err


def _drain(self, stream, on_token, on_reasoning) -> LLMResponse:
    content_parts: list[str] = []
    # index 是本轮第几个工具调用。碎片可能交错到来，所以按序号分桶。
    buckets: dict[int, dict] = {}
    prompt_tok = 0
    completion_tok = 0

    for chunk in stream:
        usage = getattr(chunk, "usage", None)
        if usage:
            prompt_tok = getattr(usage, "prompt_tokens", 0) or 0
            completion_tok = getattr(usage, "completion_tokens", 0) or 0
        if not getattr(chunk, "choices", None):
            continue
        delta = chunk.choices[0].delta

        reasoning = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
        if reasoning and on_reasoning:
            on_reasoning(reasoning)

        if getattr(delta, "content", None):
            content_parts.append(delta.content)
            if on_token:
                on_token(delta.content)

        if getattr(delta, "tool_calls", None):
            for piece in delta.tool_calls:
                bucket = buckets.setdefault(piece.index, {"id": "", "name": "", "args": ""})
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
        calls.append(ToolCall(id=raw["id"], name=raw["name"], arguments=args))

    self.total_prompt_tokens += prompt_tok
    self.total_completion_tokens += completion_tok
    return LLMResponse(content="".join(content_parts), tool_calls=calls)


def _call_with_retry(self, params: dict, max_retries: int = 3):
    """只负责把『流对象』要回来。流读到一半断开，由 chat() 的外层重试。"""
    for attempt in range(max_retries):
        try:
            return self.client.chat.completions.create(**params)
        except (RateLimitError, APITimeoutError, APIConnectionError):
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)
        except APIError as e:
            status = getattr(e, "status_code", None)
            if status and status >= 500 and attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
```

`dict.setdefault(key, 默认)`：这个序号第一次出现时放进一个空桶，并返回这个桶；已经有了就直接返回原来的桶。

`sorted(buckets)` 按 0、1、2 的顺序取出序号。字典自己的遍历顺序不一定是调用顺序。

`main.py` 里给 `chat` 加上逐字打印：

```python
answer = agent.chat(
    "读一下 hello.py，用三句话说明它做什么",
    on_token=lambda text: print(text, end="", flush=True),
    on_tool=lambda name, args: print(f"\n[tool] {name} {args}"),
)
```

`print(..., end="", flush=True)`：不换行，并且立刻刷到屏幕上，字才会一段段出现。

费用可以先做个简单属性，加在 `LLM` 上。单价是「每百万 token」的输入价和输出价，查不到就返回 `None`，界面上显示未知，不要显示成 0 美元。

```python
_PRICING = {
    "deepseek-chat": (0.27, 1.10),
    "gpt-4o-mini": (0.15, 0.6),
}

@property
def estimated_cost(self):
    rates = _PRICING.get(self.model)
    if not rates:
        return None
    in_rate, out_rate = rates
    return (
        self.total_prompt_tokens * in_rate / 1_000_000
        + self.total_completion_tokens * out_rate / 1_000_000
    )
```

对照：`corecoder/llm.py` 的 `_drain`、`_call_with_retry`，以及 `chat` 里包住整次流的循环。这个文件长，是长在碎片拼接和各种失败分支上。成品还会根据 400 的报错文本，把 `max_tokens` 改写成某些新模型才接受的 `max_completion_tokens`。你这版先把流拼对、把 5xx 重试做上。

---

## 9. 对话变长了还能继续

模型有上下文上限。读文件和跑测试的输出最容易把窗口撑满。压缩分三档，同一次检查里可以连续做：

1. 大约用到容量的 50%：超长的 tool 消息截成「前 3 行 + 省略说明 + 后 3 行」。不调用模型。
2. 大约 70%，并且消息超过 10 条：较早的消息交给模型总结，最近约 8 条原文留下。
3. 大约 90%：再总结一次，只留最近约 4 条。

切历史时有一个必踩的接口限制：每条 `role=tool` 的消息，前面必须还有那条带着对应 `tool_calls` 的 assistant。从「倒数第 N 条」一刀切开，切点正好落在 tool 结果上，下一次请求会 400。切点若落在 tool 消息上，就往前移，直到保留段的第一条是那条 assistant。

### 9.1 `context.py`

```python
import math
import re

_CJK = re.compile(r"[一-鿿]")


def estimate_tokens(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        text = m.get("content") or ""
        if text:
            total += _approx(text)
        if m.get("tool_calls"):
            total += _approx(str(m["tool_calls"]))
    return total


def _approx(text: str) -> int:
    # 粗估，只用来决定要不要压缩。接口返回的 usage 才是真实用量。
    cjk = len(_CJK.findall(text))
    rest = len(text) - cjk
    return math.ceil(cjk / 1.5) + int(rest / 3)


class ContextManager:
    def __init__(self, max_tokens: int = 128_000):
        self.max_tokens = max_tokens
        self._snip_at = int(max_tokens * 0.50)
        self._summarize_at = int(max_tokens * 0.70)
        self._collapse_at = int(max_tokens * 0.90)

    def maybe_compress(self, messages: list[dict], llm=None) -> bool:
        current = estimate_tokens(messages)
        changed = False
        if current > self._snip_at and self._snip(messages):
            changed = True
            current = estimate_tokens(messages)
        if current > self._summarize_at and len(messages) > 10 and self._summarize(messages, llm, keep_recent=8):
            changed = True
            current = estimate_tokens(messages)
        if current > self._collapse_at and len(messages) > 4:
            self._summarize(messages, llm, keep_recent=4, title="Hard context reset")
            changed = True
        return changed

    @staticmethod
    def _snip(messages: list[dict]) -> bool:
        changed = False
        for m in messages:
            if m.get("role") != "tool":
                continue
            content = m.get("content") or ""
            lines = content.splitlines()
            if len(content) <= 1500 or len(lines) <= 6:
                continue
            m["content"] = (
                "\n".join(lines[:3])
                + f"\n... ({len(lines)} lines, snipped) ...\n"
                + "\n".join(lines[-3:])
            )
            changed = True
        return changed

    @staticmethod
    def _safe_split(messages: list[dict], keep_recent: int) -> int:
        split = max(0, len(messages) - keep_recent)
        # 保留段不许以 tool 消息开头，否则它和前面的 tool_calls 拆散了
        while split > 0 and messages[split].get("role") == "tool":
            split -= 1
        return split

    def _summarize(self, messages, llm, keep_recent: int, title: str = "Context compressed") -> bool:
        if len(messages) <= keep_recent:
            return False
        split = self._safe_split(messages, keep_recent)
        old, tail = messages[:split], messages[split:]
        summary = self._summary(old, llm)
        # clear 改的是原列表。Agent.messages 和这里是同一个对象，所以外面看得见。
        messages.clear()
        messages.append({"role": "user", "content": f"[{title}]\n{summary}"})
        messages.append({"role": "assistant", "content": "Context restored. Continuing."})
        messages.extend(tail)
        return True

    def _summary(self, messages, llm) -> str:
        flat = "\n".join(
            f"[{m.get('role', '?')}] {(m.get('content') or '')[:400]}"
            for m in messages
            if m.get("content")
        )
        if llm is not None:
            try:
                resp = llm.chat(
                    messages=[
                        {"role": "system", "content": (
                            "Compress this conversation. Preserve file paths, decisions, "
                            "errors, and the current task. Drop long command output."
                        )},
                        {"role": "user", "content": flat[:15000]},
                    ]
                )
                if resp.content:
                    return resp.content
            except Exception:
                pass
        return flat[:2000] or "(empty)"
```

`@staticmethod` 表示这个方法不用 `self`。里面只用传进来的 `messages`。

`messages.clear()` 然后 `append`，改的是调用方那个列表对象。如果写 `messages = []`，只是让局部变量指向一个新列表，`Agent.messages` 还是旧的，压缩会看起来「没生效」。

摘要请求走 `llm.chat()`，不走 `Agent.chat()`。否则总结过程又会进入工具循环。

### 9.2 接到 `Agent` 上

`__init__` 增加参数，并创建管理器：

```python
def __init__(self, llm, tools=None, max_rounds: int = 50, permission=None, max_context_tokens: int = 128_000):
    ...
    from context import ContextManager
    self.context = ContextManager(max_tokens=max_context_tokens)
```

`chat` 里两处调用。用户消息追加之后一次，每轮工具执行完再一次：

```python
self.messages.append({"role": "user", "content": user_input})
self.context.maybe_compress(self.messages, self.llm)
...
            self.messages.append({...tool...})
        self.context.maybe_compress(self.messages, self.llm)
```

`max_rounds` 可以从 10 改成 50。改代码加跑测试，10 轮有时不够。

想亲眼看到第一层截断，可以临时把 `_snip_at` 改成 `1`，读一个长文件，再把 `agent.messages` 里 role 为 tool 的内容打印出来。看完改回去。

对照：`corecoder/context.py`。`article/04-context.md` 专门讲了切散 tool 消息之后接口为什么会 400。

---

## 10. 做成命令行，并能存档

引擎到这里已经能当库用。命令行是外面一层：读参数、问权限、把用户的话交给 `agent.chat()`，斜杠开头的命令自己处理，不发给模型。

### 10.1 中断时把 tool 回复补齐

人按 Ctrl+C 时，assistant 的 `tool_calls` 可能已经写入历史，对应的 tool 消息还没写完。下一轮请求会被拒绝。在 `agent.py` 里，把「执行工具」那一段包进 `try`，并加上补齐方法：

```python
try:
    for tc in resp.tool_calls:
        ...
except KeyboardInterrupt:
    self._answer_pending(resp.tool_calls)
    raise

def _answer_pending(self, tool_calls):
    answered = {
        m.get("tool_call_id")
        for m in self.messages
        if m.get("role") == "tool"
    }
    for tc in tool_calls:
        if tc.id not in answered:
            self.messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": "[interrupted]",
            })
```

花括号加 `for` 且没有冒号，得到的是集合，不是字典。集合用来做 `id in answered` 这种判断。

单独一个 `raise` 是把刚才的 `KeyboardInterrupt` 继续抛出去，让命令行打印「已打断」并回到输入提示。补齐已经做完，所以下一句用户输入仍然合法。

这只保证对话格式合法。工具已经写到磁盘上的内容不会自动撤销。撤销在阶段 12。

### 10.2 `session.py`

```python
import json
import re
import time
import uuid
from pathlib import Path

SESSIONS = Path.home() / ".myagent" / "sessions"
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_id(session_id: str | None) -> str:
    if not session_id:
        return f"session_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    name = session_id.strip().replace("\\", "/").split("/")[-1]
    name = _SAFE.sub("-", name).strip(".-_")[:100]
    return name or _safe_id(None)


def _path(session_id: str) -> Path:
    path = (SESSIONS / f"{_safe_id(session_id)}.json").resolve()
    root = SESSIONS.resolve()
    # 洗过之后，真实路径仍然必须在 sessions 目录里面
    if path.parent != root:
        raise ValueError("Invalid session id")
    return path


def save_session(messages: list[dict], model: str, session_id: str | None = None) -> str:
    SESSIONS.mkdir(parents=True, exist_ok=True)
    session_id = _safe_id(session_id)
    data = {
        "id": session_id,
        "model": model,
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "messages": messages,
    }
    _path(session_id).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return session_id


def load_session(session_id: str):
    path = _path(session_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data["messages"], data["model"]
    except (json.JSONDecodeError, OSError, KeyError):
        return None


def list_sessions() -> list[dict]:
    if not SESSIONS.exists():
        return []
    found = []
    for file in sorted(SESSIONS.glob("*.json"), reverse=True):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        preview = ""
        for m in data.get("messages", []):
            if m.get("role") == "user" and m.get("content"):
                preview = str(m["content"])[:80]
                break
        found.append({
            "id": data.get("id", file.stem),
            "model": data.get("model", "?"),
            "saved_at": data.get("saved_at", "?"),
            "preview": preview,
        })
    return found[:20]
```

会话 id 先洗成安全文件名。`../../` 这类字符串里的斜杠会被换成 `-`，解析后的路径仍然必须落在 `sessions` 目录里。这是在挡路径穿越：恶意 id 不能把 JSON 写到目录外面。

`ensure_ascii=False` 让中文原样写进文件，而不是 `\u4e00` 这种转义。

### 10.3 `cli.py`

第一版用内置 `input()`。CoreCoder 的 `cli.py` 用 `prompt_toolkit` 做多行和历史，用 `rich` 做颜色。你这版先把命令跑通，再去看那两个库。

```python
import argparse
import sys

from agent import Agent
from config import Config
from llm import LLM
from permissions import Permission
from session import list_sessions, load_session, save_session


def parse_args():
    p = argparse.ArgumentParser(prog="myagent")
    p.add_argument("-p", "--prompt", help="问一句就退出")
    p.add_argument("--yes", action="store_true", help="改动类工具全部放行")
    p.add_argument("--demo", action="store_true", help="假模型走一遍读文件")
    p.add_argument("-r", "--resume", help="恢复一个会话 id")
    p.add_argument("-m", "--model", help="模型名")
    return p.parse_args()


def ask(tool_name, arguments):
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
        answer = agent.chat(
            prompt,
            on_token=lambda t: print(t, end="", flush=True),
            on_tool=lambda name, args: print(f"\n[tool] {name} {args}"),
        )
        print("\n" + answer)
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
            print(f"in={llm.total_prompt_tokens} out={llm.total_completion_tokens} cost={llm.estimated_cost}")
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
            answer = agent.chat(
                line,
                on_token=lambda t: print(t, end="", flush=True),
                on_tool=lambda name, args: print(f"\n[tool] {name} {args}"),
            )
            print("\n" + answer)
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
        print("没有 OPENAI_API_KEY")
        sys.exit(1)

    llm = LLM(
        model=cfg.model,
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
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
        llm=llm,
        permission=permission,
        max_context_tokens=cfg.max_context_tokens,
    )
    if args.resume:
        loaded = load_session(args.resume)
        if not loaded:
            print("找不到会话", args.resume)
            sys.exit(1)
        agent.messages, loaded_model = loaded
        if not args.model:
            agent.llm.model = loaded_model
        print("resumed", args.resume)

    if args.prompt:
        run_once(agent, args.prompt)
        return
    repl(agent)


if __name__ == "__main__":
    main()
```

`argparse` 负责解析 `python cli.py -p "..." --yes`。`action="store_true"` 表示这个参数不跟值，写了就是 `True`，没写就是 `False`。

`-p` 且没有 `--yes` 时，`Permission()` 的 `ask` 是 `None`，`edit_file` 和 `bash` 会直接变成拒绝文字。要在脚本里真的改文件，加上 `--yes`。

`main.py` 可以留着给 `--demo` 用。日常从这一版开始运行：

```powershell
python cli.py
python cli.py -p "读一下 hello.py 并用一句话说明"
python cli.py -p "把 hello.py 的打印改成 bye" --yes
```

交互里输入 `/save`，记下打印出来的 id，退出后：

```powershell
python cli.py -r 那个id
```

新进程里的 `agent.messages` 会装上上次的历史。

对照：`corecoder/cli.py`、`corecoder/session.py`。

---

## 11. 任务清单、一轮多个工具、子 Agent

这三件都加在已有循环上。`chat` 的形状仍然是「问模型，没工具就返回，有工具就执行再问」。

### 11.1 `tools/todo.py`

多步任务时，让模型自己维护一份清单。每次调用传入整份清单，整体替换，不是打补丁。清单放在工具对象的内存里。每轮发给模型之前，如果清单非空，就追加到系统提示词末尾。这样旧的 tool 结果被阶段 9 截掉之后，当前清单还在。

```python
from .base import Tool

_STATUS = ("pending", "in_progress", "done")


class TodoWriteTool(Tool):
    name = "todo_write"
    description = (
        "Replace the whole task list. Each item has content and status "
        "(pending, in_progress, done). Pass the full list every time."
    )
    parameters = {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "description": "The full list, in order. Pass [] to clear.",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "status": {"type": "string", "enum": list(_STATUS)},
                    },
                    "required": ["content", "status"],
                },
            }
        },
        "required": ["tasks"],
    }

    def __init__(self):
        self._tasks: list[dict] = []

    def execute(self, tasks: list) -> str:
        if not isinstance(tasks, list):
            return "Error: tasks must be a list"
        clean = []
        for item in tasks:
            if not isinstance(item, dict):
                return "Error: each task must be an object"
            status = item.get("status")
            content = item.get("content")
            if status not in _STATUS or not isinstance(content, str) or not content.strip():
                return "Error: each task needs content and status pending|in_progress|done"
            clean.append({"content": content.strip(), "status": status})
        self._tasks = clean
        return self.render() or "(task list cleared)"

    def render(self) -> str:
        lines = []
        for i, task in enumerate(self._tasks, start=1):
            lines.append(f"{i}. [{task['status']}] {task['content']}")
        return "\n".join(lines)
```

它在 `READ_ONLY` 里：改的是进程内存中的清单，不直接改你的源码，所以不弹确认。

`Agent.__init__` 里找出这个工具：

```python
self._todo = next((t for t in self.tools if t.name == "todo_write"), None)
```

`next(迭代器, None)` 取第一个匹配的；一个都没有就返回 `None`，不抛异常。

`_full_messages` 改成：

```python
def _full_messages(self) -> list[dict]:
    system = self._system
    if self._todo is not None:
        rendered = self._todo.render()
        if rendered:
            system += "\n\n# Current task list\n" + rendered
    return [{"role": "system", "content": system}] + self.messages
```

`/reset` 时把清单也清掉，否则系统提示词里还会挂着上一份任务：

```python
def reset(self):
    self.messages.clear()
    if self._todo is not None:
        self._todo._tasks = []
```

`cli.py` 的 `/reset` 改成调用 `agent.reset()`。

### 11.2 一轮里有多个工具调用时并发执行

模型一轮返回一个调用，就在当前线程执行。返回多个时，用线程池一起跑。两条顺序：

- 询问用户仍在主线程做完，再提交线程池。多个线程同时 `input()`，问题会叠在一起。
- 写回历史时按原来的调用顺序写，不按谁先做完。每个结果仍然用自己的 `tool_call_id`。

两个 `edit_file` 可能同时读改同一个文件，后写的会覆盖先写的。给改文件加一把锁。

`tools/base.py` 顶部加上：

```python
import threading
FILE_MUTATION_LOCK = threading.Lock()
```

`write.py` 和 `edit.py` 的 `execute` 里，真正读文件、写文件的那一段用锁包住：

```python
from .base import FILE_MUTATION_LOCK

def execute(...):
    try:
        with FILE_MUTATION_LOCK:
            ...原来的读和写...
        return ...
    except Exception as e:
        return f"Error: {e}"
```

`with 锁` 的意思是：同一时刻只有一个线程能待在这个块里，出来后自动放开。

bash 的当前目录改成每个线程一份。把 `tools/bash.py` 顶部的 `_cwd` 换成：

```python
import threading
_local = threading.local()

def get_cwd():
    return getattr(_local, "cwd", None)

def set_cwd(path):
    if path is None:
        if hasattr(_local, "cwd"):
            delattr(_local, "cwd")
    else:
        _local.cwd = path
```

`execute` 里原来的 `global _cwd` 删掉，改用 `get_cwd()` / `set_cwd(...)`。`threading.local()` 上的属性，每个线程各看各的，互不影响。

`agent.py` 里，工具执行那一段改成下面这样（权限、中断补齐都还在）：

```python
import concurrent.futures

# chat() 里面，not resp.tool_calls 的分支不变。有工具时：
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
except KeyboardInterrupt:
    self._answer_pending(resp.tool_calls)
    raise
```

```python
def _exec_parallel(self, tool_calls, on_tool=None) -> list[str]:
    from tools.bash import get_cwd, set_cwd

    for tc in tool_calls:
        if on_tool:
            on_tool(tc.name, tc.arguments)

    # 先在主线程问完权限。None 的位置等一下交给线程池。
    results = [self._permit(tc) for tc in tool_calls]
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
            i: pool.submit(run, tc)
            for i, tc in enumerate(tool_calls)
            if results[i] is None
        }
        for i, future in futures.items():
            out, moved = future.result()
            results[i] = out
            if moved is not None:
                set_cwd(moved)
    return results
```

`pool.submit(run, tc)` 是把函数和参数交给线程，立刻返回一个 `Future`，不会在当前线程执行 `run`。`future.result()` 会等到那个任务结束，拿到返回值。任务里没被接住的异常也会在这里抛出来。

`enumerate` 给出 `(0, 第一个调用), (1, 第二个调用), ...`。按这个下标写回 `results`，外面的 `zip` 才能和原来的 `tool_call_id` 对齐。

同一批里的两个 bash，后一个不保证能看见前一个刚 `cd` 到的目录，因为它们是并行的。这一批全部结束后，主线程留下最后一次目录变化，下一批命令接着用。

`zip(a, b)` 把两个列表按位置配对。

### 11.3 子 Agent

增加一个工具，名字就叫 `agent`。执行时新建一个 `Agent`：对话是空的，工具列表去掉 `agent` 自己，所以它不能再派下一层。少给这一个工具，比在提示词里写「不许递归」可靠。它共用父 Agent 的同一个 `LLM`，费用记在同一本账上，也共用同一套权限。

`tools/subagent.py`：

```python
from .base import Tool


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

    def execute(self, task: str) -> str:
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
            return f"Sub-agent error: {e}"
        finally:
            # finally 无论成功还是异常都会走。把父线程的当前目录恢复回去。
            if get_cwd() != parent_cwd:
                set_cwd(parent_cwd)
```

`Agent.__init__` 末尾加上：

```python
for t in self.tools:
    if t.name == "agent":
        t._parent = self
```

子 Agent 再创建时，它的工具列表里已经没有 `agent`，这段循环对它是空的。

`[t for t in parent.tools if t.name != "agent"]` 是一个新列表，里面的工具对象仍是原来的那些。所以子 Agent 和父 Agent 共用同一个 `TodoWriteTool`，清单是同一份。这也是教学版能保持文件短的原因。

注册 `SubAgentTool()`。它会改东西（它自己还能写文件），不要放进 `READ_ONLY`。

对照：`corecoder/agent.py` 的 `_exec_tools_parallel`，`corecoder/tools/todo.py`，`corecoder/tools/agent.py`。

---

## 12. 计划模式、钩子、撤销、外部工具

做到阶段 11，读、改、跑、问人、续聊、派子任务都有了。下面四件挂在「执行这一个工具」的前后，`chat` 的主结构不用再拆。

三条约定让它们能同时存在：

- 外部能力长得和内置工具一样：`name`、`schema()`、`execute() -> str`。
- 失败是返回值里的一段文字。
- 这些外围组件超时或报错时，跳过并记一条警告，循环继续。

### 12.1 计划模式

Agent 上一个布尔值。打开时，系统提示词追加一段「先调查，给出编号计划」。执行前如果工具不在只读名单里，直接返回一段拒绝文字。这层判断放在用户授权之前，所以 `--yes` 也不能绕过。

`prompt.py` 增加：

```python
PLAN_MODE_PROMPT = """
# Plan mode
Plan mode is on. Investigate with read-only tools only. Mutating calls are refused.
When you understand the task, present a numbered plan and stop.
"""
```

`agent.py`：

```python
# __init__ 里
self.plan_mode = False

# _full_messages 里，拼 system 的开头
system = self._system
if self.plan_mode:
    from prompt import PLAN_MODE_PROMPT
    system += "\n" + PLAN_MODE_PROMPT
```

`_permit` 的最前面加上：

```python
from permissions import READ_ONLY

def _permit(self, tc):
    if self.plan_mode and tc.name not in READ_ONLY:
        return (
            "Plan mode is on, so this call was refused. "
            "Keep investigating with read-only tools, present a numbered plan, and stop."
        )
    ...原来的权限检查...
```

`cli.py` 的循环里，在交给 `agent.chat` 之前：

```python
if line == "/plan":
    agent.plan_mode = not agent.plan_mode
    print("plan mode", "on" if agent.plan_mode else "off")
    continue
if agent.plan_mode and line.strip().lower() == "approve":
    agent.plan_mode = False
    line = "The user approved the plan. Carry it out."
```

第二段不要 `continue`。开关关掉之后，这句话继续往下走，进入 `agent.chat`，模型开始执行刚才的计划。

提示符可以改成计划模式时显示 `You (plan) > `。真正拦住写文件的是 `_permit`，不是提示符。

### 12.2 钩子

`~/.myagent/hooks.json`：

```json
{
  "PreToolUse": [{"matcher": "bash", "command": "echo blocked >&2; exit 2"}],
  "PostToolUse": [{"matcher": "*", "command": "cat >> hook.log"}]
}
```

每个命令从标准输入读到这次调用的 JSON。执行前的命令以退出码 2 结束时，这次工具不执行，它的标准错误成为模型看到的理由。执行后的命令只观察。超过 10 秒就跳过。

`hooks.py`：

```python
import json
import subprocess
from pathlib import Path

from shell_util import run_shell

HOOKS_FILE = Path.home() / ".myagent" / "hooks.json"


class Hooks:
    def __init__(self, pre: list[dict], post: list[dict]):
        self.pre = pre
        self.post = post

    def __bool__(self):
        return bool(self.pre or self.post)

    def run_pre(self, tool_name: str, tool_input: dict) -> str | None:
        payload = {"tool_name": tool_name, "tool_input": tool_input}
        for hook in self.pre:
            proc = _fire(hook, payload)
            if proc is not None and proc.returncode == 2:
                reason = (proc.stderr or "").strip() or "no reason given"
                return "Blocked by hook: " + reason
        return None

    def run_post(self, tool_name: str, tool_input: dict, result: str):
        payload = {"tool_name": tool_name, "tool_input": tool_input, "tool_response": result}
        for hook in self.post:
            _fire(hook, payload)


def load_hooks(path: Path = HOOKS_FILE) -> Hooks:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Hooks([], [])
    except (json.JSONDecodeError, OSError):
        print(f"忽略无法读取的钩子文件: {path}")
        return Hooks([], [])
    pre = [h for h in data.get("PreToolUse", []) if h.get("command")]
    post = [h for h in data.get("PostToolUse", []) if h.get("command")]
    return Hooks(pre, post)


def _fire(hook: dict, payload: dict):
    matcher = hook.get("matcher", "")
    if matcher not in ("", "*", payload["tool_name"]):
        return None
    try:
        return run_shell(
            hook["command"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"hook skipped: {e}")
        return None
```

`__bool__` 让 `if agent.hooks` 这种判断走你自己的规则：一条钩子都没有时当作假。

接到循环上时，沿用和权限相同的返回值：字符串表示拒绝，`None` 表示继续。`or` 在这里正好：左边已经是拒绝文字就不再调用右边。

```python
# 单个工具
result = self._pre(tc) or self._permit(tc)
if result is None:
    result = self._exec(tc)
    self._post(tc, result)

def _pre(self, tc):
    if not self.hooks:
        return None
    return self.hooks.run_pre(tc.name, tc.arguments)

def _post(self, tc, result):
    if self.hooks:
        self.hooks.run_post(tc.name, tc.arguments, result)
```

并行那条路径也一样：主线程先把 `_pre(tc) or _permit(tc)` 算完，被拒绝的位置不再提交线程池；做完之后再 `_post`。

`cli.py` 创建 Agent 时传入 `hooks=load_hooks()`。`__init__` 增加参数 `hooks=None`。

### 12.3 撤销最近一次写文件

只跟踪 `write_file` 和 `edit_file`。bash 造成的修改不在这个栈里，`/help` 里写一句，避免用的时候以为所有操作都能撤。

`checkpoints.py`：

```python
import base64
import json
from pathlib import Path

FILE = Path.home() / ".myagent" / "checkpoints.json"
_stack: list[tuple[str, bytes | None]] = []
_loaded = False


def _load():
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        entries = json.loads(FILE.read_text(encoding="utf-8"))
        for item in entries:
            prior = item["prior"]
            raw = base64.b64decode(prior) if prior is not None else None
            _stack.append((item["path"], raw))
    except (OSError, ValueError, KeyError, TypeError):
        pass


def _save():
    entries = []
    for path, prior in _stack:
        blob = base64.b64encode(prior).decode("ascii") if prior is not None else None
        entries.append({"path": path, "prior": blob})
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(entries), encoding="utf-8")


def record(path: Path) -> None:
    """写入之前调用。文件原来不存在就记 None。"""
    _load()
    _stack.append((str(path), path.read_bytes() if path.exists() else None))
    _save()


def undo() -> str:
    _load()
    if not _stack:
        return "Nothing to undo."
    path_str, prior = _stack.pop()
    path = Path(path_str)
    if prior is None:
        path.unlink(missing_ok=True)
        message = f"Removed {path_str}"
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(prior)
        message = f"Restored {path_str}"
    _save()
    return message
```

JSON 不能直接放原始字节，所以用 base64 变成普通字符串。

在 `write.py` / `edit.py` 里，`write_text` 的前一行：

```python
from checkpoints import record
record(path)
```

这行要放在锁里面、写文件之前。`cli.py` 增加：

```python
if line == "/undo":
    from checkpoints import undo
    print(undo())
    continue
```

### 12.4 外部工具（MCP）先理解协议形状

MCP 服务器是一个子进程。你往它的标准输入写一行 JSON，从标准输出读一行 JSON。先握手 `initialize`，再 `tools/list`，之后每次调用是 `tools/call`。远程工具注册成普通 `Tool`，名字用 `mcp__服务器__工具`，权限、钩子、计划模式就不用专门认识 MCP。

教学版用「发一行、读一行」。服务器如果先推一条不带 `id` 的通知，这版会把通知误当成回复。成品 `corecoder/mcp.py` 用一个后台线程按 `id` 把回包分拣，就是为了这个。你先把协议跑通，再去读那个文件。

```python
import json
import subprocess

from tools.base import Tool


class MCPTool(Tool):
    def __init__(self, server: str, remote_name: str, description: str, parameters: dict, client):
        self.name = f"mcp__{server}__{remote_name}"
        self.description = description or remote_name
        self.parameters = parameters or {"type": "object", "properties": {}}
        self._client = client
        self._remote_name = remote_name

    def execute(self, **kwargs) -> str:
        try:
            result = self._client.request("tools/call", {
                "name": self._remote_name,
                "arguments": kwargs,
            })
        except Exception as e:
            return f"Error: {e}"
        return json.dumps(result, ensure_ascii=False)


class MCPClient:
    def __init__(self, command: str, args: list[str]):
        self.proc = subprocess.Popen(
            [command, *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self._next_id = 0

    def request(self, method: str, params: dict):
        self._next_id += 1
        msg = {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params}
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("MCP server closed the pipe")
        data = json.loads(line)
        if "error" in data:
            raise RuntimeError(data["error"])
        return data.get("result")


def load_mcp_tools(config_path) -> list[Tool]:
    from pathlib import Path
    path = Path(config_path)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    tools = []
    for server, spec in data.get("mcpServers", {}).items():
        client = MCPClient(spec["command"], spec.get("args", []))
        client.request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "myagent", "version": "0.1"},
        })
        listed = client.request("tools/list", {})
        for item in listed.get("tools", []):
            tools.append(MCPTool(
                server=server,
                remote_name=item["name"],
                description=item.get("description", ""),
                parameters=item.get("inputSchema") or {},
                client=client,
            ))
    return tools
```

`cli.py` 里：

```python
from mcp_client import load_mcp_tools
extra = load_mcp_tools(Path.home() / ".myagent" / "mcp.json")
agent = Agent(llm=llm, tools=[*ALL_TOOLS, *extra], ...)
```

`[*ALL_TOOLS, *extra]` 把两个列表的元素拆开，合成一个新列表。

没有 `mcp.json` 就得到空列表，行为和现在一样。MCP 工具不要放进 `READ_ONLY`，调用前要问人。

握手和单次调用在成品里还有超时（大约 15 秒和 60 秒）。教学版这步先省略；子进程卡住时，`readline` 会一直等。你准备真的接一个服务器时，再把 `corecoder/mcp.py` 里的超时和读线程抄过来。

对照：`corecoder/hooks.py`、`corecoder/checkpoints.py`、`corecoder/mcp.py`，以及 `agent.py` 里 `_permit` 开头的计划模式判断。`article/08-extensibility.md` 讲的就是这几件为什么可以不改主循环的形状。

---

## 13. 自己再加一个工具

循环稳了之后，新能力就是一个新文件。模型靠 `description` 决定叫不叫它。

当前时间，无参数：

```python
import time
from .base import Tool


class NowTool(Tool):
    name = "now"
    description = "Get the current local date and time."
    parameters = {"type": "object", "properties": {}, "required": []}

    def execute(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S")
```

名字用小写加下划线，和 `read_file` 同一套风格。`properties` 用空对象，`required` 用空数组。

抓网页：

```python
import urllib.request
from .base import Tool


class FetchUrlTool(Tool):
    name = "fetch_url"
    description = "Fetch the text of an http(s) URL. Use it for docs and API responses."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "http:// or https:// URL"},
            "timeout": {"type": "integer", "description": "Seconds. Default 15."},
        },
        "required": ["url"],
    }

    def execute(self, url: str, timeout: int = 15) -> str:
        if not url.startswith(("http://", "https://")):
            return "Error: only http and https URLs are supported"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "myagent"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read(1_000_000)
                text = raw.decode("utf-8", errors="replace")
        except Exception as e:
            return f"Error fetching {url}: {e}"
        if len(text) > 8000:
            text = text[:6000] + f"\n... ({len(text)} chars) ...\n" + text[-1000:]
        return text
```

`with urllib.request.urlopen(...) as resp` 用完会把连接关掉，即使中间出错也会关。

这个工具没有共享的可变状态，阶段 11 的线程池里并发调用是安全的。它能访问任意 URL，也包括本机和内网。只在你自己的机器上自己用，可以先这样。

两个类都放进 `ALL_TOOLS`。

---

## 14. 三个测试

日常用 `python cli.py` 看行为即可。下面三个用来钉住最容易写歪的约定。需要 `pip install pytest`，然后在 `d:\code\myagent` 运行 `python -m pytest tests -q`。

`tests/test_basic.py`：

```python
from pathlib import Path

from agent import Agent
from llm import LLMResponse, ScriptedLLM, ToolCall
from permissions import Permission
from tools.edit import EditFileTool


def test_loop_pairs_tool_result():
    script = [
        LLMResponse(content="", tool_calls=[
            ToolCall(id="c1", name="read_file", arguments={"file_path": "hello.py"})
        ]),
        LLMResponse(content="done"),
    ]
    agent = Agent(llm=ScriptedLLM(script))
    answer = agent.chat("read hello")
    assert answer == "done"
    roles = [m["role"] for m in agent.messages]
    assert roles == ["user", "assistant", "tool", "assistant"]
    assert agent.messages[2]["tool_call_id"] == "c1"


def test_edit_requires_unique_match(tmp_path: Path):
    file = tmp_path / "a.py"
    file.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    tool = EditFileTool()
    bad = tool.execute(str(file), "a", "b")
    assert bad.startswith("Error:")
    assert "return a - b" in file.read_text(encoding="utf-8")

    ok = tool.execute(str(file), "return a - b", "return a + b")
    assert "Edited" in ok
    assert "return a + b" in file.read_text(encoding="utf-8")


def test_permission_deny_skips_execute(tmp_path: Path):
    file = tmp_path / "a.py"
    file.write_text("x = 1\n", encoding="utf-8")
    script = [
        LLMResponse(content="", tool_calls=[
            ToolCall(id="c1", name="edit_file", arguments={
                "file_path": str(file),
                "old_string": "x = 1",
                "new_string": "x = 2",
            })
        ]),
        LLMResponse(content="refused"),
    ]
    permission = Permission(ask=lambda name, args: "deny")
    agent = Agent(llm=ScriptedLLM(script), permission=permission)
    agent.chat("change x")
    assert file.read_text(encoding="utf-8") == "x = 1\n"
    assert "Permission denied" in agent.messages[2]["content"]
```

`tmp_path` 是 pytest 提供的临时目录，测完会清掉。

这三个分别钉住：工具结果必须和调用 id 配对；`edit_file` 不唯一就不许改文件；用户拒绝时工具函数不会真的写入。

---

## 15. 写的时候对照哪份成品

| 你写到 | 打开 |
|---|---|
| 阶段 1 循环 | `corecoder/agent.py` 的 `chat`，`corecoder/demo.py` |
| 阶段 2–7 工具 | `corecoder/tools/` 里同名文件 |
| 阶段 3、8 模型 | `corecoder/llm.py` |
| 阶段 5 | `corecoder/permissions.py` |
| 阶段 9 | `corecoder/context.py`，`article/04-context.md` |
| 阶段 10 | `corecoder/cli.py`，`corecoder/session.py` |
| 阶段 11 | `corecoder/tools/agent.py`，`article/05-parallel-and-subagents.md` |
| 阶段 12 | `corecoder/hooks.py`，`checkpoints.py`，`mcp.py`，`article/08-extensibility.md` |

成品比教学版多出来的，主要是这些边角：流式过程中按 400 文本改参数名、`cd` 把引号和括号算准确、并发时按调用顺序合并目录、MCP 用线程按 id 收包、Windows 路径在 Git Bash 里把反斜杠换成斜杠。主循环没有更复杂的第二种形态。

第一版可以停在阶段 10 或 11。真正的命令沙箱、备用模型、美元硬预算、边生成边执行工具，都是这条循环已经能干活之后的下一层。
