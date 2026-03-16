import requests
import feedparser
from skills.config import NEWS_API_KEY, GNEWS_API_KEY


def fetch_newsapi(query: str, language: str = "en", page_size: int = 3) -> list:
    if not NEWS_API_KEY:
        return []

    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": query,
            "language": language,
            "sortBy": "publishedAt",
            "pageSize": page_size,
            "apiKey": NEWS_API_KEY,
        }
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        return r.json().get("articles", [])
    except Exception:
        return []


def fetch_gnews(query: str, lang: str = "en", max_results: int = 3) -> list:
    if not GNEWS_API_KEY:
        return []

    try:
        url = "https://gnews.io/api/v4/search"
        params = {
            "q": query,
            "lang": lang,
            "max": max_results,
            "token": GNEWS_API_KEY,
        }
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        return r.json().get("articles", [])
    except Exception:
        return []


def fetch_google_news_rss(query: str, hl: str = "zh-TW", gl: str = "TW", ceid: str = "TW:zh-Hant") -> list:
    try:
        rss_url = (
            f"https://news.google.com/rss/search?q={query}"
            f"&hl={hl}&gl={gl}&ceid={ceid}"
        )
        feed = feedparser.parse(rss_url)
        results = []
        for entry in feed.entries[:3]:
            results.append({
                "title": entry.get("title", ""),
                "description": entry.get("summary", ""),
                "url": entry.get("link", ""),
                "source": {"name": "Google News RSS"},
            })
        return results
    except Exception:
        return []


def fetch_news_with_fallback(query: str, language_primary: str = "en") -> list:
    articles = fetch_newsapi(query, language=language_primary, page_size=3)
    if articles:
        return articles

    articles = fetch_gnews(query, lang=language_primary, max_results=3)
    if articles:
        return articles

    return fetch_google_news_rss(query)
