

from ntpath import isfile
import os
import shutil
import subprocess


def git_bash() -> str | None:
    if os.name != "nt":
        return None
    candidate = os.path.join(os.environ.get("ProgramFiles","C:\\Program Files"),"Git","bin","bash.exe")
    if os.path.exists(candidate):
        return candidate
    git = shutil.which("git")
    if git:
        derived = os.path.join(os.path.dirname(git),"..","bin","bash.exe")
        if os.path.isfile(derived):
            return derived
    return None

def run_shell(command: str, **kwargs) -> subprocess.CompletedProcess:
    bash = git_bash()
    if bash:
        # 列表形式 + shell=False，命令字符串交给 bash -c，不经过 cmd.exe
        return subprocess.run([bash, "-c", command], **kwargs)
    # 默认使用 cmd.exe，命令字符串交给 cmd.exe 处理
    return subprocess.run(command, shell=True, **kwargs)