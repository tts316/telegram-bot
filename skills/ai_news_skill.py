from skills.news_fetcher import fetch_news_bundle
from skills.openai_summarizer import summarize_ai_news


def get_ai_news_report() -> str:
    keywords = [
        "OpenAI AI 新聞",
        "生成式 AI 科技新聞",
        "台積電 產業新聞",
        "美股 科技股 新聞",
    ]
    news_items = fetch_news_bundle(keywords, per_keyword=3)
    return summarize_ai_news(news_items)
