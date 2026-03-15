import os
import logging
from datetime import time
from zoneinfo import ZoneInfo

from openai import OpenAI
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# 基本設定
# =========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("請先設定 TELEGRAM_BOT_TOKEN")
if not OPENAI_API_KEY:
    raise ValueError("請先設定 OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)
TAIWAN_TZ = ZoneInfo("Asia/Taipei")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# =========================
# AI 回答函式
# =========================
def ask_openai(user_message: str) -> str:
    try:
        logger.info(f"送出 OpenAI 請求，內容：{user_message}")

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {
                    "role": "system",
                    "content": (
                        "你是 Tony 的 OpenClaw AI 企業助理。"
                        "請使用繁體中文回覆，語氣專業、清楚、簡潔。"
                        "你擅長企業營運、流程改善、AI導入、SaaS、RPA、自動化、管理報表與行政支援。"
                    ),
                },
                {
                    "role": "user",
                    "content": user_message,
                },
            ],
        )

        answer = response.output_text.strip()
        logger.info("OpenAI 回應成功")
        return answer

    except Exception as e:
        logger.exception("ask_openai 發生錯誤")
        return f"發生錯誤，暫時無法取得 AI 回覆：{e}"


# =========================
# 自動回報內容
# =========================
def generate_daily_report_text() -> str:
    prompt = """
請用繁體中文產出「今日企業助理回報」。
格式請清楚分段，內容包含：

1. 天氣回報（若無法取得即寫：尚未獲取天氣資訊）
2. AI新聞、科技新聞、股市新聞重點
3. 伺服器狀況回報（若無法取得即寫：尚未獲取伺服器狀況資訊）
4. 台積電及 TSM ADR 股價（若無法取得即寫：尚未獲取股價資訊）

請整理成簡潔、像主管晨會可直接閱讀的格式。
"""
    return ask_openai(prompt)


async def send_scheduled_report(context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        job = context.job
        chat_id = job.data["chat_id"]
        report_type = job.data.get("report_type", "一般回報")

        logger.info(f"開始執行排程回報：{report_type}，chat_id={chat_id}")

        if report_type == "天氣回報":
            prompt = "請用繁體中文提供今天的天氣回報。若無法取得即寫：尚未獲取天氣資訊。"
        elif report_type == "AI新聞、科技新聞、股市新聞重點":
            prompt = (
                "請用繁體中文整理今天的 AI 新聞、科技新聞、股市新聞重點。"
                "若無法取得特定資料，請明確寫出尚未獲取。"
            )
        elif report_type == "伺服器狀況回報":
            prompt = "請用繁體中文提供伺服器狀況回報。若無法取得即寫：尚未獲取伺服器狀況資訊。"
        elif report_type == "台積電及 TSM ADR 股價":
            prompt = "請用繁體中文提供台積電及 TSM ADR 股價摘要。若無法取得即寫：尚未獲取股價資訊。"
        else:
            prompt = "請用繁體中文提供一份今日企業助理摘要回報。"

        report = ask_openai(prompt)
        message = f"【自動回報】{report_type}\n\n{report}"

        await context.bot.send_message(chat_id=chat_id, text=message)
        logger.info(f"排程回報發送成功：{report_type}")

    except Exception as e:
        logger.exception("send_scheduled_report 發生錯誤")
        try:
            if context.job and context.job.data and "chat_id" in context.job.data:
                await context.bot.send_message(
                    chat_id=context.job.data["chat_id"],
                    text=f"自動回報執行失敗：{e}",
                )
        except Exception:
            logger.exception("回傳排程錯誤訊息失敗")


# =========================
# 指令
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"收到 /start，chat_id={update.effective_chat.id}")
    text = (
        "您好！我是 Tony's OpenClaw AI 助理。\n\n"
        "可用指令：\n"
        "/start - 啟動機器人\n"
        "/help - 查看說明\n"
        "/enable_report - 啟動自動回報\n"
        "/disable_report - 停止自動回報\n"
        "/report_now - 立即測試一次回報\n\n"
        "也可以直接輸入問題與我對話。"
    )
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"收到 /help，chat_id={update.effective_chat.id}")
    text = (
        "指令說明：\n\n"
        "/enable_report - 啟動每日自動回報\n"
        "/disable_report - 停止每日自動回報\n"
        "/report_now - 立即測試一次回報\n\n"
        "目前自動回報時間：\n"
        "1. 天氣回報：每天上午 8:30\n"
        "2. AI新聞、科技新聞、股市新聞重點：每天上午 8:45\n"
        "3. 伺服器狀況回報：每天上午 8:00 與下午 8:00\n"
        "4. 台積電及 TSM ADR 股價：每天中午 12:00\n"
    )
    await update.message.reply_text(text)


async def enable_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        logger.info(f"收到 /enable_report，chat_id={chat_id}")

        await update.message.reply_text("收到 /enable_report，正在設定自動回報...")

        if context.job_queue is None:
            logger.error("job_queue 未啟用")
            await update.message.reply_text("錯誤：job_queue 未啟用，請確認 requirements.txt 已使用 job-queue 版本。")
            return

        # 先移除同 chat_id 舊排程，避免重複
        current_jobs = context.job_queue.jobs()
        removed_count = 0
        for job in current_jobs:
            if job.data and job.data.get("chat_id") == chat_id:
                job.schedule_removal()
                removed_count += 1

        logger.info(f"已移除舊排程數量：{removed_count}")

        # 設定排程
        context.job_queue.run_daily(
            send_scheduled_report,
            time=time(hour=8, minute=30, tzinfo=TAIWAN_TZ),
            data={"chat_id": chat_id, "report_type": "天氣回報"},
            name=f"weather_{chat_id}",
        )

        context.job_queue.run_daily(
            send_scheduled_report,
            time=time(hour=8, minute=45, tzinfo=TAIWAN_TZ),
            data={"chat_id": chat_id, "report_type": "AI新聞、科技新聞、股市新聞重點"},
            name=f"news_{chat_id}",
        )

        context.job_queue.run_daily(
            send_scheduled_report,
            time=time(hour=8, minute=0, tzinfo=TAIWAN_TZ),
            data={"chat_id": chat_id, "report_type": "伺服器狀況回報"},
            name=f"server_am_{chat_id}",
        )

        context.job_queue.run_daily(
            send_scheduled_report,
            time=time(hour=20, minute=0, tzinfo=TAIWAN_TZ),
            data={"chat_id": chat_id, "report_type": "伺服器狀況回報"},
            name=f"server_pm_{chat_id}",
        )

        context.job_queue.run_daily(
            send_scheduled_report,
            time=time(hour=12, minute=0, tzinfo=TAIWAN_TZ),
            data={"chat_id": chat_id, "report_type": "台積電及 TSM ADR 股價"},
            name=f"tsm_{chat_id}",
        )

        await update.message.reply_text(
            "自動回報已啟動。\n\n"
            "回報時間如下：\n"
            "1. 天氣回報：每天上午 8:30\n"
            "2. AI新聞、科技新聞、股市新聞重點：每天上午 8:45\n"
            "3. 伺服器狀況回報：每天上午 8:00 和下午 8:00\n"
            "4. 台積電及 TSM ADR 股價：每天中午 12:00"
        )

        logger.info(f"/enable_report 設定完成，chat_id={chat_id}")

    except Exception as e:
        logger.exception("enable_report 發生錯誤")
        await update.message.reply_text(f"enable_report 發生錯誤：{e}")


async def disable_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        logger.info(f"收到 /disable_report，chat_id={chat_id}")

        if context.job_queue is None:
            await update.message.reply_text("目前 job_queue 未啟用。")
            return

        removed_count = 0
        for job in context.job_queue.jobs():
            if job.data and job.data.get("chat_id") == chat_id:
                job.schedule_removal()
                removed_count += 1

        await update.message.reply_text(f"自動回報已停止，共移除 {removed_count} 個排程。")
        logger.info(f"/disable_report 完成，移除 {removed_count} 個排程，chat_id={chat_id}")

    except Exception as e:
        logger.exception("disable_report 發生錯誤")
        await update.message.reply_text(f"disable_report 發生錯誤：{e}")


async def report_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        logger.info(f"收到 /report_now，chat_id={chat_id}")

        await update.message.reply_text("收到 /report_now，正在產生測試回報，請稍候...")

        report = generate_daily_report_text()
        await update.message.reply_text(report)

        logger.info(f"/report_now 執行成功，chat_id={chat_id}")

    except Exception as e:
        logger.exception("report_now 發生錯誤")
        await update.message.reply_text(f"report_now 發生錯誤：{e}")


# =========================
# 一般聊天
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_text = update.message.text
        chat_id = update.effective_chat.id

        logger.info(f"收到一般訊息，chat_id={chat_id}，內容={user_text}")

        await update.message.reply_text("收到，正在整理回覆...")

        answer = ask_openai(user_text)
        await update.message.reply_text(answer)

        logger.info(f"一般訊息回覆成功，chat_id={chat_id}")

    except Exception as e:
        logger.exception("handle_message 發生錯誤")
        await update.message.reply_text(f"處理訊息時發生錯誤：{e}")


# =========================
# 錯誤處理
# =========================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("全域錯誤處理器捕捉到例外", exc_info=context.error)

    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(f"系統發生錯誤：{context.error}")
    except Exception:
        logger.exception("error_handler 回傳錯誤訊息失敗")


# =========================
# 主程式
# =========================
def main():
    logger.info("Tony's OpenClaw AI 助理 已啟動...")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("enable_report", enable_report))
    app.add_handler(CommandHandler("disable_report", disable_report))
    app.add_handler(CommandHandler("report_now", report_now))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.add_error_handler(error_handler)

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()