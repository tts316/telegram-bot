import os
import logging
import feedparser
import urllib.parse
import pytz
import datetime
import requests

from bs4 import BeautifulSoup
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

# ===== 動態策略 =====
user_keywords = {}
user_sources = {}
user_topics = {}

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
"""

# ===== 市場情報抓取 =====
def fetch_market_intel(chat_id):
    results = []
    links = []

    try:
        keyword = user_keywords.get(chat_id, "台灣 AI 培訓")
        source = user_sources.get(chat_id, "")

        query = f"{keyword} {source}"
        encoded = urllib.parse.quote(query)

        headers = {"User-Agent": "Mozilla/5.0"}

        # Google News
        try:
            news_url = f"https://news.google.com/rss/search?q={encoded}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
            feed = feedparser.parse(news_url)

            for entry in feed.entries[:2]:
                results.append(f"📰 {entry.title}")
                links.append(entry.link)
        except Exception as e:
            print("Google News error:", e)

        # PTT
        try:
            res = requests.get(
                f"https://www.ptt.cc/bbs/Soft_Job/search?q={encoded}",
                headers=headers,
                timeout=5
            )
            soup = BeautifulSoup(res.text, "html.parser")

            for t in soup.select(".title a")[:2]:
                results.append(f"💬 PTT: {t.text.strip()}")
                links.append("https://www.ptt.cc" + t.get("href"))
        except Exception as e:
            print("PTT error:", e)

        # Dcard
        try:
            res = requests.get(
                f"https://www.dcard.tw/search?query={encoded}",
                headers=headers,
                timeout=5
            )
            soup = BeautifulSoup(res.text, "html.parser")

            for p in soup.select("h2")[:2]:
                results.append(f"📱 Dcard: {p.text.strip()}")
                links.append("https://www.dcard.tw")
        except Exception as e:
            print("Dcard error:", e)

        # fallback
        if not results:
            results.append(f"{keyword} 市場趨勢")
            links.append(f"https://www.google.com/search?q={encoded}")

    except Exception as e:
        print("fetch error:", e)
        results = ["市場資料錯誤"]
        links = []

    # 👇 關鍵：永遠回傳兩個
    return results, links

# ===== Notebook儲存 =====
def save_to_notebook(chat_id, content):
    try:
        topic = user_topics.get(chat_id, "AI行銷")
        today = datetime.datetime.now().strftime("%Y-%m-%d")

        filename = f"notebook_{topic}_{today}.txt"

        with open(filename, "a", encoding="utf-8") as f:
            f.write("\n\n====================\n")
            f.write(content)

        logger.info(f"Saved to {filename}")

    except Exception as e:
        logger.error(f"Notebook error: {e}")

# ===== AI文案生成 =====
def generate_marketing(chat_id):
    try:
        # ===== 1. 安全取得市場資料 =====
        try:
            market_data, links = fetch_market_intel(chat_id)
        except Exception as e:
            print("🔥 fetch_market_intel error:", e)
            market_data = ["AI轉職需求持續成長", "企業導入AI人才需求增加"]
            links = []

        # ===== 2. 防呆（避免 unpack / 型別錯誤）=====
        if not isinstance(market_data, list):
            market_data = ["市場資料異常"]

        if not isinstance(links, list):
            links = []

        # ===== 3. 降載（避免 token 過多 / timeout）=====
        market_text = "\n".join(market_data)[:500]

        # ===== 4. Prompt =====
        prompt = f"""
{MARKETING_PROMPT}

以下為最新市場資訊：
{market_text}

請產出更貼近台灣市場、具轉換力的內容。
"""

        # ===== 5. 呼叫 OpenAI（加強穩定性）=====
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                timeout=45  # ⬅️ 比原本更保守
            )

            result = response.choices[0].message.content

        except Exception as e:
            print("🔥 OpenAI error:", e)

            # fallback：避免整個壞掉
            result = f"""
【AI文案（備援模式）】

🔥 AI轉職正夯！
現在不學AI，你將被市場淘汰！

📌 熱門技能：
✔ ChatGPT應用
✔ 自動化工具
✔ AI行銷

👉 立即卡位未來職場
👉 免費諮詢名額開放中

⚠️（系統暫時使用備援文案）
"""

        # ===== 6. 加上來源（安全處理）=====
        if links:
            try:
                clean_links = []
                for l in links:
                    if isinstance(l, str):
                        clean_links.append(l.split("?")[0])

                if clean_links:
                    result += "\n\n📎 市場資料來源：\n" + "\n".join(clean_links[:3])

            except Exception as e:
                print("link format error:", e)

        return result

    except Exception as e:
        print("🔥 generate_marketing fatal error:", e)

        return """
⚠️ 系統暫時忙碌

請稍後再試 /marketing
（系統已進入保護模式）
"""

# ===== 指令 =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    await update.message.reply_text(
        f"✅ OpenClaw v2.6 啟動\n\n"
        f"Chat ID：{chat_id}\n\n"
        "指令：\n"
        "/marketing\n"
        "/settime 09:00\n"
        "/setkeyword AI 課程 轉職\n"
        "/setsource 巨匠 Tibame\n"
        "/settopic AI市場"
    )

async def marketing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    await update.message.reply_text("📊 分析市場 + 產生文案中...")

    result = generate_marketing(chat_id)

    save_to_notebook(chat_id, result)

    await update.message.reply_text(result)

async def setkeyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = " ".join(context.args)

    user_keywords[chat_id] = text
    await update.message.reply_text(f"✅ 關鍵字：{text}")

async def setsource(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = " ".join(context.args)

    user_sources[chat_id] = text
    await update.message.reply_text(f"✅ 來源：{text}")

async def settopic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = " ".join(context.args)

    user_topics[chat_id] = text
    await update.message.reply_text(f"✅ Notebook主題：{text}")

async def settime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        text = context.args[0]

        hour, minute = map(int, text.split(":"))

        # 移除舊 job
        jobs = context.job_queue.get_jobs_by_name(str(chat_id))
        for job in jobs:
            job.schedule_removal()

        context.job_queue.run_daily(
            daily_push,
            time=time(hour=hour, minute=minute, tzinfo=tz),
            chat_id=chat_id,
            name=str(chat_id)
        )

        await update.message.reply_text(f"✅ 推播時間：{text}")

    except:
        await update.message.reply_text("❌ 格式錯誤 /settime 09:00")

# ===== 自動推播 =====
async def daily_push(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id

    result = generate_marketing(chat_id)

    save_to_notebook(chat_id, result)

    await context.bot.send_message(
        chat_id=chat_id,
        text="📢 每日市場文案\n\n" + result
    )

# ===== 主程式 =====
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("marketing", marketing))
    app.add_handler(CommandHandler("setkeyword", setkeyword))
    app.add_handler(CommandHandler("setsource", setsource))
    app.add_handler(CommandHandler("settopic", settopic))
    app.add_handler(CommandHandler("settime", settime))

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
