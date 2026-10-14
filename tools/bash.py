

from cgitb import text
import encodings
import os
import re
import subprocess
import threading
from tools.base import Tool
from tools.shell_Util import run_shell


# 每个线程一份当前目录，并发时两条命令不会抢同一个路径。
_local = threading.local()


def get_cwd():
    return getattr(_local, "cwd", None)


def set_cwd(path):
    if path is None:
        if hasattr(_local, "cwd"):
            delattr(_local, "cwd")
    else:
        _local.cwd = path

_DANGEROUS = [
    (r"\brm\s+(-\w*)?-r\w*\s+(/|~|\$HOME)", "recursive delete on home or root"),
    (r"\brm\b(?=(?:.*\s)?-\w*[rR])(?=(?:.*\s)?-\w*f)", "force recursive delete"),
    (r"\bmkfs\b", "format filesystem"),
    (r"\bdd\s+.*of=/dev/", "raw disk write"),
    (r":\(\)\s*\{.*:\|:.*\}", "fork bomb"),
    (r"\bcurl\b.*\|\s*(sudo\s+)?(ba)?sh\b", "pipe curl to shell"),
    (r"\bwget\b.*\|\s*(sudo\s+)?(ba)?sh\b", "pipe wget to shell"),
]

class BashTool(Tool):
    name = "bash"
    description = (
        "Run a shell command. Returns stdout, stderr, and the exit code. "
        "Use it for tests, git, and other commands."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The command to run"},
            "timeout": {"type": "integer", "description": "Timeout in seconds. Default 120."},
        },
        "required": ["command"],
    }

    def execute(self, command: str, timeout: int = 120) -> str:
        reason = _danger(command)
        if reason:
            return f"Error: dangerous command: {command}. {reason}"
        
        cwd = get_cwd() or os.getcwd()
        try:
            proc = run_shell(
                command=command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=cwd,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            return f"Error: command timed out after {timeout} seconds: {command}"
        except Exception as e:
            return f"Error: command failed: {command}. {e}"
        
        if proc.returncode == 0:
            set_cwd(_track_cd(command, cwd))
        
        out = proc.stdout or ""
        if proc.stderr:
            out += f"\n\nError: {proc.stderr}"
        if proc.returncode != 0:
            out += f"\n\nError: command failed with exit code {proc.returncode}"
        if len(out) > 15000:
            out = out[:6000] + f"\n\n... truncated ({len(out)} chars total) ...\n\n" + out[-3000:]
        return out.strip() or "No output."
    
def _danger(command: str) -> str | None:
    for pattern,reason in _DANGEROUS:
        if re.search(pattern,command):
            return reason
    return None
    
def _track_cd(command: str, cwd: str) -> str:
    """只跟踪一条以 cd 开头、或用 && / ; 串起来的 cd。够用即可。"""
    current = cwd
    # 用 && 和 ; 切开。引号里的分隔符这里先不处理，成品见 corecoder/tools/bash.py
    for part in re.split(r"&&|;", command):
        words = part.strip().split()
        if not words or words[0] != "cd":
            continue
        target = words[1] if len(words) > 1 else "~"
        target = os.path.expanduser(target)
        new_dir = target if os.path.isabs(target) else os.path.normpath(os.path.join(current, target))
        if os.path.isdir(new_dir):
            current = new_dir
    return current