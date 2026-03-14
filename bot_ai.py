import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from openai import OpenAI

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """
你是 Tony's OpenClaw AI 助理。
請使用繁體中文回答，風格要專業、親切、簡潔、清楚。

你的主要任務：
1. 協助回答 AI 導入、SaaS、教育訓練、企業流程自動化、營運管理相關問題
2. 協助整理需求、提供執行建議、規劃流程與下一步
3. 遇到不明確問題時，先幫使用者釐清需求
4. 不要捏造公司不存在的制度、價格、分校、方案或承諾
5. 若問題超出已知範圍，請明確說明並提供合理建議
6. 回答以實用為優先，避免空泛
"""

def ask_ai(user_text: str) -> str:
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
    )
    return response.output_text.strip()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "你好，我是 Tony's OpenClaw AI 助理。\n"
        "我可以協助你處理 AI、SaaS、教育訓練、營運管理與流程自動化相關問題。\n\n"
        "你可以直接輸入問題，或使用以下指令：\n"
        "/help - 查看功能說明\n"
        "/services - 查看服務項目\n"
        "/contact - 聯絡方式"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "可用功能如下：\n\n"
        "/start - 啟動機器人\n"
        "/help - 查看說明\n"
        "/services - 查看可協助項目\n"
        "/contact - 查看聯絡方式\n\n"
        "也可以直接輸入問題，例如：\n"
        "・幫我規劃 AI 客服 bot\n"
        "・如何導入 OpenClaw 到公司流程？\n"
        "・請整理教育訓練課程架構"
    )


async def services_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "目前可協助的項目包括：\n\n"
        "1. AI 導入規劃\n"
        "2. Telegram / LINE / Web AI Bot 設計\n"
        "3. SaaS 與 OpenClaw 應用建議\n"
        "4. 教育訓練課程與企劃整理\n"
        "5. 企業流程自動化建議\n"
        "6. 行政、營運、報表與管理流程優化"
    )


async def contact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "聯絡方式可依你的實際需求修改，例如：\n"
        "Email：service@yourcompany.com\n"
        "電話：02-1234-5678\n"
        "官方網站：www.yourcompany.com\n\n"
        "你可以把這段改成你自己的正式聯絡資訊。"
    )


async def reply_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    try:
        ai_reply = ask_ai(user_text)
        if not ai_reply:
            ai_reply = "我已收到你的訊息，但目前無法產生回覆，請稍後再試。"
        await update.message.reply_text(ai_reply)
    except Exception as e:
        await update.message.reply_text(f"系統發生錯誤，請稍後再試。\n錯誤訊息：{str(e)}")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print(f"發生錯誤: {context.error}")


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("請先設定 TELEGRAM_BOT_TOKEN")
    if not OPENAI_API_KEY:
        raise ValueError("請先設定 OPENAI_API_KEY")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("services", services_command))
    app.add_handler(CommandHandler("contact", contact_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply_message))

    app.add_error_handler(error_handler)

    print("Tony's OpenClaw AI 助理 已啟動...")
    app.run_polling()


if __name__ == "__main__":
    main()
