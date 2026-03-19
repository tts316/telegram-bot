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
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")

tz = pytz.timezone("Asia/Taipei")

client = OpenAI(api_key=OPENAI_API_KEY)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== NEWS =====
def fetch_news():
    try:
        keyword = urllib.parse.quote("台灣 AI 培訓 數位轉型")
        url = f"https://news.google.com/rss/search?q={keyword}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(url)

        news = [e.title for e in feed.entries[:5]]
        return "\n".join(news) if news else "AI培訓市場成長中"

    except Exception as e:
        logger.error(e)
        return "AI培訓市場持續成長"

# ===== MARKETING =====
def generate_marketing():
    try:
        news = fetch_news()

        prompt = f"""
你是台灣AI與數位技能培訓行銷專家。

根據以下市場資訊：
{news}

產出：
1. FB廣告文案
2. 招生文案
3. CTA

用繁體中文，強調就業與技能
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            timeout=20
        )

        return response.choices[0].message.content

    except Exception as e:
        logger.error(e)
        return f"❌ 產生失敗: {str(e)}"

# ===== COMMAND =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot 正常運行")

async def marketing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 產生中...")

    result = generate_marketing()

    await update.message.reply_text(result)

# ===== PUSH =====
async def daily_push(context: ContextTypes.DEFAULT_TYPE):
    try:
        result = generate_marketing()

        await context.bot.send_message(
            chat_id=int(TARGET_CHAT_ID),
            text="📢 每日文案\n\n" + result
        )
    except Exception as e:
        logger.error(e)

# ===== MAIN =====
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("marketing", marketing))

    app.job_queue.run_daily(
        daily_push,
        time=time(hour=17, minute=8, tzinfo=tz)
    )

    app.run_polling()

if __name__ == "__main__":
    main()
