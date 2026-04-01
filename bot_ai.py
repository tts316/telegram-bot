import os
from dotenv import load_dotenv

# ===== 強制載入目前專案根目錄 .env =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(dotenv_path=ENV_PATH, override=False)

import logging
import json
import feedparser
import urllib.parse
import pytz
import datetime
import requests
import uuid

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

TRACK_BASE_URL = os.getenv("TRACK_BASE_URL", "https://your-domain.com")
LANDING_PAGE_URL = os.getenv("LANDING_PAGE_URL", "https://your-landing-page.com")
THANKYOU_PAGE_URL = os.getenv("THANKYOU_PAGE_URL", "https://your-thankyou-page.com")

GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "-5266698491"))
GROUP_CONFIG_FILE = os.path.join(BASE_DIR, "group_config.json")
SCHEDULE_CONFIG_FILE = os.path.join(BASE_DIR, "schedule_config.json")
ALLOWED_REPORT_TYPES = ["marketing", "report", "optimize", "daily_push"]

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
def load_group_config():
    try:
        with open(GROUP_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {k: int(v) for k, v in data.items()}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning("load_group_config error: %s", e)
        return {}


def save_group_config(data):
    with open(GROUP_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_schedule_config():
    try:
        with open(SCHEDULE_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {
                schedule_name: {
                    "chat_id": int(item["chat_id"]),
                    "hour": int(item["hour"]),
                    "minute": int(item["minute"]),
                    "group_id": int(item["group_id"]),
                }
                for schedule_name, item in data.items()
            }
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning("load_schedule_config error: %s", e)
        return {}


def save_schedule_config(data):
    with open(SCHEDULE_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def build_schedule_job_name(chat_id, schedule_name):
    return f"schedule:{chat_id}:{schedule_name}"


def schedule_daily_job(job_queue, schedule_name, chat_id, hour, minute, group_id):
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


# ===== 市場資料 =====
def fetch_market_intel(chat_id):
    results = []
    links = []

    try:
        keyword = user_keywords.get(chat_id, "台灣 AI 培訓")
        source = user_sources.get(chat_id, "")

        query = f"{keyword} {source}".strip()
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

            count = 0
            for p in soup.select("h2"):
                title = p.text.strip()
                if title:
                    results.append(f"📱 Dcard: {title}")
                    links.append("https://www.dcard.tw/search?query=" + encoded)
                    count += 1
                if count >= 2:
                    break
        except Exception as e:
            logger.warning("Dcard error: %s", e)

        if not results:
            results.append(f"{keyword} 市場趨勢")
            links.append(f"https://www.google.com/search?q={encoded}")

    except Exception as e:
        logger.exception("fetch_market_intel error: %s", e)
        results = ["市場資料錯誤"]
        links = []

    return results, links


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
                clean_links = [l.split("?")[0] for l in links if isinstance(l, str)]
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


# ===== Telegram 指令 =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ OpenClaw AI 行銷系統已啟動")


async def marketing(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    value = " ".join(context.args).strip()
    if not value:
        await update.message.reply_text("⚠️ 用法：/setkeyword 關鍵字")
        return

    user_keywords[update.effective_chat.id] = value
    await update.message.reply_text(f"✅ keyword 設定完成：{value}")


async def setsource(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value = " ".join(context.args).strip()
    if not value:
        await update.message.reply_text("⚠️ 用法：/setsource 來源")
        return

    user_sources[update.effective_chat.id] = value
    await update.message.reply_text(f"✅ source 設定完成：{value}")


async def settopic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value = " ".join(context.args).strip()
    if not value:
        await update.message.reply_text("⚠️ 用法：/settopic 主題")
        return

    user_topics[update.effective_chat.id] = value
    await update.message.reply_text(f"✅ topic 設定完成：{value}")


async def settime(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

        config = load_schedule_config()
        config[schedule_name] = {
            "chat_id": chat_id,
            "hour": hour,
            "minute": minute,
            "group_id": group_id,
        }
        save_schedule_config(config)

        schedule_daily_job(
            context.job_queue,
            schedule_name=schedule_name,
            chat_id=chat_id,
            hour=hour,
            minute=minute,
            group_id=group_id,
        )

        await update.message.reply_text(
            f"✅ 已建立排程\n名稱：{schedule_name}\n時間：{hour:02d}:{minute:02d}\n群組ID：{group_id}"
        )
    except Exception as e:
        logger.exception("setschedule error: %s", e)
        await update.message.reply_text("⚠️ 設定失敗，請確認時間與群組ID格式正確")


async def showschedules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = load_schedule_config()
    chat_id = update.effective_chat.id

    lines = ["🗓️ 目前排程設定："]
    has_item = False

    for schedule_name, item in sorted(config.items()):
        if item.get("chat_id") != chat_id:
            continue
        has_item = True
        lines.append(
            f"- {schedule_name} → {item['hour']:02d}:{item['minute']:02d} / 群組 {item['group_id']}"
        )

    if not has_item:
        lines.append("- 尚未設定任何自訂排程")

    await update.message.reply_text("\n".join(lines))


async def delschedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
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


async def setgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    config = load_group_config()
    lines = ["📋 目前群組路由設定："]

    for report_type in ALLOWED_REPORT_TYPES:
        group_id = config.get(report_type, GROUP_CHAT_ID)
        source = "自訂" if report_type in config else "預設"
        lines.append(f"- {report_type} → {group_id}（{source}）")

    await update.message.reply_text("\n".join(lines))


async def delgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
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


async def scheduled_daily_push(context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = context.job.chat_id
        schedule_name = context.job.data.get("schedule_name", "schedule")
        group_id = int(context.job.data.get("group_id", GROUP_CHAT_ID))

        msg = generate_marketing(chat_id)
        save_to_notebook(chat_id, msg)

        personal_text = f"📢 排程AI文案：{schedule_name}\n\n" + msg
        group_text = (
            f"📢 排程AI文案同步：{schedule_name}\n\n"
            f"來源 chat_id：{chat_id}\n"
            f"目標群組：{group_id}\n\n{msg}"
        )

        await context.bot.send_message(
            chat_id=chat_id,
            text=personal_text
        )

        await context.bot.send_message(
            chat_id=group_id,
            text=group_text
        )
    except Exception as e:
        logger.exception("scheduled_daily_push error: %s", e)


# ===== 主程式 =====
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("marketing", marketing))
    app.add_handler(CommandHandler("optimize", optimize))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("simulate", simulate))
    app.add_handler(CommandHandler("setkeyword", setkeyword))
    app.add_handler(CommandHandler("setsource", setsource))
    app.add_handler(CommandHandler("settopic", settopic))
    app.add_handler(CommandHandler("settime", settime))
    app.add_handler(CommandHandler("setschedule", setschedule))
    app.add_handler(CommandHandler("showschedules", showschedules))
    app.add_handler(CommandHandler("delschedule", delschedule))
    app.add_handler(CommandHandler("setgroup", setgroup))
    app.add_handler(CommandHandler("showgroups", showgroups))
    app.add_handler(CommandHandler("delgroup", delgroup))

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

    app.run_polling()


if __name__ == "__main__":
    main()
