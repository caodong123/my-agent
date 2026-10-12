

from pathlib import Path
from warnings import showwarning
from tools.base import Tool


SKIP = {".git", "node_modules", "__pycache__", ".venv","venv","dist","build"}

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
                return f"Error: directory {path} does not exist."
            if not base.is_dir():
                return f"Error: {path} is not a directory."
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
                text += f"\n...({len(hits)} matches, showing first 100)"
            return text or "No matches found."
        except Exception as e:
            return f"Error: {e}"
