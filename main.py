import logging
import os
from datetime import time
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from skills.weather_skill import get_weather_report
from skills.ai_news_skill import get_ai_news_report
from skills.stock_skill import get_stock_report
from skills.server_monitor_skill import get_server_report
from skills.training_market_skill import get_training_market_report


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TIMEZONE = ZoneInfo("Asia/Taipei")


# =========================
# 基本訊息
# =========================
START_TEXT = """你好，我是 Tony's OpenClaw 助理。

我可以協助你處理 AI、SaaS、教育訓練、營運管理與流程自動化相關問題。

可使用以下指令：
/start - 啟動說明
/help - 查看功能說明
/enable_report - 啟動自動回報
/disable_report - 關閉自動回報
/report_now - 立即產生一次完整回報
/status - 查看目前自動回報狀態
"""

HELP_TEXT = """功能說明：

1. 自動回報內容包含：
- 天氣回報
- AI / 科技 / 股市新聞重點
- 伺服器狀況回報
- 台積電及 TSM ADR 股價
- 台灣補教 / 培訓市場情報
- Threads / Dcard 台灣培訓、補教相關熱點摘要

2. 自動回報排程：
- 08:00 伺服器狀況回報
- 08:30 天氣回報
- 08:45 AI / 科技 / 股市新聞重點
- 10:00 台灣補教 / 培訓市場情報
- 12:00 台積電及 TSM ADR 股價
- 15:00 台灣補教 / 培訓市場情報
- 20:00 伺服器狀況回報

3. 可手動執行：
/report_now
"""

REPORT_ENABLED_MESSAGE = """自動回報已啟動。

回報時間如下：
1. 天氣回報：每天上午 8:30
2. AI新聞、科技新聞、股市新聞重點：每天上午 8:45
3. 台灣補教 / 培訓市場情報：每天上午 10:00、下午 3:00
4. 台積電及 TSM ADR 股價：每天中午 12:00
5. 伺服器狀況回報：每天上午 8:00 和下午 8:00
"""

REPORT_DISABLED_MESSAGE = "自動回報已關閉。"


# =========================
# Skills Dispatcher
# =========================
async def send_weather_report(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    chat_id = job.chat_id
    text = get_weather_report()
    await context.bot.send_message(chat_id=chat_id, text=text)


async def send_ai_news_report(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    chat_id = job.chat_id
    text = get_ai_news_report()
    await context.bot.send_message(chat_id=chat_id, text=text)


async def send_stock_report(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    chat_id = job.chat_id
    text = get_stock_report()
    await context.bot.send_message(chat_id=chat_id, text=text)


async def send_server_report(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    chat_id = job.chat_id
    text = get_server_report()
    await context.bot.send_message(chat_id=chat_id, text=text)


async def send_training_market_report(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    chat_id = job.chat_id
    text = get_training_market_report()
    await context.bot.send_message(chat_id=chat_id, text=text)


# =========================
# 指令處理
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(START_TEXT)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    jobs = context.job_queue.get_jobs_by_name(str(chat_id))

    if not jobs:
        await update.message.reply_text(
            "目前尚未啟用自動回報。\n\n可使用 /enable_report 啟動。"
        )
        return

    status_text = """目前自動回報已啟用。

排程如下：
1. 天氣回報：每天上午 8:30
2. AI新聞、科技新聞、股市新聞重點：每天上午 8:45
3. 台灣補教 / 培訓市場情報：每天上午 10:00、下午 3:00
4. 台積電及 TSM ADR 股價：每天中午 12:00
5. 伺服器狀況回報：每天上午 8:00 與下午 8:00

目前此聊天室共有 {} 個排程工作。
""".format(len(jobs))

    await update.message.reply_text(status_text)


async def disable_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    jobs = context.job_queue.get_jobs_by_name(str(chat_id))

    removed_count = 0
    for job in jobs:
        job.schedule_removal()
        removed_count += 1

    await update.message.reply_text(
        f"{REPORT_DISABLED_MESSAGE}\n已移除 {removed_count} 個排程工作。"
    )


async def enable_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    logger.info("收到 /enable_report，chat_id=%s", chat_id)

    await update.message.reply_text("收到 /enable_report，正在設定自動回報...")

    # 先刪除舊排程，避免重複
    old_jobs = context.job_queue.get_jobs_by_name(str(chat_id))
    for job in old_jobs:
        job.schedule_removal()

    # 08:00 伺服器狀況
    context.job_queue.run_daily(
        send_server_report,
        time=time(hour=8, minute=0, tzinfo=BOT_TIMEZONE),
        chat_id=chat_id,
        name=str(chat_id),
    )

    # 08:30 天氣
    context.job_queue.run_daily(
        send_weather_report,
        time=time(hour=8, minute=30, tzinfo=BOT_TIMEZONE),
        chat_id=chat_id,
        name=str(chat_id),
    )

    # 08:45 AI / 科技 / 股市新聞
    context.job_queue.run_daily(
        send_ai_news_report,
        time=time(hour=8, minute=45, tzinfo=BOT_TIMEZONE),
        chat_id=chat_id,
        name=str(chat_id),
    )

    # 10:00 台灣補教 / 培訓市場情報
    context.job_queue.run_daily(
        send_training_market_report,
        time=time(hour=10, minute=0, tzinfo=BOT_TIMEZONE),
        chat_id=chat_id,
        name=str(chat_id),
    )

    # 12:00 台積電 / ADR 股價
    context.job_queue.run_daily(
        send_stock_report,
        time=time(hour=12, minute=0, tzinfo=BOT_TIMEZONE),
        chat_id=chat_id,
        name=str(chat_id),
    )

    # 15:00 台灣補教 / 培訓市場情報
    context.job_queue.run_daily(
        send_training_market_report,
        time=time(hour=15, minute=0, tzinfo=BOT_TIMEZONE),
        chat_id=chat_id,
        name=str(chat_id),
    )

    # 20:00 伺服器狀況
    context.job_queue.run_daily(
        send_server_report,
        time=time(hour=20, minute=0, tzinfo=BOT_TIMEZONE),
        chat_id=chat_id,
        name=str(chat_id),
    )

    await update.message.reply_text(REPORT_ENABLED_MESSAGE)
    logger.info("/enable_report 設定完成，chat_id=%s", chat_id)


async def report_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("收到 /report_now")
    await update.message.reply_text("收到 /report_now，正在產生測試回報，請稍候...")

    full_report = "\n\n".join(
        [
            get_weather_report(),
            get_ai_news_report(),
            get_server_report(),
            get_stock_report(),
            get_training_market_report(),
        ]
    )

    await update.message.reply_text(full_report)


# =========================
# 主程式
# =========================
def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("找不到 TELEGRAM_BOT_TOKEN，請先設定環境變數。")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("enable_report", enable_report))
    app.add_handler(CommandHandler("disable_report", disable_report))
    app.add_handler(CommandHandler("report_now", report_now))
    app.add_handler(CommandHandler("status", status))

    logger.info("Bot 啟動中，時區：%s", BOT_TIMEZONE)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()