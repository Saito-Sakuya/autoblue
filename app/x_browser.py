import asyncio
import json
import logging
import random
from typing import Dict, List, Optional

from twikit import Client

log = logging.getLogger(__name__)


class XBrowser:
    """
    Twikit facade for X operations.
    Keep method names close to previous implementation to minimize main.py changes.
    """

    def __init__(
        self,
        cookies_file: str,
        language: str = "en-US",
        following_users: Optional[List[str]] = None,
    ):
        self.cookies_file = cookies_file
        self.language = language or "en-US"
        self.following_users = following_users or []
        self.client = Client(self.language)
        self._ready = False
        self.max_retries = 3
        self.base_delay = 1.2
        self.max_jitter = 0.8

    async def init_client(self) -> None:
        if self._ready:
            return
        # Twikit load_cookies expects dict or list of (name,value);
        # our cookies file is list[dict], convert to name->value dict.
        with open(self.cookies_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            cookie_map = {c.get('name'): c.get('value') for c in data if isinstance(c, dict) and c.get('name') and c.get('value')}
            self.client.set_cookies(cookie_map)
        elif isinstance(data, dict):
            self.client.set_cookies(data)
        else:
            raise ValueError('Unsupported cookies format')
        self._ready = True


    async def _with_retry(self, coro_factory, op_name: str):
        last_err = None
        for i in range(1, self.max_retries + 1):
            try:
                if i > 1:
                    delay = self.base_delay * (2 ** (i - 2)) + random.random() * self.max_jitter
                    await asyncio.sleep(delay)
                return await coro_factory()
            except Exception as e:
                last_err = e
                msg = str(e).lower()
                if '429' in msg or 'rate' in msg or 'too many' in msg:
                    log.warning('%s hit rate limit on try %s/%s: %s', op_name, i, self.max_retries, e)
                elif '401' in msg or '403' in msg or 'auth' in msg or 'login' in msg:
                    log.error('%s auth/session issue on try %s/%s: %s', op_name, i, self.max_retries, e)
                else:
                    log.warning('%s failed on try %s/%s: %s', op_name, i, self.max_retries, e)
        raise last_err
    async def manual_login(self, *args, **kwargs) -> None:
        raise RuntimeError("Twikit mode does not support Playwright manual_login here. Use scripts/import_cookies.py.")

    async def fetch_following(self, following_url: str = "") -> List[str]:
        """
        In Twikit mode we prefer configured static following list.
        following_url kept only for compatibility.
        """
        await self.init_client()
        users = [u.strip().lstrip('@') for u in self.following_users if str(u).strip()]
        return sorted(list(dict.fromkeys(users)))

    async def fetch_user_tweets(self, username: str, max_items: int = 5) -> List[Dict[str, str]]:
        await self.init_client()
        username = username.strip().lstrip('@')
        if not username:
            return []

        try:
            user = await self._with_retry(
                lambda: self.client.get_user_by_screen_name(username),
                f"get_user_by_screen_name:{username}"
            )
            tweets = await self._with_retry(
                lambda: self.client.get_user_tweets(user.id, 'Tweets'),
                f"get_user_tweets:{username}"
            )
        except Exception as e:
            log.exception("fetch_user_tweets failed for %s after retries: %s", username, e)
            return []

        results: List[Dict[str, str]] = []
        for t in tweets:
            text = getattr(t, 'text', None) or ''
            tid = str(getattr(t, 'id', ''))
            if not text:
                continue
            url = f"https://x.com/{username}/status/{tid}" if tid else f"https://x.com/{username}"
            results.append({
                "author": username,
                "text": text,
                "url": url,
                "created_at": getattr(t, 'created_at', None)
            })
            if len(results) >= max_items:
                break
        if not results:
            log.info("fetched 0 tweets for %s (possible filtering/empty timeline)", username)
        else:
            log.info("fetched %s tweets for %s", len(results), username)
        return results

    async def post_tweet(self, text: str) -> str:
        await self.init_client()
        try:
            tw = await self._with_retry(
                lambda: self.client.create_tweet(text=text[:280]),
                "create_tweet"
            )
        except Exception as e:
            log.exception("post_tweet failed after retries: %s", e)
            raise
        tid = str(getattr(tw, 'id', ''))
        return f"https://x.com/i/status/{tid}" if tid else "https://x.com/home"
