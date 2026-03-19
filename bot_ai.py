import os
import logging
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

# ===== AI 呼叫（穩定版）=====
def ask_ai(user_text: str) -> str:
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",   # ✅ 最穩模型
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            temperature=0.7,
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"OpenAI Error: {e}")
        return f"⚠️ AI錯誤：{str(e)}"


# ===== 指令 =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Tony's OpenClaw AI 助理 已啟動\n\n"
        "我可以協助：\n"
        "・AI 導入\n"
        "・SaaS 系統\n"
        "・教育訓練\n"
        "・營運流程優化\n\n"
        "請直接輸入問題 👇"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 指令：\n"
        "/start\n/help\n"
        "或直接輸入問題"
    )


# ===== 訊息處理 =====
async def reply_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    logger.info(f"User: {user_text}")

    reply = ask_ai(user_text)

    logger.info(f"AI: {reply}")
    await update.message.reply_text(reply)


# ===== 錯誤處理 =====
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"❌ Exception: {context.error}")


# ===== 主程式 =====
def main():
    logger.info("🚀 Bot starting...")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply_message))

    app.add_error_handler(error_handler)

    logger.info("✅ Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()