import os
import logging
import feedparser
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

# ===== 環境變數 =====
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")

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

# ===== 系統提示 =====
SYSTEM_PROMPT = """
你是 Tony's OpenClaw AI 助理。

請使用繁體中文回答，並符合：
- 專業
- 精簡
- 可執行

優先提供：
1. 商業建議
2. AI導入策略
3. 培訓與市場分析
"""

# ===== 抓新聞 =====
import urllib.parse

def fetch_news():
    keyword = "台灣 補教 培訓 AI 教育"
    
    encoded_keyword = urllib.parse.quote(keyword)

    url = f"https://news.google.com/rss/search?q={encoded_keyword}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"

    feed = feedparser.parse(url)

    news = []
    for entry in feed.entries[:5]:
        news.append(entry.title)

    return "\n".join(news)

# ===== AI 回答 =====
def ask_ai(user_text: str) -> str:
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"OpenAI Error: {e}")
        return f"⚠️ AI錯誤：{str(e)}"

# ===== 產生廣告文案 =====
def generate_marketing():
    try:
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
"""

        logger.info("🧠 呼叫 OpenAI...")

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            timeout=30  # 🔥 關鍵（避免卡死）
        )

        result = response.choices[0].message.content

        logger.info("✅ OpenAI 回應完成")

        return result

    except Exception as e:
        logger.error(f"❌ generate_marketing error: {e}")
        return f"⚠️ 產生文案失敗：{str(e)}"

# ===== 指令 =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    await update.message.reply_text(
        "🤖 OpenClaw AI 助理已啟動\n\n"
        f"你的 Chat ID：{chat_id}\n"
        "👉 請確認已設定 TARGET_CHAT_ID"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 指令：\n"
        "/start\n"
        "/marketing\n"
        "或直接輸入問題"
    )


async def marketing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 產生今日行銷文案中...")

    result = generate_marketing()

    await update.message.reply_text(result)


# ===== 訊息處理 =====
async def reply_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    logger.info(f"User: {user_text}")

    reply = ask_ai(user_text)

    logger.info(f"AI: {reply}")

    await update.message.reply_text(reply)


# ===== 自動推播 =====
async def daily_push(context: ContextTypes.DEFAULT_TYPE):
    logger.info("⏰ 執行每日推播")

    try:
        result = generate_marketing()

        await context.bot.send_message(
            chat_id=TARGET_CHAT_ID,
            text="📢 每日行銷文案\n\n" + result
        )

    except Exception as e:
        logger.error(f"推播錯誤: {e}")


# ===== 錯誤處理 =====
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"❌ Exception: {context.error}")


# ===== 主程式 =====
def main():
    logger.info("🚀 Bot starting...")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # 指令
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("marketing", marketing))

    # 訊息
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply_message))

    # 錯誤
    app.add_error_handler(error_handler)

    # ===== 每日 09:00 台灣時間 =====
    app.job_queue.run_daily(
        daily_push,
        time=time(hour=9, minute=0, tzinfo=tz)
    )

    logger.info("✅ Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
