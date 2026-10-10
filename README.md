# my-agent

一个从零手写的简易 Coding Agent。实现顺序跟 `document/Agent开发指南-grok.md` 走。当前停在阶段 3：工具调用循环已经接上真实模型，一次拿回完整回复，还没有流式输出。

模型只负责产出文字，以及「请调用某个工具」的结构化数据。读文件由本地 Python 完成。一次调用在历史里是四条消息：

```text
user        用户的话
assistant   模型回复；要工具时带上 tool_calls
tool        本地执行结果，用 tool_call_id 和那次调用配对
assistant   模型看到结果后的最终回答
```

## 现在能看到什么

需要 Python 3.10 或以上。在项目根目录激活虚拟环境并安装依赖：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install openai python-dotenv
```

复制一份 `.env`（这个文件不要提交）：

```text
OPENAI_API_KEY=你的key
OPENAI_BASE_URL=https://api.deepseek.com
MYAGENT_MODEL=deepseek-chat
```

`OPENAI_BASE_URL` 和 `MYAGENT_MODEL` 按所用服务修改。不设 `OPENAI_BASE_URL` 时走 OpenAI 官方地址。可选变量还有 `MYAGENT_MAX_TOKENS`、`MYAGENT_TEMPERATURE`、`MYAGENT_MAX_CONTEXT`。

然后运行：

```powershell
python main.py
```

程序会读取 `hello.py`，先打印 `[tool] read_file ...`，再打印模型根据文件内容写的说明。没有 `OPENAI_API_KEY` 时会直接退出。

不接网络、沿用假模型剧本时：

```powershell
$env:MYAGENT_DEMO = "1"
python main.py
```

## 目录

| 文件 | 作用 |
|---|---|
| `config.py` | 从环境变量和 `.env` 读取模型、密钥和地址 |
| `llm.py` | 假模型 `ScriptedLLM`，以及调用 OpenAI 兼容接口的 `LLM` |
| `agent.py` | 主循环：把工具说明书发给模型，执行工具，把结果写回历史 |
| `main.py` | 有密钥走真实模型；`MYAGENT_DEMO=1` 走假模型 |
| `hello.py` | 给这次演示读取的示例文件 |
| `tools/` | `read_file`：按行号读取文件，并提供给模型的 JSON 说明书 |
| `document/` | 两份开发指南，实现时以 Grok 那份为准 |

密钥、`.env` 和虚拟环境不进仓库。`.gitignore` 已经排除了 `.venv/`、`__pycache__/`、`*.pyc` 和 `.env`。
