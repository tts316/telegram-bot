import os
import logging
import feedparser
import urllib.parse
import pytz
from datetime import time

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from openai import OpenAI

# ===== ENV =====
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TOKEN or not OPENAI_API_KEY:
    raise ValueError("❌ 缺少環境變數")

# ===== 基本設定 =====
tz = pytz.timezone("Asia/Taipei")
client = OpenAI(api_key=OPENAI_API_KEY)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== 行銷 Prompt =====
MARKETING_PROMPT = """
你是台灣「AI / 數位技能培訓」行銷專家（非升學補習班）。

目標族群：
- 上班族轉職
- AI技能學習者
- 想提升職場競爭力的人

請產出：

1️⃣ Facebook廣告文案（高轉換）
2️⃣ 招生文案（強調就業/技能）
3️⃣ LINE短文案
4️⃣ 3個吸引標題
5️⃣ CTA

⚠️ 不要出現升學補習內容
"""

# ===== 抓新聞 =====
def fetch_news():
    try:
        keyword = urllib.parse.quote("台灣 AI 培訓 數位轉型 職能教育")
        url = f"https://news.google.com/rss/search?q={keyword}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"

        feed = feedparser.parse(url)

        news_list = []
        for entry in feed.entries[:5]:
            news_list.append({
                "title": entry.title,
                "link": entry.link
            })

        return news_list

    except Exception as e:
        logger.error(f"RSS error: {e}")
        return []

# ===== 產生文案 =====
def generate_marketing():
    try:
        news_data = fetch_news()

        if not news_data:
            news_text = "AI培訓市場持續成長"
            links_text = ""
        else:
            news_text = "\n".join([n["title"] for n in news_data])
            links_text = "\n".join([n["link"] for n in news_data])

        prompt = f"""
{MARKETING_PROMPT}

市場資訊：
{news_text}

另外請產出：

🎬 AI影音生成提示詞：
- 30秒短影片
- 分鏡腳本
- 字幕內容
- 配音語氣
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            timeout=25
        )

        result = response.choices[0].message.content

        # 加上來源
        if links_text:
            result += "\n\n📎 市場資料來源：\n" + links_text

        return result

    except Exception as e:
        logger.error(f"Marketing error: {e}")
        return f"❌ 產生失敗：{str(e)}"

# ===== 指令 =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ OpenClaw 已啟動\n\n"
        "指令：\n"
        "/marketing → 產生文案\n"
        "/settime 09:00 → 設定每日推播"
    )

# ===== 手動文案 =====
async def marketing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 產生中...")

    result = generate_marketing()

    await update.message.reply_text(result)

# ===== 設定時間 =====
async def settime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        text = context.args[0]

        hour, minute = map(int, text.split(":"))

        # 移除舊排程
        jobs = context.job_queue.get_jobs_by_name(str(chat_id))
        for job in jobs:
            job.schedule_removal()

        # 建立新排程
        context.job_queue.run_daily(
            daily_push,
            time=time(hour=hour, minute=minute, tzinfo=tz),
            chat_id=chat_id,
            name=str(chat_id)
        )

        await update.message.reply_text(f"✅ 推播時間設定為 {text}")

    except:
        await update.message.reply_text("❌ 格式錯誤：/settime 09:30")

# ===== 推播 =====
async def daily_push(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id

    result = generate_marketing()

    await context.bot.send_message(
        chat_id=chat_id,
        text="📢 每日行銷文案\n\n" + result
    )

# ===== MAIN =====
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("marketing", marketing))
    app.add_handler(CommandHandler("settime", settime))

    # 預設排程（防止沒設定）
    app.job_queue.run_daily(
        daily_push,
        time=time(hour=9, minute=0, tzinfo=tz),
        chat_id=int(os.getenv("TARGET_CHAT_ID", "0")),
        name="default"
    )

    app.run_polling()

if __name__ == "__main__":
    main()