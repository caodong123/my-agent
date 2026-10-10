# my-agent

一个从零手写的简易 Coding Agent。实现顺序跟 `document/Agent开发指南-grok.md` 走。当前停在阶段 1：不接网络，用预先写好的剧本把工具调用循环跑通。

模型只负责产出文字，以及「请调用某个工具」的结构化数据。读文件、改文件、跑命令都由本地 Python 完成。一次调用在历史里是四条消息：

```text
user        用户的话
assistant   模型回复；要工具时带上 tool_calls
tool        本地执行结果，用 tool_call_id 和那次调用配对
assistant   模型看到结果后的最终回答
```

## 现在能看到什么

在项目根目录运行：

```powershell
python main.py
```

`main.py` 里的假模型会先要求读取 `hello.py`，`Agent` 在本地执行 `read_file`，再按剧本给出一句说明，并打印完整的 `messages`。假模型不看工具结果，下一句是写死的。会根据文件内容继续思考的，是后面接入的真实模型。

需要 Python 3.10 或以上。建议使用项目里的虚拟环境：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python main.py
```

## 目录

| 文件 | 作用 |
|---|---|
| `llm.py` | `ToolCall`、`LLMResponse`，以及按剧本吐回复的 `ScriptedLLM` |
| `agent.py` | 主循环：问模型、执行工具、把结果写回历史 |
| `main.py` | 用剧本走一遍「读 hello.py」 |
| `hello.py` | 给这次演示读取的示例文件 |
| `tools/` | 工具包目录。阶段 2 才把读文件做成正式工具 |
| `document/` | 两份开发指南，实现时以 Grok 那份为准 |

密钥、`.env` 和虚拟环境不进仓库。`.gitignore` 已经排除了 `.venv/`、`__pycache__/`、`*.pyc` 和 `.env`。
