

from dataclasses import dataclass
import os
from dotenv import load_dotenv

@dataclass
class Config:
    """
    Configuration for the agent.
    """
    model: str
    api_key: str
    base_url: str | None
    max_tokens: int = 4096
    temperature: float = 0.0
    max_context_tokens: int = 128_000

    @classmethod
    def from_env(cls) -> "Config":
        # 从环境变量中加载配置
        load_dotenv(override=False)
        return cls(
            model=os.getenv("MYAGENT_MODEL", "deepseek-chat"),
            api_key=os.getenv("OPENAI_API_KEY", ""),
            base_url=os.getenv("OPENAI_BASE_URL") or None,
            max_tokens=int(os.getenv("MYAGENT_MAX_TOKENS", "4096")),
            temperature=float(os.getenv("MYAGENT_TEMPERATURE", "0")),
            max_context_tokens=int(os.getenv("MYAGENT_MAX_CONTEXT", "128000")),
        )