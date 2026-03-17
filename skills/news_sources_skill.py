import requests
import os

NEWS_API_KEY = os.getenv("NEWS_API_KEY")

def get_ai_news():

    url = "https://newsapi.org/v2/top-headlines"

    params = {
        "country": "us",
        "category": "technology",
        "apiKey": NEWS_API_KEY
    }

    try:

        r = requests.get(url, params=params, timeout=10, verify=False)

        data = r.json()

        articles = data.get("articles", [])[:3]

        news = []

        for a in articles:
            news.append(a["title"])

        if not news:
            return "目前抓不到AI / 科技新聞"

        text = "\n".join([f"- {n}" for n in news])

        return f"""
2. AI / 科技新聞
{text}
"""

    except Exception as e:
        return f"新聞取得失敗：{e}"
