# my-agent

一个从零手写的简易 Coding Agent。实现顺序跟 `document/Agent开发指南-grok.md` 走。当前停在阶段 10：模型可以查找、读取和修改文件，也可以运行命令。日常从 `cli.py` 进入。`write_file`、`edit_file` 和 `bash` 执行前会先询问。回复是流式输出，对话变长时会压缩历史。斜杠命令可以查看累计 token、保存会话，下次再用 id 恢复。

模型只负责产出文字，以及「请调用某个工具」的结构化数据。读文件、改文件和跑命令由本地 Python 完成。一次调用在历史里是四条消息：

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
python cli.py
```

程序停在 `You >`，可以一句接一句输入。输入 `quit` 或 `exit` 结束。模型的正文会逐段出现。思考过程可以打印，但不会写进历史。没有 `OPENAI_API_KEY` 时会直接退出。

斜杠开头的输入由命令行自己处理，不发给模型：

| 命令 | 作用 |
|---|---|
| `/help` | 列出命令 |
| `/reset` | 清空当前对话历史 |
| `/tokens` | 打印累计输入 token、输出 token，以及按每百万 token 单价估算的美元费用。价目表里没有的模型显示 `None` |
| `/save` | 把当前历史写到 `sessions/`，并打印会话 id |
| `/sessions` | 列出最近 20 个会话的 id、保存时间和第一句用户话 |
| `quit` | 退出 |

工具执行过程中按 Ctrl+C，会给还没写完的 tool 消息补上中断说明，然后回到 `You >`。已经写到磁盘上的内容不会撤销。在 `You >` 时按 Ctrl+C 则直接退出。

问一句就退出：

```powershell
python cli.py -p "读一下 hello.py，用一句话说明它打印了什么"
```

`-p` 没有人坐在键盘前，不带 `--yes` 时 `edit_file`、`write_file` 和 `bash` 会直接变成拒绝文字。要在这一句里真的改文件或跑命令，加上 `--yes`。`-m` 可以临时换模型名。`--demo` 不接网络，用假模型走一遍读文件。

交互里输入 `/save`，记下打印出来的 id，退出后恢复：

```powershell
python cli.py -r 那个id
```

新进程会装上上次的历史。没写 `-m` 时沿用存档里的模型名。会话 id 会洗成安全文件名，JSON 只写在当前目录的 `sessions/` 里。这个目录不进仓库。

`main.py` 仍是阶段 9 的连续对话，每轮结束打印 `[usage]`。不接网络时也可以：

```powershell
$env:MYAGENT_DEMO = "1"
python main.py
```

每轮请求都会带上系统提示词：当前目录、操作系统，以及已注册工具的说明。历史留在同一个 `Agent` 里，系统提示词不写入历史。限流 429、超时、连接断开和 5xx 会按 1 秒、2 秒、4 秒重试。其余 4xx 直接失败。流读到一半断开时，整次请求重发，这时工具还没有执行。

可以让它读取 `hello.py`，或把其中的文字改成别的内容。小改动应走 `edit_file`，原文必须在文件里恰好出现一次；新建或整文件覆盖走 `write_file`。终端会打印 `[tool]` 和它调用的参数。

`read_file`、`glob`、`grep` 直接执行。`glob` 按通配符找文件，例如 `**/*.py`，最近修改的排在前面。`grep` 用正则搜文件内容，返回路径、行号和那一行。两者都会跳过 `.git`、`.venv`、`__pycache__` 等目录，结果过多时会截断。

在 `python cli.py` 里，`write_file`、`edit_file` 和 `bash` 会停下来问一句：输入 `y` 允许这一次，输入 `a` 以后都允许这个工具，输入其他内容则拒绝。拒绝会变成一条 `Permission denied` 的工具结果交给模型，文件不会被修改，命令也不会执行。选择 `a` 之后，工具名写入用户主目录的 `.myagent/permissions.json`，下次启动仍然有效。`main.py` 仍把允许名单写在当前目录的 `permission.json`。

`bash` 在 Windows 上优先使用 Git Bash。它返回标准输出、标准错误和退出码，默认 120 秒超时，过长的输出会截断。递归删除家目录、格式化磁盘这类命令会在执行前被拦住。这份名单不是沙箱，挡不住换一种写法。

历史变长时按粗估 token 分三档处理，默认窗口是 128000。大约超过 50% 时，过长的工具结果收成开头 3 行和结尾 3 行。大约超过 70% 且消息多于 10 条时，较早的对话交给模型摘要，最近约 8 条原文留下。大约超过 90% 时再摘要一次，只留最近约 4 条。切分时不会把 `tool` 消息和前面的 `tool_calls` 拆开。摘要走 `llm.chat()`，不会再进入工具循环。

## 目录

| 文件 | 作用 |
|---|---|
| `config.py` | 从环境变量和 `.env` 读取模型、密钥和地址 |
| `llm.py` | 假模型 `ScriptedLLM`，以及流式调用 OpenAI 兼容接口的 `LLM`。累计 token 并估算费用 |
| `prompt.py` | 生成系统提示词：环境信息、工具列表和修改规则 |
| `permission.py` | 只读工具直接放行；改文件和运行命令前询问。`None` 表示允许，字符串表示拒绝理由 |
| `context.py` | 按估算用量截短工具结果，或摘要较早的历史。切分时保留成对的工具调用 |
| `agent.py` | 主循环。执行工具前先过权限；用户消息和工具结果写入后尝试压缩。Ctrl+C 时补齐未完成的 tool 消息 |
| `cli.py` | 命令行入口：参数、权限询问、斜杠命令、保存和恢复会话 |
| `session.py` | 把对话历史存成 `sessions/*.json`，并按 id 读回 |
| `main.py` | 阶段 9 的连续对话；`MYAGENT_DEMO=1` 或 `python cli.py --demo` 走假模型 |
| `hello.py` | 给演示读取和修改的示例文件 |
| `tools/` | `read_file` 按行号读文件；`glob` 按通配符找文件；`grep` 按正则搜内容；`write_file` 整文件写入；`edit_file` 替换唯一原文并返回 diff；`bash` 运行命令 |
| `document/` | 两份开发指南，实现时以 Grok 那份为准 |

密钥、`.env`、允许名单、会话记录和虚拟环境不进仓库。`.gitignore` 已经排除了 `.venv/`、`__pycache__/`、`*.pyc`、`.env`、`permission.json` 和 `sessions/`。
