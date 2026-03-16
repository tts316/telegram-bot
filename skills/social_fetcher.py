import urllib.parse
import feedparser


def fetch_social_signals(keyword: str, limit: int = 5) -> list[dict]:
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
                "summary": entry.get("summary", ""),
                "keyword": keyword,
            }
        )

    return items


def fetch_social_bundle(keywords: list[str], per_keyword: int = 2) -> list[dict]:
    results = []
    for keyword in keywords:
        items = fetch_social_signals(keyword, limit=per_keyword)
        results.extend(items)
    return results
