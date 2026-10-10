

import chunk
from pathlib import Path
from unittest import result
from tools.base import Tool


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
            
            # 遇到坏字节就换成替代字符
            text = path.read_text(encoding='utf-8', errors='replace')
            lines = text.splitlines()
            start = max(0, offset - 1)
            chunk = lines[start:start+limit]
            # 行号从1开始，方便用户理解
            numbered = [f"{start + i + 1}\t{line}" for i, line in enumerate(chunk)]
            result = "\n".join(numbered)
            if len(lines) > start + limit:
                result += f"\n... ({len(lines)} lines total, showing {start + 1}-{start + len(chunk)})"
            return result or "No content to read"
        except Exception as e:
            return f"Error: {e}"


