
import math
import re


_CJK = re.compile(r"[一-鿿]")

def estimate_token(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        text = m.get("content") or ""
        if text:
            total += _approx(text)
        if m.get("tool_calls"):
            total += _approx(str(m.get("tool_calls")))
    return total

def _approx(text: str) -> int:
    # 粗估，只用来决定要不要压缩。接口返回的 usage 才是真实用量。
    cjk = len(_CJK.findall(text))
    rest = len(text) - cjk
    return math.ceil(cjk / 1.5) + int(rest / 3)

class ContextManager:
    def __init__(self, max_tokens: int = 128_000):
        self.max_tokens = max_tokens
        # 压缩门槛
        self._snip_at = int(max_tokens * 0.50)
        self._summarize_at = int(max_tokens * 0.70)
        self._collapse_at = int(max_tokens * 0.90)

    def maybe_compress(self,messages: list[dict], llm = None) -> bool:
        current = estimate_token(messages)
        changed = False
        if current > self._snip_at and self._snip(messages):
            changed = True
            current = estimate_token(messages)
        if current > self._summarize_at and len(messages) > 10 and self._summarize(messages, llm, keep_recent = 8):
            changed = True
            current = estimate_token(messages)
        if current > self._collapse_at and len(messages) > 4:
            self._summarize(messages, llm, keep_recent = 4,title = "Hard context reset")
            changed = True
        return changed
    

    @staticmethod
    def _snip( messages: list[dict]) -> bool:
        changed = False
        for m in messages:
            if m.get("role") != "tool":
                continue
            content = m.get("content") or ""
            lines = content.splitlines()
            if len(content) <= 1500 or len(lines) <= 6:
                continue
            m["content"] = (
                "\n".join(lines[:3])
                + f"\n... ({len(lines)} lines, snipped)...\n"
                + "\n".join(lines[-3:])
            )
            changed = True
        return changed
    

    @staticmethod
    def _safe_split(messages: list[dict],keep_recent : int) -> int:
        split = max(0,len(messages) - keep_recent)
        # 保留段不许以 tool 开头，需要和tool_calls 保持一致
        while split > 0 and messages[split].get("role") == "tool":
            split -= 1
        return split
    
    def _summarize(self, messages: list[dict], llm = None, keep_recent = 8, title = "Context compressed") -> bool:
        if len(messages) <= keep_recent:
            return False
        split = self._safe_split(messages, keep_recent)
        old, tail = messages[:split], messages[split:]
        summary = self._summary(old,llm)
        # clear 改的是原列表。Agent.messages 和这里是同一个对象，所以外面看得见。
        messages.clear()
        messages.append(
            {"role": "user", "content": f"{title}\n{summary}"}
        )
        messages.append(
            {"role": "assistant", "content": "Context restored. Continuing."}
        )
        messages.extend(tail)
        return True


    def _summary(self,messages: list[dict], llm = None) -> str:
        flat = "\n".join(
            f"[{m.get('role')}] {(m.get('content') or '')[:400]}"
            for m in messages
            if m.get("content")
        )
        if llm is not None:
            try:
                resp = llm.chat(
                    message=[
                        {"role": "system", "content": (
                        "Compress this conversation. Preserve file paths, decisions, "
                        "errors, and the current task. Drop long command output."
                        )},
                        {"role": "user", "content": flat[:15000]},
                    ]
                )
                if resp.content:
                    return resp.content
            except Exception as e:
                pass
        return flat[:2000] or "(empty)"