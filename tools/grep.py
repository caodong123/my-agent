from pathlib import Path
import re
from tools.base import Tool


SKIP = {".git", "node_modules", "__pycache__", ".venv","venv","dist","build"}

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
                return f"Error: directory {path} does not exist."
            files = [base] if base.is_file() else list(base.rglob(include or "*"))
            matches = []
            for file in files:
                if not file.is_file():
                    continue
                if any(part in SKIP for part in file.parts):
                    continue
                try:
                    text = file.read_text(encoding="utf-8",errors="replace")
                except OSError:
                    continue
                for i,line in enumerate(text.splitlines(),start=1):
                    if regex.search(line):
                        matches.append(f"{file}:{i}:{line}")
                        if len(matches) >= 50:
                            return "\n".join(matches) + "\n... (stopped at 50 matches)"
            return "\n".join(matches) or "No matches found."
        except Exception as e:
            return f"Error: {e}"