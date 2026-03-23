import os
import logging
import feedparser
import urllib.parse
import pytz
import datetime
import requests
import uuid

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

# ===== 使用者設定 =====
user_keywords = {}
user_sources = {}
user_topics = {}

# ===== 成效追蹤 =====
campaign_logs = []
campaign_performance = {}

# ===== Prompt =====
MARKETING_PROMPT = """
你是台灣AI培訓產業行銷專家

目標族群：
上班族轉職 / 技能提升

請產出：
1. Facebook廣告
2. 招生文案
3. LINE短文
4. 標題
5. CTA
6. 影音腳本

語氣要有「轉職焦慮 + 機會感」
"""

# ===== Notebook =====
def save_to_notebook(chat_id, content):
    topic = user_topics.get(chat_id, "AI行銷")
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    filename = f"notebook_{topic}_{today}.txt"

    with open(filename, "a", encoding="utf-8") as f:
        f.write("\n\n====\n")
        f.write(content)

# ===== 市場資料 =====
def fetch_market_intel(chat_id):
    results = []
    links = []

    try:
        keyword = user_keywords.get(chat_id, "台灣 AI 培訓")
        source = user_sources.get(chat_id, ""

)
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
            print("news error:", e)

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
            print("ptt error:", e)

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
            print("dcard error:", e)

        if not results:
            results.append(f"{keyword} 市場趨勢")
            links.append(f"https://www.google.com/search?q={encoded}")

    except Exception as e:
        print("fetch error:", e)
        results = ["市場資料錯誤"]
        links = []

    return results, links

# ===== 文案生成 =====
def generate_marketing(chat_id):
    try:
        market_data, links = fetch_market_intel(chat_id)
        market_text = "\n".join(market_data)[:500]

        campaign_id = str(uuid.uuid4())[:8]
        topic = user_topics.get(chat_id, "AI行銷")
        keyword = user_keywords.get(chat_id, "AI課程")

        tracking_link = f"https://yourdomain.com/?cid={campaign_id}&kw={keyword}"

        prompt = f"""
{MARKETING_PROMPT}

市場資訊：
{market_text}

請產出高轉換招生文案
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            timeout=45
        )

        result = response.choices[0].message.content

        # ✅ tracking link
        result += f"\n\n👉 立即諮詢：{tracking_link}"

        # ✅ 資料來源
        if links:
            clean_links = [l.split("?")[0] for l in links if isinstance(l, str)]
            result += "\n\n📎 市場資料來源：\n" + "\n".join(clean_links[:3])

        # ✅ 記錄
        campaign_logs.append({
            "campaign_id": campaign_id,
            "chat_id": chat_id,
            "topic": topic,
            "content": result,
            "date": datetime.datetime.now()
        })

        campaign_performance[campaign_id] = {"click": 0, "lead": 0}

        return result

    except Exception as e:
        print("generate error:", e)
        return "⚠️ 系統忙碌"

# ===== 成效更新 =====
def update_campaign_performance(campaign_id, click=0, lead=0):
    if campaign_id in campaign_performance:
        campaign_performance[campaign_id]["click"] += click
        campaign_performance[campaign_id]["lead"] += lead

# ===== 優化 =====
def optimize_marketing(chat_id):
    recent = [c for c in campaign_logs if c["chat_id"] == chat_id][-2:]
    if len(recent) < 2:
        return "⚠️ 至少需要2筆文案"

    c1, c2 = recent

    p1 = campaign_performance.get(c1["campaign_id"], {})
    p2 = campaign_performance.get(c2["campaign_id"], {})

    prompt = f"""
文案A：
{c1['content']}
成效：點擊 {p1.get('click',0)} 留單 {p1.get('lead',0)}

文案B：
{c2['content']}
成效：點擊 {p2.get('click',0)} 留單 {p2.get('lead',0)}

請分析並產出更強版本
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        timeout=45
    )

    return response.choices[0].message.content

# ===== 報表 =====
def generate_report(chat_id):
    user_campaigns = [c for c in campaign_logs if c["chat_id"] == chat_id]
    if not user_campaigns:
        return "⚠️ 無資料"

    total_click = 0
    total_lead = 0

    for c in user_campaigns:
        perf = campaign_performance.get(c["campaign_id"], {})
        total_click += perf.get("click", 0)
        total_lead += perf.get("lead", 0)

    return f"""
📊 成效報表

總文案數：{len(user_campaigns)}
總點擊：{total_click}
總留單：{total_lead}
轉換率：{(total_lead / total_click * 100) if total_click else 0:.1f}%
"""

# ===== Telegram 指令 =====
async def marketing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    msg = generate_marketing(chat_id)
    save_to_notebook(chat_id, msg)
    await update.message.reply_text(msg)

async def optimize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(optimize_marketing(chat_id))

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(generate_report(chat_id))

async def simulate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if campaign_logs:
        cid = campaign_logs[-1]["campaign_id"]
        update_campaign_performance(cid, click=20, lead=5)
        await update.message.reply_text(f"✅ 模擬成效已更新 {cid}")

async def setkeyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_keywords[update.effective_chat.id] = " ".join(context.args)
    await update.message.reply_text("✅ keyword 設定完成")

async def setsource(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_sources[update.effective_chat.id] = " ".join(context.args)
    await update.message.reply_text("✅ source 設定完成")

async def settopic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_topics[update.effective_chat.id] = " ".join(context.args)
    await update.message.reply_text("✅ topic 設定完成")

async def settime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    hour, minute = map(int, context.args[0].split(":"))

    context.job_queue.run_daily(
        daily_push,
        time=time(hour=hour, minute=minute, tzinfo=tz),
        chat_id=chat_id,
        name=str(chat_id)
    )

    await update.message.reply_text("✅ 推播設定完成")

# ===== 每日推播 =====
async def daily_push(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    msg = generate_marketing(chat_id)
    save_to_notebook(chat_id, msg)

    await context.bot.send_message(
        chat_id=chat_id,
        text="📢 每日AI文案\n\n" + msg
    )

# ===== 主程式 =====
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("marketing", marketing))
    app.add_handler(CommandHandler("optimize", optimize))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("simulate", simulate))
    app.add_handler(CommandHandler("setkeyword", setkeyword))
    app.add_handler(CommandHandler("setsource", setsource))
    app.add_handler(CommandHandler("settopic", settopic))
    app.add_handler(CommandHandler("settime", settime))

    if TARGET_CHAT_ID:
        app.job_queue.run_daily(
            daily_push,
            time=time(hour=9, minute=0, tzinfo=tz),
            chat_id=int(TARGET_CHAT_ID),
        )

    app.run_polling()

if __name__ == "__main__":
    main()