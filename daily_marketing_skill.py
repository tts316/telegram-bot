import requests
import feedparser
from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ===== 抓新聞 =====
def fetch_news(keyword="台灣 補教 培訓 AI 教育", limit=5):
    url = f"https://news.google.com/rss/search?q={keyword}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    
    feed = feedparser.parse(url)
    news_list = []

    for entry in feed.entries[:limit]:
        news_list.append(entry.title)

    return news_list


# ===== 產生廣告文案 =====
def generate_ad_copy():
    news = fetch_news()
    
    news_text = "\n".join(news)

    prompt = f"""
你是一位頂級行銷顧問。

請根據以下台灣教育/補教市場最新資訊：

{news_text}

產出：

1️⃣ 1則高轉換Facebook廣告文案  
2️⃣ 1則招生文案（補習班/培訓課）  
3️⃣ 3個吸引點標題  
4️⃣ CTA（行動呼籲）

要求：
- 繁體中文
- 符合台灣市場
- 有銷售力（不是報告）
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )

    return response.choices[0].message.content
