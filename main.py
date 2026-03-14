import os
import logging
from datetime import time
from zoneinfo import ZoneInfo

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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

TW_TZ = ZoneInfo("Asia/Taipei")

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

REPORT_SYSTEM_PROMPT = """
你是 Tony's OpenClaw AI 助理，請用繁體中文產出簡潔、可讀性高的每日回報內容。
若無法取得真實即時資料，請明確寫出「目前未串接即時資料來源，以下為示意摘要」。
避免捏造精確數字、即時股價、即時天氣、即時新聞標題或伺服器狀態。
"""

def ask_ai(user_text: str, system_prompt: str = SYSTEM_PROMPT) -> str:
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
    )
    return response.output_text.strip()

def remove_existing_jobs(job_queue, prefix: str) -> int:
    current_jobs = job_queue.get_jobs_by_name(prefix)
    for job in current_jobs:
        job.schedule_removal()
    return len(current_jobs)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "你好，我是 Tony's OpenClaw AI 助理。\n"
        "你可以直接輸入問題，或使用以下指令：\n"
        "/help - 查看功能說明\n"
        "/services - 查看服務項目\n"
        "/contact - 聯絡方式\n"
        "/myid - 查看目前 chat_id\n"
        "/enable_report - 啟動自動回報\n"
        "/disable_report - 停止自動回報\n"
        "/report_now - 立即測試回報"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "可用功能如下：\n\n"
        "/start - 啟動機器人\n"
        "/help - 查看說明\n"
        "/services - 查看可協助項目\n"
        "/contact - 查看聯絡方式\n"
        "/myid - 查看 chat_id\n"
        "/enable_report - 啟動每日自動回報\n"
        "/disable_report - 停止每日自動回報\n"
        "/report_now - 立即測試一次回報\n\n"
        "你也可以直接輸入問題，例如：\n"
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
        "聯絡方式：\n"
        "Email：service@yourcompany.com\n"
        "電話：02-2772-3696\n"
        "官方網站：www.lccnet.comtw\n\n"
    )

async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"你的 chat_id 是：{update.effective_chat.id}")

async def generate_full_report() -> str:
    prompt = """
請依照以下格式，用繁體中文產出一份「今日自動回報」：

1. 天氣回報
2. AI新聞、科技新聞、股市新聞重點
3. 伺服器狀況回報
4. 台積電及 TSM ADR 股價

規則：
- 若無法取得真實即時資料，請明確寫出目前未串接即時資料來源
- 不要捏造精確數字
- 內容簡潔、條列清楚
- 最後補一句：若需改成正式串接即時資料，可再擴充 API
"""
    return ask_ai(prompt, REPORT_SYSTEM_PROMPT)

async def send_report(chat_id: int, context: ContextTypes.DEFAULT_TYPE, title: str):
    try:
        report_text = await generate_full_report()
        message = f"{title}\n\n{report_text}"
        await context.bot.send_message(chat_id=chat_id, text=message)
    except Exception as e:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{title}\n\n系統發生錯誤，暫時無法產生回報。\n錯誤訊息：{str(e)}"
        )

async def weather_report(context: ContextTypes.DEFAULT_TYPE):
    await send_report(context.job.chat_id, context, "【08:30 天氣回報】")

async def news_report(context: ContextTypes.DEFAULT_TYPE):
    await send_report(context.job.chat_id, context, "【08:45 AI / 科技 / 股市新聞重點】")

async def server_report(context: ContextTypes.DEFAULT_TYPE):
    now_hour = context.job.data.get("hour_label", "")
    await send_report(context.job.chat_id, context, f"【{now_hour} 伺服器狀況回報】")

async def stock_report(context: ContextTypes.DEFAULT_TYPE):
    await send_report(context.job.chat_id, context, "【11:55 台積電 / TSM ADR 股價回報】")

async def enable_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    job_prefix = f"report_{chat_id}"

    removed_count = remove_existing_jobs(context.job_queue, job_prefix)

    context.job_queue.run_daily(
        weather_report,
        time=time(hour=8, minute=30, tzinfo=TW_TZ),
        chat_id=chat_id,
        name=job_prefix,
    )
    context.job_queue.run_daily(
        news_report,
        time=time(hour=8, minute=45, tzinfo=TW_TZ),
        chat_id=chat_id,
        name=job_prefix,
    )
    context.job_queue.run_daily(
        server_report,
        time=time(hour=8, minute=0, tzinfo=TW_TZ),
        chat_id=chat_id,
        name=job_prefix,
        data={"hour_label": "08:00"},
    )
    context.job_queue.run_daily(
        server_report,
        time=time(hour=20, minute=0, tzinfo=TW_TZ),
        chat_id=chat_id,
        name=job_prefix,
        data={"hour_label": "20:00"},
    )
    context.job_queue.run_daily(
        stock_report,
        time=time(hour=11, minute=55, tzinfo=TW_TZ),
        chat_id=chat_id,
        name=job_prefix,
    )

    await update.message.reply_text(
        "已啟動自動回報。\n\n"
        "目前排程如下：\n"
        "1. 天氣回報：每天上午 08:30\n"
        "2. AI / 科技 / 股市新聞：每天上午 08:45\n"
        "3. 伺服器狀況：每天上午 08:00、下午 08:00\n"
        "4. 台積電 / TSM ADR 股價：每天上午 11:55\n\n"
        f"已清除舊排程數量：{removed_count}"
    )

async def disable_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    job_prefix = f"report_{chat_id}"
    removed_count = remove_existing_jobs(context.job_queue, job_prefix)

    await update.message.reply_text(
        f"已停止自動回報。\n已移除排程數量：{removed_count}"
    )

async def report_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text("正在產生測試回報，請稍候...")
    await send_report(chat_id, context, "【立即測試回報】")

async def reply_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    try:
        ai_reply = ask_ai(user_text)
        if not ai_reply:
            ai_reply = "我已收到你的訊息，但目前無法產生回覆，請稍後再試。"
        await update.message.reply_text(ai_reply)
    except Exception as e:
        await update.message.reply_text(
            f"系統發生錯誤，請稍後再試。\n錯誤訊息：{str(e)}"
        )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error("發生錯誤: %s", context.error)

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
    app.add_handler(CommandHandler("myid", myid_command))
    app.add_handler(CommandHandler("enable_report", enable_report))
    app.add_handler(CommandHandler("disable_report", disable_report))
    app.add_handler(CommandHandler("report_now", report_now))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply_message))

    app.add_error_handler(error_handler)

    print("Tony's OpenClaw AI 助理 已啟動...")
    app.run_polling()

if __name__ == "__main__":
    main()