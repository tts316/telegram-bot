import urllib.parse
import feedparser


def fetch_google_news(keyword: str, limit: int = 5) -> list[dict]:
    query = urllib.parse.quote(keyword)
    url = f"https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"

    feed = feedparser.parse(url)
    items = []

    for entry in feed.entries[:limit]:
        items.append(
            {
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
                "source": getattr(entry, "source", {}).get("title", "") if hasattr(entry, "source") else "",
                "summary": entry.get("summary", ""),
            }
        )

    return items


def fetch_news_bundle(keywords: list[str], per_keyword: int = 3) -> list[dict]:
    results = []
    for keyword in keywords:
        news = fetch_google_news(keyword, limit=per_keyword)
        for item in news:
            item["keyword"] = keyword
            results.append(item)
    return results
