import traceback
from datetime import time
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from skills.config import TELEGRAM_BOT_TOKEN, REPORT_MAX_CHARS
from skills.logger_util import setup_logger
from skills.weather_skill import get_weather_report
from skills.ai_news_skill import get_ai_news_report
from skills.stock_skill import get_stock_report
from skills.server_monitor_skill import get_server_monitor_report
from skills.training_market_skill import get_training_market_report

logger = setup_logger("openclaw")
TAIWAN_TZ = ZoneInfo("Asia/Taipei")
chat_jobs = {}


def clamp_text(text: str, max_chars: int = REPORT_MAX_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n（內容過長，已自動截斷）"


def build_full_report() -> str:
    sections = [
        get_weather_report(),
        get_ai_news_report(),
        get_server_monitor_report(),
        get_stock_report(),
        get_training_market_report(),
    ]
    return clamp_text("今日企業助理回報\n\n" + "\n\n".join(sections))


async def safe_send(chat_id: int, bot, text: str):
    try:
        await bot.send_message(chat_id=chat_id, text=clamp_text(text))
    except Exception as e:
        logger.error(f"send_message failed chat_id={chat_id}, error={e}")
        logger.error(traceback.format_exc())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Tony,s OpenClaw 助理已啟動。\n\n"
        "可使用以下指令：\n"
        "/start - 啟動說明\n"
        "/help - 查看功能說明\n"
        "/enable_report - 啟動自動回報\n"
        "/disable_report - 關閉自動回報\n"
        "/report_now - 立即產生一次完整回報\n"
        "/status - 查看目前自動回報狀態\n"
        "/test_weather - 測試天氣模組\n"
        "/test_stock - 測試股價模組\n"
        "/test_training - 測試補教/培訓情報模組"
    )
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def report_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("收到 /report_now，正在產生完整回報，請稍候...")
    await update.message.reply_text(build_full_report())


async def test_weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_weather_report())


async def test_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_stock_report())


async def test_training(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(clamp_text(get_training_market_report()))


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    jobs = chat_jobs.get(chat_id, [])

    if not jobs:
        await update.message.reply_text("目前尚未啟用自動回報。\n\n可使用 /enable_report 啟動。")
        return

    text = (
        "目前自動回報已啟用。\n\n"
        "排程如下：\n"
        "1. 天氣回報：每天上午 8:30\n"
        "2. AI新聞、科技新聞、股市新聞重點：每天上午 8:45\n"
        "3. 台灣補教 / 培訓市場情報：每天上午 10:00、下午 3:00\n"
        "4. 台積電及 TSM ADR 股價：每天中午 12:00\n"
        "5. 伺服器狀況回報：每天上午 8:00 與下午 8:00\n\n"
        f"目前此聊天室共有 {len(jobs)} 個排程工作。"
    )
    await update.message.reply_text(text)


async def send_weather_report(context: ContextTypes.DEFAULT_TYPE):
    await safe_send(context.job.chat_id, context.bot, get_weather_report())


async def send_ai_news_report(context: ContextTypes.DEFAULT_TYPE):
    await safe_send(context.job.chat_id, context.bot, get_ai_news_report())


async def send_server_report(context: ContextTypes.DEFAULT_TYPE):
    await safe_send(context.job.chat_id, context.bot, get_server_monitor_report())


async def send_stock_report(context: ContextTypes.DEFAULT_TYPE):
    await safe_send(context.job.chat_id, context.bot, get_stock_report())


async def send_training_market_report(context: ContextTypes.DEFAULT_TYPE):
    await safe_send(context.job.chat_id, context.bot, get_training_market_report())


async def enable_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text("收到 /enable_report，正在設定自動回報...")

    old_jobs = chat_jobs.get(chat_id, [])
    for job in old_jobs:
        job.schedule_removal()

    jobs = []

    jobs.append(context.job_queue.run_daily(send_server_report, time=time(8, 0, tzinfo=TAIWAN_TZ), chat_id=chat_id, name=f"{chat_id}_server_am"))
    jobs.append(context.job_queue.run_daily(send_weather_report, time=time(8, 30, tzinfo=TAIWAN_TZ), chat_id=chat_id, name=f"{chat_id}_weather"))
    jobs.append(context.job_queue.run_daily(send_ai_news_report, time=time(8, 45, tzinfo=TAIWAN_TZ), chat_id=chat_id, name=f"{chat_id}_ai_news"))
    jobs.append(context.job_queue.run_daily(send_training_market_report, time=time(10, 0, tzinfo=TAIWAN_TZ), chat_id=chat_id, name=f"{chat_id}_training_am"))
    jobs.append(context.job_queue.run_daily(send_stock_report, time=time(12, 0, tzinfo=TAIWAN_TZ), chat_id=chat_id, name=f"{chat_id}_stock"))
    jobs.append(context.job_queue.run_daily(send_training_market_report, time=time(15, 0, tzinfo=TAIWAN_TZ), chat_id=chat_id, name=f"{chat_id}_training_pm"))
    jobs.append(context.job_queue.run_daily(send_server_report, time=time(20, 0, tzinfo=TAIWAN_TZ), chat_id=chat_id, name=f"{chat_id}_server_pm"))

    chat_jobs[chat_id] = jobs

    await update.message.reply_text(
        "自動回報已啟動。\n\n"
        "回報時間如下：\n"
        "1. 天氣回報：每天上午 8:30\n"
        "2. AI新聞、科技新聞、股市新聞重點：每天上午 8:45\n"
        "3. 台灣補教 / 培訓市場情報：每天上午 10:00、下午 3:00\n"
        "4. 台積電及 TSM ADR 股價：每天中午 12:00\n"
        "5. 伺服器狀況回報：每天上午 8:00 和下午 8:00"
    )


async def disable_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    jobs = chat_jobs.get(chat_id, [])
    removed = 0

    for job in jobs:
        job.schedule_removal()
        removed += 1

    chat_jobs[chat_id] = []
    await update.message.reply_text(f"自動回報已關閉。\n已移除 {removed} 個排程工作。")


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("未設定 TELEGRAM_BOT_TOKEN")

    logger.info("OpenClaw v2.2 starting...")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("enable_report", enable_report))
    app.add_handler(CommandHandler("disable_report", disable_report))
    app.add_handler(CommandHandler("report_now", report_now))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("test_weather", test_weather))
    app.add_handler(CommandHandler("test_stock", test_stock))
    app.add_handler(CommandHandler("test_training", test_training))

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()