from skills.news_sources_skill import fetch_news_with_fallback
from skills.openai_summary_skill import summarize_text
from skills.social_heat_skill import get_dcard_heat_report, get_threads_heat_report
from skills.config import REPORT_MAX_ITEMS


def get_training_market_report() -> str:
    articles = fetch_news_with_fallback("台灣 補教 OR 培訓 OR 教育科技 OR 課程", language_primary="zh")

    news_lines = []
    if articles:
        for i, a in enumerate(articles[:REPORT_MAX_ITEMS], start=1):
            title = a.get("title", "無標題")
            desc = a.get("description") or a.get("content") or "無內容"
            summary = summarize_text(title, desc, topic="台灣補教與培訓市場新聞")
            news_lines.append(f"{i}. {summary}")
    else:
        news_lines.append("1. 目前未抓到台灣補教 / 培訓市場的可用新聞。")

    return (
        "5. 台灣補教 / 培訓市場情報\n"
        "【新聞重點】\n"
        + "\n".join(news_lines)
        + "\n\n【社群觀測】\n"
        + get_dcard_heat_report()
        + "\n\n"
        + get_threads_heat_report()
    )
