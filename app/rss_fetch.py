from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import feedparser
import requests
from dateutil import parser as dtparser


def _to_ts(entry: dict) -> int | None:
    for k in ("published", "updated"):
        if k in entry and entry[k]:
            try:
                return int(dtparser.parse(entry[k]).timestamp())
            except Exception:
                pass
    return None


def _guid(entry: dict) -> str | None:
    return entry.get("id") or entry.get("guid") or entry.get("link")


@dataclass
class RSSFetcher:
    timeout_seconds: int = 20
    user_agent: str = "xrss-tg/1.0"

    def fetch(self, source_name: str, rss_url: str) -> Tuple[List[Dict[str, Any]], str | None]:
        try:
            r = requests.get(
                rss_url,
                timeout=self.timeout_seconds,
                headers={"User-Agent": self.user_agent},
            )
            r.raise_for_status()
            parsed = feedparser.parse(r.text)
            items: List[Dict[str, Any]] = []
            for ent in parsed.entries or []:
                items.append(
                    {
                        "guid": _guid(ent),
                        "title": (ent.get("title") or "").strip(),
                        "link": ent.get("link"),
                        "published_ts": _to_ts(ent),
                    }
                )
            items.sort(key=lambda x: x.get("published_ts") or 0, reverse=True)
            return items, None
        except Exception as e:
            return [], f"{type(e).__name__}: {e}"
