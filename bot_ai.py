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

# ===== OpenAI Client =====
client = OpenAI(api_key=OPENAI_API_KEY)

# ===== Logging（Zeabur Debug 很重要）=====
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# ===== AI 系統設定 =====
SYSTEM_PROMPT = """
你是 Tony's OpenClaw AI 助理。

請使用繁體中文回答，風格需：
- 專業
- 簡潔
- 實用導向

你的任務：
1. 協助 AI 導入、SaaS、教育訓練、企業流程自動化
2. 提供可執行建議（不要空泛）
3. 若資訊不足，主動詢問補充
4. 不可捏造資訊
"""

# ===== AI 回覆 =====
def ask_ai(user_text: str) -> str:
    try:
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
        )

        return response.output_text.strip()

    except Exception as e:
        logger.error(f"OpenAI Error: {e}")
        return "⚠️ AI 服務暫時無法使用，請稍後再試"


# ===== 指令區 =====

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
        "📌 可用指令：\n\n"
        "/start - 啟動機器人\n"
        "/help - 查看說明\n"
        "/services - 服務項目\n"
        "/contact - 聯絡資訊\n\n"
        "或直接輸入問題即可"
    )


async def services_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧠 OpenClaw 可協助：\n\n"
        "1️⃣ AI 客服 / Bot 建置\n"
        "2️⃣ SaaS 系統設計\n"
        "3️⃣ 教育訓練課程規劃\n"
        "4️⃣ 企業流程自動化\n"
        "5️⃣ 營運與管理優化"
    )


async def contact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📞 聯絡方式：\n\n"
        "Email：service@yourcompany.com\n"
        "電話：02-1234-5678\n"
        "（請自行替換成正式資訊）"
    )


# ===== 一般訊息（AI回覆）=====
async def reply_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    logger.info(f"User: {user_text}")

    ai_reply = ask_ai(user_text)

    logger.info(f"AI: {ai_reply}")

    await update.message.reply_text(ai_reply)


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
    app.add_handler(CommandHandler("services", services_command))
    app.add_handler(CommandHandler("contact", contact_command))

    # 一般訊息
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply_message))

    # 錯誤處理
    app.add_error_handler(error_handler)

    logger.info("✅ Bot is running...")

    app.run_polling()


if __name__ == "__main__":
    main()
