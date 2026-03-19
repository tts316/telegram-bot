import os
import logging
import feedparser
import urllib.parse
import pytz
import requests
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
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")
LINE_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN 未設定")

if not OPENAI_API_KEY:
    raise ValueError("❌ OPENAI_API_KEY 未設定")

if not TARGET_CHAT_ID:
    raise ValueError("❌ TARGET_CHAT_ID 未設定")

# ===== 時區 =====
tz = pytz.timezone("Asia/Taipei")

# ===== OpenAI =====
client = OpenAI(api_key=OPENAI_API_KEY)

# ===== Logging =====
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== 行銷 Prompt（優化版）=====
MARKETING_PROMPT = """
你是台灣「電腦技能培訓 / AI職能教育」行銷專家（非升學補習班）。

目標客群：
- 上班族轉職
- 想學AI技能的人
- 想提升職場競爭力的人

請根據最新市場資訊，產出：

1️⃣ Facebook廣告文案（高轉換）
2️⃣ 招生文案（強調技能與就業）
3️⃣ LINE推播文（短版）
4️⃣ 3個吸引點標題
5️⃣ CTA

要求：
- 繁體中文
- 強調「技能 > 考試」
- 強調「就業 / 加薪 / 轉職」
- 不要出現升學補習內容
"""

# ===== 抓新聞（穩定版）=====
def fetch_news():
    try:
        keyword = "台灣 AI 培訓 數位轉型 職能教育"
        encoded = urllib.parse.quote(keyword)

        url = f"https://news.google.com/rss/search?q={encoded}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(url)

        news = [entry.title for entry in feed.entries[:5]]

        if not news:
            return "台灣AI培訓需求持續成長，企業加速數位轉型。"

        return "\n".join(news)

    except Exception as e:
        logger.error(f"RSS error: {e}")
        return "AI培訓市場持續成長，企業對數位技能需求增加。"

# ===== AI 問答 =====
def ask_ai(user_text: str) -> str:
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": user_text},
            ],
            timeout=25
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return f"⚠️ AI錯誤：{str(e)}"

# ===== 行銷文案生成（穩定+retry）=====
def generate_marketing():
    try:
        news = fetch_news()
        prompt = f"{MARKETING_PROMPT}\n\n市場資訊：\n{news}"

        for i in range(2):
            try:
                logger.info("🧠 呼叫 OpenAI")

                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    timeout=25
                )

                return response.choices[0].message.content

            except Exception as e:
                logger.warning(f"Retry {i}: {e}")

        return "⚠️ 系統忙碌，請稍後再試"

    except Exception as e:
        logger.error(f"Marketing error: {e}")
        return f"⚠️ 產生失敗：{str(e)}"

# ===== LINE 推播 =====
def send_line_message(text):
    if not LINE_TOKEN:
        logger.warning("LINE_TOKEN 未設定，略過 LINE 推播")
        return

    try:
        url = "https://api.line.me/v2/bot/message/broadcast"

        headers = {
            "Authorization": f"Bearer {LINE_TOKEN}",
            "Content-Type": "application/json"
        }

        data = {
            "messages": [
                {"type": "text", "text": text[:5000]}
            ]
        }

        requests.post(url, headers=headers, json=data)

    except Exception as e:
        logger.error(f"LINE error: {e}")

# ===== 指令 =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    await update.message.reply_text(
        f"🤖 OpenClaw AI 助理已啟動\n\n你的 Chat ID：{chat_id}"
    )

async def marketing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 產生今日行銷文案中...")

    result = generate_marketing()

    await update.message.reply_text(result)

# ===== 一般聊天 =====
async def reply_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    reply = ask_ai(user_text)
    await update.message.reply_text(reply)

# ===== 每日推播 =====
async def daily_push(context: ContextTypes.DEFAULT_TYPE):
    logger.info("⏰ 每日推播執行")

    result = generate_marketing()

    # Telegram
    await context.bot.send_message(
        chat_id=int(TARGET_CHAT_ID),
        text="📢 每日行銷文案\n\n" + result
    )

    # LINE
    send_line_message("📢 每日行銷文案\n\n" + result)

# ===== 主程式 =====
def main():
    logger.info("🚀 Bot starting...")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("marketing", marketing))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply_message))

    # 每日 09:00 台灣時間
    app.job_queue.run_daily(
        daily_push,
        time=time(hour=9, minute=0, tzinfo=tz)
    )

    logger.info("✅ Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()