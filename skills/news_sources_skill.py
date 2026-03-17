import requests
import os

NEWS_API_KEY = os.getenv("NEWS_API_KEY")


def fetch_news_with_fallback():

    news_list = []

    # === 1. NewsAPI ===
    try:
        url = "https://newsapi.org/v2/top-headlines"
        params = {
            "country": "us",
            "category": "technology",
            "apiKey": NEWS_API_KEY
        }

        r = requests.get(url, params=params, timeout=10, verify=False)
        data = r.json()

        articles = data.get("articles", [])[:3]

        for a in articles:
            news_list.append(a["title"])

    except:
        pass

    # === 2. RSS 備援（Google News RSS）===
    if not news_list:
        try:
            rss_url = "https://news.google.com/rss/search?q=AI+technology&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"

            r = requests.get(rss_url, timeout=10, verify=False)

            import xml.etree.ElementTree as ET
            root = ET.fromstring(r.content)

            items = root.findall(".//item")[:3]

            for item in items:
                title = item.find("title").text
                news_list.append(title)

        except:
            pass

    # === fallback still empty ===
    if not news_list:
        return ["目前抓不到新聞"]

    return news_list
