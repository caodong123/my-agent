

import difflib
from pathlib import Path
from tools.base import Tool


class EditFileTool(Tool):
    name = "edit_file"
    description = (
        "Replace an exact string in a file. "
        "old_string must appear exactly once. Include surrounding lines to make it unique."
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to the file"},
            "old_string": {"type": "string", "description": "Exact text to find, must be unique"},
            "new_string": {"type": "string", "description": "Replacement text"},
        },
        "required": ["file_path", "old_string", "new_string"],
    }

    def execute(self, file_path: str, old_string: str, new_string: str) -> str:
        try:
            path = Path(file_path).expanduser().resolve()
            if not path.exists():
                return f"Error: file {file_path} does not exist."
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return f"Error: file {file_path} is not a UTF-8 text file."
            
            found = content.count(old_string)
            if found == 0:
                preview = content[:500] + ("..." if len(content) > 500 else "")
                return (
                    f"Error: old_string not found in {file_path}.\n"
                    f"File starts with:\n{preview}"
                )
            if found > 1:
                return(
                    f"Error: old_string appears {found} times in {file_path}. "
                    "Include more surrounding lines to make it unique."
                )
            
            new_content = content.replace(old_string, new_string,1)
            path.write_text(new_content, encoding="utf-8")
            diff = _unifed_diff(content, new_content,str(path))
            return f"File {path} edited. Changes:\n{diff}"
        except Exception as e:
            return f"Error editing file {file_path}: {e}"
    

def _unifed_diff(old_content: str, new_content: str, filename: str) -> str:
    diff = difflib.unified_diff(
        old_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=f"(before {filename})",
        tofile=f"(after {filename})",
        n=3,
    )
    text =  "".join(diff)
    if len(text) > 3000:
        text = text[:3000] + "\n...(truncated)\n"
    return text