

from tools.base import Tool


_STATUS = ("pending","in_progress","done")

class TodoWriteTool(Tool):
    name = "todo_write"
    description = (
        "Replace the whole task list. Each item has content and status "
        "(pending, in_progress, done). Pass the full list every time."
    )
    parameters = {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "description": "The full list, in order. Pass [] to clear.",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "status": {"type": "string", "enum": list(_STATUS)},
                    },
                    "required": ["content", "status"],
                },
            }
        },
        "required": ["tasks"],
    }

    def __init__(self):
        self._tasks:list[dict] = []

    def execute(self, tasks:list) -> str:
        if not isinstance(tasks, list):
            return "Error: tasks must be a list"
        clean = []
        for item in tasks:
            if not isinstance(item, dict):
                return "Error: each item must be a dict"
            status = item.get("status")
            content = item.get("content")
            if status not in _STATUS or not isinstance(content,str) or not content.strip():
                return "Error: each task needs content and status pending|in_progress|done"
            clean.append(
                {"content":content.strip(),"status":status}
            )
        self._tasks = clean
        return self.render() or "(Task list cleaned)"
    
    def render(self) -> str:
        lines = []
        for i,task in enumerate(self._tasks,start=1):
            lines.append(f"{i}. [{task['status']}] {task['content']}")
        return "\n".join(lines)