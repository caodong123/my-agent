

# 只读工具，调用时不需要确认
import json
from pathlib import Path


READ_ONLY = {"read_file","glob","grep","todo_write"}


class Permission:
    def __init__(self, ask = None, allow_all: bool = False, persist_path: Path | None = None):
        # ask(tool_name, arguments) -> "once" | "always" | "deny"
        self.ask = ask
        self.allow_all = allow_all
        self._persist_path = persist_path
        self._always: set[str] = set()

        if self._persist_path:
            try:
                saved = json.loads(self._persist_path.read_text(encoding="utf-8"))
                self._always = {x for x in saved.get("always",[]) if isinstance(x,str)}
            except (OSError,ValueError):
                self._always = set()
    
    def check(self, tool_name: str, arguments: dict) -> str | None:
        """检查工具调用是否允许，返回None表示允许，返回字符串表示不允许"""
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
    
    def _save(self):
        if self._persist_path is None:
            return
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"always": sorted(self._always)}
        self._persist_path.write_text(json.dumps(data,indent=2) + "\n", encoding="utf-8")
