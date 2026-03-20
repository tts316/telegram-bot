import os
import logging
import feedparser
import urllib.parse
import pytz
from datetime import time

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

from openai import OpenAI

# ===== 環境變數 =====
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")

if not TOKEN or not OPENAI_API_KEY:
    raise ValueError("❌ 缺少必要環境變數")

# ===== 基本設定 =====
tz = pytz.timezone("Asia/Taipei")
client = OpenAI(api_key=OPENAI_API_KEY)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== 動態策略（核心）=====
user_keywords = {}
user_sources = {}

# ===== Prompt =====
MARKETING_PROMPT = """
你是台灣「AI / 數位技能培訓」行銷專家（非升學補習班）。

目標族群：
- 上班族轉職
- AI技能學習者
- 想提升職場競爭力的人

產出內容要「可轉換」、「商業導向」、「實戰感」

禁止：
- 升學補習
- 考試導向

請輸出：

1️⃣ Facebook廣告文案（高轉換）
2️⃣ 招生文案
3️⃣ LINE短文案
4️⃣ 三個吸引標題
5️⃣ CTA（行動呼籲）

語氣：
專業 + 行銷 + 有成交力
"""

# ===== 抓新聞 =====
def fetch_news(chat_id):
    try:
        keyword = user_keywords.get(
            chat_id,
            "台灣 AI 培訓 數位轉型 職能教育"
        )

        encoded = urllib.parse.quote(keyword)

        url = f"https://news.google.com/rss/search?q={encoded}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"

        feed = feedparser.parse(url)

        news_list = []
        for entry in feed.entries[:5]:
            news_list.append({
                "title": entry.title,
                "link": entry.link
            })

        return news_list

    except Exception as e:
        logger.error(f"RSS error: {e}")
        return []

# ===== 產生文案 =====
def generate_marketing(chat_id):
    try:
        news_data = fetch_news(chat_id)

        keyword = user_keywords.get(chat_id, "AI培訓")
        source = user_sources.get(chat_id, "Google News / 台灣市場")

        news_text = "\n".join([n["title"] for n in news_data])
        links_text = "\n".join([n["link"] for n in news_data])

        prompt = f"""
{MARKETING_PROMPT}

市場關鍵字：
{keyword}

市場來源策略：
{source}

市場資訊：
{news_text}

另外請產出：

🎬 AI影音生成提示詞（30秒短影片）：
- 分鏡
- 字幕
- 配音語氣
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            timeout=25
        )

        result = response.choices[0].message.content

        if links_text:
            result += "\n\n📎 市場資料來源：\n" + links_text

        return result

    except Exception as e:
        logger.error(f"Marketing error: {e}")
        return f"❌ 文案產生失敗：{str(e)}"

# ===== 指令 =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    await update.message.reply_text(
        f"✅ OpenClaw 啟動\n\n"
        f"你的 Chat ID：{chat_id}\n\n"
        "指令：\n"
        "/marketing\n"
        "/settime 09:00\n"
        "/setkeyword AI 課程 轉職\n"
        "/setsource 資策會 MIC AI 市場"
    )

# ===== 手動產文案 =====
async def marketing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    await update.message.reply_text("📊 產生中...")

    result = generate_marketing(chat_id)

    await update.message.reply_text(result)

# ===== 設定關鍵字 =====
async def setkeyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    text = " ".join(context.args)

    if not text:
        await update.message.reply_text("❌ 用法：/setkeyword AI 課程 轉職")
        return

    user_keywords[chat_id] = text

    await update.message.reply_text(f"✅ 關鍵字設定完成：\n{text}")

# ===== 設定來源 =====
async def setsource(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    text = " ".join(context.args)

    if not text:
        await update.message.reply_text("❌ 用法：/setsource 資策會 MIC AI")
        return

    user_sources[chat_id] = text

    await update.message.reply_text(f"✅ 市場來源設定：\n{text}")

# ===== 設定推播時間 =====
async def settime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        text = context.args[0]

        hour, minute = map(int, text.split(":"))

        # 移除舊 job
        jobs = context.job_queue.get_jobs_by_name(str(chat_id))
        for job in jobs:
            job.schedule_removal()

        # 新增 job
        context.job_queue.run_daily(
            daily_push,
            time=time(hour=hour, minute=minute, tzinfo=tz),
            chat_id=chat_id,
            name=str(chat_id)
        )

        await update.message.reply_text(f"✅ 推播時間設定為 {text}")

    except:
        await update.message.reply_text("❌ 格式錯誤：/settime 09:30")

# ===== 自動推播 =====
async def daily_push(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id

    result = generate_marketing(chat_id)

    await context.bot.send_message(
        chat_id=chat_id,
        text="📢 每日行銷文案\n\n" + result
    )

# ===== 主程式 =====
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("marketing", marketing))
    app.add_handler(CommandHandler("setkeyword", setkeyword))
    app.add_handler(CommandHandler("setsource", setsource))
    app.add_handler(CommandHandler("settime", settime))

    # 預設推播（防呆）
    if TARGET_CHAT_ID:
        app.job_queue.run_daily(
            daily_push,
            time=time(hour=9, minute=0, tzinfo=tz),
            chat_id=int(TARGET_CHAT_ID),
            name="default"
        )

    app.run_polling()

if __name__ == "__main__":
    main()