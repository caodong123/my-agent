# my-agent

一个从零手写的简易 Coding Agent。实现顺序跟 `document/Agent开发指南-grok.md` 走。当前停在阶段 4：模型可以读文件，也可以新建、覆盖和按唯一原文修改文件。改文件前还不会询问，那是下一阶段的事。回复仍是一次拿回整段，没有流式输出。

模型只负责产出文字，以及「请调用某个工具」的结构化数据。读文件和改文件由本地 Python 完成。一次调用在历史里是四条消息：

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

程序停在 `You >`，可以一句接一句输入。输入 `quit` 或 `exit` 结束。每轮请求都会带上系统提示词：当前目录、操作系统，以及已注册工具的说明。历史留在同一个 `Agent` 里，系统提示词不写入历史。没有 `OPENAI_API_KEY` 时会直接退出。

可以让它读取 `hello.py`，或把其中的文字改成别的内容。小改动应走 `edit_file`，原文必须在文件里恰好出现一次；新建或整文件覆盖走 `write_file`。终端会打印 `[tool]` 和它调用的参数。

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
| `prompt.py` | 生成系统提示词：环境信息、工具列表和修改规则 |
| `agent.py` | 主循环。`full_messages()` 在历史前临时拼上系统提示词 |
| `main.py` | 有密钥进入连续对话；`MYAGENT_DEMO=1` 走假模型 |
| `hello.py` | 给演示读取和修改的示例文件 |
| `tools/` | `read_file` 按行号读文件；`write_file` 整文件写入；`edit_file` 替换唯一原文并返回 diff |
| `document/` | 两份开发指南，实现时以 Grok 那份为准 |

密钥、`.env` 和虚拟环境不进仓库。`.gitignore` 已经排除了 `.venv/`、`__pycache__/`、`*.pyc` 和 `.env`。
