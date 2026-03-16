from skills.news_sources_skill import fetch_news_with_fallback
from skills.openai_summary_skill import summarize_text
from skills.config import REPORT_MAX_ITEMS


def format_block(title_prefix: str, articles: list, topic: str) -> str:
    if not articles:
        return f"- {title_prefix}：目前抓不到可用新聞。"

    lines = [f"- {title_prefix}："]
    for idx, a in enumerate(articles[:REPORT_MAX_ITEMS], start=1):
        title = a.get("title", "無標題")
        desc = a.get("description") or a.get("content") or "無內容"
        summary = summarize_text(title, desc, topic=topic)
        lines.append(f"  {idx}. {summary}")
    return "\n".join(lines)


def get_ai_news_report() -> str:
    ai_articles = fetch_news_with_fallback("OpenAI OR ChatGPT OR AI", language_primary="en")
    tech_articles = fetch_news_with_fallback("technology OR Apple OR Microsoft OR Nvidia", language_primary="en")
    stock_articles = fetch_news_with_fallback("stock market OR Nasdaq OR semiconductor", language_primary="en")

    return (
        "2. AI新聞、科技新聞、股市新聞重點\n"
        f"{format_block('AI新聞', ai_articles, 'AI新聞')}\n"
        f"{format_block('科技新聞', tech_articles, '科技新聞')}\n"
        f"{format_block('股市新聞', stock_articles, '股市新聞')}"
    )
