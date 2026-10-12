

from os import path
from pathlib import Path
from tools.base import Tool


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
            n_lines = content.count("\n") + (0 if content.endswith("\n") else 1)
            return f"File {path} written with {n_lines} lines."
        except Exception as e:
            return f"Error writing file {file_path}: {e}"