import os
import logging
import feedparser
import urllib.parse
import pytz
import datetime
import requests

from bs4 import BeautifulSoup
from datetime import time

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

from openai import OpenAI

# ===== 環境變數 =====
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")

if not TOKEN or not OPENAI_API_KEY:
    raise ValueError("❌ 缺少必要環境變數")

# ===== 基本設定 =====
tz = pytz.timezone("Asia/Taipei")
client = OpenAI(api_key=OPENAI_API_KEY)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== 動態策略 =====
user_keywords = {}
user_sources = {}
user_topics = {}

# ===== Prompt =====
MARKETING_PROMPT = """
你是台灣「AI / 數位技能培訓」行銷專家（非升學補習班）。

目標族群：
- 上班族轉職
- AI技能學習者
- 想提升職場競爭力的人

產出內容要「可轉換」、「商業導向」、「實戰感」

禁止：
- 升學補習
- 考試導向

請輸出：

1️⃣ Facebook廣告文案（高轉換）
2️⃣ 招生文案
3️⃣ LINE短文案
4️⃣ 三個吸引標題
5️⃣ CTA（行動呼籲）
"""

# ===== 市場情報抓取 =====
def fetch_market_intel(chat_id):
    try:
        keyword = user_keywords.get(chat_id, "台灣 AI 培訓")
        source = user_sources.get(chat_id, "")

        query = f"{keyword} {source}"
        encoded = urllib.parse.quote(query)

        results = []

        headers = {"User-Agent": "Mozilla/5.0"}

        # ===== Google News =====
        news_url = f"https://news.google.com/rss/search?q={encoded}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(news_url)

        for entry in feed.entries[:3]:
            results.append(f"📰 {entry.title}")

        # ===== PTT =====
        try:
            ptt_url = f"https://www.ptt.cc/bbs/Soft_Job/search?q={encoded}"
            res = requests.get(ptt_url, headers=headers, timeout=5)

            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                titles = soup.select(".title a")

                for t in titles[:3]:
                    results.append(f"💬 PTT: {t.text.strip()}")
        except:
            pass

        # ===== Dcard =====
        try:
            dcard_url = f"https://www.dcard.tw/search?query={encoded}"
            res = requests.get(dcard_url, headers=headers, timeout=5)

            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                posts = soup.select("h2")

                for p in posts[:3]:
                    results.append(f"📱 Dcard: {p.text.strip()}")
        except:
            pass

        # ===== fallback =====
        if not results:
            results.append(f"{keyword} 市場趨勢")

        return "\n".join(results)

    except Exception as e:
        logger.error(f"Market intel error: {e}")
        return "市場資料取得失敗"

# ===== Notebook儲存 =====
def save_to_notebook(chat_id, content):
    try:
        topic = user_topics.get(chat_id, "AI行銷")
        today = datetime.datetime.now().strftime("%Y-%m-%d")

        filename = f"notebook_{topic}_{today}.txt"

        with open(filename, "a", encoding="utf-8") as f:
            f.write("\n\n====================\n")
            f.write(content)

        logger.info(f"Saved to {filename}")

    except Exception as e:
        logger.error(f"Notebook error: {e}")

# ===== AI文案生成 =====
def generate_marketing(chat_id):
    try:
        # ===== 取得市場資料 =====
        market_data, links = fetch_market_intel(chat_id)

        keyword = user_keywords.get(chat_id, "")
        source = user_sources.get(chat_id, "")

        # ===== 限制長度（避免 timeout）=====
        market_text = "\n".join(market_data)
        market_text = market_text[:1000]

        # ===== Prompt =====
        prompt = f"""
{MARKETING_PROMPT}

【市場情報】
{market_text}

【關鍵字】
{keyword}

【來源】
{source}

請產出：

1️⃣ Facebook廣告
2️⃣ 招生文案
3️⃣ LINE短文
4️⃣ 三個標題
5️⃣ CTA
6️⃣ 🎬 AI影音腳本（分鏡 + 字幕 + 語氣）

👉 市場機會
👉 競品差異
"""

        # ===== GPT 呼叫（加長 timeout）=====
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            timeout=60
        )

        result = response.choices[0].message.content

        # ===== 加回來源連結 =====
        if links:
            clean_links = [l.split("?")[0] for l in links]
            result += "\n\n📎 市場資料來源：\n" + "\n".join(clean_links)

        return result

    except Exception as e:
        logger.error(f"GPT error: {e}")

        # ===== fallback（避免整個壞掉）=====
        return "⚠️ 系統忙碌或資料過多，請稍後再試 /marketing"

# ===== 指令 =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    await update.message.reply_text(
        f"✅ OpenClaw v2.6 啟動\n\n"
        f"Chat ID：{chat_id}\n\n"
        "指令：\n"
        "/marketing\n"
        "/settime 09:00\n"
        "/setkeyword AI 課程 轉職\n"
        "/setsource 巨匠 Tibame\n"
        "/settopic AI市場"
    )

async def marketing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    await update.message.reply_text("📊 分析市場 + 產生文案中...")

    result = generate_marketing(chat_id)

    save_to_notebook(chat_id, result)

    await update.message.reply_text(result)

async def setkeyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = " ".join(context.args)

    user_keywords[chat_id] = text
    await update.message.reply_text(f"✅ 關鍵字：{text}")

async def setsource(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = " ".join(context.args)

    user_sources[chat_id] = text
    await update.message.reply_text(f"✅ 來源：{text}")

async def settopic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = " ".join(context.args)

    user_topics[chat_id] = text
    await update.message.reply_text(f"✅ Notebook主題：{text}")

async def settime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        text = context.args[0]

        hour, minute = map(int, text.split(":"))

        # 移除舊 job
        jobs = context.job_queue.get_jobs_by_name(str(chat_id))
        for job in jobs:
            job.schedule_removal()

        context.job_queue.run_daily(
            daily_push,
            time=time(hour=hour, minute=minute, tzinfo=tz),
            chat_id=chat_id,
            name=str(chat_id)
        )

        await update.message.reply_text(f"✅ 推播時間：{text}")

    except:
        await update.message.reply_text("❌ 格式錯誤 /settime 09:00")

# ===== 自動推播 =====
async def daily_push(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id

    result = generate_marketing(chat_id)

    save_to_notebook(chat_id, result)

    await context.bot.send_message(
        chat_id=chat_id,
        text="📢 每日市場文案\n\n" + result
    )

# ===== 主程式 =====
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("marketing", marketing))
    app.add_handler(CommandHandler("setkeyword", setkeyword))
    app.add_handler(CommandHandler("setsource", setsource))
    app.add_handler(CommandHandler("settopic", settopic))
    app.add_handler(CommandHandler("settime", settime))

    if TARGET_CHAT_ID:
        app.job_queue.run_daily(
            daily_push,
            time=time(hour=9, minute=0, tzinfo=tz),
            chat_id=int(TARGET_CHAT_ID),
            name="default"
        )

    app.run_polling()

if __name__ == "__main__":
    main()
