import os
from dotenv import load_dotenv

# ===== 強制載入目前專案根目錄 .env =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(dotenv_path=ENV_PATH, override=False)

import logging
import json
import secrets
import feedparser
import urllib.parse
import html
import re
import pytz
import datetime
import requests
import uuid
import threading

from bs4 import BeautifulSoup
from datetime import time

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

from openai import OpenAI
from gsheet import get_tracking_data

# ===== 環境變數 =====
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
NEWS_SEARCH_TIMEOUT = int(os.getenv("NEWS_SEARCH_TIMEOUT", "10"))
WEATHER_LOCATION = os.getenv("WEATHER_LOCATION", "Taipei")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

TRACK_BASE_URL = os.getenv("TRACK_BASE_URL", "https://your-domain.com")
LANDING_PAGE_URL = os.getenv("LANDING_PAGE_URL", "https://your-landing-page.com")
THANKYOU_PAGE_URL = os.getenv("THANKYOU_PAGE_URL", "https://your-thankyou-page.com")

GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "-5266698491"))
DATA_DIR = os.getenv("BOT_DATA_DIR", BASE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)
GROUP_CONFIG_FILE = os.path.join(DATA_DIR, "group_config.json")
SCHEDULE_CONFIG_FILE = os.path.join(DATA_DIR, "schedule_config.json")
AUTHORIZED_USERS_FILE = os.path.join(DATA_DIR, "authorized_users.json")
PAIR_CODES_FILE = os.path.join(DATA_DIR, "pending_pair_codes.json")
SCHEDULE_EXECUTION_LOG_FILE = os.path.join(DATA_DIR, "schedule_execution_log.json")
SESSION_SETTINGS_FILE = os.path.join(DATA_DIR, "session_settings.json")
LEGACY_GROUP_CONFIG_FILE = os.path.join(BASE_DIR, "group_config.json")
LEGACY_SCHEDULE_CONFIG_FILE = os.path.join(BASE_DIR, "schedule_config.json")
LEGACY_AUTHORIZED_USERS_FILE = os.path.join(BASE_DIR, "authorized_users.json")
LEGACY_PAIR_CODES_FILE = os.path.join(BASE_DIR, "pending_pair_codes.json")
LEGACY_SCHEDULE_EXECUTION_LOG_FILE = os.path.join(BASE_DIR, "schedule_execution_log.json")
LEGACY_SESSION_SETTINGS_FILE = os.path.join(BASE_DIR, "session_settings.json")
ALLOWED_REPORT_TYPES = ["marketing", "report", "optimize", "daily_push"]
ADMIN_USER_IDS = {
    int(value.strip())
    for value in os.getenv("ADMIN_USER_IDS", "").split(",")
    if value.strip()
}
if TARGET_CHAT_ID:
    try:
        ADMIN_USER_IDS.add(int(TARGET_CHAT_ID))
    except ValueError:
        pass

if not TOKEN or not OPENAI_API_KEY:
    raise ValueError("❌ 缺少必要環境變數：TELEGRAM_BOT_TOKEN / OPENAI_API_KEY")

# ===== 基本設定 =====
tz = pytz.timezone("Asia/Taipei")
client = OpenAI(api_key=OPENAI_API_KEY)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)

# ===== 使用者設定 =====
user_keywords = {}
user_sources = {}
user_topics = {}

# ===== 成效追蹤 / 文案記錄 =====
campaign_logs = []
campaign_performance = {}


# ===== Prompt =====
MARKETING_PROMPT = """
你是台灣AI培訓產業行銷專家

目標族群：
上班族轉職 / 技能提升

請產出：
1. Facebook廣告
2. 招生文案
3. LINE短文
4. 標題
5. CTA
6. 影音腳本

語氣要有：
- 轉職焦慮
- 升級機會感
- 台灣市場口吻
- 能提升報名動機
"""


# ===== Notebook =====
def save_to_notebook(chat_id, content):
    try:
        topic = user_topics.get(chat_id, "AI行銷")
        today = datetime.datetime.now(tz).strftime("%Y-%m-%d")
        safe_topic = topic.replace("/", "_").replace("\\", "_").strip() or "AI行銷"
        filename = f"notebook_{safe_topic}_{today}.txt"

        with open(filename, "a", encoding="utf-8") as f:
            f.write("\n\n====\n")
            f.write(content)
    except Exception as e:
        logger.exception("save_to_notebook error: %s", e)


# ===== 群組路由設定 =====
def load_json_with_fallback(primary_path, fallback_path, default_value):
    for path in [primary_path, fallback_path]:
        if not path:
            continue

        if not os.path.exists(path):
            continue

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if path != primary_path:
                save_json(primary_path, data)

            return data
        except Exception as e:
            logger.warning("load_json_with_fallback error (%s): %s", path, e)

    return default_value


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_group_config():
    try:
        data = load_json_with_fallback(
            GROUP_CONFIG_FILE,
            LEGACY_GROUP_CONFIG_FILE if GROUP_CONFIG_FILE != LEGACY_GROUP_CONFIG_FILE else None,
            {},
        )
        return {k: int(v) for k, v in data.items()}
    except Exception as e:
        logger.warning("load_group_config error: %s", e)
        return {}


def save_group_config(data):
    save_json(GROUP_CONFIG_FILE, data)


def load_authorized_users():
    try:
        default_admins = sorted(ADMIN_USER_IDS)
        data = load_json_with_fallback(
            AUTHORIZED_USERS_FILE,
            LEGACY_AUTHORIZED_USERS_FILE if AUTHORIZED_USERS_FILE != LEGACY_AUTHORIZED_USERS_FILE else None,
            {"admins": default_admins, "operators": default_admins.copy()},
        )
        return {
            "admins": [int(user_id) for user_id in data.get("admins", [])],
            "operators": [int(user_id) for user_id in data.get("operators", [])],
        }
    except Exception as e:
        logger.warning("load_authorized_users error: %s", e)
        default_admins = sorted(ADMIN_USER_IDS)
        return {"admins": default_admins, "operators": default_admins.copy()}


def save_authorized_users(data):
    normalized = {
        "admins": sorted({int(user_id) for user_id in data.get("admins", [])}),
        "operators": sorted({int(user_id) for user_id in data.get("operators", [])}),
    }
    save_json(AUTHORIZED_USERS_FILE, normalized)


def load_pair_codes():
    try:
        return load_json_with_fallback(
            PAIR_CODES_FILE,
            LEGACY_PAIR_CODES_FILE if PAIR_CODES_FILE != LEGACY_PAIR_CODES_FILE else None,
            {},
        )
    except Exception as e:
        logger.warning("load_pair_codes error: %s", e)
        return {}


def save_pair_codes(data):
    save_json(PAIR_CODES_FILE, data)


def load_session_settings():
    try:
        return load_json_with_fallback(
            SESSION_SETTINGS_FILE,
            LEGACY_SESSION_SETTINGS_FILE if SESSION_SETTINGS_FILE != LEGACY_SESSION_SETTINGS_FILE else None,
            {},
        )
    except Exception as e:
        logger.warning("load_session_settings error: %s", e)
        return {}


def save_session_settings(data):
    save_json(SESSION_SETTINGS_FILE, data)


def get_user_session_settings(user_id):
    data = load_session_settings()
    return data.get(str(user_id), {"think": "medium", "verbose": False, "elevated": False})


def update_user_session_settings(user_id, **kwargs):
    data = load_session_settings()
    key = str(user_id)
    current = data.get(key, {"think": "medium", "verbose": False, "elevated": False})
    current.update(kwargs)
    data[key] = current
    save_session_settings(data)
    return current


def load_schedule_execution_log():
    try:
        return load_json_with_fallback(
            SCHEDULE_EXECUTION_LOG_FILE,
            LEGACY_SCHEDULE_EXECUTION_LOG_FILE if SCHEDULE_EXECUTION_LOG_FILE != LEGACY_SCHEDULE_EXECUTION_LOG_FILE else None,
            {},
        )
    except Exception as e:
        logger.warning("load_schedule_execution_log error: %s", e)
        return {}


def save_schedule_execution_log(data):
    save_json(SCHEDULE_EXECUTION_LOG_FILE, data)


def get_schedule_execution_entry(schedule_name):
    log_data = load_schedule_execution_log()
    return log_data.get(schedule_name, {})


def record_schedule_execution(schedule_name, status, trigger_type, detail=""):
    log_data = load_schedule_execution_log()
    entry = log_data.get(schedule_name, {})
    now_iso = datetime.datetime.now(tz).isoformat()

    entry["last_status"] = status
    entry["last_trigger_type"] = trigger_type
    entry["last_detail"] = detail
    entry["last_attempt_at"] = now_iso

    if status == "success":
        entry["last_success_at"] = now_iso
        entry["last_success_trigger_type"] = trigger_type
    else:
        entry["last_error_at"] = now_iso

    log_data[schedule_name] = entry
    save_schedule_execution_log(log_data)


def has_schedule_run_today(schedule_name):
    entry = get_schedule_execution_entry(schedule_name)
    last_success_at = entry.get("last_success_at")
    if not last_success_at:
        return False

    try:
        success_dt = datetime.datetime.fromisoformat(last_success_at)
        return success_dt.astimezone(tz).date() == datetime.datetime.now(tz).date()
    except Exception:
        return False


def is_admin(user_id):
    auth = load_authorized_users()
    return int(user_id) in set(auth.get("admins", []))


def is_operator(user_id):
    auth = load_authorized_users()
    operators = set(auth.get("operators", [])) | set(auth.get("admins", []))
    return int(user_id) in operators


def ensure_default_admins():
    auth = load_authorized_users()
    changed = False

    for admin_id in sorted(ADMIN_USER_IDS):
        if admin_id not in auth["admins"]:
            auth["admins"].append(admin_id)
            changed = True
        if admin_id not in auth["operators"]:
            auth["operators"].append(admin_id)
            changed = True

    if changed:
        save_authorized_users(auth)


async def require_operator(update: Update):
    user = update.effective_user
    if user and is_operator(user.id):
        return True

    await update.message.reply_text(
        "⛔ 你尚未被授權操作排程或群組設定。\n請先私訊 bot 輸入 /start 取得配對碼，再請管理者核准。"
    )
    return False


async def require_admin(update: Update):
    user = update.effective_user
    if user and is_admin(user.id):
        return True

    await update.message.reply_text("⛔ 只有管理者可以執行這個指令。")
    return False


def load_schedule_config():
    try:
        data = load_json_with_fallback(
            SCHEDULE_CONFIG_FILE,
            LEGACY_SCHEDULE_CONFIG_FILE if SCHEDULE_CONFIG_FILE != LEGACY_SCHEDULE_CONFIG_FILE else None,
            {},
        )
        return {
            schedule_name: {
                "chat_id": int(item["chat_id"]),
                "hour": int(item["hour"]),
                "minute": int(item["minute"]),
                "group_id": int(item["group_id"]),
                "task_prompt": str(item.get("task_prompt", "")).strip(),
                "owner_user_id": int(item.get("owner_user_id", item["chat_id"])),
                "owner_name": str(item.get("owner_name", "")).strip(),
                "created_at": str(item.get("created_at", "")).strip(),
                "updated_at": str(item.get("updated_at", "")).strip(),
            }
            for schedule_name, item in data.items()
        }
    except Exception as e:
        logger.warning("load_schedule_config error: %s", e)
        return {}


def save_schedule_config(data):
    save_json(SCHEDULE_CONFIG_FILE, data)


def build_schedule_job_name(chat_id, schedule_name):
    return f"schedule:{chat_id}:{schedule_name}"


def schedule_daily_job(job_queue, schedule_name, chat_id, hour, minute, group_id, task_prompt=""):
    job_name = build_schedule_job_name(chat_id, schedule_name)

    current_jobs = job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()

    job_queue.run_daily(
        scheduled_daily_push,
        time=time(hour=hour, minute=minute, tzinfo=tz),
        chat_id=chat_id,
        name=job_name,
        data={
            "schedule_name": schedule_name,
            "group_id": group_id,
            "task_prompt": task_prompt,
            "trigger_type": "scheduled",
        },
    )


def get_report_group(report_type):
    config = load_group_config()
    return config.get(report_type, GROUP_CHAT_ID)


async def send_to_report_group(bot, report_type, text):
    group_id = get_report_group(report_type)
    if not group_id:
        return False

    try:
        await bot.send_message(chat_id=group_id, text=text)
        return True
    except Exception as e:
        logger.warning("send_to_report_group error (%s): %s", report_type, e)
        return False


# ===== 讀取真實追蹤資料 =====
def load_tracking_data():
    try:
        return get_tracking_data()
    except Exception as e:
        logger.exception("load_tracking_data error: %s", e)
        return {}


def get_campaign_performance(campaign_id):
    data = load_tracking_data()
    return data.get(campaign_id, {"click": 0, "lead": 0})


def dedupe_links(links):
    ordered = []
    seen = set()

    for link in links:
        if not isinstance(link, str):
            continue
        cleaned = link.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        ordered.append(cleaned)

    return ordered


def resolve_final_url(url, headers=None, timeout=8):
    if not isinstance(url, str):
        return ""

    cleaned = url.strip()
    if not cleaned:
        return ""

    try:
        response = requests.get(
            cleaned,
            headers=headers or {"User-Agent": "Mozilla/5.0"},
            timeout=timeout,
            allow_redirects=True,
        )
        final_url = (response.url or "").strip()
        if final_url:
            return final_url
    except Exception as e:
        logger.warning("resolve_final_url error (%s): %s", cleaned, e)

    return cleaned


def extract_schedule_queries(task_prompt, fallback_query):
    queries = []
    seen = set()

    for raw_line in task_prompt.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith(("課程名稱", "可以使用以下方式搜尋")):
            continue

        for prefix in ("- ", "• ", "* "):
            if line.startswith(prefix):
                line = line[len(prefix):].strip()
                break

        if not line:
            continue

        if len(line) > 30:
            continue

        lowered = line.lower()
        if lowered.startswith("http://") or lowered.startswith("https://"):
            continue

        if line in seen:
            continue

        seen.add(line)
        queries.append(line)

    if queries:
        return queries[:12]

    fallback = (fallback_query or "").strip()
    return [fallback[:40]] if fallback else []


def fetch_google_news_articles(queries, limit_per_query=1, max_total=12):
    articles = []
    search_links = []
    seen_links = set()
    headers = {"User-Agent": "Mozilla/5.0"}

    for query in queries:
        if len(articles) >= max_total:
            break

        search_query = f"when:1d {query}".strip()
        encoded = urllib.parse.quote(search_query)
        rss_url = (
            f"https://news.google.com/rss/search?q={encoded}"
            f"&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        )
        search_links.append(rss_url)

        try:
            feed = feedparser.parse(rss_url)
            added_for_query = 0

            for entry in getattr(feed, "entries", []):
                title = getattr(entry, "title", "").strip()
                link = resolve_final_url(
                    getattr(entry, "link", "").strip(),
                    headers=headers,
                )

                if not title or not link or link in seen_links:
                    continue

                seen_links.add(link)
                articles.append(
                    {
                        "query": query,
                        "title": title,
                        "link": link,
                    }
                )
                added_for_query += 1

                if added_for_query >= limit_per_query or len(articles) >= max_total:
                    break
        except Exception as e:
            logger.warning("fetch_google_news_articles error (%s): %s", query, e)

    return articles, dedupe_links(search_links)


async def send_long_message(
    bot,
    chat_id,
    text,
    chunk_size=3500,
    parse_mode=None,
    disable_web_page_preview=None,
):
    message = str(text or "").strip()
    if not message:
        return

    while message:
        if len(message) <= chunk_size:
            await bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
            )
            return

        split_at = message.rfind("\n", 0, chunk_size)
        if split_at <= 0:
            split_at = chunk_size

        chunk = message[:split_at].strip()
        if chunk:
            await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
            )

        message = message[split_at:].strip()


# ===== 市場資料 =====
def fetch_market_intel_by_query(query):
    results = []
    links = []

    try:
        query = query.strip() or "台灣 AI 培訓"
        encoded = urllib.parse.quote(query)
        headers = {"User-Agent": "Mozilla/5.0"}

        # Google News
        try:
            news_url = (
                f"https://news.google.com/rss/search?q={encoded}"
                f"&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
            )
            feed = feedparser.parse(news_url)

            for entry in getattr(feed, "entries", [])[:2]:
                title = getattr(entry, "title", "").strip()
                link = getattr(entry, "link", "").strip()
                if title:
                    results.append(f"📰 {title}")
                if link:
                    links.append(link)
        except Exception as e:
            logger.warning("Google News error: %s", e)

        # PTT
        try:
            res = requests.get(
                f"https://www.ptt.cc/bbs/Soft_Job/search?q={encoded}",
                headers=headers,
                timeout=5
            )
            soup = BeautifulSoup(res.text, "html.parser")

            for t in soup.select(".title a")[:2]:
                title = t.text.strip()
                href = t.get("href")
                if title:
                    results.append(f"💬 PTT: {title}")
                if href:
                    links.append("https://www.ptt.cc" + href)
        except Exception as e:
            logger.warning("PTT error: %s", e)

        # Dcard
        try:
            res = requests.get(
                f"https://www.dcard.tw/search?query={encoded}",
                headers=headers,
                timeout=5
            )
            soup = BeautifulSoup(res.text, "html.parser")
            dcard_search_url = "https://www.dcard.tw/search?query=" + encoded

            count = 0
            for p in soup.select("h2"):
                title = p.text.strip()
                if title:
                    results.append(f"📱 Dcard: {title}")
                    count += 1
                if count >= 2:
                    break

            if count > 0:
                links.append(dcard_search_url)
        except Exception as e:
            logger.warning("Dcard error: %s", e)

        if not results:
            results.append(f"{query} 市場趨勢")
            links.append(f"https://www.google.com/search?q={encoded}")

    except Exception as e:
        logger.exception("fetch_market_intel_by_query error: %s", e)
        results = ["市場資料錯誤"]
        links = []

    return results, links


def fetch_market_intel(chat_id):
    keyword = user_keywords.get(chat_id, "台灣 AI 培訓")
    source = user_sources.get(chat_id, "")
    query = f"{keyword} {source}".strip()
    return fetch_market_intel_by_query(query)


# ===== 文案生成 =====
def generate_marketing(chat_id):
    try:
        market_data, links = fetch_market_intel(chat_id)

        if not isinstance(market_data, list):
            market_data = ["市場資料異常"]
        if not isinstance(links, list):
            links = []

        market_text = "\n".join(market_data)[:500]

        campaign_id = str(uuid.uuid4())[:8]
        topic = user_topics.get(chat_id, "AI行銷")
        keyword = user_keywords.get(chat_id, "AI課程")

        tracking_link = (
            f"{TRACK_BASE_URL}/track"
            f"?cid={campaign_id}"
            f"&action=click"
            f"&target={urllib.parse.quote(LANDING_PAGE_URL, safe='')}"
        )

        lead_link = (
            f"{TRACK_BASE_URL}/lead"
            f"?cid={campaign_id}"
            f"&target={urllib.parse.quote(THANKYOU_PAGE_URL, safe='')}"
        )

        prompt = f"""
{MARKETING_PROMPT}

市場資訊：
{market_text}

請產出高轉換招生文案，必須包含：
1. Facebook 廣告文案
2. 招生主文案
3. LINE 短文
4. 強力 CTA
5. 影音腳本
"""

        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                timeout=45
            )
            result = response.choices[0].message.content
        except Exception as e:
            logger.exception("OpenAI generate error: %s", e)
            result = (
                "【AI文案（備援模式）】\n\n"
                "🔥 AI轉職正夯！\n"
                "現在不升級技能，你可能被市場淘汰！\n\n"
                "📌 熱門技能：\n"
                "✔ ChatGPT應用\n"
                "✔ 自動化工具\n"
                "✔ AI行銷\n\n"
                "👉 立即卡位未來職場\n"
                "👉 免費諮詢名額開放中"
            )

        result += f"\n\n👉 立即諮詢：{tracking_link}"
        result += f"\n📝 表單送出測試（lead）：{lead_link}"

        if links:
            try:
                clean_links = dedupe_links(links)
                if clean_links:
                    result += "\n\n📎 市場資料來源：\n" + "\n".join(clean_links[:3])
            except Exception as e:
                logger.warning("link format error: %s", e)

        campaign_logs.append({
            "campaign_id": campaign_id,
            "chat_id": chat_id,
            "topic": topic,
            "keyword": keyword,
            "content": result,
            "date": datetime.datetime.now(tz)
        })

        if campaign_id not in campaign_performance:
            campaign_performance[campaign_id] = {"click": 0, "lead": 0}

        return result

    except Exception as e:
        logger.exception("generate_marketing fatal error: %s", e)
        return "⚠️ 系統暫時忙碌，請稍後再試"


# ===== 測試用模擬成效 =====
def update_campaign_performance(campaign_id, click=0, lead=0):
    if campaign_id in campaign_performance:
        campaign_performance[campaign_id]["click"] += click
        campaign_performance[campaign_id]["lead"] += lead


# ===== 文案優化 =====
def optimize_marketing(chat_id):
    try:
        recent = [c for c in campaign_logs if c["chat_id"] == chat_id][-2:]

        if len(recent) < 2:
            return "⚠️ 至少需要先產生 2 筆文案，再執行 /optimize"

        c1, c2 = recent
        p1 = get_campaign_performance(c1["campaign_id"])
        p2 = get_campaign_performance(c2["campaign_id"])

        prompt = f"""
你是台灣招生行銷優化專家

以下是兩則文案：

【文案A】
{c1['content']}

成效：
- 點擊：{p1.get('click', 0)}
- 留單：{p1.get('lead', 0)}

【文案B】
{c2['content']}

成效：
- 點擊：{p2.get('click', 0)}
- 留單：{p2.get('lead', 0)}

請完成：
1. 分析哪一篇表現較好
2. 說明原因
3. 產出一篇更高轉換率的優化版文案
4. 提供更強 CTA
"""

        prompt += (
            f"\n\n本次需要覆蓋的課程/關鍵字共有 {len(queries)} 個：\n"
            + "\n".join(f"- {query}" for query in queries)
            + "\n\n請務必逐一處理每個課程/關鍵字，不要只挑其中 3 則。"
        )

        prompt += (
            f"\n\n本次需要覆蓋的課程/關鍵字共有 {len(queries)} 個：\n"
            + "\n".join(f"- {query}" for query in queries)
            + "\n\n請務必逐一處理每個課程/關鍵字，不要只挑其中 3 則。"
        )

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            timeout=45
        )

        return response.choices[0].message.content

    except Exception as e:
        logger.exception("optimize_marketing error: %s", e)
        return "⚠️ 優化失敗"


# ===== Dashboard / 報表 =====
def optimize_marketing(chat_id):
    try:
        recent = [c for c in campaign_logs if c["chat_id"] == chat_id][-2:]

        if len(recent) < 2:
            return "⚠️ 至少要有 2 篇文案後才能使用 /optimize"

        c1, c2 = recent
        p1 = get_campaign_performance(c1["campaign_id"])
        p2 = get_campaign_performance(c2["campaign_id"])

        prompt = f"""
你是一位行銷優化顧問，請分析最近兩篇文案的表現，並提出更好的優化版本。

文案 1：
{c1['content']}

表現 1：
- 點擊：{p1.get('click', 0)}
- 留單：{p1.get('lead', 0)}

文案 2：
{c2['content']}

表現 2：
- 點擊：{p2.get('click', 0)}
- 留單：{p2.get('lead', 0)}

請輸出：
1. 哪一篇表現較好
2. 原因分析
3. 更高轉換率的優化版文案
4. 更強的 CTA
"""

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            timeout=45
        )

        return response.choices[0].message.content

    except Exception as e:
        logger.exception("optimize_marketing error: %s", e)
        return "⚠️ optimize 生成失敗"


def generate_report(chat_id):
    try:
        data = load_tracking_data()
        user_campaigns = [c for c in campaign_logs if c["chat_id"] == chat_id]

        if not user_campaigns:
            return "⚠️ 目前沒有文案資料"

        total_click = 0
        total_lead = 0

        best = None
        best_rate = 0
        best_click = 0
        best_lead = 0

        report_lines = []

        for c in user_campaigns:
            perf = data.get(c["campaign_id"], {"click": 0, "lead": 0})

            click = int(perf.get("click", 0) or 0)
            lead = int(perf.get("lead", 0) or 0)

            total_click += click
            total_lead += lead

            rate = (lead / click) if click else 0

            report_lines.append(
                f"• {c['campaign_id']} | 點擊 {click} / 留單 {lead} / 轉換 {rate * 100:.1f}%"
            )

            if rate > best_rate:
                best_rate = rate
                best = c
                best_click = click
                best_lead = lead

        avg_rate = (total_lead / total_click * 100) if total_click else 0

        return f"""
📊 AI行銷 Dashboard

📌 總文案數：{len(user_campaigns)}
📈 總點擊：{total_click}
💰 總留單：{total_lead}
🎯 平均轉換率：{avg_rate:.1f}%

🏆 最佳文案 Campaign：
{best['campaign_id'] if best else "無"}

🔥 最佳文案成效：
點擊 {best_click} / 留單 {best_lead} / 轉換率 {best_rate * 100:.1f}%

📝 最近成效：
{chr(10).join(report_lines[-5:])}
""".strip()

    except Exception as e:
        logger.exception("generate_report error: %s", e)
        return "⚠️ 報表產生失敗"


def generate_custom_schedule_task(chat_id, schedule_name, task_prompt):
    try:
        query_text = task_prompt[:120].strip() or user_keywords.get(chat_id, "台灣 AI 培訓")
        market_data, links = fetch_market_intel_by_query(query_text)
        market_text = "\n".join(market_data[:6]) if market_data else "目前沒有額外市場資料"

        prompt = f"""
你是台灣教育招生與競品分析助理。

現在要執行的排程名稱：{schedule_name}

任務要求：
{task_prompt}

可參考的最新市場資料：
{market_text}

請依照任務要求直接輸出可發送到 Telegram 的完整內容。
如果任務要求中有比較、熱度、建議、清單、表格，請整理成容易閱讀的區塊或表格樣式。
若資訊不足，請明確標註「待人工確認」而不要編造。
"""

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            timeout=45
        )
        result = response.choices[0].message.content

        if links:
            clean_links = dedupe_links(links)
            if clean_links:
                result += "\n\n📎 參考資料：\n" + "\n".join(clean_links[:5])

        return result
    except Exception as e:
        logger.exception("generate_custom_schedule_task error: %s", e)
        return (
            f"⚠️ 排程任務 {schedule_name} 產生失敗\n\n"
            f"任務內容：{task_prompt}\n\n"
            "請稍後重試或調整任務描述。"
        )


def generate_custom_schedule_task(chat_id, schedule_name, task_prompt):
    try:
        query_text = task_prompt[:120].strip() or user_keywords.get(chat_id, "AI")
        queries = extract_schedule_queries(task_prompt, query_text)
        articles, search_links = fetch_google_news_articles(queries)
        article_map = {article["query"]: article for article in articles}

        if articles:
            market_text = "\n".join(
                [
                    f"- 關鍵字：{article['query']}\n"
                    f"  標題：{article['title']}\n"
                    f"  網址：{article['link']}"
                    for article in articles[:12]
                ]
            )
        else:
            market_text = "目前沒有查到可用的一日內 Google News 新聞，請直接說明查無資料，不要自造新聞或網址。"

        prompt = f"""
你是一位招生與市場情報助理，請根據使用者任務產出適合 Telegram 閱讀的回覆。
排程名稱：{schedule_name}

任務內容：
{task_prompt}

以下是已查到的真實 Google News 新聞資料：
{market_text}

請嚴格遵守：
1. 只能使用上方提供的真實新聞標題與網址。
2. 禁止產生、猜測或示範用網址，例如 example.com。
3. 如果某個課程名稱查不到合適新聞，請直接寫「查無一日內相關新聞」。
4. 回覆格式要適合 Telegram 閱讀，並保留每則新聞的真實網址。
5. 不要把 Dcard、PTT 當成資料來源；本次只使用 Google News。
6. 若使用薪資或產業趨勢補充說法，沒有真實來源就不要編造數字。
"""

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            timeout=45
        )
        result = response.choices[0].message.content

        course_lines = []
        for query in queries:
            article = article_map.get(query)
            if article:
                course_lines.append(
                    f"### {query}\n"
                    f"- 新聞標題：{article['title']}\n"
                    f"- 網址連結：{article['link']}"
                )
            else:
                course_lines.append(
                    f"### {query}\n"
                    "- 新聞標題：查無一日內相關新聞"
                )

        if course_lines:
            result += "\n\n📚 各課程新聞索引：\n" + "\n\n".join(course_lines)

        article_links = [article["link"] for article in articles]
        clean_links = dedupe_links(article_links)
        if clean_links:
            result += "\n\n📎 資料來源（Google News）：\n" + "\n".join(clean_links[:12])

        return result
    except Exception as e:
        logger.exception("generate_custom_schedule_task error: %s", e)
        return (
            f"⚠️ 排程 {schedule_name} 執行失敗\n\n"
            f"任務內容：{task_prompt}\n\n"
            "請稍後再試或縮短關鍵字後重試。"
        )


def build_query_variants(query):
    base = (query or "").strip()
    if not base:
        return []

    variants = [base]
    suffixes = [
        "程式設計師",
        "系統整合工程師",
        "人工智慧工程師",
        "機構設計工程師",
        "證照班",
        "設計師",
        "工程師",
    ]

    for suffix in suffixes:
        if base.endswith(suffix):
            trimmed = base[: -len(suffix)].strip()
            if trimmed and trimmed not in variants:
                variants.append(trimmed)

    replacements = {
        "AI人工智慧工程師": "AI 工程師",
        "Java軟體工程師": "Java 工程師",
        "雲端系統整合工程師": "雲端 系統整合",
    }
    for source, target in replacements.items():
        if base == source and target not in variants:
            variants.append(target)

    return variants[:4]


def format_html_link(url, label=None):
    cleaned = (url or "").strip()
    if not cleaned:
        return ""

    parsed = urllib.parse.urlparse(cleaned)
    domain = (parsed.netloc or "").replace("www.", "")
    visible = label or f"查看新聞（{domain}）"
    return f'<a href="{html.escape(cleaned, quote=True)}">{html.escape(visible)}</a>'


def fetch_newsapi_article_for_variant(query):
    if not NEWS_API_KEY:
        return None

    try:
        since = (datetime.datetime.now(tz) - datetime.timedelta(days=1)).isoformat()
        response = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": f'"{query}"',
                "searchIn": "title,description",
                "sortBy": "publishedAt",
                "pageSize": 5,
                "from": since,
                "apiKey": NEWS_API_KEY,
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=NEWS_SEARCH_TIMEOUT,
        )
        if not response.ok:
            logger.warning("NewsAPI error (%s): %s", query, response.text[:200])
            return None

        data = response.json()
        for item in data.get("articles", []):
            title = str(item.get("title", "")).strip()
            link = resolve_final_url(
                str(item.get("url", "")).strip(),
                timeout=NEWS_SEARCH_TIMEOUT,
            )
            if title and link:
                return {
                    "query": query,
                    "title": title,
                    "link": link,
                    "source": "NewsAPI",
                }
    except Exception as e:
        logger.warning("fetch_newsapi_article_for_variant error (%s): %s", query, e)

    return None


def fetch_google_news_articles(queries, limit_per_query=1, max_total=12):
    articles = []
    search_links = []
    seen_links = set()
    headers = {"User-Agent": "Mozilla/5.0"}

    for original_query in queries:
        if len(articles) >= max_total:
            break

        selected_article = None

        for variant in build_query_variants(original_query):
            search_query = f"when:1d {variant}".strip()
            encoded = urllib.parse.quote(search_query)
            rss_url = (
                f"https://news.google.com/rss/search?q={encoded}"
                f"&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
            )
            search_links.append(rss_url)

            try:
                feed = feedparser.parse(rss_url)
                for entry in getattr(feed, "entries", [])[: max(2, limit_per_query)]:
                    title = getattr(entry, "title", "").strip()
                    link = resolve_final_url(
                        getattr(entry, "link", "").strip(),
                        headers=headers,
                        timeout=NEWS_SEARCH_TIMEOUT,
                    )

                    if not title or not link or link in seen_links:
                        continue

                    selected_article = {
                        "query": original_query,
                        "title": title,
                        "link": link,
                        "source": "Google News",
                    }
                    break
            except Exception as e:
                logger.warning("fetch_google_news_articles error (%s): %s", variant, e)

            if selected_article:
                break

        if not selected_article:
            for variant in build_query_variants(original_query):
                selected_article = fetch_newsapi_article_for_variant(variant)
                if selected_article:
                    selected_article["query"] = original_query
                    if selected_article["link"] in seen_links:
                        selected_article = None
                        continue
                    break

        if selected_article:
            seen_links.add(selected_article["link"])
            articles.append(selected_article)

    return articles, dedupe_links(search_links)


def generate_custom_schedule_task(chat_id, schedule_name, task_prompt):
    try:
        query_text = task_prompt[:120].strip() or user_keywords.get(chat_id, "AI")
        queries = extract_schedule_queries(task_prompt, query_text)
        articles, _search_links = fetch_google_news_articles(queries)
        article_map = {article["query"]: article for article in articles}

        if articles:
            market_text = "\n".join(
                [
                    f"- 關鍵字：{article['query']}\n"
                    f"  標題：{article['title']}\n"
                    f"  網址：{article['link']}\n"
                    f"  來源：{article.get('source', 'Google News')}"
                    for article in articles[:12]
                ]
            )
        else:
            market_text = "目前沒有查到可用的一日內新聞，請明確寫出查無資料，不要自造新聞或網址。"

        prompt = f"""
你是一位招生與市場情報助理，請根據使用者任務產出適合 Telegram 閱讀的回覆。
排程名稱：{schedule_name}

任務內容：
{task_prompt}

以下是已查到的真實新聞資料：
{market_text}

請嚴格遵守：
1. 只能使用上方提供的真實新聞標題與網址。
2. 禁止產生、猜測或示範用網址，例如 example.com。
3. 如果某個課程名稱查不到合適新聞，請直接寫「查無一日內相關新聞」。
4. 回覆格式要精簡、適合 Telegram 閱讀。
5. 沒有真實來源就不要編造薪資數字或新聞內容。
"""

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            timeout=60
        )
        result = render_compact_html_text((response.choices[0].message.content or "").strip())

        course_lines = []
        for query in queries:
            article = article_map.get(query)
            if article:
                parsed = urllib.parse.urlparse(article["link"])
                domain = (parsed.netloc or "").replace("www.", "")
                course_lines.append(
                    f"● {html.escape(query)}\n"
                    f"新聞：{html.escape(article['title'])}\n"
                    f"連結：{format_html_link(article['link'], f'查看新聞（{domain}）')}"
                )
            else:
                course_lines.append(
                    f"● {html.escape(query)}\n"
                    "新聞：查無一日內相關新聞"
                )

        source_lines = []
        for idx, article in enumerate(articles[:12], start=1):
            parsed = urllib.parse.urlparse(article["link"])
            domain = (parsed.netloc or "").replace("www.", "")
            source_lines.append(
                f"• {format_html_link(article['link'], f'來源 {idx}（{domain}）')}"
            )

        parts = [result]
        if course_lines:
            parts.append("\n\n📚 各課程新聞索引：\n" + "\n\n".join(course_lines))
        if source_lines:
            parts.append("\n\n📎 資料來源：\n" + "\n".join(source_lines))

        return "".join(parts)
    except Exception as e:
        logger.exception("generate_custom_schedule_task error: %s", e)
        return html.escape(
            f"⚠️ 排程 {schedule_name} 執行失敗\n\n任務內容：{task_prompt}\n\n請稍後再試。"
        )


def format_schedule_detail(schedule_name, item):
    task_prompt = item.get("task_prompt", "").strip()
    task_preview = task_prompt if task_prompt else "未設定，將使用預設 AI 文案流程"
    execution_entry = get_schedule_execution_entry(schedule_name)
    last_success_at = execution_entry.get("last_success_at", "尚無成功紀錄")
    last_trigger_type = execution_entry.get("last_success_trigger_type", "無")
    last_status = execution_entry.get("last_status", "尚無紀錄")
    return (
        f"📌 排程詳細資料\n"
        f"名稱：{schedule_name}\n"
        f"時間：{item['hour']:02d}:{item['minute']:02d}\n"
        f"群組ID：{item['group_id']}\n"
        f"建立者 chat_id：{item['chat_id']}\n"
        f"建立者 user_id：{item.get('owner_user_id', item['chat_id'])}\n"
        f"建立者名稱：{item.get('owner_name') or '未記錄'}\n"
        f"建立時間：{item.get('created_at') or '未記錄'}\n"
        f"最後更新：{item.get('updated_at') or '未記錄'}\n"
        f"最近成功執行：{last_success_at}\n"
        f"最近成功來源：{last_trigger_type}\n"
        f"最近執行狀態：{last_status}\n"
        f"任務內容：\n{task_preview}"
    )


def get_schedule_for_chat(chat_id, schedule_name):
    config = load_schedule_config()
    item = config.get(schedule_name)
    if not item or int(item.get("chat_id", 0)) != chat_id:
        return config, None
    return config, item


def get_schedule_any(schedule_name):
    config = load_schedule_config()
    return config, config.get(schedule_name)


async def apply_schedule_task(update: Update, context: ContextTypes.DEFAULT_TYPE, schedule_name: str, task_prompt: str):
    chat_id = update.effective_chat.id
    config, item = get_schedule_for_chat(chat_id, schedule_name)

    if not item:
        await update.message.reply_text(
            f"⚠️ 找不到排程：{schedule_name}，請先用 /setschedule 建立"
        )
        return

    task_prompt = task_prompt.rstrip()
    item["task_prompt"] = task_prompt
    item["updated_at"] = datetime.datetime.now(tz).isoformat()
    config[schedule_name] = item
    save_schedule_config(config)

    schedule_daily_job(
        context.job_queue,
        schedule_name=schedule_name,
        chat_id=item["chat_id"],
        hour=item["hour"],
        minute=item["minute"],
        group_id=item["group_id"],
        task_prompt=task_prompt,
    )

    preview = task_prompt[:80] + ("..." if len(task_prompt) > 80 else "")
    await update.message.reply_text(
        f"✅ 已設定排程任務內容\n名稱：{schedule_name}\n內容摘要：{preview}"
    )


# ===== Telegram 指令 =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        await update.message.reply_text("⚠️ 無法辨識目前使用者")
        return

    ensure_default_admins()

    if is_operator(user.id):
        role = "管理者" if is_admin(user.id) else "已授權操作員"
        await update.message.reply_text(
            f"✅ OpenClaw AI 行銷系統已啟動\n你的身份：{role}\n你可以直接使用排程與群組管理指令。"
        )
        return

    pair_codes = load_pair_codes()
    existing_code = None
    for code, item in pair_codes.items():
        if int(item.get("user_id", 0)) == int(user.id):
            existing_code = code
            break

    if not existing_code:
        existing_code = secrets.token_hex(3).upper()
        pair_codes[existing_code] = {
            "user_id": int(user.id),
            "username": user.username or "",
            "full_name": user.full_name or "",
            "created_at": datetime.datetime.now(tz).isoformat(),
        }
        save_pair_codes(pair_codes)

    await update.message.reply_text(
        "🔐 你尚未被授權。\n"
        f"你的配對碼：{existing_code}\n"
        "請將這組配對碼提供給管理者，由管理者執行 /approveuser 配對碼 開通權限。"
    )


async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        await update.message.reply_text("⚠️ 無法辨識目前使用者")
        return

    role = "管理者" if is_admin(user.id) else "已授權操作員" if is_operator(user.id) else "未授權"
    await update.message.reply_text(
        f"🙋 使用者資訊\n"
        f"user_id：{user.id}\n"
        f"username：@{user.username or '無'}\n"
        f"姓名：{user.full_name}\n"
        f"狀態：{role}"
    )


async def approveuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return

    if not context.args:
        await update.message.reply_text("⚠️ 用法：/approveuser 配對碼")
        return

    pair_code = context.args[0].strip().upper()
    pair_codes = load_pair_codes()
    item = pair_codes.get(pair_code)

    if not item:
        await update.message.reply_text(f"⚠️ 找不到配對碼：{pair_code}")
        return

    auth = load_authorized_users()
    user_id = int(item["user_id"])
    if user_id not in auth["operators"]:
        auth["operators"].append(user_id)
    save_authorized_users(auth)

    del pair_codes[pair_code]
    save_pair_codes(pair_codes)

    await update.message.reply_text(
        f"✅ 已授權使用者\nuser_id：{user_id}\n名稱：{item.get('full_name') or '未知'}"
    )


async def listusers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return

    auth = load_authorized_users()
    admin_ids = sorted(set(auth.get("admins", [])))
    operator_ids = sorted(set(auth.get("operators", [])))

    lines = ["👥 已授權使用者："]
    lines.append("管理者：" + (", ".join(str(user_id) for user_id in admin_ids) or "無"))
    lines.append("操作員：" + (", ".join(str(user_id) for user_id in operator_ids) or "無"))
    await update.message.reply_text("\n".join(lines))


async def revokeuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return

    if not context.args:
        await update.message.reply_text("⚠️ 用法：/revokeuser user_id")
        return

    try:
        user_id = int(context.args[0].strip())
    except ValueError:
        await update.message.reply_text("⚠️ user_id 格式錯誤")
        return

    if user_id in ADMIN_USER_IDS:
        await update.message.reply_text("⚠️ 不能移除預設管理者")
        return

    auth = load_authorized_users()
    before_count = len(auth.get("operators", []))
    auth["operators"] = [item for item in auth.get("operators", []) if int(item) != user_id]
    auth["admins"] = [item for item in auth.get("admins", []) if int(item) != user_id]
    save_authorized_users(auth)

    if len(auth["operators"]) == before_count:
        await update.message.reply_text(f"⚠️ user_id {user_id} 不在授權名單中")
        return

    await update.message.reply_text(f"✅ 已移除 user_id {user_id} 的操作權限")


async def addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return

    if not context.args:
        await update.message.reply_text("⚠️ 用法：/addadmin user_id")
        return

    try:
        user_id = int(context.args[0].strip())
    except ValueError:
        await update.message.reply_text("⚠️ user_id 格式錯誤")
        return

    auth = load_authorized_users()
    if user_id not in auth["admins"]:
        auth["admins"].append(user_id)
    if user_id not in auth["operators"]:
        auth["operators"].append(user_id)
    save_authorized_users(auth)

    await update.message.reply_text(f"✅ 已新增管理者 user_id：{user_id}")


async def deleteallpairs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return

    save_pair_codes({})
    await update.message.reply_text("✅ 已清空所有待核准配對碼")


async def marketing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_operator(update):
        return

    chat_id = update.effective_chat.id
    msg = generate_marketing(chat_id)
    save_to_notebook(chat_id, msg)

    await update.message.reply_text(msg)

    try:
        await send_to_report_group(
            context.bot,
            "marketing",
            f"📢 手動產生文案同步\n\n來源 chat_id：{chat_id}\n\n{msg}"
        )
    except Exception as e:
        logger.warning("group send error (marketing): %s", e)


async def optimize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_operator(update):
        return

    chat_id = update.effective_chat.id
    msg = optimize_marketing(chat_id)
    await update.message.reply_text(msg)

    try:
        await send_to_report_group(
            context.bot,
            "optimize",
            f"🤖 文案優化同步\n\n來源 chat_id：{chat_id}\n\n{msg}"
        )
    except Exception as e:
        logger.warning("group send error (optimize): %s", e)


async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_operator(update):
        return

    chat_id = update.effective_chat.id
    msg = generate_report(chat_id)
    await update.message.reply_text(msg)

    try:
        await send_to_report_group(
            context.bot,
            "report",
            f"📊 成效報表同步\n\n來源 chat_id：{chat_id}\n\n{msg}"
        )
    except Exception as e:
        logger.warning("group send error (report): %s", e)


async def simulate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_operator(update):
        return

    if campaign_logs:
        cid = campaign_logs[-1]["campaign_id"]
        update_campaign_performance(cid, click=20, lead=5)
        await update.message.reply_text(
            f"🧪 測試模式：已模擬 campaign {cid} 成效\n"
            f"點擊 +20 / 留單 +5\n"
            f"（正式環境請改用真實 tracking link）"
        )
    else:
        await update.message.reply_text("⚠️ 尚無 campaign 可模擬")


async def setkeyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_operator(update):
        return

    value = " ".join(context.args).strip()
    if not value:
        await update.message.reply_text("⚠️ 用法：/setkeyword 關鍵字")
        return

    user_keywords[update.effective_chat.id] = value
    await update.message.reply_text(f"✅ keyword 設定完成：{value}")


async def setsource(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_operator(update):
        return

    value = " ".join(context.args).strip()
    if not value:
        await update.message.reply_text("⚠️ 用法：/setsource 來源")
        return

    user_sources[update.effective_chat.id] = value
    await update.message.reply_text(f"✅ source 設定完成：{value}")


async def settopic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_operator(update):
        return

    value = " ".join(context.args).strip()
    if not value:
        await update.message.reply_text("⚠️ 用法：/settopic 主題")
        return

    user_topics[update.effective_chat.id] = value
    await update.message.reply_text(f"✅ topic 設定完成：{value}")


async def settime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_operator(update):
        return

    try:
        chat_id = update.effective_chat.id

        if not context.args:
            await update.message.reply_text("⚠️ 用法：/settime 09:30")
            return

        hour, minute = map(int, context.args[0].split(":"))

        current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))
        for job in current_jobs:
            job.schedule_removal()

        context.job_queue.run_daily(
            daily_push,
            time=time(hour=hour, minute=minute, tzinfo=tz),
            chat_id=chat_id,
            name=str(chat_id)
        )

        await update.message.reply_text(f"✅ 推播設定完成：每天 {hour:02d}:{minute:02d}")

    except Exception as e:
        logger.exception("settime error: %s", e)
        await update.message.reply_text("⚠️ 時間格式錯誤，請用 /settime 09:30")


async def setschedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_operator(update):
        return

    try:
        if len(context.args) < 3:
            await update.message.reply_text(
                "⚠️ 用法：/setschedule 排程名稱 HH:MM 群組ID\n例如：/setschedule schedule1 09:30 -5266698491"
            )
            return

        schedule_name = context.args[0].strip().lower()
        hour, minute = map(int, context.args[1].strip().split(":"))
        group_id = int(context.args[2].strip())
        chat_id = update.effective_chat.id
        user = update.effective_user

        config = load_schedule_config()
        existing_task_prompt = ""
        existing_created_at = datetime.datetime.now(tz).isoformat()
        owner_user_id = int(user.id) if user else chat_id
        owner_name = user.full_name if user else ""
        if schedule_name in config and int(config[schedule_name].get("chat_id", 0)) == chat_id:
            existing_task_prompt = config[schedule_name].get("task_prompt", "")
            existing_created_at = config[schedule_name].get("created_at", existing_created_at)
            owner_user_id = int(config[schedule_name].get("owner_user_id", owner_user_id))
            owner_name = config[schedule_name].get("owner_name", owner_name)
        config[schedule_name] = {
            "chat_id": chat_id,
            "hour": hour,
            "minute": minute,
            "group_id": group_id,
            "task_prompt": existing_task_prompt,
            "owner_user_id": owner_user_id,
            "owner_name": owner_name,
            "created_at": existing_created_at,
            "updated_at": datetime.datetime.now(tz).isoformat(),
        }
        save_schedule_config(config)

        schedule_daily_job(
            context.job_queue,
            schedule_name=schedule_name,
            chat_id=chat_id,
            hour=hour,
            minute=minute,
            group_id=group_id,
            task_prompt=existing_task_prompt,
        )

        await update.message.reply_text(
            f"✅ 已建立排程\n名稱：{schedule_name}\n時間：{hour:02d}:{minute:02d}\n群組ID：{group_id}"
        )
    except Exception as e:
        logger.exception("setschedule error: %s", e)
        await update.message.reply_text("⚠️ 設定失敗，請確認時間與群組ID格式正確")


async def showschedules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_operator(update):
        return

    config = load_schedule_config()

    lines = ["🗓️ 目前排程設定："]
    has_item = False

    for schedule_name, item in sorted(config.items()):
        has_item = True
        task_status = "已設任務" if item.get("task_prompt") else "預設文案"
        lines.append(
            f"- {schedule_name} → {item['hour']:02d}:{item['minute']:02d} / 群組 {item['group_id']} / {task_status} / 建立者 {item.get('owner_name') or item.get('owner_user_id', item['chat_id'])}"
        )

    if not has_item:
        lines.append("- 尚未設定任何自訂排程")

    await update.message.reply_text("\n".join(lines))


async def delschedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_operator(update):
        return

    try:
        if not context.args:
            await update.message.reply_text("⚠️ 用法：/delschedule 排程名稱")
            return

        schedule_name = context.args[0].strip().lower()
        chat_id = update.effective_chat.id
        config = load_schedule_config()
        item = config.get(schedule_name)

        if not item or int(item.get("chat_id", 0)) != chat_id:
            await update.message.reply_text(f"⚠️ 找不到排程：{schedule_name}")
            return

        del config[schedule_name]
        save_schedule_config(config)

        job_name = build_schedule_job_name(chat_id, schedule_name)
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()

        await update.message.reply_text(f"✅ 已刪除排程：{schedule_name}")
    except Exception as e:
        logger.exception("delschedule error: %s", e)
        await update.message.reply_text("⚠️ 刪除排程失敗")


async def setscheduletask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_operator(update):
        return

    try:
        raw_text = (update.message.text or "").strip()
        parts = raw_text.split(None, 2)

        if len(parts) < 3:
            await update.message.reply_text(
                "⚠️ 用法：/setscheduletask 排程名稱 任務內容"
            )
            return

        schedule_name = parts[1].strip().lower()
        task_prompt = parts[2].rstrip()
        await apply_schedule_task(update, context, schedule_name, task_prompt)
    except Exception as e:
        logger.exception("setscheduletask error: %s", e)
        await update.message.reply_text("⚠️ 設定排程任務失敗")


async def setscheduletaskedit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_operator(update):
        return

    try:
        if not context.args:
            await update.message.reply_text(
                "⚠️ 用法：先輸入 /setscheduletaskedit 排程名稱，再回覆一則多行文字訊息"
            )
            return

        if not update.message.reply_to_message or not update.message.reply_to_message.text:
            await update.message.reply_text(
                "⚠️ 請回覆一則多行文字訊息，再輸入 /setscheduletaskedit 排程名稱"
            )
            return

        schedule_name = context.args[0].strip().lower()
        task_prompt = update.message.reply_to_message.text.rstrip()
        await apply_schedule_task(update, context, schedule_name, task_prompt)
    except Exception as e:
        logger.exception("setscheduletaskedit error: %s", e)
        await update.message.reply_text("⚠️ 設定排程任務失敗")


async def setscheduletaskfile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_operator(update):
        return

    try:
        if not context.args:
            await update.message.reply_text(
                "⚠️ 用法：先輸入 /setscheduletaskfile 排程名稱，再回覆一個 .txt 文件或文字檔"
            )
            return

        if not update.message.reply_to_message or not update.message.reply_to_message.document:
            await update.message.reply_text(
                "⚠️ 請回覆一個文字檔，再輸入 /setscheduletaskfile 排程名稱"
            )
            return

        schedule_name = context.args[0].strip().lower()
        document = update.message.reply_to_message.document
        file_name = (document.file_name or "").lower()
        if file_name and not file_name.endswith((".txt", ".md")):
            await update.message.reply_text("⚠️ 目前僅支援 .txt 或 .md 文字檔")
            return

        tg_file = await context.bot.get_file(document.file_id)
        file_bytes = await tg_file.download_as_bytearray()
        task_prompt = bytes(file_bytes).decode("utf-8").rstrip()

        if not task_prompt:
            await update.message.reply_text("⚠️ 檔案內容為空，請重新上傳")
            return

        await apply_schedule_task(update, context, schedule_name, task_prompt)
    except UnicodeDecodeError:
        await update.message.reply_text("⚠️ 檔案編碼不是 UTF-8，請改用 UTF-8 文字檔")
    except Exception as e:
        logger.exception("setscheduletaskfile error: %s", e)
        await update.message.reply_text("⚠️ 讀取任務檔案失敗")


async def viewschedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_operator(update):
        return

    if not context.args:
        await update.message.reply_text("⚠️ 用法：/viewschedule 排程名稱")
        return

    schedule_name = context.args[0].strip().lower()
    _, item = get_schedule_any(schedule_name)

    if not item:
        await update.message.reply_text(f"⚠️ 找不到排程：{schedule_name}")
        return

    await update.message.reply_text(format_schedule_detail(schedule_name, item))


async def updateschedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_operator(update):
        return

    try:
        if len(context.args) < 3:
            await update.message.reply_text(
                "⚠️ 用法：/updateschedule 排程名稱 HH:MM 群組ID"
            )
            return

        schedule_name = context.args[0].strip().lower()
        hour, minute = map(int, context.args[1].strip().split(":"))
        group_id = int(context.args[2].strip())
        chat_id = update.effective_chat.id
        config = load_schedule_config()
        item = config.get(schedule_name)

        if not item or int(item.get("chat_id", 0)) != chat_id:
            await update.message.reply_text(f"⚠️ 找不到排程：{schedule_name}")
            return

        item["hour"] = hour
        item["minute"] = minute
        item["group_id"] = group_id
        item["updated_at"] = datetime.datetime.now(tz).isoformat()
        config[schedule_name] = item
        save_schedule_config(config)

        schedule_daily_job(
            context.job_queue,
            schedule_name=schedule_name,
            chat_id=item["chat_id"],
            hour=hour,
            minute=minute,
            group_id=group_id,
            task_prompt=item.get("task_prompt", ""),
        )

        await update.message.reply_text(
            f"✅ 已更新排程\n名稱：{schedule_name}\n時間：{hour:02d}:{minute:02d}\n群組ID：{group_id}"
        )
    except Exception as e:
        logger.exception("updateschedule error: %s", e)
        await update.message.reply_text("⚠️ 更新排程失敗，請確認時間與群組ID格式正確")


async def runschedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_operator(update):
        return

    if not context.args:
        await update.message.reply_text("⚠️ 用法：/runschedule 排程名稱")
        return

    schedule_name = context.args[0].strip().lower()
    chat_id = update.effective_chat.id
    config = load_schedule_config()
    item = config.get(schedule_name)

    if not item or int(item.get("chat_id", 0)) != chat_id:
        await update.message.reply_text(f"⚠️ 找不到排程：{schedule_name}")
        return

    await update.message.reply_text(f"🧪 正在手動執行排程：{schedule_name}")

    class ManualJob:
        def __init__(self, job_chat_id, data):
            self.chat_id = job_chat_id
            self.data = data

    manual_context = type(
        "ManualScheduleContext",
        (),
        {
            "bot": context.bot,
            "job": ManualJob(
                item["chat_id"],
                {
                    "schedule_name": schedule_name,
                    "group_id": item["group_id"],
                    "task_prompt": item.get("task_prompt", ""),
                    "trigger_type": "manual",
                },
            ),
        },
    )()

    await scheduled_daily_push(manual_context)
    await update.message.reply_text(f"✅ 已手動執行排程：{schedule_name}")


async def runschedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_operator(update):
        return

    if not context.args:
        await update.message.reply_text("⚠️ 用法：/runschedule 排程名稱")
        return

    schedule_name = context.args[0].strip().lower()
    chat_id = update.effective_chat.id
    config = load_schedule_config()
    item = config.get(schedule_name)

    if not item or int(item.get("chat_id", 0)) != chat_id:
        await update.message.reply_text(f"⚠️ 找不到排程：{schedule_name}")
        return

    await update.message.reply_text(f"🧪 正在手動執行排程：{schedule_name}")

    try:
        await execute_schedule_push(
            context.bot,
            chat_id=item["chat_id"],
            schedule_name=schedule_name,
            group_id=item["group_id"],
            task_prompt=item.get("task_prompt", ""),
            trigger_type="manual",
        )
        await update.message.reply_text(f"✅ 已手動執行排程：{schedule_name}")
    except Exception as e:
        await update.message.reply_text(
            f"⚠️ 手動執行排程失敗：{schedule_name}\n原因：{e}"
        )


async def exportschedules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_operator(update):
        return

    config = load_schedule_config()
    matched = sorted(config.items())

    if not matched:
        await update.message.reply_text("📤 目前沒有可匯出的排程設定")
        return

    lines = ["📤 排程設定摘要匯出："]
    for schedule_name, item in matched:
        task_prompt = item.get("task_prompt", "").strip()
        task_preview = task_prompt[:60] + ("..." if len(task_prompt) > 60 else "")
        if not task_preview:
            task_preview = "未設定，使用預設 AI 文案流程"
        lines.append(
            f"- {schedule_name} | {item['hour']:02d}:{item['minute']:02d} | 群組 {item['group_id']} | 建立者 {item.get('owner_name') or item.get('owner_user_id', item['chat_id'])} | {task_preview}"
        )

    await update.message.reply_text("\n".join(lines))


async def schedulelogs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_operator(update):
        return

    if not context.args:
        await update.message.reply_text("⚠️ 用法：/schedulelogs 排程名稱")
        return

    schedule_name = context.args[0].strip().lower()
    _, item = get_schedule_any(schedule_name)
    if not item:
        await update.message.reply_text(f"⚠️ 找不到排程：{schedule_name}")
        return

    entry = get_schedule_execution_entry(schedule_name)
    if not entry:
        await update.message.reply_text(
            f"📜 排程執行紀錄：{schedule_name}\n目前尚無執行紀錄"
        )
        return

    await update.message.reply_text(
        f"📜 排程執行紀錄：{schedule_name}\n"
        f"最近執行狀態：{entry.get('last_status', '未知')}\n"
        f"最近執行方式：{entry.get('last_trigger_type', '未知')}\n"
        f"最近嘗試時間：{entry.get('last_attempt_at', '無')}\n"
        f"最近成功時間：{entry.get('last_success_at', '無')}\n"
        f"最近錯誤時間：{entry.get('last_error_at', '無')}\n"
        f"最近錯誤明細：{entry.get('last_detail', '無')}"
    )


def schedule_missed_jobs(job_queue, schedule_config):
    now = datetime.datetime.now(tz)

    for schedule_name, item in schedule_config.items():
        try:
            scheduled_at = now.replace(
                hour=int(item["hour"]),
                minute=int(item["minute"]),
                second=0,
                microsecond=0,
            )

            if now < scheduled_at:
                continue

            if has_schedule_run_today(schedule_name):
                continue

            catchup_job_name = f"catchup:{item['chat_id']}:{schedule_name}:{now.date().isoformat()}"
            existing_jobs = job_queue.get_jobs_by_name(catchup_job_name)
            if existing_jobs:
                continue

            job_queue.run_once(
                scheduled_daily_push,
                when=5,
                chat_id=item["chat_id"],
                name=catchup_job_name,
                data={
                    "schedule_name": schedule_name,
                    "group_id": item["group_id"],
                    "task_prompt": item.get("task_prompt", ""),
                    "trigger_type": "catchup",
                },
            )
            logger.info(
                "Scheduled catch-up run for %s at startup because today's run was missed",
                schedule_name,
            )
        except Exception as e:
            logger.exception("schedule_missed_jobs error (%s): %s", schedule_name, e)


async def setgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_operator(update):
        return

    try:
        if len(context.args) < 2:
            await update.message.reply_text(
                "⚠️ 用法：/setgroup 報告類型 群組ID\n例如：/setgroup marketing -5266698491"
            )
            return

        report_type = context.args[0].strip().lower()
        if report_type not in ALLOWED_REPORT_TYPES:
            await update.message.reply_text(
                "⚠️ 報告類型錯誤，可用類型：marketing / report / optimize / daily_push"
            )
            return

        group_id = int(context.args[1].strip())
        config = load_group_config()
        config[report_type] = group_id
        save_group_config(config)

        await update.message.reply_text(
            f"✅ 已設定群組路由\n類型：{report_type}\n群組ID：{group_id}"
        )
    except Exception as e:
        logger.exception("setgroup error: %s", e)
        await update.message.reply_text("⚠️ 設定失敗，請確認群組ID格式正確")


async def showgroups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_operator(update):
        return

    config = load_group_config()
    lines = ["📋 目前群組路由設定："]

    for report_type in ALLOWED_REPORT_TYPES:
        group_id = config.get(report_type, GROUP_CHAT_ID)
        source = "自訂" if report_type in config else "預設"
        lines.append(f"- {report_type} → {group_id}（{source}）")

    await update.message.reply_text("\n".join(lines))


async def delgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_operator(update):
        return

    try:
        if not context.args:
            await update.message.reply_text("⚠️ 用法：/delgroup 報告類型")
            return

        report_type = context.args[0].strip().lower()
        config = load_group_config()

        if report_type not in config:
            await update.message.reply_text(
                f"⚠️ {report_type} 尚未設定自訂群組，現在使用預設 GROUP_CHAT_ID"
            )
            return

        del config[report_type]
        save_group_config(config)
        await update.message.reply_text(f"✅ 已刪除 {report_type} 的群組路由設定")
    except Exception as e:
        logger.exception("delgroup error: %s", e)
        await update.message.reply_text("⚠️ 刪除失敗")


# ===== 每日推播 =====
async def daily_push(context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = context.job.chat_id
        msg = generate_marketing(chat_id)
        save_to_notebook(chat_id, msg)

        personal_text = "📢 每日AI文案\n\n" + msg
        group_text = f"📢 每日AI文案（同步群組）\n\n來源 chat_id：{chat_id}\n\n{msg}"

        await context.bot.send_message(
            chat_id=chat_id,
            text=personal_text
        )

        try:
            await send_to_report_group(
                context.bot,
                "daily_push",
                group_text
            )
        except Exception as e:
            logger.warning("group send error (daily_push): %s", e)

    except Exception as e:
        logger.exception("daily_push error: %s", e)


async def execute_schedule_push(bot, chat_id, schedule_name, group_id, task_prompt="", trigger_type="scheduled"):
    try:
        if task_prompt:
            msg = generate_custom_schedule_task(chat_id, schedule_name, task_prompt)
        else:
            msg = generate_marketing(chat_id)
        save_to_notebook(chat_id, msg)

        trigger_label = {
            "scheduled": "排程AI文案",
            "manual": "手動測試排程",
            "catchup": "補跑排程",
        }.get(trigger_type, "排程AI文案")

        personal_text = f"📢 {trigger_label}：{schedule_name}\n\n" + msg
        group_text = (
            f"📢 {trigger_label}同步：{schedule_name}\n\n"
            f"來源 chat_id：{chat_id}\n"
            f"目標群組：{group_id}\n"
            f"執行方式：{trigger_type}\n\n{msg}"
        )

        await send_long_message(bot, chat_id, personal_text)
        await send_long_message(bot, group_id, group_text)

        record_schedule_execution(schedule_name, "success", trigger_type)
    except Exception as e:
        logger.exception("execute_schedule_push error (%s): %s", schedule_name, e)
        record_schedule_execution(schedule_name, "error", trigger_type, str(e))
        raise


async def scheduled_daily_push(context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = context.job.chat_id
        schedule_name = context.job.data.get("schedule_name", "schedule")
        group_id = int(context.job.data.get("group_id", GROUP_CHAT_ID))
        task_prompt = str(context.job.data.get("task_prompt", "")).strip()
        trigger_type = str(context.job.data.get("trigger_type", "scheduled")).strip() or "scheduled"

        await execute_schedule_push(
            context.bot,
            chat_id=chat_id,
            schedule_name=schedule_name,
            group_id=group_id,
            task_prompt=task_prompt,
            trigger_type=trigger_type,
        )
    except Exception as e:
        logger.exception("scheduled_daily_push error: %s", e)


# ===== 主程式 =====
async def execute_schedule_push(bot, chat_id, schedule_name, group_id, task_prompt="", trigger_type="scheduled"):
    try:
        if task_prompt:
            msg = generate_custom_schedule_task(chat_id, schedule_name, task_prompt)
        else:
            msg = generate_marketing(chat_id)
        save_to_notebook(chat_id, msg)

        trigger_label = {
            "scheduled": "排程AI任務",
            "manual": "手動執行排程",
            "catchup": "補跑排程",
        }.get(trigger_type, "排程AI任務")

        if task_prompt and schedule_name.strip() == "每日招生新聞":
            summary_source = strip_html_tags(msg)[:4000]
            if summary_source:
                summary = summarize_text_content(summary_source, None)
                msg += "\n\n🧾 摘要重點：\n" + html.escape(summary)

        if task_prompt and schedule_name.strip() == "每日招生新聞":
            summary_source = strip_html_tags(msg)[:4000]
            if summary_source:
                summary = summarize_text_content(summary_source, None)
                msg += "\n\n🧾 摘要重點：\n" + html.escape(summary)

        if task_prompt:
            personal_text = f"📢 {html.escape(trigger_label)}：{html.escape(schedule_name)}\n\n{msg}"
            group_text = (
                f"📢 {html.escape(trigger_label)}同步：{html.escape(schedule_name)}\n\n"
                f"來源 chat_id：{chat_id}\n"
                f"目標群組：{group_id}\n"
                f"執行方式：{html.escape(trigger_type)}\n\n{msg}"
            )

            await send_long_message(
                bot,
                chat_id,
                personal_text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            await send_long_message(
                bot,
                group_id,
                group_text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )

            if schedule_name.strip() == "每日招生新聞":
                summary_source = strip_html_tags(msg)
                sales_lines = generate_sales_copies_from_report(summary_source[:4000], None)
                for line in sales_lines:
                    title_text = "招生銷售文案"
                    personal_copy = f"🧾 {html.escape(title_text)}\n{html.escape(line)}"
                    group_copy = f"🧾 {html.escape(title_text)}\n{html.escape(line)}"
                    await send_long_message(
                        bot,
                        chat_id,
                        personal_copy,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                    await send_long_message(
                        bot,
                        group_id,
                        group_copy,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
        else:
            personal_text = f"📢 {trigger_label}：{schedule_name}\n\n" + msg
            group_text = (
                f"📢 {trigger_label}同步：{schedule_name}\n\n"
                f"來源 chat_id：{chat_id}\n"
                f"目標群組：{group_id}\n"
                f"執行方式：{trigger_type}\n\n{msg}"
            )

            await send_long_message(bot, chat_id, personal_text)
            await send_long_message(bot, group_id, group_text)

        record_schedule_execution(schedule_name, "success", trigger_type)
    except Exception as e:
        logger.exception("execute_schedule_push error (%s): %s", schedule_name, e)
        record_schedule_execution(schedule_name, "error", trigger_type, str(e))
        raise


PROMOTIONAL_PHRASES = [
    "即將開課",
    "請盡速報名",
    "立即報名",
    "招生中",
    "名額有限",
    "優惠截止",
    "限時優惠",
    "火熱招生",
    "報名從速",
]


ARTICLE_TEXT_CACHE = {}


def fetch_article_text(url, timeout=None):
    cleaned = (url or "").strip()
    if not cleaned:
        return ""


def compact_runtime_state():
    cleared = len(ARTICLE_TEXT_CACHE)
    ARTICLE_TEXT_CACHE.clear()
    return cleared

    cached = ARTICLE_TEXT_CACHE.get(cleaned)
    if cached is not None:
        return cached

    try:
        response = requests.get(
            cleaned,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=timeout or max(NEWS_SEARCH_TIMEOUT, 12),
        )
        soup = BeautifulSoup(response.text, "html.parser")
        text = " ".join(soup.stripped_strings)
        ARTICLE_TEXT_CACHE[cleaned] = text[:5000]
        return ARTICLE_TEXT_CACHE[cleaned]
    except Exception as e:
        logger.warning("fetch_article_text error (%s): %s", cleaned, e)
        ARTICLE_TEXT_CACHE[cleaned] = ""
        return ""


def is_promotional_article(title, url):
    title_text = (title or "").strip()
    article_text = fetch_article_text(url)
    combined = f"{title_text}\n{article_text}"
    return any(phrase in combined for phrase in PROMOTIONAL_PHRASES)


def format_compact_source_label(url, prefix="閱讀更多"):
    parsed = urllib.parse.urlparse((url or "").strip())
    domain = (parsed.netloc or "").replace("www.", "") or "新聞來源"
    return f"{prefix}（{domain}）"


def render_compact_html_text(text):
    raw_text = str(text or "")
    pattern = re.compile(
        r"\[(?P<label>[^\]]+)\]\((?P<mdurl>https?://[^\s)]+)\)|(?P<rawurl>https?://[^\s<]+)"
    )

    parts = []
    last_end = 0

    for match in pattern.finditer(raw_text):
        start, end = match.span()
        if start > last_end:
            parts.append(html.escape(raw_text[last_end:start]))

        url = match.group("mdurl") or match.group("rawurl") or ""
        suffix = ""
        while url and url[-1] in ".,);]":
            suffix = url[-1] + suffix
            url = url[:-1]

        if url:
            parts.append(format_html_link(url, format_compact_source_label(url)))
        if suffix:
            parts.append(html.escape(suffix))

        last_end = end

    if last_end < len(raw_text):
        parts.append(html.escape(raw_text[last_end:]))

    return "".join(parts)


def strip_html_tags(text):
    raw = str(text or "")
    no_tags = re.sub(r"<[^>]+>", "", raw)
    return html.unescape(no_tags).strip()


def fetch_newsapi_article_for_variant(query):
    if not NEWS_API_KEY:
        return None

    try:
        since = (datetime.datetime.now(tz) - datetime.timedelta(days=1)).isoformat()
        response = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": f'"{query}" OR {query}',
                "searchIn": "title,description,content",
                "sortBy": "publishedAt",
                "pageSize": 10,
                "from": since,
                "language": "zh",
                "apiKey": NEWS_API_KEY,
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=max(NEWS_SEARCH_TIMEOUT, 12),
        )
        if not response.ok:
            logger.warning("NewsAPI error (%s): %s", query, response.text[:200])
            return None

        data = response.json()
        for item in data.get("articles", []):
            title = str(item.get("title", "")).strip()
            link = resolve_final_url(
                str(item.get("url", "")).strip(),
                timeout=max(NEWS_SEARCH_TIMEOUT, 12),
            )
            if not title or not link:
                continue
            if is_promotional_article(title, link):
                continue
            return {
                "query": query,
                "title": title,
                "link": link,
                "source": "NewsAPI",
            }
    except Exception as e:
        logger.warning("fetch_newsapi_article_for_variant error (%s): %s", query, e)

    return None


def fetch_google_news_articles(queries, limit_per_query=1, max_total=12):
    articles = []
    search_links = []
    seen_links = set()
    headers = {"User-Agent": "Mozilla/5.0"}

    for original_query in queries:
        if len(articles) >= max_total:
            break

        selected_article = None

        for variant in build_query_variants(original_query):
            search_query = f"when:1d {variant}".strip()
            encoded = urllib.parse.quote(search_query)
            rss_url = (
                f"https://news.google.com/rss/search?q={encoded}"
                f"&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
            )
            search_links.append(rss_url)

            try:
                feed = feedparser.parse(rss_url)
                for entry in getattr(feed, "entries", [])[:6]:
                    title = getattr(entry, "title", "").strip()
                    link = resolve_final_url(
                        getattr(entry, "link", "").strip(),
                        headers=headers,
                        timeout=max(NEWS_SEARCH_TIMEOUT, 12),
                    )

                    if not title or not link or link in seen_links:
                        continue
                    if is_promotional_article(title, link):
                        continue

                    selected_article = {
                        "query": original_query,
                        "title": title,
                        "link": link,
                        "source": "Google News",
                    }
                    break
            except Exception as e:
                logger.warning("fetch_google_news_articles error (%s): %s", variant, e)

            if selected_article:
                break

        if not selected_article:
            for variant in build_query_variants(original_query):
                selected_article = fetch_newsapi_article_for_variant(variant)
                if selected_article:
                    selected_article["query"] = original_query
                    if selected_article["link"] in seen_links:
                        selected_article = None
                        continue
                    break

        if selected_article:
            seen_links.add(selected_article["link"])
            articles.append(selected_article)

    return articles, dedupe_links(search_links)


def generate_custom_schedule_task(chat_id, schedule_name, task_prompt):
    try:
        query_text = task_prompt[:120].strip() or user_keywords.get(chat_id, "AI")
        queries = extract_schedule_queries(task_prompt, query_text)
        articles, _search_links = fetch_google_news_articles(queries)
        article_map = {article["query"]: article for article in articles}

        if articles:
            market_text = "\n".join(
                [
                    f"- 關鍵字：{article['query']}\n"
                    f"  標題：{article['title']}\n"
                    f"  網址：{article['link']}\n"
                    f"  來源：{article.get('source', 'Google News')}"
                    for article in articles[:12]
                ]
            )
        else:
            market_text = "目前沒有查到可用的一日內新聞，請明確寫出查無資料，不要自造新聞或網址。"

        prompt = f"""
你是一位招生與市場情報助理，請根據使用者任務產出適合 Telegram 閱讀的回覆。
排程名稱：{schedule_name}

任務內容：
{task_prompt}

以下是已查到的真實新聞資料：
{market_text}

請嚴格遵守：
1. 只能使用上方提供的真實新聞標題與網址。
2. 禁止產生、猜測或示範用網址，例如 example.com。
3. 如果某個課程名稱查不到合適新聞，請直接寫「查無一日內相關新聞」。
4. 不要採用帶有「即將開課」、「請盡速報名」等招生廣告意味的新聞。
5. 回覆格式要精簡、適合 Telegram 閱讀。
"""

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            timeout=70
        )
        result = render_compact_html_text((response.choices[0].message.content or "").strip())

        course_lines = []
        for query in queries:
            article = article_map.get(query)
            if article:
                course_lines.append(
                    f"● {html.escape(query)}\n"
                    f"新聞：{html.escape(article['title'])}\n"
                    f"連結：{format_html_link(article['link'], format_compact_source_label(article['link']))}"
                )
            else:
                course_lines.append(
                    f"● {html.escape(query)}\n"
                    "新聞：查無一日內相關新聞"
                )

        source_lines = []
        for idx, article in enumerate(articles[:12], start=1):
            source_lines.append(
                f"• {format_html_link(article['link'], format_compact_source_label(article['link'], f'來源 {idx}'))}"
            )

        parts = [result]
        if course_lines:
            parts.append("\n\n📚 各課程新聞索引：\n" + "\n\n".join(course_lines))
        if source_lines:
            parts.append("\n\n📎 資料來源：\n" + "\n".join(source_lines))

        return "".join(parts)
    except Exception as e:
        logger.exception("generate_custom_schedule_task error: %s", e)
        return html.escape(
            f"⚠️ 排程 {schedule_name} 執行失敗\n\n任務內容：{task_prompt}\n\n請稍後再試。"
        )


async def execute_schedule_push(bot, chat_id, schedule_name, group_id, task_prompt="", trigger_type="scheduled"):
    try:
        if task_prompt:
            msg = generate_custom_schedule_task(chat_id, schedule_name, task_prompt)
        else:
            msg = generate_marketing(chat_id)
        save_to_notebook(chat_id, msg)

        trigger_label = {
            "scheduled": "排程AI任務",
            "manual": "手動執行排程",
            "catchup": "補跑排程",
        }.get(trigger_type, "排程AI任務")

        if task_prompt:
            personal_text = f"📢 {html.escape(trigger_label)}：{html.escape(schedule_name)}\n\n{msg}"
            group_text = (
                f"📢 {html.escape(trigger_label)}同步：{html.escape(schedule_name)}\n\n"
                f"來源 chat_id：{chat_id}\n"
                f"目標群組：{group_id}\n"
                f"執行方式：{html.escape(trigger_type)}\n\n{msg}"
            )

            await send_long_message(
                bot,
                chat_id,
                personal_text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            await send_long_message(
                bot,
                group_id,
                group_text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )

            if schedule_name.strip() == "每日招生新聞":
                summary_source = strip_html_tags(msg)
                sales_lines = generate_sales_copies_from_report(summary_source[:4000], None)
                for line in sales_lines:
                    title_text = "招生銷售文案"
                    personal_copy = f"🧾 {html.escape(title_text)}\n{html.escape(line)}"
                    group_copy = f"🧾 {html.escape(title_text)}\n{html.escape(line)}"
                    await send_long_message(
                        bot,
                        chat_id,
                        personal_copy,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                    await send_long_message(
                        bot,
                        group_id,
                        group_copy,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
        else:
            personal_text = f"📢 {trigger_label}：{schedule_name}\n\n" + msg
            group_text = (
                f"📢 {trigger_label}同步：{schedule_name}\n\n"
                f"來源 chat_id：{chat_id}\n"
                f"目標群組：{group_id}\n"
                f"執行方式：{trigger_type}\n\n{msg}"
            )
            await send_long_message(bot, chat_id, personal_text)
            await send_long_message(bot, group_id, group_text)

        record_schedule_execution(schedule_name, "success", trigger_type)
    except Exception as e:
        logger.exception("execute_schedule_push error (%s): %s", schedule_name, e)
        record_schedule_execution(schedule_name, "error", trigger_type, str(e))
        raise


def get_command_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        return " ".join(context.args).strip()

    if update.message and update.message.reply_to_message:
        reply = update.message.reply_to_message
        return (reply.text or reply.caption or "").strip()

    return ""


def get_status_text(user=None):
    session = get_user_session_settings(user.id) if user else {"think": "medium", "verbose": False}
    schedule_count = len(load_schedule_config())
    auth = load_authorized_users()
    return "\n".join(
        [
            "🟢 Bot 狀態正常",
            f"模型：{OPENAI_MODEL}",
            f"資料目錄：{DATA_DIR}",
            f"自訂排程數：{schedule_count}",
            f"管理者數：{len(auth.get('admins', []))}",
            f"操作員數：{len(auth.get('operators', []))}",
            f"NEWS_API_KEY：{'已設定' if NEWS_API_KEY else '未設定'}",
            f"GEMINI_API_KEY：{'已設定' if GEMINI_API_KEY else '未設定'}",
            f"思考等級：{session.get('think', 'medium')}",
            f"詳細模式：{'開啟' if session.get('verbose') else '關閉'}",
        ]
    )


def get_weather_text(location):
    target = (location or WEATHER_LOCATION).strip() or WEATHER_LOCATION
    response = requests.get(
        f"https://wttr.in/{urllib.parse.quote(target)}",
        params={"format": "j1"},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=12,
    )
    data = response.json()
    current = (data.get("current_condition") or [{}])[0]
    desc = ((current.get("weatherDesc") or [{}])[0].get("value") or "").strip()
    temp_c = current.get("temp_C", "?")
    feels = current.get("FeelsLikeC", "?")
    humidity = current.get("humidity", "?")
    return "\n".join(
        [
            f"🌤️ 天氣：{target}",
            f"狀況：{desc or '未知'}",
            f"溫度：{temp_c}°C",
            f"體感：{feels}°C",
            f"濕度：{humidity}%",
        ]
    )


def summarize_text_content(text, user_id=None):
    session = get_user_session_settings(user_id) if user_id else {"think": "medium", "verbose": False}
    detail = "詳細" if session.get("verbose") else "精簡"
    prompt = (
        f"請用繁體中文做{detail}摘要，條列重點、關鍵結論與可執行建議。"
        f"思考深度偏好：{session.get('think', 'medium')}。\n\n{text}"
    )
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        timeout=60,
    )
    return response.choices[0].message.content.strip()


def generate_sales_copies_from_report(text, user_id=None):
    session = get_user_session_settings(user_id) if user_id else {"think": "medium", "verbose": False}
    prompt = (
        "請根據以下新聞回報內容，產出 5 則招生銷售文案建議。\n"
        "每則 50~100 字（含標點），用繁體中文。\n"
        "文案需引用前面新聞中的具體資訊，例如公司名稱或數據。\n"
        "若新聞未提供明確數據，不要硬編數字，可用趨勢描述取代。\n"
        "至少提到薪資提升幅度或薪資區間（若新聞有資料）。\n"
        "只輸出 5 行文案，不要標題、不要序號、不要其他說明。\n"
        f"思考深度偏好：{session.get('think', 'medium')}。\n\n{text}"
    )
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        timeout=60,
    )
    raw = (response.choices[0].message.content or "").strip()
    lines = []
    for line in raw.splitlines():
        clean = line.strip().lstrip("-•*").strip()
        if clean:
            lines.append(clean)
    if len(lines) < 5:
        retry_prompt = (
            "請重新輸出 5 行招生銷售文案（每行 100 字內），只要 5 行文字，不要序號。\n\n"
            f"{text}"
        )
        retry = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": retry_prompt}],
            timeout=60,
        )
        raw = (retry.choices[0].message.content or "").strip()
        lines = []
        for line in raw.splitlines():
            clean = line.strip().lstrip("-•*").strip()
            if clean:
                lines.append(clean)
    return lines[:5]


def generate_skill_template(topic):
    clean_topic = (topic or "招生新聞任務").strip()
    return "\n".join(
        [
            f"🧩 Skill 範本：{clean_topic}",
            "1. 任務目標：說明這個 skill 要解決什麼問題",
            "2. 輸入資料：列出會提供哪些關鍵字、來源、限制",
            "3. 執行步驟：",
            "- 搜尋最近一日內新聞",
            "- 排除招生廣告型內容",
            "- 摘要可用重點",
            "- 產出可用回報格式",
            "4. 輸出格式：標題、摘要、連結、建議",
            "",
            "範例用途：",
            f"/setscheduletask 每日技能 {clean_topic} ...",
        ]
    )


def list_tool_text():
    return "\n".join(
        [
            "🧰 可用工具 / 能力",
            "- OpenAI：文案、摘要、優化",
            "- Google News：新聞搜尋",
            "- NewsAPI：補強新聞搜尋",
            "- Google Sheets：追蹤資料讀取",
            "- Telegram 排程：定時推播與群組路由",
            "- 目前不含完整 OpenClaw runtime shell / subagent 執行環境",
        ]
    )


def generate_gifgrep_text(query):
    clean_query = (query or "").strip()
    if not clean_query:
        clean_query = "AI marketing"
    encoded = urllib.parse.quote(clean_query)
    return "\n".join(
        [
            f"🎞️ GIF 搜尋：{clean_query}",
            f"Tenor：https://tenor.com/search/{encoded}-gifs",
            f"Giphy：https://giphy.com/search/{encoded}",
        ]
    )


def generate_nano_pdf_text(text):
    clean_text = (text or "").strip()
    if not clean_text:
        return "⚠️ 用法：/nano_pdf 文字內容，或回覆一段文字後輸入 /nano_pdf"
    return "\n".join(
        [
            "📄 Nano PDF 摘要大綱",
            "1. 封面標題",
            "2. 一頁摘要",
            "3. 核心重點 3-5 點",
            "4. 圖表或數據建議",
            "5. 行動建議",
            "",
            "內容摘要：",
            summarize_text_content(clean_text[:4000]),
        ]
    )


def run_gemini_prompt(text):
    clean_text = (text or "").strip()
    if not clean_text:
        return "⚠️ 用法：/gemini 問題內容，或回覆文字後輸入 /gemini"

    if not GEMINI_API_KEY:
        return "\n".join(
            [
                "ℹ️ 目前未設定 GEMINI_API_KEY。",
                "你可以把下面這段直接貼到 Gemini：",
                "",
                clean_text,
            ]
        )

    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}",
        headers={"Content-Type": "application/json"},
        json={"contents": [{"parts": [{"text": clean_text}]}]},
        timeout=40,
    )
    data = response.json()
    candidates = data.get("candidates") or []
    if not candidates:
        return "⚠️ Gemini 沒有回傳內容。"
    parts = (((candidates[0] or {}).get("content") or {}).get("parts") or [])
    text_parts = [part.get("text", "").strip() for part in parts if part.get("text")]
    return "\n".join(text_parts).strip() or "⚠️ Gemini 沒有可讀取內容。"


INSTALLED_COMMAND_HELP = [
    ("/start", "啟動 bot；未授權者可取得配對流程。", "/start"),
    ("/whoami", "查看自己的 user_id、username、姓名與權限狀態。", "/whoami"),
    ("/approveuser 配對碼", "管理者核准新使用者。", "/approveuser ABC12345"),
    ("/listusers", "查看已授權名單。", "/listusers"),
    ("/revokeuser user_id", "移除某位使用者權限。", "/revokeuser 123456789"),
    ("/addadmin user_id", "新增第二管理者。", "/addadmin 123456789"),
    ("/deleteallpairs", "清空待核准配對碼。", "/deleteallpairs"),
    ("/status", "查看 bot 狀態、模型、排程數量與 API 設定。", "/status"),
    ("/model", "查看目前 OpenAI 模型。", "/model"),
    ("/models", "查看目前模型與可切換方式。", "/models"),
    ("/model_usage", "查看模型使用概況。", "/model_usage"),
    ("/weather [地點]", "查詢天氣；未填則用預設地點。", "/weather Taipei"),
    ("/tools", "查看這支 bot 可用工具與整合。", "/tools"),
    ("/summarize 文字", "摘要一段文字，或回覆文字後使用。", "/summarize 請幫我摘要這段內容"),
    ("/skill_creator 主題", "產生可重用的 skill / 任務模板。", "/skill_creator 每日競品分析"),
    ("/skill [主題]", "查看 skill 類型，或直接產生特定主題模板。", "/skill 招生新聞"),
    ("/gemini 內容", "若有 GEMINI_API_KEY 則呼叫 Gemini，否則產出可貼給 Gemini 的 prompt。", "/gemini 幫我整理這段需求"),
    ("/gemini_status", "顯示 Gemini 是否已接上與目前模型。", "/gemini_status"),
    ("/dock_telegram", "顯示目前已在 Telegram 模式。", "/dock_telegram"),
    ("/think low|medium|high", "查看或設定個人思考等級。", "/think high"),
    ("/verbose on|off", "查看或切換個人詳細模式。", "/verbose on"),
    ("/elevated on|off", "查看或切換 Elevated 模式。", "/elevated on"),
    ("/compact", "清理暫存資料（文章快取）。", "/compact"),
    ("/exec 子指令", "執行部分內建指令，如 marketing/report/optimize/status/weather。", "/exec status"),
    ("/gifgrep 關鍵字", "快速產出 GIF 搜尋連結。", "/gifgrep AI marketing"),
    ("/healthcheck", "查看 bot 健康狀態。", "/healthcheck"),
    ("/nano_pdf 文字", "將文字整理成 PDF 摘要大綱。", "/nano_pdf 請整理這段文章"),
    ("/restart confirm", "管理者重啟 Zeabur bot。", "/restart confirm"),
    ("/reset", "重設目前聊天的 keyword/source/topic 與個人 think/verbose。", "/reset"),
    ("/marketing", "立即產生 AI 行銷文案。", "/marketing"),
    ("/optimize", "比較最近兩篇文案並產出優化版。", "/optimize"),
    ("/report", "查看成效報表。", "/report"),
    ("/simulate", "模擬 campaign 成效資料。", "/simulate"),
    ("/setkeyword 關鍵字", "設定搜尋關鍵字。", "/setkeyword AI 招生"),
    ("/setsource 來源", "設定搜尋來源輔助字。", "/setsource Google News"),
    ("/settopic 主題", "設定主題。", "/settopic AI 課程招生"),
    ("/settime HH:MM", "設定舊版單一每日推播時間。", "/settime 09:00"),
    ("/setschedule 名稱 HH:MM 群組ID", "建立自訂排程。", "/setschedule 每日招生新聞 08:00 -5114067569"),
    ("/setscheduletask 名稱 任務內容", "設定排程任務內容。", "/setscheduletask 每日招生新聞 搜尋一日內新聞並整理"),
    ("/setscheduletaskedit 名稱", "用回覆多行文字方式設定任務內容。", "/setscheduletaskedit 每日招生新聞"),
    ("/setscheduletaskfile 名稱", "用回覆 .txt/.md 檔方式設定任務內容。", "/setscheduletaskfile 每日招生新聞"),
    ("/showschedules", "查看所有排程摘要。", "/showschedules"),
    ("/viewschedule 名稱", "查看單一排程明細。", "/viewschedule 每日招生新聞"),
    ("/updateschedule 名稱 HH:MM 群組ID", "修改既有排程時間與群組。", "/updateschedule 每日招生新聞 13:00 -5114067569"),
    ("/runschedule 名稱", "立即手動執行一次排程。", "/runschedule 每日招生新聞"),
    ("/exportschedules", "匯出所有排程摘要。", "/exportschedules"),
    ("/schedulelogs 名稱", "查看最近執行紀錄。", "/schedulelogs 每日招生新聞"),
    ("/delschedule 名稱", "刪除排程。", "/delschedule 每日招生新聞"),
    ("/setgroup 類型 群組ID", "設定不同訊息類型的群組路由。", "/setgroup report -5114067569"),
    ("/showgroups", "查看群組路由設定。", "/showgroups"),
    ("/delgroup 類型", "刪除某類型群組路由。", "/delgroup report"),
    ("/task_commands", "列出任務/排程相關指令明細。", "/task_commands"),
]

TASK_COMMANDS_HELP = [
    ("/setschedule 名稱 HH:MM 群組ID", "建立自訂排程。", "/setschedule 每日招生新聞 08:00 -5114067569"),
    ("/setscheduletask 名稱 任務內容", "設定排程任務內容。", "/setscheduletask 每日招生新聞 搜尋一日內新聞"),
    ("/setscheduletaskedit 名稱", "用回覆多行文字方式設定任務內容。", "/setscheduletaskedit 每日招生新聞"),
    ("/setscheduletaskfile 名稱", "用回覆 .txt/.md 檔方式設定任務內容。", "/setscheduletaskfile 每日招生新聞"),
    ("/showschedules", "查看所有排程摘要。", "/showschedules"),
    ("/viewschedule 名稱", "查看單一排程明細。", "/viewschedule 每日招生新聞"),
    ("/updateschedule 名稱 HH:MM 群組ID", "修改既有排程時間與群組。", "/updateschedule 每日招生新聞 13:00 -5114067569"),
    ("/runschedule 名稱", "立即手動執行一次排程。", "/runschedule 每日招生新聞"),
    ("/schedulelogs 名稱", "查看最近執行紀錄。", "/schedulelogs 每日招生新聞"),
    ("/exportschedules", "匯出所有排程摘要。", "/exportschedules"),
    ("/delschedule 名稱", "刪除排程。", "/delschedule 每日招生新聞"),
]

OPENCLAW_PLATFORM_COMMANDS = [
    "/approve", "/context", "/btw", "/export_session", "/sessions", "/subagents", "/acp",
    "/focus", "/unfocus", "/agents", "/kill", "/usage", "/stop", "/activation", "/send",
    "/new", "/fast", "/reasoning", "/queue", "/1password", "/apple_notes",
    "/apple_reminders", "/davhub", "/eightctl", "/gh_issues",
    "/github", "/node_connect",
    "/openai_whisper", "/openai_whisper_api", "/openhue", "/oracle",
    "/things_mac", "/video_frames", "/wa",
]

OPENCLAW_PLATFORM_COMMAND_HELP = [
    ("/approve", "核准或拒絕存取請求（平台流程）。", "/approve ABC123"),
    ("/context", "查看/解釋平台如何建立上下文。", "/context"),
    ("/btw", "用小提示詢問、不改變 session。", "/btw 今天重點是什麼"),
    ("/export_session", "匯出平台 session（HTML）。", "/export_session"),
    ("/sessions", "列出平台 sessions。", "/sessions"),
    ("/subagents", "列出或管理子代理。", "/subagents"),
    ("/acp", "管理 ACP 連線或 runtime 選項。", "/acp"),
    ("/focus", "綁定主題或頻道。", "/focus 招生新聞"),
    ("/unfocus", "解除綁定主題或頻道。", "/unfocus"),
    ("/agents", "列出可用的 thread-bound agents。", "/agents"),
    ("/kill", "停止目前任務或代理。", "/kill"),
    ("/usage", "顯示使用量摘要。", "/usage"),
    ("/stop", "停止目前執行流程。", "/stop"),
    ("/activation", "切換或設定行為模式。", "/activation"),
    ("/send", "傳送系統訊息或設定策略。", "/send 設定行為"),
    ("/new", "開新 session。", "/new"),
    ("/compact", "壓縮 session 上下文。", "/compact"),
    ("/fast", "切換快速模式。", "/fast"),
    ("/reasoning", "切換推理顯示。", "/reasoning"),
    ("/elevated", "切換高等模式。", "/elevated"),
    ("/queue", "調整佇列設定。", "/queue"),
    ("/1password", "與 1Password CLI 互動。", "/1password"),
    ("/apple_notes", "管理 Apple Notes。", "/apple_notes"),
    ("/apple_reminders", "管理 Apple Reminders。", "/apple_reminders"),
    ("/davhub", "更新與發佈技能清單。", "/davhub"),
    ("/eightctl", "控制 8x8/Light/設備（平台工具）。", "/eightctl"),
    ("/gh_issues", "抓取 GitHub issues。", "/gh_issues"),
    ("/github", "GitHub 相關工具。", "/github"),
    ("/node_connect", "診斷 OpenAI/Android iOS 連線。", "/node_connect"),
    ("/openai_whisper", "語音轉文字（Whisper CLI）。", "/openai_whisper"),
    ("/openai_whisper_api", "語音轉文字（Whisper API）。", "/openai_whisper_api"),
    ("/openhue", "控制智慧燈泡/場景。", "/openhue"),
    ("/oracle", "提示最佳實務/指引。", "/oracle"),
    ("/things_mac", "控制 Things 3。", "/things_mac"),
    ("/video_frames", "擷取影片影格。", "/video_frames"),
    ("/wa", "WhatsApp 相關工具。", "/wa"),
]


def build_help_text():
    lines = [
        "📘 指令說明",
        "",
        "以下為本 bot 已安裝指令。",
        "你在 Telegram 對話欄看到的其他 OpenClaw 指令，若未列於「已安裝指令」，代表目前尚未安裝到本 bot。",
        "本次已讓這些 OpenClaw 指令可回應提示，但它們不是這支 Zeabur Python bot 的完整原生功能。",
        "",
        "常用功能：",
    ]

    for command, description, example in INSTALLED_COMMAND_HELP[:12]:
        lines.append(f"{command}")
        lines.append(f"功能：{description}")
        lines.append(f"範例：{example}")
        lines.append("")

    lines.append("排程與群組管理：")
    for command, description, example in INSTALLED_COMMAND_HELP[12:]:
        lines.append(f"{command}")
        lines.append(f"功能：{description}")
        lines.append(f"範例：{example}")
        lines.append("")

    lines.append("OpenClaw 平台指令：")
    lines.append("以下指令目前僅提供提示回覆，未在本 bot 內完整實作：")
    for command, description, example in OPENCLAW_PLATFORM_COMMAND_HELP:
        lines.append(f"{command}")
        lines.append(f"功能：{description}")
        lines.append(f"範例：{example}")
        lines.append("")
    return "\n".join(lines).strip()


def build_commands_text():
    lines = [
        "📋 已安裝指令清單",
        "",
    ]
    for command, description, example in INSTALLED_COMMAND_HELP:
        lines.append(f"{command}")
        lines.append(f"- 功能：{description}")
        lines.append(f"- 範例：{example}")
    lines.append("")
    lines.append("🧩 OpenClaw 平台指令")
    lines.append("以下指令目前僅掛載提示，未在本 bot 完整實作：")
    for command, description, example in OPENCLAW_PLATFORM_COMMAND_HELP:
        lines.append(f"{command}")
        lines.append(f"- 功能：{description}")
        lines.append(f"- 範例：{example}")
    return "\n".join(lines).strip()


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_long_message(context.bot, update.effective_chat.id, build_help_text())


async def commands_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_long_message(context.bot, update.effective_chat.id, build_commands_text())


async def task_commands_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ["📋 任務/排程指令明細", ""]
    for command, description, example in TASK_COMMANDS_HELP:
        lines.append(f"{command}")
        lines.append(f"- 功能：{description}")
        lines.append(f"- 範例：{example}")
        lines.append("")
    await send_long_message(context.bot, update.effective_chat.id, "\n".join(lines).strip())


async def openclaw_platform_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    command_text = (update.message.text or "").split()[0]
    await update.message.reply_text(
        f"ℹ️ {command_text}\n"
        "這是 OpenClaw 平台指令。\n"
        "目前這支 Zeabur Python bot 只掛載了提示回覆，尚未在 bot 內完整實作此功能。\n"
        "請輸入 /help 查看本 bot 已安裝指令。"
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_status_text(update.effective_user))


async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🤖 目前模型：{OPENAI_MODEL}")


async def models_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "\n".join(
            [
                "📚 模型清單",
                f"目前使用：{OPENAI_MODEL}",
                "可切換方式：修改 Zeabur 環境變數 OPENAI_MODEL",
                "Gemini 預設：{}".format(GEMINI_MODEL),
            ]
        )
    )


async def model_usage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "\n".join(
            [
                "📈 模型使用狀態",
                f"OpenAI 模型：{OPENAI_MODEL}",
                f"Gemini 模型：{GEMINI_MODEL}",
                "目前 bot 尚未實作 token / cost 累計記錄。",
            ]
        )
    )


async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    location = get_command_input(update, context) or WEATHER_LOCATION
    try:
        await update.message.reply_text(get_weather_text(location))
    except Exception as e:
        await update.message.reply_text(f"⚠️ weather 查詢失敗：{e}")


async def summarize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = get_command_input(update, context)
    if not text:
        await update.message.reply_text("⚠️ 用法：/summarize 文字內容，或回覆一段文字後輸入 /summarize")
        return
    await send_long_message(
        context.bot,
        update.effective_chat.id,
        summarize_text_content(text[:6000], update.effective_user.id if update.effective_user else None),
    )


async def skill_creator_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_long_message(
        context.bot,
        update.effective_chat.id,
        generate_skill_template(get_command_input(update, context)),
    )


async def skill_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = get_command_input(update, context)
    if topic:
        await send_long_message(context.bot, update.effective_chat.id, generate_skill_template(topic))
    else:
        await update.message.reply_text(
            "🧩 目前可用 skill 類型：招生新聞、競品分析、每日文案、成效摘要。\n"
            "範例：/skill_creator 每日競品新聞摘要"
        )


async def tools_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(list_tool_text())


async def dock_telegram_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📌 目前已在 Telegram 模式中執行。")


async def think_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    value = get_command_input(update, context).lower()
    if value in {"low", "medium", "high"}:
        session = update_user_session_settings(user.id, think=value)
        await update.message.reply_text(f"🧠 思考等級已設定為：{session['think']}")
        return
    session = get_user_session_settings(user.id)
    await update.message.reply_text(f"🧠 目前思考等級：{session.get('think', 'medium')}\n用法：/think low|medium|high")


async def verbose_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    value = get_command_input(update, context).lower()
    if value in {"on", "off"}:
        session = update_user_session_settings(user.id, verbose=(value == "on"))
        await update.message.reply_text(f"📝 詳細模式已{'開啟' if session['verbose'] else '關閉'}")
        return
    session = get_user_session_settings(user.id)
    await update.message.reply_text(f"📝 詳細模式：{'開啟' if session.get('verbose') else '關閉'}\n用法：/verbose on|off")


async def elevated_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    value = get_command_input(update, context).lower()
    if value in {"on", "off"}:
        session = update_user_session_settings(user.id, elevated=(value == "on"))
        await update.message.reply_text(f"🧩 Elevated 模式已{'開啟' if session['elevated'] else '關閉'}")
        return
    session = get_user_session_settings(user.id)
    await update.message.reply_text(f"🧩 Elevated 模式：{'開啟' if session.get('elevated') else '關閉'}\n用法：/elevated on|off")


async def compact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_operator(update):
        return
    cleared = compact_runtime_state()
    await update.message.reply_text(
        f"🗜️ 已清理暫存資料：{cleared} 筆文章快取。\n"
        "若需完整重置，請使用 /reset。"
    )


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_keywords.pop(chat_id, None)
    user_sources.pop(chat_id, None)
    user_topics.pop(chat_id, None)
    if update.effective_user:
        update_user_session_settings(update.effective_user.id, think="medium", verbose=False)
    await update.message.reply_text("♻️ 已重設目前聊天的 keyword/source/topic 與個人 think/verbose 設定。")


async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    value = get_command_input(update, context).lower()
    if value != "confirm":
        await update.message.reply_text("⚠️ 用法：/restart confirm\n這會讓 Zeabur 服務重新啟動。")
        return
    await update.message.reply_text("🔄 正在重新啟動 OpenClaw bot...")
    threading.Timer(1.0, lambda: os._exit(0)).start()


async def exec_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_operator(update):
        return
    text = get_command_input(update, context)
    if not text:
        await update.message.reply_text("⚠️ 用法：/exec marketing|report|optimize|status|weather [參數]")
        return
    parts = text.split()
    action = parts[0].lower()
    arg_text = " ".join(parts[1:]).strip()

    if action == "marketing":
        await update.message.reply_text(generate_marketing(update.effective_chat.id))
    elif action == "report":
        await update.message.reply_text(generate_report(update.effective_chat.id))
    elif action == "optimize":
        await update.message.reply_text(optimize_marketing(update.effective_chat.id))
    elif action == "status":
        await update.message.reply_text(get_status_text(update.effective_user))
    elif action == "weather":
        try:
            await update.message.reply_text(get_weather_text(arg_text or WEATHER_LOCATION))
        except Exception as e:
            await update.message.reply_text(f"⚠️ weather 查詢失敗：{e}")
    else:
        await update.message.reply_text("⚠️ /exec 目前支援：marketing, report, optimize, status, weather")


async def gifgrep_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(generate_gifgrep_text(get_command_input(update, context)))


async def healthcheck_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    schedule_count = len(load_schedule_config())
    last_logs = load_schedule_execution_log()
    await update.message.reply_text(
        "\n".join(
            [
                "🩺 Healthcheck",
                f"Bot：正常",
                f"模型：{OPENAI_MODEL}",
                f"資料目錄：{DATA_DIR}",
                f"排程數：{schedule_count}",
                f"執行紀錄數：{len(last_logs)}",
                f"News API：{'已設定' if NEWS_API_KEY else '未設定'}",
            ]
        )
    )


async def nano_pdf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_long_message(
        context.bot,
        update.effective_chat.id,
        generate_nano_pdf_text(get_command_input(update, context)),
    )


async def gemini_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await send_long_message(
            context.bot,
            update.effective_chat.id,
            run_gemini_prompt(get_command_input(update, context)),
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ gemini 執行失敗：{e}")


async def gemini_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = "已設定" if GEMINI_API_KEY else "未設定"
    await update.message.reply_text(
        "\n".join(
            [
                "🔎 Gemini 狀態",
                f"GEMINI_API_KEY：{status}",
                f"GEMINI_MODEL：{GEMINI_MODEL}",
            ]
        )
    )


def main():
    ensure_default_admins()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("commands", commands_command))
    app.add_handler(CommandHandler("task_commands", task_commands_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("model", model_command))
    app.add_handler(CommandHandler("models", models_command))
    app.add_handler(CommandHandler("model_usage", model_usage_command))
    app.add_handler(CommandHandler("weather", weather_command))
    app.add_handler(CommandHandler("summarize", summarize_command))
    app.add_handler(CommandHandler("skill_creator", skill_creator_command))
    app.add_handler(CommandHandler("skill", skill_command))
    app.add_handler(CommandHandler("tools", tools_command))
    app.add_handler(CommandHandler("restart", restart_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("gemini", gemini_command))
    app.add_handler(CommandHandler("gemini_status", gemini_status_command))
    app.add_handler(CommandHandler("dock_telegram", dock_telegram_command))
    app.add_handler(CommandHandler("think", think_command))
    app.add_handler(CommandHandler("verbose", verbose_command))
    app.add_handler(CommandHandler("elevated", elevated_command))
    app.add_handler(CommandHandler("compact", compact_command))
    app.add_handler(CommandHandler("exec", exec_command))
    app.add_handler(CommandHandler("gifgrep", gifgrep_command))
    app.add_handler(CommandHandler("healthcheck", healthcheck_command))
    app.add_handler(CommandHandler("nano_pdf", nano_pdf_command))
    app.add_handler(CommandHandler("whoami", whoami))
    app.add_handler(CommandHandler("approveuser", approveuser))
    app.add_handler(CommandHandler("listusers", listusers))
    app.add_handler(CommandHandler("revokeuser", revokeuser))
    app.add_handler(CommandHandler("addadmin", addadmin))
    app.add_handler(CommandHandler("deleteallpairs", deleteallpairs))
    app.add_handler(CommandHandler("marketing", marketing))
    app.add_handler(CommandHandler("optimize", optimize))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("simulate", simulate))
    app.add_handler(CommandHandler("setkeyword", setkeyword))
    app.add_handler(CommandHandler("setsource", setsource))
    app.add_handler(CommandHandler("settopic", settopic))
    app.add_handler(CommandHandler("settime", settime))
    app.add_handler(CommandHandler("setschedule", setschedule))
    app.add_handler(CommandHandler("setscheduletask", setscheduletask))
    app.add_handler(CommandHandler("setscheduletaskedit", setscheduletaskedit))
    app.add_handler(CommandHandler("setscheduletaskfile", setscheduletaskfile))
    app.add_handler(CommandHandler("showschedules", showschedules))
    app.add_handler(CommandHandler("viewschedule", viewschedule))
    app.add_handler(CommandHandler("updateschedule", updateschedule))
    app.add_handler(CommandHandler("runschedule", runschedule))
    app.add_handler(CommandHandler("exportschedules", exportschedules))
    app.add_handler(CommandHandler("schedulelogs", schedulelogs))
    app.add_handler(CommandHandler("delschedule", delschedule))
    app.add_handler(CommandHandler("setgroup", setgroup))
    app.add_handler(CommandHandler("showgroups", showgroups))
    app.add_handler(CommandHandler("delgroup", delgroup))
    app.add_handler(CommandHandler([
        "tools", "skill", "status", "approve", "context", "btw", "export_session",
        "sessions", "subagents", "acp", "focus", "unfocus", "agents", "kill",
        "usage", "stop", "restart", "activation", "send", "reset", "new",
        "compact", "think", "verbose", "fast", "reasoning", "elevated", "exec",
        "model", "models", "queue", "dock_telegram", "1password", "apple_notes",
        "apple_reminders", "davhub", "eightctl", "gemini", "gh_issues", "gifgrep",
        "github", "healthcheck", "model_usage", "nano_pdf", "node_connect",
        "openai_whisper", "openai_whisper_api", "openhue", "oracle",
        "skill_creator", "summarize", "things_mac", "video_frames", "wa",
        "weather"
    ], openclaw_platform_command))

    if TARGET_CHAT_ID:
        try:
            app.job_queue.run_daily(
                daily_push,
                time=time(hour=9, minute=0, tzinfo=tz),
                chat_id=int(TARGET_CHAT_ID),
                name=str(TARGET_CHAT_ID)
            )
            logger.info("Default daily push scheduled for TARGET_CHAT_ID=%s", TARGET_CHAT_ID)
        except Exception as e:
            logger.exception("Default schedule error: %s", e)

    schedule_config = load_schedule_config()
    for schedule_name, item in schedule_config.items():
        try:
            schedule_daily_job(
                app.job_queue,
                schedule_name=schedule_name,
                chat_id=item["chat_id"],
                hour=item["hour"],
                minute=item["minute"],
                group_id=item["group_id"],
                task_prompt=item.get("task_prompt", ""),
            )
            logger.info(
                "Loaded custom schedule %s for chat_id=%s at %02d:%02d -> group %s",
                schedule_name,
                item["chat_id"],
                item["hour"],
                item["minute"],
                item["group_id"],
            )
        except Exception as e:
            logger.exception("Load custom schedule error (%s): %s", schedule_name, e)

    schedule_missed_jobs(app.job_queue, schedule_config)

    app.run_polling()


if __name__ == "__main__":
    main()
