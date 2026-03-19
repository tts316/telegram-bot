import os
import logging
import feedparser
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

# ===== 環境變數 =====
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN 未設定")

if not OPENAI_API_KEY:
    raise ValueError("❌ OPENAI_API_KEY 未設定")

# 👉 設定你的 Telegram Chat ID（很重要）
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")

# ===== OpenAI =====
client = OpenAI(api_key=OPENAI_API_KEY)

# ===== Logging =====
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== 抓新聞 =====
def fetch_news():
    url = "https://news.google.com/rss/search?q=台灣 補教 培訓 AI 教育&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    feed = feedparser.parse(url)

    news = []
    for entry in feed.entries[:5]:
        news.append(entry.title)

    return "\n".join(news)

# ===== 產生廣告文案 =====
def generate_marketing():
    news = fetch_news()

    prompt = f"""
你是一位台灣頂級補教產業行銷顧問。

請根據以下最新市場資訊：

{news}

產出：
1️⃣ Facebook廣告文案
2️⃣ 招生文案
3️⃣ 3個吸引標題
4️⃣ CTA

要求：
- 繁體中文
- 高轉換
- 貼近台灣市場
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )

    return response.choices[0].message.content

# ===== 指令 =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    await update.message.reply_text(
        "🤖 OpenClaw AI 助理已啟動\n\n"
        f"你的 Chat ID：{chat_id}\n"
        "👉 請把這個 ID 設到 Zeabur 環境變數 TARGET_CHAT_ID"
    )

async def marketing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 產生今日行銷文案中...")

    result = generate_marketing()

    await update.message.reply_text(result)

# ===== 自動推播 =====
async def daily_push(context: ContextTypes.DEFAULT_TYPE):
    logger.info("⏰ 執行每日推播")

    result = generate_marketing()

    await context.bot.send_message(
        chat_id=TARGET_CHAT_ID,
        text="📢 每日行銷文案\n\n" + result
    )

# ===== 主程式 =====
def main():
    logger.info("🚀 Bot starting...")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # 指令
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("marketing", marketing))

    # 排程（每天09:00）
    app.job_queue.run_daily(
        daily_push,
        time=time(hour=9, minute=0)
    )

    logger.info("✅ Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()