from skills.news_sources_skill import fetch_google_news_rss
from skills.openai_summary_skill import summarize_text
from skills.config import REPORT_MAX_ITEMS


def build_social_keyword_observation(keywords: list, platform_name: str) -> list:
    items = []
    for kw in keywords[:REPORT_MAX_ITEMS]:
        articles = fetch_google_news_rss(kw)
        if articles:
            top = articles[0]
            title = top.get("title", kw)
            desc = top.get("description", "")
            summary = summarize_text(title, desc, topic=f"{platform_name} 關鍵字觀測")
            items.append(f"{kw}：{summary}")
        else:
            items.append(f"{kw}：近期未抓到穩定可用的交叉新聞來源。")
    return items


def get_dcard_heat_report() -> str:
    keywords = [
        "Dcard 補習班",
        "Dcard 課程推薦",
        "Dcard AI 課程",
        "Dcard 英文補習",
    ]
    lines = build_social_keyword_observation(keywords, "Dcard")
    return "Dcard 熱點觀測\n" + "\n".join([f"- {x}" for x in lines])


def get_threads_heat_report() -> str:
    keywords = [
        "Threads AI 課程",
        "Threads 轉職 課程",
        "Threads 補教",
        "Threads 培訓",
    ]
    lines = build_social_keyword_observation(keywords, "Threads")
    return "Threads 熱點觀測\n" + "\n".join([f"- {x}" for x in lines])
