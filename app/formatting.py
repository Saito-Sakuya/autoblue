import html
import time
from typing import Any, Dict, List


def _fmt_ts(ts: int | None) -> str:
    if not ts:
        return ""
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def _item_line(item: Dict[str, Any]) -> str:
    title = html.escape(item.get("title") or "(no title)")
    link = item.get("link") or ""
    link_esc = html.escape(link)
    ts = _fmt_ts(item.get("published_ts"))
    if link:
        core = f"<a href=\"{link_esc}\">{title}</a>"
    else:
        core = title
    if ts:
        return f"• {core} <code>{html.escape(ts)}</code>"
    return f"• {core}"


def build_messages(new_by_source: Dict[str, List[Dict[str, Any]]], fmt: str = "grouped", max_chars: int = 3800) -> List[str]:
    blocks: List[str] = []

    if fmt == "chronological":
        merged: List[Dict[str, Any]] = []
        for src, items in new_by_source.items():
            for it in items:
                it2 = dict(it)
                it2["_source"] = src
                merged.append(it2)
        merged.sort(key=lambda x: x.get("published_ts") or 0, reverse=True)
        lines: List[str] = []
        for it in merged:
            src = html.escape(it.get("_source") or "")
            lines.append(f"<b>{src}</b> { _item_line(it) }")
        blocks.append("\n".join(lines) if lines else "(no updates)")
    else:
        for src, items in new_by_source.items():
            if not items:
                continue
            src_esc = html.escape(src)
            lines = [f"<b>{src_esc}</b>"]
            for it in items:
                lines.append(_item_line(it))
            blocks.append("\n".join(lines))

    text = "\n\n".join(blocks) if blocks else "(no updates)"

    chunks: List[str] = []
    cur = ""
    for part in text.split("\n\n"):
        cand = part if not cur else (cur + "\n\n" + part)
        if len(cand) <= max_chars:
            cur = cand
        else:
            if cur:
                chunks.append(cur)
            if len(part) <= max_chars:
                cur = part
            else:
                buf = ""
                for line in part.split("\n"):
                    cand2 = line if not buf else (buf + "\n" + line)
                    if len(cand2) <= max_chars:
                        buf = cand2
                    else:
                        if buf:
                            chunks.append(buf)
                        buf = line[:max_chars]
                cur = buf
    if cur:
        chunks.append(cur)
    return chunks
