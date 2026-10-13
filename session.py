
import json
from pathlib import Path
import re
import time
import uuid

# 会话目录
SESSIONS = Path.cwd() / "sessions"
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")

def _safe_id(session_id: str | None) -> str:
    if not session_id:
        return f"session_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    name = session_id.strip().replace("\\", "/").split("/")[-1]
    name = _SAFE.sub("", name).strip(".-_")[:100]
    return name or _safe_id(None)

def _path(session_id: str) -> Path:
    path = (SESSIONS / f"{_safe_id(session_id)}.json").resolve()
    root = SESSIONS.resolve()
    # 洗过之后，真实路径仍然必须在 sessions 目录里面
    if path.parent != root:
        raise ValueError(f"Invalid session ID: {session_id}")
    return path

def save_session(messages:list[dict],model:str, session_id: str | None = None) -> str:
    SESSIONS.mkdir(parents=True, exist_ok=True)
    session_id = _safe_id(session_id)
    data = {
        "id": session_id,
        "model": model,
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "messages": messages,
    }

    _path(session_id).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return session_id

def load_session(session_id: str):
    path = _path(session_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data["messages"], data["model"]
    except(json.JSONDecodeError,OSError,KeyError):
        return None
    
def list_sessions() -> list[dict]:
    if not SESSIONS.exists():
        return []
    found = []
    for file in sorted(SESSIONS.glob("*.json"),reverse=True):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except(json.JSONDecodeError,OSError):
            continue
        preview = ""
        for m in data.get("messages",[]):
            if m.get("role") == "user" and m.get("content"):
                preview = str(m["content"])[:80]
                break
        found.append({
            "id": data.get("id", file.stem),
            "model": data.get("model", "?"),
            "saved_at": data.get("saved_at", "?"),
            "preview": preview,
        })
    return found[:20]
