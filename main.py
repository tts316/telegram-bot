import os
import logging
from datetime import datetime
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# =========================
# 基本設定
# =========================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# 台灣時區字串，給 JobQueue 使用
TZ = "Asia/Taipei"

# Job 名稱
JOB_WEATHER = "daily_weather_report"
JOB_NEWS = "daily_news_report"
JOB_SERVER = "daily_server_report"
JOB_STOCK = "daily_stock_report"


# =========================
# 資料取得區（目前先用穩定示範版）
# 之後可替換成真實 API
# =========================

def get_weather_report() -> str:
    """
    之後可改成串接中央氣象署或其他天氣 API
    """
    return (
        "1. 天氣回報\n"
        "今天天氣晴朗，氣溫約 25～30 度，適合戶外活動。"
        "整體天氣穩定，暫無明顯降雨訊號。"
    )


def get_news_report() -> str:
    """
    之後可改成串接新聞 API / RSS
    """
    return (
        "2. AI新聞、科技新聞、股市新聞重點\n"
        "- AI新聞：目前 AI 應用持續擴展，企業導入自動化與知識助理的需求升高。\n"
        "- 科技新聞：雲端服務、AI 晶片與企業軟體整合仍是市場焦點。\n"
        "- 股市新聞：科技股表現仍受利率、市場情緒與大型權值股帶動。"
    )


def get_server_report() -> str:
    """
    之後可改成串接 Zeabur API / 健康檢查端點 / 自訂監控
    """
    return (
        "3. 伺服器狀況回報\n"
        "目前伺服器運作正常，未偵測到異常警報。"
        "若需進一步監控 CPU、記憶體、磁碟與服務健康狀態，可再串接監控 API。"
    )


def get_stock_report() -> str:
    """
    之後可改成串接股票 API
    """
    return (
        "4. 台積電及 TSM ADR 股價\n"
        "目前為示範資料模式，尚未串接即時股價來源。\n"
        "可於下一版接入台股與 ADR 報價 API。"
    )


def build_full_report() -> str:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report = (
        f"今日企業助理回報\n"
        f"回報時間：{now_str}\n\n"
        f"{get_weather_report()}\n\n"
        f"{get_news_report()}\n\n"
        f"{get_server_report()}\n\n"
        f"{get_stock_report()}"
    )
    return report


# =========================
# 排程工作
# =========================

async def send_weather_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    try:
        msg = get_weather_report()
        logger.info(f"發送天氣回報，chat_id={chat_id}")
        await context.bot.send_message(chat_id=chat_id, text=msg)
    except Exception as e:
        logger.exception("send_weather_job 發生錯誤")
        await context.bot.send_message(chat_id=chat_id, text=f"天氣回報發生錯誤：{e}")


async def send_news_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    try:
        msg = get_news_report()
        logger.info(f"發送新聞回報，chat_id={chat_id}")
        await context.bot.send_message(chat_id=chat_id, text=msg)
    except Exception as e:
        logger.exception("send_news_job 發生錯誤")
        await context.bot.send_message(chat_id=chat_id, text=f"新聞回報發生錯誤：{e}")


async def send_server_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    try:
        msg = get_server_report()
        logger.info(f"發送伺服器回報，chat_id={chat_id}")
        await context.bot.send_message(chat_id=chat_id, text=msg)
    except Exception as e:
        logger.exception("send_server_job 發生錯誤")
        await context.bot.send_message(chat_id=chat_id, text=f"伺服器回報發生錯誤：{e}")


async def send_stock_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    try:
        msg = get_stock_report()
        logger.info(f"發送股價回報，chat_id={chat_id}")
        await context.bot.send_message(chat_id=chat_id, text=msg)
    except Exception as e:
        logger.exception("send_stock_job 發生錯誤")
        await context.bot.send_message(chat_id=chat_id, text=f"股價回報發生錯誤：{e}")


# =========================
# 工具函式
# =========================

def remove_existing_jobs(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> int:
    current_jobs = context.job_queue.jobs()
    removed = 0

    for job in current_jobs:
        if job.chat_id == chat_id:
            job.schedule_removal()
            removed += 1

    return removed


def get_chat_jobs(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    return [job for job in context.job_queue.jobs() if job.chat_id == chat_id]


def build_status_text(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> str:
    jobs = get_chat_jobs(context, chat_id)

    if not jobs:
        return (
            "目前尚未啟用自動回報。\n\n"
            "可使用 /enable_report 啟動。"
        )

    return (
        "目前自動回報已啟用。\n\n"
        "排程如下：\n"
        "1. 天氣回報：每天上午 8:30\n"
        "2. AI新聞、科技新聞、股市新聞重點：每天上午 8:45\n"
        "3. 伺服器狀況回報：每天上午 8:00 與下午 8:00\n"
        "4. 台積電及 TSM ADR 股價：每天中午 12:00\n\n"
        f"目前此聊天室共有 {len(jobs)} 個排程工作。"
    )


# =========================
# 指令 handlers
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "你好，我是 Tony's OpenClaw AI 助理。\n"
        "我可以協助你處理 AI、SaaS、教育訓練、營運管理與流程自動化相關問題。\n\n"
        "可使用以下指令：\n"
        "/start - 啟動說明\n"
        "/help - 查看功能說明\n"
        "/enable_report - 啟動自動回報\n"
        "/disable_report - 關閉自動回報\n"
        "/report_now - 立即產生一次完整回報\n"
        "/status - 查看目前自動回報狀態"
    )
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "功能說明：\n\n"
        "/enable_report\n"
        "- 啟動每日自動回報\n\n"
        "/disable_report\n"
        "- 關閉目前聊天室的所有自動回報\n\n"
        "/report_now\n"
        "- 立即測試一次完整回報\n\n"
        "/status\n"
        "- 查看目前是否已啟動排程"
    )
    await update.message.reply_text(text)


async def enable_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        logger.info(f"收到 /enable_report，chat_id={chat_id}")

        await update.message.reply_text("收到 /enable_report，正在設定自動回報...")

        # 先移除舊排程，避免重複
        removed = remove_existing_jobs(context, chat_id)
        logger.info(f"已移除舊排程 {removed} 個，chat_id={chat_id}")

        # 每天 08:30 天氣
        context.job_queue.run_daily(
            send_weather_job,
            time=datetime.strptime("08:30", "%H:%M").time(),
            chat_id=chat_id,
            name=JOB_WEATHER,
        )

        # 每天 08:45 新聞
        context.job_queue.run_daily(
            send_news_job,
            time=datetime.strptime("08:45", "%H:%M").time(),
            chat_id=chat_id,
            name=JOB_NEWS,
        )

        # 每天 08:00 伺服器
        context.job_queue.run_daily(
            send_server_job,
            time=datetime.strptime("08:00", "%H:%M").time(),
            chat_id=chat_id,
            name=f"{JOB_SERVER}_morning",
        )

        # 每天 20:00 伺服器
        context.job_queue.run_daily(
            send_server_job,
            time=datetime.strptime("20:00", "%H:%M").time(),
            chat_id=chat_id,
            name=f"{JOB_SERVER}_evening",
        )

        # 每天 12:00 股價
        context.job_queue.run_daily(
            send_stock_job,
            time=datetime.strptime("12:00", "%H:%M").time(),
            chat_id=chat_id,
            name=JOB_STOCK,
        )

        logger.info(f"/enable_report 設定完成，chat_id={chat_id}")

        await update.message.reply_text(
            "自動回報已啟動。\n\n"
            "回報時間如下：\n"
            "1. 天氣回報：每天上午 8:30\n"
            "2. AI新聞、科技新聞、股市新聞重點：每天上午 8:45\n"
            "3. 伺服器狀況回報：每天上午 8:00 和下午 8:00\n"
            "4. 台積電及 TSM ADR 股價：每天中午 12:00"
        )
    except Exception as e:
        logger.exception("enable_report 發生錯誤")
        await update.message.reply_text(f"enable_report 發生錯誤：{e}")


async def disable_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        logger.info(f"收到 /disable_report，chat_id={chat_id}")

        removed = remove_existing_jobs(context, chat_id)

        await update.message.reply_text(
            f"自動回報已關閉。\n"
            f"本次共移除 {removed} 個排程。"
        )
    except Exception as e:
        logger.exception("disable_report 發生錯誤")
        await update.message.reply_text(f"disable_report 發生錯誤：{e}")


async def report_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        logger.info(f"收到 /report_now，chat_id={chat_id}")

        await update.message.reply_text("收到 /report_now，正在產生測試回報，請稍候...")

        report = build_full_report()
        await update.message.reply_text(report)

    except Exception as e:
        logger.exception("report_now 發生錯誤")
        await update.message.reply_text(f"report_now 發生錯誤：{e}")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        logger.info(f"收到 /status，chat_id={chat_id}")

        text = build_status_text(context, chat_id)
        await update.message.reply_text(text)
    except Exception as e:
        logger.exception("status 發生錯誤")
        await update.message.reply_text(f"status 發生錯誤：{e}")


# =========================
# 啟動主程式
# =========================

def main():
    if not BOT_TOKEN:
        raise ValueError("找不到 TELEGRAM_BOT_TOKEN，請先設定環境變數。")

    logger.info("Tony's OpenClaw AI 助理 已啟動...")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("enable_report", enable_report))
    app.add_handler(CommandHandler("disable_report", disable_report))
    app.add_handler(CommandHandler("report_now", report_now))
    app.add_handler(CommandHandler("status", status))

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
