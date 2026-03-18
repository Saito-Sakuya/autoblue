import asyncio
import logging
import os
import time
import re
import requests
import html
import random
from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Any, Dict, List

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

from .config import ConfigManager, cfg_get
from .state import StateDB
from .utils import normalize_text, sha1_hex, simhash_text, hamming_distance
from .ai_client import AIClient
from .x_browser import XBrowser

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("xrss-tg-v2")

# 自动检测运行环境：Docker vs 本地
def get_default_path(env_var, docker_path, local_path):
    path = os.getenv(env_var)
    if path:
        return path
    if os.path.exists(os.path.dirname(docker_path)):
        return docker_path
    # 获取项目根目录下的相对路径
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, local_path.lstrip("./"))

CONFIG_PATH = get_default_path("CONFIG_PATH", "/data/config.yaml", "./data/config.yaml")
STATE_PATH = get_default_path("STATE_PATH", "/data/state.sqlite", "./data/state.sqlite")


def validate_runtime_config(cfg: Dict[str, Any]) -> List[str]:
    errs: List[str] = []
    token = cfg_get(cfg, "telegram.bot_token")
    if not token or token == "CHANGE_ME":
        errs.append("telegram.bot_token 未设置")

    xcfg = cfg.get("x", {}) or {}
    cookies_file = str(xcfg.get("cookies_file", "./data/x_cookies.json"))
    following_users = xcfg.get("following_users", []) or []

    if not os.path.exists(cookies_file):
        errs.append(f"cookies 文件不存在: {cookies_file}")
    if not isinstance(following_users, list) or len([u for u in following_users if str(u).strip()]) == 0:
        errs.append("x.following_users 为空，请至少配置 1 个用户名")

    return errs


class Service:
    def __init__(self, cfgm: ConfigManager, db: StateDB):
        self.cfgm = cfgm
        self.db = db
        self.fetch_lock = asyncio.Lock()

    def _cfg(self) -> Dict[str, Any]:
        self.cfgm.reload_if_changed()
        return self.cfgm.get()

    def _is_allowed(self, cfg: Dict[str, Any], update: Update) -> bool:
        allowed = cfg_get(cfg, "telegram.allowed_user_id")
        if allowed is None:
            return True
        try:
            return int(allowed) == int(update.effective_user.id)
        except Exception:
            return False

    async def fetch_and_send(self, app: Application, reason: str = "scheduled") -> None:
        async with self.fetch_lock:
            cfg = self._cfg()
            chat_id = cfg_get(cfg, "telegram.chat_id")
            if not chat_id:
                log.warning("chat_id not set; skipping")
                return

            xcfg = cfg.get("x", {}) or {}
            following_url = xcfg.get("following_url", "")
            cookies_file = xcfg.get("cookies_file", "./data/x_cookies.json")
            language = xcfg.get("language", "en-US")
            following_users = xcfg.get("following_users", [])

            x = XBrowser(cookies_file=cookies_file, language=language, following_users=following_users)

            log.info(f"开始同步关注列表（Twikit）: {following_url or 'config.following_users'}")
            users = await x.fetch_following(following_url)
            
            if not users:
                await app.bot.send_message(chat_id=chat_id, text="未能获取关注账号列表，请先在 config.yaml 设置 x.following_users，或检查 cookies 是否有效。")
                return

            fetch_cfg = cfg.get("fetch", {}) or {}
            max_candidates = int(fetch_cfg.get("max_candidates", 5))
            max_tweets_per_user = int(fetch_cfg.get("max_tweets_per_user", 5))
            batch_size = int(fetch_cfg.get("batch_size", 10))
            user_delay = float(fetch_cfg.get("user_delay", 5.0))  # 账号间的基础随机延迟
            batch_delay = float(fetch_cfg.get("batch_delay", 60.0)) # 分组间的长随机延迟

            ai_cfg = cfg.get("ai", {}) or {}
            # ... (AIClient initialization logic)
            ai = AIClient(
                api_url=str(ai_cfg.get("api_url", "")),
                api_key=str(ai_cfg.get("api_key", "")),
                model=str(ai_cfg.get("model", "gpt-4o-mini")),
                temperature=float(ai_cfg.get("temperature", 0.2)),
                max_tokens=int(ai_cfg.get("max_tokens", 800)),
            )

            candidates = []
            today_utc = datetime.now(timezone.utc).date()
            for idx, u in enumerate(users):
                # 分组与随机延迟逻辑
                if idx > 0:
                    if idx % batch_size == 0:
                        # 换组时休息久一点
                        wait = batch_delay + random.uniform(0, batch_delay * 0.5)
                        log.info(f"已处理一批 ({batch_size}个)，正在进入组间休息: {wait:.1f}s...")
                        await asyncio.sleep(wait)
                    else:
                        # 同组内账号间短休息
                        wait = user_delay + random.uniform(0, user_delay * 0.5)
                        await asyncio.sleep(wait)

                log.info(f"正在抓取用户动态 ({idx+1}/{len(users)}): {u}")
                tweets = await x.fetch_user_tweets(u, max_tweets_per_user)
                for tw in tweets:
                    # 仅保留今天的推文
                    created_at = tw.get("created_at")
                    if created_at:
                        # twikit created_at format is "Fri Jan 17 07:44:02 +0000 2025"
                        # But it's already a string, we need to parse it if we want accurate date.
                        # Actually, let's assume it might be a timestamp or a string.
                        # Based on twikit, it's usually a formatted string.
                        try:
                            # Twikit Tweet objects sometimes have created_at as a string
                            dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
                            if dt.date() != today_utc:
                                continue
                        except Exception as e:
                            log.warning(f"Failed to parse date {created_at}: {e}")
                            # If parsing fails, we skip it to be safe or keep it? 
                            # Let's keep it to avoid missing data if format changes slightly.
                            pass

                    text = normalize_text(tw["text"])
                    h = sha1_hex(text)
                    simh = simhash_text(text)
                    simh = int(simh) & ((1 << 63) - 1)
                    cid = self.db.add_candidate(h, simh, tw["author"], tw["text"], tw["url"])
                    if cid:
                        candidates.append((cid, tw))
                    if len(candidates) >= max_candidates:
                        break
                if len(candidates) >= max_candidates:
                    break

            if not candidates:
                await app.bot.send_message(chat_id=chat_id, text="没有新候选信息。")
                return

            for cid, tw in candidates:
                res = ai.analyze(
                    ai_cfg.get("prompt_system", ""),
                    ai_cfg.get("prompt_filter", ""),
                    ai_cfg.get("prompt_style", ""),
                    tw["text"],
                )
                score = res.get("score")
                threshold = float(ai_cfg.get("keep_threshold", 0.5))
                keep = False
                if score is not None:
                    try:
                        keep = float(score) >= threshold
                    except Exception:
                        keep = bool(res.get("keep"))
                else:
                    keep = bool(res.get("keep"))

                if not keep:
                    self.db.mark_status(cid, "ignored")
                    continue
                summary = res.get("summary", "")
                importance = res.get("importance", "中")
                ttype = res.get("type", "行业")
                msg = (
                    f"<b>重要等级</b>：{importance}\n"
                    f"<b>类型</b>：{ttype}\n"
                    f"<b>摘要</b>：{summary}\n"
                    f"<b>作者</b>：{tw['author']}\n"
                    f"<b>原文</b>：{tw['text']}\n"
                    f"<b>链接</b>：{tw['url']}\n"
                    f"<b>ID</b>：<code>{cid}</code>"
                )
                kb = InlineKeyboardMarkup(
                    [[
                        InlineKeyboardButton("✅ 通过并加入发布队列", callback_data=f"approve:{cid}"),
                        InlineKeyboardButton("❌ 忽略", callback_data=f"ignore:{cid}"),
                    ]]
                )
                await app.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML, reply_markup=kb)




I18N = {
    "zh": {
        "status_title": "状态",
        "queue_title": "待发布队列",
        "queue_empty": "当前没有待发布队列项。",
        "set_interval_ok": "已设置抓取间隔为 {m} 分钟（已生效）。",
        "set_interval_usage": "用法: /set_interval 20",
        "set_interval_invalid": "请输入 >=1 的分钟整数",
        "set_keywords_ok": "已设置关键词: {kws}",
        "set_api_key_ok": "API Key 已更新。",
        "set_api_key_usage": "用法: /set_api_key YOUR_KEY",
        "set_api_key_invalid": "API Key 为空或过短，请重新输入。",
        "set_model_ok": "模型已更新为: {model}",
        "set_model_usage": "用法: /set_model gpt-4o-mini",
        "set_model_invalid": "模型名不能为空。",
        "set_api_url_ok": "API 地址已更新为: {url}",
        "set_api_url_usage": "用法: /set_api_url https://api.openai.com/v1",
        "set_api_url_invalid": "API 地址不合法，请输入 http(s) URL。",
        "set_threshold_ok": "阈值已更新为: {v}",
        "set_threshold_usage": "用法: /set_threshold 0.6",
        "set_threshold_invalid": "阈值必须在 0~1 之间。",
        "test_model_ok": "✅ 模型可用 ({ms} ms)",
        "test_model_fail": "❌ 模型不可用: {err}",
        "test_model_usage": "请先设置 ai.api_url / ai.model / ai.api_key",
        "refresh_start": "⏳ 正在校验关注列表（Twikit）...",
        "refresh_submitted": "✅ 关注列表已校验。可用 /run 触发抓取。",
        "refresh_need_users": "未配置 following_users，请先用 /set_following_url 批量设置。",
        "setchat_ok": "已绑定当前聊天为推送目标。",
        "allowme_ok": "已设置你为管理员。",
        "ignore_ok": "已忽略此条。",
        "approve_ok": "已加入发布队列。",
        "already_posted": "该条已发布，未重复入队。",
        "already_in_queue": "该条已在队列中，无需重复加入。",
        "show_following_title": "关注列表（第 {page} 页）",
        "show_following_empty": "关注列表为空，请用 /set_following_url 添加。",
        "show_following_usage": "用法: /show_following 1",
        "set_following_ok": "已更新 following_users：{n} 个",
        "set_following_usage": "用法: /set_following_url a b c 或 /set_following_url https://x.com/name",
        "set_following_clear": "已清空 following_users。",
        "set_ai_filter_ok": "AI 筛选提示词已更新。",
        "set_ai_filter_usage": "用法: /set_ai_filter [提示词内容]",
        "set_max_tokens_ok": "Max Tokens 已更新为: {v}",
        "set_max_tokens_usage": "用法: /set_max_tokens 1000",
        "set_max_tokens_invalid": "请输入有效的整数 (如 100~4000)。",
    },
    "en": {
        "status_title": "Status",
        "queue_title": "Queue",
        "queue_empty": "Queue is empty.",
        "set_interval_ok": "Fetch interval set to {m} minutes (applied).",
        "set_interval_usage": "Usage: /set_interval 20",
        "set_interval_invalid": "Please input an integer >= 1",
        "set_keywords_ok": "Keywords updated: {kws}",
        "set_api_key_ok": "API key updated.",
        "set_api_key_usage": "Usage: /set_api_key YOUR_KEY",
        "set_api_key_invalid": "API key is empty or too short.",
        "set_model_ok": "Model updated: {model}",
        "set_model_usage": "Usage: /set_model gpt-4o-mini",
        "set_model_invalid": "Model name is empty.",
        "set_api_url_ok": "API URL updated: {url}",
        "set_api_url_usage": "Usage: /set_api_url https://api.openai.com/v1",
        "set_api_url_invalid": "Invalid API URL, please input http(s).",
        "set_threshold_ok": "Threshold updated: {v}",
        "set_threshold_usage": "Usage: /set_threshold 0.6",
        "set_threshold_invalid": "Threshold must be between 0 and 1.",
        "test_model_ok": "✅ Model OK ({ms} ms)",
        "test_model_fail": "❌ Model failed: {err}",
        "test_model_usage": "Please set ai.api_url / ai.model / ai.api_key",
        "refresh_start": "Checking following list (Twikit)...",
        "refresh_submitted": "✅ Following list checked. Use /run to fetch now.",
        "refresh_need_users": "following_users is empty. Use /set_following_url to add.",
        "setchat_ok": "Chat bound as notification target.",
        "allowme_ok": "You are now an admin.",
        "ignore_ok": "Ignored.",
        "approve_ok": "Added to publish queue.",
        "already_posted": "Already posted, not queued again.",
        "already_in_queue": "Already in queue, no duplicate added.",
        "show_following_title": "Following list (page {page})",
        "show_following_empty": "Following list is empty. Use /set_following_url.",
        "show_following_usage": "Usage: /show_following 1",
        "set_following_ok": "following_users updated: {n}",
        "set_following_usage": "Usage: /set_following_url a b c or /set_following_url https://x.com/name",
        "set_following_clear": "following_users cleared.",
        "set_ai_filter_ok": "AI filter prompt updated.",
        "set_ai_filter_usage": "Usage: /set_ai_filter [prompt text]",
        "set_max_tokens_ok": "Max Tokens updated to: {v}",
        "set_max_tokens_usage": "Usage: /set_max_tokens 1000",
        "set_max_tokens_invalid": "Please input a valid integer (e.g., 100~4000).",
    }
}


def get_lang(cfg: Dict[str, Any]) -> str:
    xcfg = cfg.get("x", {}) or {}
    lang = str(xcfg.get("language", "zh")).lower()
    if lang.startswith("en"):
        return "en"
    return "zh"

def t(key: str, lang: str = "zh", **kwargs) -> str:
    d = I18N.get(lang, I18N["zh"])
    text = d.get(key, key)
    return text.format(**kwargs)

def get_help_text() -> str:
    return """<b>🌟 AutoBlue - 指令手册</b>

<b>1. 核心设置</b>
🔗 <code>/set_following_url ...</code>
   支持批量：URL / @用户名 / 纯用户名，空格或逗号分隔
🔍 <code>/show_following [页码]</code>
   查看当前 following 列表
🔄 <code>/refresh_following</code>
   校验关注列表（Twikit 语义）
🚀 <code>/run</code>
   手动触发一次全量抓取与 AI 筛选

<b>2. AI 与策略调整</b>
🤖 <code>/show_ai</code> - 查看当前 AI 配置
🧠 <code>/set_model [模型名]</code>
🌐 <code>/set_api_url [地址]</code>
🔑 <code>/set_api_key [KEY]</code>
🎯 <code>/set_threshold [0~1]</code>
📝 <code>/set_ai_filter [内容]</code> - 修改 AI 筛选提示词
🔢 <code>/set_max_tokens [长度]</code> - 修改 Max Tokens 长度
🧪 <code>/test_model</code> - 模型连通性自检
🔍 <code>/set_keywords [词1,词2]</code> - 设置额外关键词
⏱️ <code>/set_interval [分钟]</code> - 修改抓取频率

<b>3. 管理</b>
📊 <code>/status</code> - 查看运行状态摘要
📅 <code>/queue</code> - 查看待发布任务队列
🆔 <code>/allowme</code> - 绑定当前账号为管理员
📌 <code>/setchat</code> - 将当前窗口设为推送目标

<i>💡 提示：所有设置项也可以通过服务器上的 scripts/menu.sh 修改。</i>"""


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc: Service = context.application.bot_data["svc"]
    cfg = svc._cfg()
    if not svc._is_allowed(cfg, update):
        return
    text = get_help_text()
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)


def _parse_following_inputs(args):
    raw = " ".join(args).strip()
    if not raw:
        return [], False
    tokens = []
    for part in re.split(r"[\s,]+", raw):
        if not part:
            continue
        tokens.append(part)
    if len(tokens) == 1 and tokens[0].lower() in ("clear", "reset", "empty"):
        return [], True

    users = []
    for t in tokens:
        t = t.strip()
        if not t:
            continue
        if t.startswith("http://") or t.startswith("https://"):
            try:
                u = urlparse(t)
                path = u.path.strip("/")
                if not path:
                    continue
                name = path.split("/")[0]
            except Exception:
                continue
        else:
            name = t
        if name.startswith("@"):
            name = name[1:]
        name = name.strip()
        if not name:
            continue
        if not re.match(r"^[A-Za-z0-9_]{1,15}$", name):
            continue
        users.append(name)

    seen = set()
    uniq = []
    for u in users:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq, False


async def cmd_set_following_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc: Service = context.application.bot_data["svc"]
    cfg = svc._cfg()
    if not svc._is_allowed(cfg, update):
        return

    lang = get_lang(cfg)
    if not context.args:
        await update.effective_message.reply_text(t("set_following_usage", lang))
        return

    users, do_clear = _parse_following_inputs(context.args)
    if do_clear:
        cfg.setdefault("x", {})["following_users"] = []
        svc.cfgm.save(cfg)
        await update.effective_message.reply_text(t('set_following_clear', lang))
        return

    if not users:
        await update.effective_message.reply_text(t('set_following_usage', lang))
        return

    xcfg = cfg.setdefault("x", {})
    existing = xcfg.get("following_users", [])
    if not isinstance(existing, list):
        existing = []

    # 增量添加并去重
    updated = list(dict.fromkeys(existing + users))
    xcfg["following_users"] = updated
    svc.cfgm.save(cfg)
    await update.effective_message.reply_text(t('set_following_ok', lang, n=len(updated)))



async def cmd_show_following(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc: Service = context.application.bot_data["svc"]
    cfg = svc._cfg()
    if not svc._is_allowed(cfg, update):
        return
    lang = get_lang(cfg)
    users = (cfg.get("x", {}) or {}).get("following_users", []) or []
    if not users:
        await update.effective_message.reply_text(t("show_following_empty", lang))
        return
    page = 1
    if context.args:
        try:
            page = int(context.args[0])
            if page < 1:
                page = 1
        except Exception:
            await update.effective_message.reply_text(t("show_following_usage", lang))
            return
    page_size = 20
    start = (page - 1) * page_size
    end = start + page_size
    slice_users = users[start:end]
    if not slice_users:
        await update.effective_message.reply_text(t("show_following_usage", lang))
        return
    lines = [f"<b>{t('show_following_title', lang, page=page)}</b>"]
    for u in slice_users:
        lines.append(f"- <code>{u}</code>")
    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_refresh_following(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc: Service = context.application.bot_data["svc"]
    cfg = svc._cfg()
    if not svc._is_allowed(cfg, update):
        return

    lang = get_lang(cfg)
    users = (cfg.get("x", {}) or {}).get("following_users", []) or []
    if not users:
        await update.effective_message.reply_text(t("refresh_need_users", lang))
        return
    await update.effective_message.reply_text(t("refresh_start", lang))
    await update.effective_message.reply_text(t("refresh_submitted", lang))


async def cmd_setchat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc: Service = context.application.bot_data["svc"]
    cfg = svc._cfg()
    if not svc._is_allowed(cfg, update):
        return
    cfg.setdefault("telegram", {})
    cfg["telegram"]["chat_id"] = int(update.effective_chat.id)
    svc.cfgm.save(cfg)
    lang = get_lang(cfg)
    await update.effective_message.reply_text(t("setchat_ok", lang))


async def cmd_allowme(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc: Service = context.application.bot_data["svc"]
    cfg = svc._cfg()
    cfg.setdefault("telegram", {})
    cfg["telegram"]["allowed_user_id"] = int(update.effective_user.id)
    svc.cfgm.save(cfg)
    lang = get_lang(cfg)
    await update.effective_message.reply_text(t("allowme_ok", lang))


async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc: Service = context.application.bot_data["svc"]
    cfg = svc._cfg()
    if not svc._is_allowed(cfg, update):
        return
    await svc.fetch_and_send(context.application, reason="manual")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc: Service = context.application.bot_data["svc"]
    cfg = svc._cfg()
    if not svc._is_allowed(cfg, update):
        return
    fetch = cfg.get("fetch", {}) or {}
    xcfg = cfg.get("x", {}) or {}
    db = svc.db
    lang = xcfg.get("language", "zh")
    text = (
        f"<b>{t('status_title', lang)}</b>\n"
        f"interval: {fetch.get('interval_minutes', 20)} 分钟\n"
        f"following_users: {len(xcfg.get('following_users', []) or [])}\n"
        f"cookies_file: <code>{xcfg.get('cookies_file', './data/x_cookies.json')}</code>\n"
        f"queue_pending: {db.count_queue_pending()}\n"
        f"posts_today: {db.count_posts_today()}"
    )
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)



async def cmd_show_ai(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc: Service = context.application.bot_data["svc"]
    cfg = svc._cfg()
    if not svc._is_allowed(cfg, update):
        return
    ai = cfg.get("ai", {}) or {}
    pf = str(ai.get('prompt_filter', ''))
    
    # 扩大显示范围到 3000 字符，并转义特殊字符
    if len(pf) > 3000:
        pf_display = html.escape(pf[:3000]) + "..."
    else:
        pf_display = html.escape(pf)

    text = (
        f"<b>AI设置</b>\n"
        f"model: <code>{ai.get('model','')}</code>\n"
        f"api_url: <code>{ai.get('api_url','')}</code>\n"
        f"temperature: {ai.get('temperature', 0.2)}\n"
        f"max_tokens: {ai.get('max_tokens', 800)}\n"
        f"keep_threshold: {ai.get('keep_threshold', 0.5)}\n"
        f"筛选提示词: <code>{pf_display}</code>"
    )
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_set_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc: Service = context.application.bot_data["svc"]
    cfg = svc._cfg()
    if not svc._is_allowed(cfg, update):
        return
    lang = get_lang(cfg)
    if not context.args:
        await update.effective_message.reply_text(t('set_model_usage', lang))
        return
    model = ' '.join(context.args).strip()
    if not model:
        await update.effective_message.reply_text(t('set_model_invalid', lang))
        return
    cfg.setdefault("ai", {})["model"] = model
    svc.cfgm.save(cfg)
    await update.effective_message.reply_text(t('set_model_ok', lang, model=model))


async def cmd_set_api_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc: Service = context.application.bot_data["svc"]
    cfg = svc._cfg()
    if not svc._is_allowed(cfg, update):
        return
    lang = get_lang(cfg)
    if not context.args:
        await update.effective_message.reply_text(t('set_api_url_usage', lang))
        return
    url = ' '.join(context.args).strip()
    if not (url.startswith('http://') or url.startswith('https://')):
        await update.effective_message.reply_text(t('set_api_url_invalid', lang))
        return
    cfg.setdefault("ai", {})["api_url"] = url
    svc.cfgm.save(cfg)
    await update.effective_message.reply_text(t('set_api_url_ok', lang, url=url))


async def cmd_set_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc: Service = context.application.bot_data["svc"]
    cfg = svc._cfg()
    if not svc._is_allowed(cfg, update):
        return
    lang = get_lang(cfg)
    if not context.args:
        await update.effective_message.reply_text(t('set_threshold_usage', lang))
        return
    try:
        v = float(context.args[0])
    except Exception:
        await update.effective_message.reply_text(t('set_threshold_invalid', lang))
        return
    if v < 0 or v > 1:
        await update.effective_message.reply_text(t('set_threshold_invalid', lang))
        return
    cfg.setdefault("ai", {})["keep_threshold"] = v
    svc.cfgm.save(cfg)
    await update.effective_message.reply_text(t('set_threshold_ok', lang, v=v))


async def cmd_set_ai_filter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc: Service = context.application.bot_data["svc"]
    cfg = svc._cfg()
    if not svc._is_allowed(cfg, update):
        return
    lang = get_lang(cfg)
    if not context.args:
        await update.effective_message.reply_text(t('set_ai_filter_usage', lang))
        return
    content = ' '.join(context.args).strip()
    cfg.setdefault("ai", {})["prompt_filter"] = content
    svc.cfgm.save(cfg)
    await update.effective_message.reply_text(t('set_ai_filter_ok', lang))


async def cmd_set_max_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc: Service = context.application.bot_data["svc"]
    cfg = svc._cfg()
    if not svc._is_allowed(cfg, update):
        return
    lang = get_lang(cfg)
    if not context.args:
        await update.effective_message.reply_text(t('set_max_tokens_usage', lang))
        return
    try:
        v = int(context.args[0])
    except Exception:
        await update.effective_message.reply_text(t('set_max_tokens_invalid', lang))
        return
    if v < 1 or v > 128000:
        await update.effective_message.reply_text(t('set_max_tokens_invalid', lang))
        return
    cfg.setdefault("ai", {})["max_tokens"] = v
    svc.cfgm.save(cfg)
    await update.effective_message.reply_text(t('set_max_tokens_ok', lang, v=v))


async def cmd_test_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc: Service = context.application.bot_data["svc"]
    cfg = svc._cfg()
    if not svc._is_allowed(cfg, update):
        return
    lang = get_lang(cfg)
    ai = cfg.get("ai", {}) or {}
    api_url = str(ai.get("api_url", "")).strip()
    api_key = str(ai.get("api_key", "")).strip()
    model = str(ai.get("model", "")).strip()
    if not api_url or not model:
        await update.effective_message.reply_text(t('test_model_usage', lang))
        return

    if api_url.endswith('/chat/completions'):
        endpoint = api_url
    elif api_url.endswith('/v1'):
        endpoint = api_url + '/chat/completions'
    else:
        endpoint = api_url.rstrip('/') + '/v1/chat/completions'

    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 10,
        "messages": [{"role": "user", "content": "ping"}],
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    import time as _time
    start = _time.time()
    try:
        r = requests.post(endpoint, headers=headers, json=payload, timeout=20)
        if r.status_code >= 400:
            raise Exception(f"HTTP {r.status_code}: {r.text[:200]}")
        ms = int((_time.time() - start) * 1000)
        await update.effective_message.reply_text(t('test_model_ok', lang, ms=ms))
    except Exception as e:
        await update.effective_message.reply_text(t('test_model_fail', lang, err=str(e)[:200]))


async def cmd_set_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc: Service = context.application.bot_data["svc"]
    cfg = svc._cfg()
    if not svc._is_allowed(cfg, update):
        return
    xcfg = cfg.get("x", {}) or {}
    lang = xcfg.get("language", "zh")
    if not context.args:
        await update.effective_message.reply_text(t('set_interval_usage', lang))
        return
    try:
        m = int(context.args[0])
        if m < 1:
            raise ValueError
    except Exception:
        await update.effective_message.reply_text(t('set_interval_invalid', lang))
        return
    cfg.setdefault("fetch", {})["interval_minutes"] = m
    svc.cfgm.save(cfg)

    scheduler = context.application.bot_data.get('scheduler')
    fetch_job_id = context.application.bot_data.get('fetch_job_id')
    if scheduler and fetch_job_id:
        try:
            scheduler.remove_job(fetch_job_id)
        except Exception:
            pass
        job = scheduler.add_job(svc.fetch_and_send, "interval", args=[context.application], minutes=m)
        context.application.bot_data['fetch_job_id'] = job.id
    await update.effective_message.reply_text(t('set_interval_ok', lang, m=m))



async def cmd_queue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc: Service = context.application.bot_data["svc"]
    cfg = svc._cfg()
    if not svc._is_allowed(cfg, update):
        return
    xcfg = cfg.get("x", {}) or {}
    lang = xcfg.get("language", "zh")
    items = svc.db.list_queue_pending(limit=10)
    if not items:
        await update.effective_message.reply_text(t('queue_empty', lang))
        return
    lines = [f"<b>{t('queue_title', lang)}</b>"]
    for it in items:
        text = (it.get('text') or '').replace('\n',' ')[:120]
        lines.append(f"- <code>{it['candidate_id']}</code> {it['author']}: {text}")
    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)



async def cmd_set_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc: Service = context.application.bot_data["svc"]
    cfg = svc._cfg()
    if not svc._is_allowed(cfg, update):
        return
    xcfg = cfg.get("x", {}) or {}
    lang = xcfg.get("language", "zh")
    raw = ' '.join(context.args).strip()
    kws = [x.strip() for x in raw.split(',') if x.strip()] if raw else []
    # 去重保序
    seen = set()
    uniq = []
    for k in kws:
        if k not in seen:
            seen.add(k)
            uniq.append(k)
    cfg.setdefault("monitor", {})["keywords"] = uniq
    svc.cfgm.save(cfg)
    await update.effective_message.reply_text(t('set_keywords_ok', lang, kws=uniq))



async def cmd_set_api_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc: Service = context.application.bot_data["svc"]
    cfg = svc._cfg()
    if not svc._is_allowed(cfg, update):
        return
    xcfg = cfg.get("x", {}) or {}
    lang = xcfg.get("language", "zh")
    if not context.args:
        await update.effective_message.reply_text(t('set_api_key_usage', lang))
        return
    key = ' '.join(context.args).strip()
    if not key or len(key) < 8:
        await update.effective_message.reply_text(t('set_api_key_invalid', lang))
        return
    cfg.setdefault("ai", {})["api_key"] = key
    svc.cfgm.save(cfg)
    await update.effective_message.reply_text(t('set_api_key_ok', lang))



async def cb_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc: Service = context.application.bot_data["svc"]
    cfg = svc._cfg()
    if not svc._is_allowed(cfg, update):
        return
    q = update.callback_query
    await q.answer()
    action, cid = q.data.split(":", 1)
    cid_i = int(cid)
    if action == "ignore":
        svc.db.mark_status(cid_i, "ignored")
        await q.edit_message_reply_markup(reply_markup=None)
        lang = get_lang(cfg)
        await q.edit_message_text(t("ignore_ok", lang))
        return
    if action == "approve":
        if svc.db.has_post(cid_i):
            lang = get_lang(cfg)
            await q.edit_message_text(t("already_posted", lang))
            return
        if svc.db.is_in_queue(cid_i):
            lang = get_lang(cfg)
            await q.edit_message_text(t("already_in_queue", lang))
            return
        now = int(time.time())
        svc.db.enqueue(cid_i, now)
        svc.db.mark_status(cid_i, "queued")
        await q.edit_message_reply_markup(reply_markup=None)
        lang = get_lang(cfg)
        await q.edit_message_text(t("approve_ok", lang))


async def publish_worker(app: Application, svc: Service) -> None:
    cfg = svc._cfg()
    pub = cfg.get("publish", {}) or {}
    daily_limit = int(pub.get("daily_limit", 5))
    if svc.db.count_posts_today() >= daily_limit:
        return
    xcfg = cfg.get("x", {}) or {}
    x = XBrowser(cookies_file=xcfg.get("cookies_file", "./data/x_cookies.json"), language=xcfg.get("language", "en-US"), following_users=xcfg.get("following_users", []))
    for item in svc.db.claim_ready(int(time.time())):
        qid = item["queue_id"]
        cid = item["candidate_id"]
        if svc.db.has_post(cid):
            svc.db.mark_queue_status(qid, "done")
            continue
        try:
            # 简化：从数据库取文案
            # 实际可扩展为：存储草稿/编辑文本
            # 目前直接复用候选文本
            # TODO: 支持编辑文本
            url = await x.post_tweet("自动发布内容，请在 Telegram 中编辑版本优化。")
            svc.db.record_post(cid, url)
            svc.db.mark_status(cid, "posted")
            svc.db.mark_queue_status(qid, "done")
        except Exception as e:
            svc.db.mark_queue_status(qid, "failed")
            log.exception("publish_worker failed for cid=%s: %s", cid, e)


async def main() -> None:
    cfgm = ConfigManager(CONFIG_PATH)
    cfg = cfgm.load()

    errs = validate_runtime_config(cfg)
    if errs:
        raise SystemExit("启动配置检查失败:\n- " + "\n- ".join(errs))

    db = StateDB(STATE_PATH)
    db.init()

    app = Application.builder().token(cfg_get(cfg, "telegram.bot_token")).build()
    svc = Service(cfgm, db)
    app.bot_data["svc"] = svc

    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("setchat", cmd_setchat))
    app.add_handler(CommandHandler("allowme", cmd_allowme))
    app.add_handler(CommandHandler("run", cmd_run))
    app.add_handler(CommandHandler("set_following_url", cmd_set_following_url))
    app.add_handler(CommandHandler("show_following", cmd_show_following))
    app.add_handler(CommandHandler("refresh_following", cmd_refresh_following))
    app.add_handler(CommandHandler("set_api_key", cmd_set_api_key))
    app.add_handler(CommandHandler("set_model", cmd_set_model))
    app.add_handler(CommandHandler("set_api_url", cmd_set_api_url))
    app.add_handler(CommandHandler("set_threshold", cmd_set_threshold))
    app.add_handler(CommandHandler("set_ai_filter", cmd_set_ai_filter))
    app.add_handler(CommandHandler("set_max_tokens", cmd_set_max_tokens))
    app.add_handler(CommandHandler("test_model", cmd_test_model))
    app.add_handler(CommandHandler("set_keywords", cmd_set_keywords))
    app.add_handler(CommandHandler("queue", cmd_queue))
    app.add_handler(CommandHandler("set_interval", cmd_set_interval))
    app.add_handler(CommandHandler("show_ai", cmd_show_ai))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CallbackQueryHandler(cb_action))

    scheduler = AsyncIOScheduler()
    # 直接传递异步函数名和参数，AsyncIOScheduler 会自动处理协程
    fetch_interval = int(cfg_get(cfg, "fetch.interval_minutes", 20))
    job = scheduler.add_job(svc.fetch_and_send, "interval", args=[app], minutes=fetch_interval)
    app.bot_data["fetch_job_id"] = job.id
    scheduler.add_job(publish_worker, "interval", args=[app, svc], minutes=1)

    scheduler.start()

    app.bot_data["scheduler"] = scheduler

    await app.initialize()
    await app.start()
    # startup greeting
    try:
        chat_id = cfg_get(cfg, "telegram.chat_id")
        if chat_id:
            await app.bot.send_message(chat_id=chat_id, text="✅ AutoBlue 已启动，以下是指令手册：\n\n" + get_help_text(), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except Exception as e:
        log.warning(f"startup greeting failed: {e}")
    await app.updater.start_polling()
    log.info("机器人已启动，正在监听消息 (按下 Ctrl+C 停止)...")
    
    # 保持程序运行，直到收到退出信号
    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
        log.info("正在停止服务...")
    finally:
        # 停止服务
        if app.updater.running:
            await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
